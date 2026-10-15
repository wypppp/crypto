"""固定执行的 CSV 下载；保留响应编码、逐页原子保存，不重跑 SQL。

断线后须另有批准，才读取缺页。HTTP 响应体字节不含 TLS/请求头。
分页严格连续，整数作为文本写回，非执行费增量立即封住后续付费。
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path

import paid_guard as PG
from dune_get import get, norm
from run_dune import budget_gate, usage

H = PG.H
PAGE = 50000


def write_json(path, value):
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    part.replace(path)


def decode(body, headers, cols, types=None):
    encoding = headers.get("content-encoding", "identity").lower()
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding != "identity":
        raise ValueError("未知响应编码")
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    if next(reader, None) != cols:
        raise ValueError("CSV 列名或列次序与执行元数据不同")
    rows = list(reader)
    if any(len(r) != len(cols) for r in rows):
        raise ValueError("CSV 字段数不符")
    for row in rows:
        for i, value in enumerate(row):
            # 本实验只有身份、整数与质量标志；<nil>不可能是合法原值。
            if value == "<nil>":
                row[i] = ""
            elif (
                types
                and types[i] in ("bigint", "integer", "smallint", "tinyint")
                and value
            ):
                n = Decimal(value)
                if not n.is_finite() or n != n.to_integral_value() or abs(n) >= 2**53:
                    raise ValueError("CSV整数无法无损核对；须改文本列或另批JSON下载")
                row[i] = str(int(n))
    return rows


def validate(rows, offset, n, headers):
    end = offset + len(rows)
    cursor = headers.get("x-dune-next-offset")
    next_offset = None if cursor in (None, "", "null") else int(cursor)
    if not rows or end > n:
        raise ValueError("页面为空或行数越界")
    if (end < n and next_offset != end) or (end == n and next_offset is not None):
        raise ValueError("分页不连续或结果截断")
    return end


def fetch(qid, label, sql_file, ticket, execution_id, encoding="gzip"):
    if Path(label).name != label or encoding not in ("gzip", "identity"):
        raise ValueError("标签或编码无效")
    q = get(f"/query/{qid}")
    if norm(q.get("query_sql", "")) != norm((H / sql_file).read_text()):
        raise ValueError("查询 SQL 与批准不同")
    st = get(f"/execution/{execution_id}/status")
    meta = st.get("result_metadata") or {}
    n, cols = meta.get("total_row_count"), meta.get("column_names")
    size = meta.get("total_result_set_bytes", meta.get("result_set_bytes"))
    if st["state"] != "QUERY_STATE_COMPLETED" or str(st.get("query_id")) != str(qid):
        raise ValueError("执行未完成或属于其他查询")
    if n is None or not cols or size is None or float(size) > ticket["max_mb"] * 1e6:
        raise ValueError("元数据缺失或结果超过下载上限")
    identity = {
        "execution_id": execution_id,
        "query_id": str(qid),
        "sql_sha256": PG.sha(H / sql_file),
        "rows": n,
        "cols": cols,
        "types": meta.get("column_types"),
        "bytes": size,
        "encoding": encoding,
    }
    root = H / "raw/dune" / (label + ".csv-pages")
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "identity.json"
    if manifest.exists():
        if json.loads(manifest.read_text()) != identity:
            raise ValueError("恢复身份或列定义改变")
    else:
        write_json(manifest, identity)
    pages, offset, wire = [], 0, 0
    while offset < n:
        path = root / f"{offset:012d}.body"
        mark = path.with_suffix(".json")
        if mark.exists():
            saved = json.loads(mark.read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest() != saved["sha256"]:
                raise ValueError("已保存页面哈希不同")
        else:
            before = usage()
            if before is None:
                raise PG.Refused("读不到下载前用量")
            try:
                headers = PG.request_bytes(
                    f"/execution/{execution_id}/results/csv?limit={PAGE}&offset={offset}",
                    ticket,
                    path,
                    encoding=encoding,
                )
            finally:
                after = usage()
                PG.check_download_usage(before, after, label)
            # 保存费用读数后再做格式验证；失败也不能隐去已发生下载。
            saved = {
                "headers": headers,
                "before": before,
                "after": after,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            write_json(path.with_suffix(".attempt.json"), saved)
            rows = decode(path.read_bytes(), headers, cols, identity["types"])
            validate(rows, offset, n, headers)
            write_json(mark, saved)
            wire += headers["wire_bytes"]
            print(
                "CSV 页",
                offset,
                "行",
                len(rows),
                "响应体字节",
                headers["wire_bytes"],
                "编码",
                headers.get("content-encoding", "identity"),
                flush=True,
            )
        rows = decode(path.read_bytes(), saved["headers"], cols, identity["types"])
        offset = validate(rows, offset, n, saved["headers"])
        pages.append((path, saved))
    out = H / "raw/dune" / (label + ".csv.gz")
    part = out.with_suffix(".gz.part")
    with gzip.open(part, "wt", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for path, saved in pages:
            writer.writerows(
                decode(path.read_bytes(), saved["headers"], cols, identity["types"])
            )
    part.replace(out)
    measurement = dict(
        identity,
        downloaded_wire_bytes=wire,
        all_pages_wire_bytes=sum(s["headers"]["wire_bytes"] for _, s in pages),
        page_encodings=[
            s["headers"].get("content-encoding", "identity") for _, s in pages
        ],
        page_count=len(pages),
        local_gzip_bytes=out.stat().st_size,
    )
    write_json(H / "runs" / (label + "_transport.json"), measurement)
    return measurement


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query_id")
    p.add_argument("label")
    p.add_argument("sql_file")
    p.add_argument("--execution", required=True)
    p.add_argument("--approve", required=True)
    p.add_argument("--encoding", choices=("gzip", "identity"), required=True)
    a = p.parse_args()
    ticket = PG.check(a.approve, a.sql_file)
    with PG.one_at_a_time(ticket):
        u0 = usage()
        why = (
            PG.halt_gate()
            or budget_gate(u0, ticket.download_cap)
            or PG.round_gate(a.approve)
        )
        if why:
            raise PG.Refused(why)
        PG.idle_usage_gate(u0)
        PG.mark_used(a.approve, a.execution, "CSV 传输测量；不执行 SQL")
        try:
            fetch(a.query_id, a.label, a.sql_file, ticket, a.execution, a.encoding)
        finally:
            u1 = usage()
            PG.record_actual(
                a.approve, a.execution, u0[0], None if u1 is None else u1[0], 0
            )
        PG.check_download_usage(u0, u1, a.label)


if __name__ == "__main__":
    main()

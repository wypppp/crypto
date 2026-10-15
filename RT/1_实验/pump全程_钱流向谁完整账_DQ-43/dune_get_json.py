"""第十轮：固定执行JSON、gzip实测、20MB以内分段等到账、原子续页。

不执行SQL，不重试；原始响应体只存raw。整数不经float。
计费等待持付费锁，单调时钟计时；出现增量立即重新封锁。
"""

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import time
from decimal import Decimal
from pathlib import Path

import paid_guard as PG
from dune_get import get
from run_dune import budget_gate, usage

H = PG.H
PAGE = 5000
PAGE_WIRE_CAP = 5_000_000
SEGMENT_CAP = 20_000_000


def atomic(path, value):
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    part.replace(path)


def wait_seconds():
    return (
        json.loads(PG.S3_POLICY.read_text())["settlement_wait_seconds"]
        if PG.S3_POLICY.exists()
        else 120
    )


def observe(
    before, label, save, wait_sec=None, execution_cost=None, expected_download=0
):
    seconds = wait_seconds() if wait_sec is None else wait_sec
    start = time.monotonic()
    samples = []
    while True:
        current = usage()
        elapsed = time.monotonic() - start
        samples.append(
            {
                "at_utc": dt.datetime.now(dt.UTC).isoformat(),
                "elapsed_seconds": elapsed,
                "used": None if current is None else current[0],
            }
        )
        out = {
            "label": label,
            "before": before,
            "wait_seconds": seconds,
            "observations": samples,
            "expected_download_credits": str(expected_download),
        }
        atomic(save, out)
        if execution_cost is None:
            PG.check_download_usage(before, current, label, expected=expected_download)
        else:
            if before is None or current is None:
                raise PG.Refused("执行结算用量缺失，停止")
            expected = Decimal(str(before[0])) + Decimal(str(execution_cost))
            excess = Decimal(str(current[0])) - expected
            if excess > Decimal("0.001"):
                PG.check_download_usage((float(expected), current[1]), current, label)
            if elapsed >= seconds and abs(excess) > Decimal("0.001"):
                raise PG.Refused("执行费用尚未核到账，停止下载")
        if elapsed >= seconds:
            return current, out
        time.sleep(min(10, seconds - elapsed))


def settle_execution(before, cost, label):
    # 先让已知执行费结算，避免把它的延迟到账误记成下载费。
    return observe(
        before,
        label + ":执行结算",
        H / "runs" / (label + "_execution_settlement.json"),
        execution_cost=cost,
    )[0]


def decode(body, headers):
    encoding = headers.get("content-encoding", "identity").lower()
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as f:
            body = f.read(SEGMENT_CAP + 1)
    elif encoding != "identity":
        raise ValueError("未知JSON响应编码")
    if len(body) > SEGMENT_CAP:
        raise ValueError("单页解码结果超过20MB，停止；不自动拆页")
    return json.loads(body, parse_float=Decimal), len(body)


def normalize(rows, cols, types):
    out = []
    for r in rows:
        if set(r) != set(cols):
            raise ValueError("JSON行字段不符")
        row = []
        for c, typ in zip(cols, types):
            value = r[c]
            if value is None:
                row.append(None)
            elif typ in ("bigint", "integer", "smallint", "tinyint"):
                n = Decimal(str(value))
                if not n.is_finite() or n != n.to_integral_value():
                    raise ValueError("JSON整数非整数或不有限")
                row.append(str(int(n)))
            elif isinstance(value, str):
                row.append(value)
            else:
                raise ValueError("文本列没有保持文本类型")
        out.append(row)
    return out


def validate(page, identity, offset):
    meta = (page.get("result") or {}).get("metadata") or {}
    rows = (page.get("result") or {}).get("rows") or []
    if (
        page.get("execution_id") != identity["execution_id"]
        or (
            page.get("query_id") is not None
            and str(page["query_id"]) != identity["query_id"]
        )
        or page.get("state") != "QUERY_STATE_COMPLETED"
        or meta.get("total_row_count") != identity["rows"]
        or meta.get("column_names") != identity["cols"]
    ):
        raise ValueError("页面执行身份、总行数或列改变")
    end = offset + len(rows)
    if not rows or end > identity["rows"]:
        raise ValueError("页面为空或计数越界")
    if (end < identity["rows"] and page.get("next_offset") != end) or (
        end == identity["rows"] and page.get("next_offset") is not None
    ):
        raise ValueError("分页游标不连续或结果截断")
    return normalize(rows, identity["cols"], identity["types"]), end


def fetch(qid, label, sql_file, ticket, eid, encoding="gzip", wait_sec=None):
    if Path(label).name != label:
        raise ValueError("标签只能是文件名")
    binding = PG.small_download_binding(ticket, eid=eid, qid=qid)
    full = ticket.source.startswith("总控第十四轮")
    page_rows = binding["page_rows"] if binding else PAGE
    expected_total = (
        Decimal(str(binding["expected_credits"])) if binding else Decimal(0)
    )
    q = get(f"/query/{qid}")
    if q.get("query_sql", "") != (H / sql_file).read_text():
        raise ValueError("远端SQL与批准不同")
    st = get(f"/execution/{eid}/status")
    meta = st.get("result_metadata") or {}
    n, cols, types = (
        meta.get("total_row_count"),
        meta.get("column_names"),
        meta.get("column_types"),
    )
    size = meta.get("total_result_set_bytes", meta.get("result_set_bytes"))
    if st.get("state") != "QUERY_STATE_COMPLETED" or str(st.get("query_id")) != str(
        qid
    ):
        raise ValueError("执行未完成或查询不同")
    if (
        n is None
        or not cols
        or not types
        or len(types) != len(cols)
        or size is None
        or Decimal(str(size)) > Decimal(str(ticket["max_mb"])) * 1_000_000
    ):
        raise ValueError("元数据缺失或结果超过批准大小")
    if binding and size != binding["metadata_bytes"]:
        raise ValueError("平台结果字节与下载批准不同")
    if full and n != binding["row_count"]:
        raise ValueError("全量结果行数与下载批准不同")
    identity = {
        "execution_id": eid,
        "query_id": str(qid),
        "sql_sha256": PG.sha(H / sql_file),
        "rows": n,
        "cols": cols,
        "types": types,
        "bytes": size,
        "encoding": encoding,
    }
    if binding:
        identity["page_rows"] = page_rows
    root = H / "raw/dune" / (label + ".json-pages")
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "identity.json"
    if manifest.exists():
        if json.loads(manifest.read_text()) != identity:
            raise ValueError("续页身份或编码不同")
    else:
        atomic(manifest, identity)
    before = usage()
    PG.idle_usage_gate(before)
    original_before = before
    offset, segment_bytes, wire, unpacked = 0, 0, 0, 0
    pages, segments = [], []
    started = time.monotonic()
    segment_expected = Decimal(0)
    last_page_usage = before

    def checkpoint():
        nonlocal segment_bytes, before, segment_expected, last_page_usage
        if not segment_bytes:
            return
        observed_bytes, segment_bytes = segment_bytes, 0
        extra = {"expected_download": segment_expected} if binding else {}
        after, observation = observe(
            before,
            label,
            H / "runs" / (label + f"_segment_{len(segments):03d}.json"),
            wait_sec,
            **extra,
        )
        PG.check_download_usage(original_before, after, label, expected=expected_total)
        segments.append(
            {
                "wire_bytes": observed_bytes,
                "after": after,
                "wait_seconds": observation["wait_seconds"],
            }
        )
        before = after
        last_page_usage = after
        segment_expected = Decimal(0)

    try:
        while offset < n:
            path = root / f"{offset:012d}.body"
            mark = path.with_suffix(".json")
            if mark.exists():
                saved = json.loads(mark.read_text())
                if hashlib.sha256(path.read_bytes()).hexdigest() != saved["sha256"]:
                    raise ValueError("续页哈希不符")
            else:
                if segment_bytes + PAGE_WIRE_CAP > SEGMENT_CAP:
                    checkpoint()
                PG.check_download_usage(
                    original_before,
                    last_page_usage if full else usage(),
                    label,
                    expected=expected_total,
                )
                # 请求失败仍留一页最大传输量，finally隔离核账；成功后换成实收。
                segment_bytes += PAGE_WIRE_CAP
                # 出错的付费请求也要结账；未知页大小时只容许已登记的总预计。
                previous_expected = segment_expected
                if binding:
                    segment_expected = expected_total
                headers = PG.request_bytes(
                    f"/execution/{eid}/results?limit={page_rows}&offset={offset}",
                    ticket,
                    path,
                    encoding=encoding,
                    max_bytes=PAGE_WIRE_CAP,
                )
                wire += headers["wire_bytes"]
                segment_bytes += headers["wire_bytes"] - PAGE_WIRE_CAP
                page, decoded_bytes = decode(path.read_bytes(), headers)
                _, end = validate(page, identity, offset)
                page_metadata_bytes = (
                    (page.get("result") or {})
                    .get("metadata", {})
                    .get("result_set_bytes")
                )
                if binding:
                    if (
                        not isinstance(page_metadata_bytes, int)
                        or isinstance(page_metadata_bytes, bool)
                        or page_metadata_bytes <= 0
                    ):
                        raise ValueError("分页计费字节缺失，停止")
                    if (
                        full
                        and max(decoded_bytes, page_metadata_bytes)
                        > binding["max_page_billed_bytes"]
                    ):
                        raise ValueError("全量单页超预登记250KB，停止核账，不自动缩页")
                    segment_expected = (
                        Decimal(0)
                        if full
                        else previous_expected
                        + Decimal(page_metadata_bytes) * 2 / 1_000_000
                    )
                unpacked += decoded_bytes
                page_usage = usage() if binding else None
                if full:
                    last_page_usage = page_usage
                saved = {
                    "headers": headers,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "rows": end - offset,
                }
                if binding:
                    saved.update(
                        metadata_bytes=page_metadata_bytes,
                        immediate_used=None if page_usage is None else page_usage[0],
                    )
                atomic(mark, saved)
                if binding:
                    PG.check_download_usage(
                        original_before, page_usage, label, expected=expected_total
                    )
                print(
                    "JSON页",
                    offset,
                    "行",
                    end - offset,
                    "响应体字节",
                    headers["wire_bytes"],
                    "编码",
                    headers.get("content-encoding", "identity"),
                    flush=True,
                )
            page, _ = decode(path.read_bytes(), saved["headers"])
            _, offset = validate(page, identity, offset)
            pages.append((path, saved))
        checkpoint()
    finally:
        # 失败也隔离计费，不自动重试；已成功页继续保留。
        checkpoint()
    output = H / "raw/dune" / (label + ".csv.gz")
    part = output.with_suffix(".gz.part")
    with gzip.open(part, "wt", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for path, saved in pages:
            page, _ = decode(path.read_bytes(), saved["headers"])
            writer.writerows(normalize(page["result"]["rows"], cols, types))
    part.replace(output)
    result = dict(
        identity,
        downloaded_wire_bytes=wire,
        decoded_json_bytes=unpacked,
        page_count=len(pages),
        segment_count=len(segments),
        segments=segments,
        page_encodings=[
            s["headers"].get("content-encoding", "identity") for _, s in pages
        ],
        elapsed_seconds=time.monotonic() - started,
        download_did_not_execute_sql=True,
        page_rows=page_rows,
        expected_download_credits=str(expected_total),
    )
    atomic(H / "runs" / (label + "_transport.json"), result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query_id")
    p.add_argument("label")
    p.add_argument("sql_file")
    p.add_argument("--execution", required=True)
    p.add_argument("--approve", required=True)
    a = p.parse_args()
    ticket = PG.check(a.approve, a.sql_file)
    with PG.one_at_a_time(ticket):
        u0 = usage()
        why = (
            PG.halt_gate()
            or budget_gate(u0, ticket.download_cap)
            or PG.round_gate(a.approve)
            or PG.s3_period_gate(u0, ticket.download_cap)
        )
        if why:
            raise PG.Refused(why)
        PG.idle_usage_gate(u0)
        PG.mark_used(
            a.approve, a.execution, "JSON gzip已有结果测量；分段核账；无SQL执行"
        )
        try:
            fetch(a.query_id, a.label, a.sql_file, ticket, a.execution)
        finally:
            u1 = usage()
            PG.record_actual(
                a.approve, a.execution, u0[0], None if u1 is None else u1[0], 0
            )


if __name__ == "__main__":
    main()

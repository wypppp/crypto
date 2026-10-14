"""热点可恢复下载：每页原子落盘，绑定 execution/SQL/列/总行数。

页面失败直接退出，不重试、不执行 SQL。恢复须新的下载批准。
只取缺失页面；最终 gzip CSV 的整数由 csv.writer 原样写出。
本轮只做离线故障测试，未用它追加任何付费下载。
"""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import paid_guard as PG
from dune_get import get, norm
from run_dune import budget_gate, usage

H = Path(__file__).resolve().parent
PAGE = 1000


def atomic_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    tmp.write_bytes(gzip.compress(data, mtime=0))
    tmp.replace(path)


def digest(rows):
    return hashlib.sha256(
        json.dumps(
            rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def fetch(qid, label, sql_file, ticket, execution_id):
    if Path(label).name != label:
        raise SystemExit("标签只能是一个文件名")
    q = get(f"/query/{qid}")
    if norm(q.get("query_sql", "")) != norm((H / sql_file).read_text()):
        raise SystemExit("查询 SQL 与批准文件不一致")
    st = get(f"/execution/{execution_id}/status")
    meta = st.get("result_metadata") or {}
    if st["state"] != "QUERY_STATE_COMPLETED" or str(st.get("query_id")) != str(qid):
        raise SystemExit("执行未完成或属于其他查询")
    n = meta.get("total_row_count")
    cols = meta.get("column_names")
    size = meta.get("total_result_set_bytes", meta.get("result_set_bytes"))
    if n is None or not cols or size is None or float(size) / 1e6 > ticket["max_mb"]:
        raise SystemExit("结果元数据缺失或超过下载上限")
    identity = {
        "execution_id": execution_id,
        "query_id": str(qid),
        "sql_sha256": PG.sha(H / sql_file),
        "rows": n,
        "cols": cols,
        "types": meta.get("column_types"),
        "bytes": size,
    }
    root = H / "raw/dune" / (label + ".pages")
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "identity.json.gz"
    if manifest.exists():
        if json.loads(gzip.decompress(manifest.read_bytes())) != identity:
            raise SystemExit("恢复身份、列或总行数不一致，停止")
    else:
        atomic_json(manifest, identity)
    pages = []
    offset = 0
    while offset < n:
        p = root / (f"{offset:012d}.json.gz")
        if p.exists():
            saved = json.loads(gzip.decompress(p.read_bytes()))
        else:
            result = get(
                f"/execution/{execution_id}/results?limit={PAGE}&offset={offset}",
                ticket,
            )
            md = (result.get("result") or {}).get("metadata") or {}
            rs = (result.get("result") or {}).get("rows") or []
            if (
                result.get("execution_id") != execution_id
                or md.get("total_row_count") != n
                or md.get("column_names") != cols
            ):
                raise SystemExit("页面身份、总行数或列不一致")
            saved = {
                "offset": offset,
                "rows": rs,
                "next": result.get("next_offset"),
                "sha256": digest(rs),
            }
            # 在提交页之前验证完整性；不接受部分结果或不推进的游标。
            validate(saved, offset, n, cols)
            atomic_json(p, saved)
            print("已保存页", offset, "行", len(rs), flush=True)
        validate(saved, offset, n, cols)
        pages.append(p)
        offset += len(saved["rows"])
    part = H / "raw/dune" / (label + ".csv.gz.part")
    with gzip.open(part, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in pages:
            for row in json.loads(gzip.decompress(p.read_bytes()))["rows"]:
                w.writerow([row[c] for c in cols])
    part.replace(H / "raw/dune" / (label + ".csv.gz"))
    print("下载核对完成", n, "行", flush=True)


def validate(saved, offset, n, cols):
    rows = saved["rows"]
    end = offset + len(rows)
    if (
        saved["offset"] != offset
        or not rows
        or end > n
        or saved["sha256"] != digest(rows)
    ):
        raise SystemExit("页面计数或哈希不符")
    if any(set(r) != set(cols) for r in rows):
        raise SystemExit("页面字段不符")
    if (end < n and saved["next"] != end) or (end == n and saved["next"] is not None):
        raise SystemExit("分页游标不连续或结果截断")


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
        why = budget_gate(u0, ticket.download_cap) or PG.round_gate(a.approve)
        if why:
            raise SystemExit(why)
        PG.mark_used(a.approve, a.execution, "恢复下载")
        try:
            fetch(a.query_id, a.label, a.sql_file, ticket, a.execution)
        finally:
            u1 = usage()
            PG.record_actual(
                a.approve, a.execution, u0[0], None if u1 is None else u1[0], 0
            )


if __name__ == "__main__":
    main()

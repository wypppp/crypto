#!/usr/bin/env python3
"""DQ-35 v2：按清单逐片核对重取是否齐全（GPT 提取 SQL 审计第 10 条，10-03）。

python check_manifest_v2.py GRAD2|GRADPRE2 [起月 止月，默认 2025-03 2026-09]  → runs/manifest_<前缀>.csv
每片核对：①清单里的片都有文件；②文件行数＝Dune 执行状态里的 total_row_count；③台账里有该片且状态为完成；
④记下文件 sha256。缺任何一项的片列为“不齐”，返回码 1。不读数据内容，只数行。
"""

import csv
import gzip
import hashlib
import json
import sys

from dune_get import H
from run_all_v2 import halves


def rows_in(path):
    with gzip.open(path, "rt", newline="") as f:
        return sum(1 for _ in f) - 1


def check(pre, a="2025-03", b="2026-09"):
    raw = H / "raw" / "dune"
    with open(H / "runs" / "dune_ledger.csv") as f:
        led = {}
        for r in csv.DictReader(f):
            led[r["sql_file"]] = r
    out, bad = [], 0
    for label, s, e in halves(a, b, pre):
        p = raw / ("%s.csv.gz" % label)
        st = raw / ("%s_status.json" % label)
        row = {"label": label, "start": s, "end": e}
        row["has_file"] = p.exists()
        exp = None
        if st.exists():
            exp = json.loads(st.read_text())["result_metadata"]["total_row_count"]
        row["expected_rows"] = exp
        row["rows"] = rows_in(p) if p.exists() else None
        lr = led.get("sql/%s.sql" % label)
        row["ledger_state"] = lr["state"] if lr else None
        row["sha256"] = (
            hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        )
        ok = (
            row["has_file"]
            and exp is not None
            and row["rows"] == exp
            and row["ledger_state"] == "QUERY_STATE_COMPLETED"
        )
        # 整片在封存周内、查询 0 行时不生成文件：只要台账完成且预期 0 行即算齐
        if (
            not p.exists()
            and exp == 0
            and row["ledger_state"] == "QUERY_STATE_COMPLETED"
        ):
            ok = True
        row["ok"] = ok
        bad += 0 if ok else 1
        out.append(row)
    dst = H / "runs" / ("manifest_%s.csv" % pre)
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    return out, bad


def main():
    pre = sys.argv[1]
    a, b = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("2025-03", "2026-09")
    out, bad = check(pre, a, b)
    print("%s：清单 %d 片，不齐 %d 片" % (pre, len(out), bad))
    for r in out:
        if not r["ok"]:
            print(
                "  不齐：",
                r["label"],
                r["has_file"],
                r["rows"],
                r["expected_rows"],
                r["ledger_state"],
            )
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

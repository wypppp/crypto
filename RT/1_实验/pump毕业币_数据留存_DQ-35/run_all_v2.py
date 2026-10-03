#!/usr/bin/env python3
"""DQ-35 v2：按半月分片依次执行重取（10-03 草稿；GPT 复核 v2 SQL 通过后才运行）。

python run_all_v2.py <起月 YYYY-MM> <止月 YYYY-MM> <累计上限 credits> GRAD2|GRADPRE2
标签用新前缀 GRAD2_*／GRADPRE2_*，不与 v1 文件混（GPT 提取 SQL 审计第 10 条）。已有同名完整文件的片跳过；
跑完后用 check_manifest_v2.py 按清单逐片核对齐全。累计超过上限即停。
事件止日最晚 2026-09-29（见 build_grad_sql_v2.py）；GRADPRE2 的 2026-06b 落在封存周内，照常跑（应为 0 行）。
"""

import csv
import datetime as dt
import subprocess
import sys

from dune_get import H

LAST = dt.date(2026, 9, 29)


def halves(a, b, pre):
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        first = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        s1, e1 = first, dt.date(y, m, 15)
        s2, e2 = dt.date(y, m, 16), min(nxt - dt.timedelta(days=1), LAST)
        s1 = max(s1, dt.date(2025, 3, 16))
        if s1 <= e1:
            out.append(("%s_%04d%02da" % (pre, y, m), s1, e1))
        if s2 <= e2:
            out.append(
                ("%s_%04d%02db" % (pre, y, m), max(s2, dt.date(2025, 3, 16)), e2)
            )
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def last_cost(label):
    with open(H / "runs" / "dune_ledger.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["sql_file"] == "sql/%s.sql" % label]
    return float(rows[-1]["credits"] or 0) if rows else 0.0


def main():
    cap = float(sys.argv[3])
    pre = sys.argv[4]
    builder = {"GRAD2": "build_grad_sql_v2.py", "GRADPRE2": "build_gradpre_sql_v2.py"}[
        pre
    ]
    spent = 0.0
    for label, s, e in halves(sys.argv[1], sys.argv[2], pre):
        if (H / "raw" / "dune" / ("%s.csv.gz" % label)).exists():
            continue
        subprocess.run(
            [sys.executable, builder, s.isoformat(), e.isoformat(), label],
            cwd=H,
            check=True,
        )
        r = subprocess.run(
            [sys.executable, "run_dune.py", label, "sql/%s.sql" % label], cwd=H
        )
        c = last_cost(label)
        spent += c
        print(
            "%s rc=%s cost=%.3f spent=%.3f" % (label, r.returncode, c, spent),
            flush=True,
        )
        if spent > cap:
            print("停止：累计超过上限", flush=True)
            break


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DQ-35：按半月分片依次执行留存查询（10-02）。
python run_all.py <起月 YYYY-MM> <止月 YYYY-MM> <累计上限 credits> [GRAD|GRADPRE]
GRAD 用 build_grad_sql.py（毕业后），GRADPRE 用 build_gradpre_sql.py（毕业前 300 秒）。
每片：生成 SQL → run_dune.py（执行、台账、下载）；已下载的片跳过。
单片实际费用 >100 或本次累计超过上限时停止（审批阈值 100；上限由执行模型按剩余额度设）。
"""

import csv
import datetime as dt
import subprocess
import sys

from dune_get import H


def halves(a: str, b: str, pre: str = "GRAD") -> list:
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        first = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        out.append((f"{pre}_{y:04d}{m:02d}a", first, dt.date(y, m, 15)))
        out.append(
            (f"{pre}_{y:04d}{m:02d}b", dt.date(y, m, 16), nxt - dt.timedelta(days=1))
        )
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def last_cost(label: str) -> float:
    with open(H / "runs" / "dune_ledger.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["sql_file"] == f"sql/{label}.sql"]
    return float(rows[-1]["credits"] or 0) if rows else 0.0


def main() -> None:
    cap = float(sys.argv[3])
    pre = sys.argv[4] if len(sys.argv) > 4 else "GRAD"
    builder = {"GRAD": "build_grad_sql.py", "GRADPRE": "build_gradpre_sql.py"}[pre]
    spent = 0.0
    for label, s, e in halves(sys.argv[1], sys.argv[2], pre):
        if s < dt.date(2025, 3, 16):
            s = dt.date(2025, 3, 16)
        if s > e or (H / "raw" / "dune" / f"{label}.csv.gz").exists():
            continue
        subprocess.run(
            [sys.executable, builder, s.isoformat(), e.isoformat(), label],
            cwd=H,
            check=True,
        )
        r = subprocess.run(
            [sys.executable, "run_dune.py", label, f"sql/{label}.sql"], cwd=H
        )
        c = last_cost(label)
        spent += c
        print(f"{label} rc={r.returncode} cost={c:.3f} spent={spent:.3f}", flush=True)
        if c > 100 or spent > cap:
            print("停止：单片超过 100 或累计超过上限", flush=True)
            break


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""依次执行 sql/C1_W*.sql（10 周）；单条费用 >100 或累计超过上限即停。python run_weeks.py <累计上限>"""

import csv
import subprocess
import sys
from pathlib import Path

H = Path(__file__).resolve().parent


def main() -> None:
    cap = float(sys.argv[1])
    for f in sorted((H / "sql").glob("C1_W*.sql")):
        label = f.stem
        if (H / "raw" / "dune" / f"{label}.csv.gz").exists():
            continue
        r = subprocess.run(
            [sys.executable, "run_dune.py", label, f"sql/{f.name}"], cwd=H
        )
        rows = list(csv.reader(open(H / "runs" / "dune_ledger.csv")))[1:]
        spent = sum(float(x[4]) for x in rows if x[4] and "C1_W" in x[1])
        last = float(rows[-1][4]) if rows[-1][4] else 0.0
        print(
            label,
            "rc",
            r.returncode,
            "cost",
            last,
            "spent_weeks",
            round(spent, 3),
            flush=True,
        )
        if r.returncode != 0 or last > 100 or spent > cap:
            print("停止", flush=True)
            break


if __name__ == "__main__":
    main()

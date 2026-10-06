#!/usr/bin/env python3
"""DQ-35 InitBoost 全量扫描的执行（10-06；总控第二十轮第二节，算在 vq 解码额度里，用试用余额）。

python 过程/run_boostscan.py a b c d
每段执行前读账户用量（budget_v22.usage）：试用额度 2,500 减已用不足 MARGIN 就停，不跑；
跑完把执行费记进 runs/budget_v22.csv（task=vq）。执行与下载用 run_dune.py（试用期导出不计费）。
"""

import subprocess
import sys
from pathlib import Path

H = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(H))
import budget_v22 as b  # noqa: E402

QUOTA = 2500.0
MARGIN = 40.0  # 一段的上沿：一天 1.66 × 21 天的约 1.2 倍


def last_cost(sql_file):
    import csv

    with open(H / "runs" / "dune_ledger.csv", newline="") as f:
        rs = [r for r in csv.DictReader(f) if r["sql_file"] == sql_file]
    return float(rs[-1]["credits"]) if rs else None


def main():
    with b.run_lock():  # 10-06：与 run_all_v22 共用单运行器锁
        _main()


def _main():
    for tag in sys.argv[1:]:
        u = b.usage()
        if u is None or QUOTA - u < MARGIN:
            print(
                "停：用量 %s，余额不足 %.0f，段 %s 不跑" % (u, MARGIN, tag), flush=True
            )
            return
        sql = "sql/SCAN23_BOOST_%s.sql" % tag
        subprocess.run(
            [sys.executable, "run_dune.py", "SCAN23_BOOST_%s" % tag, sql],
            cwd=H,
            check=True,
        )
        c = last_cost(sql)
        after = b.usage()
        b.record("vq", "SCAN23_BOOST_%s" % tag, "execute", c or 0.0, u, after)
        print("段 %s：费用 %s，用量 %s → %s" % (tag, c, u, after), flush=True)


if __name__ == "__main__":
    main()

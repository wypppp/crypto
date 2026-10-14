#!/usr/bin/env python3
"""双跑比对（取数附录 v2 §7）：python cmp_smoke.py <标签前缀>  → 比较 <前缀>_r1 与 <前缀>_r2 的冒烟输出，逐项列出是否一致。"""

import sys
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent


def main():
    pre = sys.argv[1]
    a, b = (
        pd.read_csv(H / "raw" / "dune" / ("%s_%s.csv.gz" % (pre, r)), dtype=str).T[0]
        for r in ("r1", "r2")
    )
    t = pd.DataFrame({"r1": a, "r2": b})
    t["same"] = t.r1 == t.r2
    print(t.to_string())
    print("双跑", "一致" if t.same.all() else "不一致")


if __name__ == "__main__":
    main()

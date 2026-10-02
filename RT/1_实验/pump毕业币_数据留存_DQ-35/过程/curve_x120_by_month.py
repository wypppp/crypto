#!/usr/bin/env python3
"""总控第十轮第 2 条①（10-02）：毕业币里曲线虚拟 SOL >120 的占比，按完成月统计——判断 C1 的异常剔除（审计第 12 处）是否系统性删掉了毕业币。
只用 GRADPRE（完成前 300 秒的曲线成交）的储备字段，不看价格路径与收益。
python 过程/curve_x120_by_month.py → runs/curve_x120_by_month.csv
"""

from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parents[1]
rows = []
for f in sorted((H / "raw" / "dune").glob("GRADPRE_2*.csv.gz")):
    d = pd.read_csv(f, usecols=["mint", "completed_at", "x_first", "x_last"])
    g = d.groupby("mint").agg(
        completed_at=("completed_at", "first"),
        x_first=("x_first", "max"),
        x_last=("x_last", "max"),
    )
    g["x_max"] = g[["x_first", "x_last"]].max(axis=1)
    rows.append(g)
a = pd.concat(rows)
a = a[~a.index.duplicated()]
a["month"] = a.completed_at.str[:7]
out = a.groupby("month").agg(
    n_graduated=("x_max", "size"),
    n_x_gt_120=("x_max", lambda s: int((s > 120).sum())),
    x_max_median=("x_max", "median"),
    x_max_p99=("x_max", lambda s: float(s.quantile(0.99))),
)
out["share_x_gt_120"] = (out.n_x_gt_120 / out.n_graduated).round(4)
(H / "runs").mkdir(exist_ok=True)
out.to_csv(H / "runs" / "curve_x120_by_month.csv")
print(out.to_string())

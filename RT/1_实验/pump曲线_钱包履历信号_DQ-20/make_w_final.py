"""DQ-20：由 Q0c 结果生成 raw/W_final.csv（按活跃度校正后命中 ≥3 且泊松尾概率 ≤1e-4 的钱包）。
卡片 v3.1 起它只用于描述（S_W），不参与判定；泊松校准假设钱包之间独立，并不可靠（外部复核 09-27）。
python make_w_final.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

H = Path(__file__).resolve().parent
NB = [3, 5, 10, 30, 100, 300, 1e9]

df = pd.read_csv(H / "raw" / "dune" / "Q0c.csv.gz", low_memory=False)
df["w"] = np.where(df.obs >= 1, 1, 4)
df["nb"] = pd.cut(df.n_coins, NB, right=False)
fac = df.groupby("nb", observed=True).apply(lambda s: (s.w * s.obs).sum() / (s.w * s.expct).sum())
df["lam2"] = df.expct * df.nb.map(fac).astype(float)
df["p2"] = poisson.sf(df.obs - 1, df.lam2)
W = df[(df.obs >= 3) & (df.p2 <= 1e-4)]
W[["usr", "n_coins", "obs", "lam2", "p2"]].to_csv(H / "raw" / "W_final.csv", index=False)
print(len(W))

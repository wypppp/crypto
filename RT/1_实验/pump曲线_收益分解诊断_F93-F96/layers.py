# -*- coding: utf-8 -*-
"""改善目标表按层重算：全池 vs 净流入前20% vs 前5%。
同时按层估 MDE（自助法），因为选择率越低、标准误越大。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
FEE = 0.004; rng = np.random.default_rng(20260918)

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    d["loser"] = (~d["winner"]) & (d["rec"] >= 0.5) & (d["rec"] < 0.9)
    return d

def boot_se(x, n=2000):
    return np.std([rng.choice(x, len(x), replace=True).mean() for _ in range(n)], ddof=1)

for nm, path, rec, ms in [("A 周", "dq7/raw/F2_dev.csv", "b50", "ms_30d"),
                          ("B 周", "dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")]:
    d = load(path, rec, ms)
    q = d["net_sol_pre"].astype(float)
    print("=" * 92); print(nm)
    print("%-14s %6s %8s %7s %8s %9s %9s %10s %9s"
          % ("层","n","基线","SE(1周)","SE(4周)","可确认门槛","缺口","剔25%上限","够不够"))
    for lname, m in [("全池", np.ones(len(d), bool)),
                     ("净流入前20%", (q >= q.quantile(0.80)).values),
                     ("净流入前5%",  (q >= q.quantile(0.95)).values)]:
        s = d[m]; base = s.rec.mean()
        se1 = boot_se(s.rec.values); se4 = se1/2
        thr = 1 + 1.28*se4                      # 单侧 90% 可确认
        gap = thr - base
        cl = s.loser.mean()*(s.rec.values[s.loser.values].mean()-1) if s.loser.sum() else 0.0
        ok = "够" if -cl >= gap else "不够"
        print("%-14s %6d %8.4f %7.4f %8.4f %9.4f %+9.4f %10.4f %9s"
              % (lname, len(s), base, se1, se4, thr, gap, -cl, ok))
    print("   注：'剔25%上限' = 完美剔除该层全部被止损非赢家(0.5-0.9)所能带来的最大提升，不含误伤赢家的损失。")
    print("   摩擦上限：往返成本降到 0 最多贡献 +0.025。")

# -*- coding: utf-8 -*-
"""收益公式改善目标表（0 credits，用现成 CSV）。
A 周 dq7/raw/F2_dev.csv + b50 + ms_30d；B 周 dq1f/raw/F1_val.csv + x50_24h + ms_60d。
第一步先复现 F88① 以确认口径，再做 F88 未做的部分。"""
import numpy as np, pandas as pd

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]

def load(path, rec, ms):
    d = pd.read_csv(path)
    d["rec"] = d[rec].astype(float)
    d["ms"] = d[ms].astype(float)
    d["winner"] = d["ms"] >= 10.0
    return d

def strata(d, fee):
    r = d["rec"] - fee
    w = d["winner"].values
    lab = np.where(w, "1_赢家 ms>=10",
          np.where(r < 0.5, "4_深跌 <0.5",
          np.where(r < 0.9, "3_被止损非赢家 0.5-0.9",
          np.where(r < 1.1, "5_持平 0.9-1.1", "2_上涨非赢家 >1.1"))))
    out = []
    n = len(d)
    for k in sorted(set(lab)):
        m = lab == k
        out.append(dict(层=k, 占比=m.mean(), 均值=r[m].mean(), 贡献=m.mean()*(r[m].mean()-1)))
    t = pd.DataFrame(out)
    return t, r.mean(), lab

for name, path, rec, ms in [("A 周 (06-01~07, b50)", "dq7/raw/F2_dev.csv", "b50", "ms_30d"),
                            ("B 周 (06-08~14, x50_24h)", "dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")]:
    d = load(path, rec, ms)
    print("=" * 78); print(name, "| n =", len(d), "| 赢家 =", int(d.winner.sum()),
          "(%.2f%%)" % (100*d.winner.mean()))
    for fee in (0.0, 0.004):
        t, mu, _ = strata(d, fee)
        print("  -- 扣费 %.3f，总平均回收 %.4f" % (fee, mu))
        for _, r0 in t.iterrows():
            print("     %-24s 占比 %5.1f%%  均值 %6.3f  贡献 %+7.4f"
                  % (r0["层"], 100*r0["占比"], r0["均值"], r0["贡献"]))

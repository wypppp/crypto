"""DQ-20 第 0 段：Q0c（履历窗口 05-21～06-06）的本地检验。

1. 标签对账：A 周部分按 Dune 标签与按 F3 名单的命中总数；F3 的 96 个赢家有多少出现在 Dune 赢家里。
2. 超额检验：各显著性阈值下，实际钱包数对比纯运气预期数；另按钱包活跃度（早买币数档）校正期望后再比。
3. 按卡片 v2 的合格定义（命中 ≥3、泊松尾概率 ≤1e-4），报告合格钱包、预期幸运数与命中集合的重合。
实际命中为 0 的钱包在 SQL 里按哈希保留 1/4，权重记 4。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

H = Path(__file__).resolve().parent
NB = [3, 5, 10, 30, 100, 300, 1e9]


def excess(df, lam, alphas=(0.05, 0.01, 0.001, 1e-4)):
    p = poisson.sf(df.obs - 1, lam)
    out = {}
    for a in alphas:
        k = np.array([int(poisson.isf(a, l)) + 1 for l in lam])
        null = float((df.w * poisson.sf(k - 1, lam)).sum())
        obs = float((df.w * (p <= a)).sum())
        out[str(a)] = {"observed": obs, "null": round(null, 1), "ratio": round(obs / null, 3) if null else None}
    return out, p


def main():
    df = pd.read_csv(H / "raw" / "dune" / "Q0c.csv.gz")
    df["w"] = np.where(df.obs >= 1, 1, 4)
    f3 = set(pd.read_csv(H / "raw" / "A_winners_24h.csv").mint)
    dune_w = {m for s in df.hit_mints.dropna() for m in s.split(",") if m}
    res = {"rows": int(len(df)), "wallets_weighted": float(df.w.sum()),
           "label_check": {"sum_obs_a_dune": int((df.w * df.obs_a).sum()), "sum_obs_a_f3": int((df.w * df.obs_a_f3).sum()),
                           "f3_winners": len(f3), "f3_in_dune_winner_union": len(f3 & dune_w),
                           "dune_winner_union": len(dune_w)}}
    res["obs_total"] = float((df.w * df.obs).sum())
    res["exp_total"] = round(float((df.w * df.expct).sum()), 1)
    df["nb"] = pd.cut(df.n_coins, NB, right=False)
    fac = df.groupby("nb", observed=True).apply(lambda s: (s.w * s.obs).sum() / (s.w * s.expct).sum())
    res["activity_factor"] = {str(k): round(float(v), 3) for k, v in fac.items()}
    res["excess_state_only"], df["p"] = excess(df, df.expct)
    lam2 = df.expct * df.nb.map(fac).astype(float)
    res["excess_activity_adjusted"], df["p2"] = excess(df, lam2)
    Q = df[(df.obs >= 3) & (df.p <= 1e-4)].sort_values("p")
    Q2 = df[(df.obs >= 3) & (df.p2 <= 1e-4)].sort_values("p2")
    res["qualified_v2_state_only"] = int(len(Q))
    res["qualified_activity_adjusted"] = int(len(Q2))
    res["qualified_activity_adjusted_list"] = Q2[["usr", "n_coins", "obs", "expct", "p2", "n_age_lt2s", "n_days"]].round(6).to_dict("records")
    hs = Q2.hit_mints.fillna("")
    res["qualified_activity_adjusted_distinct_hitsets"] = int(hs.nunique())
    (H / "results").mkdir(exist_ok=True)
    (H / "results" / "q0c_summary.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    Q2.to_csv(H / "raw" / "W_qualified_q0c.csv", index=False)
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()

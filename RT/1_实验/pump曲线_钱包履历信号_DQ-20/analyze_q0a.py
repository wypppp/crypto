"""DQ-20 第 0 段：Q0a 结果的本地评分（只用 A 周）。

- 合格（卡片 v2 §4）：实际命中 ≥3，且泊松尾概率 P(X ≥ obs | λ = 期望命中) ≤ 1e-4。
- 预期幸运入选数：Σ_w 权重 × P(Pois(λ_w) ≥ max(3, k_w))，k_w 为使尾概率 ≤1e-4 的最小整数；
  实际命中 = 0 的钱包在 SQL 里按哈希保留 1/4，权重记 4，其余权重 1。
- 安慰剂池：实际命中 ≤ 期望命中的钱包，按（早买币数档 × 期望命中档）与合格钱包同格。
- 输出：results/q0a_summary.json、raw/W_qualified.csv、raw/placebo_pool.csv、raw/q0b_wallets.csv（Q0b 的钱包名单，含 H1 案例币早买者作字段核对）。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

H = Path(__file__).resolve().parent
P_MAX = 1e-4
MIN_OBS = 3
NC_BINS = [3, 5, 10, 30, 100, np.inf]
EX_BINS = [0, 0.05, 0.2, 0.5, 1, 3, np.inf]
H1 = H.parent / "pump曲线_案例时序与点火跟随_H1" / "trades.csv"


def main():
    df = pd.DataFrame(json.load(open(H / "raw" / "dune" / "Q0a.json"))["rows"])
    for c in ("n_coins", "obs", "expct", "sol_total", "n_age_lt2s", "n_create_slot", "n_days", "min_cell_n"):
        df[c] = pd.to_numeric(df[c])
    df["w"] = np.where(df.obs >= 1, 1, 4)
    df["p"] = poisson.sf(df.obs - 1, df.expct)
    kmin = np.array([max(MIN_OBS, int(poisson.isf(P_MAX, l)) + 1) for l in df.expct])
    # isf 给出使 sf(k) ≤ P_MAX 的 k；尾概率 P(X ≥ k+1) = sf(k)
    df["null_p_qual"] = poisson.sf(kmin - 1, df.expct)
    df["qual"] = (df.obs >= MIN_OBS) & (df.p <= P_MAX)
    df["nc_bin"] = pd.cut(df.n_coins, NC_BINS, right=False).astype(str)
    df["ex_bin"] = pd.cut(df.expct, EX_BINS, right=False).astype(str)
    Q = df[df.qual].copy()
    lucky = float((df.w * df.null_p_qual).sum())
    Q["sniper_share"] = Q.n_age_lt2s / Q.n_coins
    Q["create_slot_share"] = Q.n_create_slot / Q.n_coins
    hitsets = Q.hit_mints.fillna("")
    winners_covered = sorted({m for s in hitsets for m in s.split(",") if m})
    plac = df[(~df.qual) & (df.obs <= df.expct)]
    cells = Q.groupby(["nc_bin", "ex_bin"]).size().rename("n_qual")
    pool = plac.groupby(["nc_bin", "ex_bin"]).size().rename("n_pool")
    match = pd.concat([cells, pool], axis=1).fillna(0).astype(int)
    match = match[match.n_qual > 0]
    summ = {
        "rows": int(len(df)), "wallets_weighted": float(df.w.sum()),
        "qualified": int(len(Q)), "expected_lucky_qualified": round(lucky, 3),
        "qualified_obs_dist": Q.obs.value_counts().sort_index().to_dict(),
        "qualified_n_coins_quantiles": Q.n_coins.quantile([0, .25, .5, .75, 1]).round(1).to_dict(),
        "qualified_sniper_share_median": round(float(Q.sniper_share.median()), 3) if len(Q) else None,
        "qualified_create_slot_share_median": round(float(Q.create_slot_share.median()), 3) if len(Q) else None,
        "qualified_distinct_hitsets": int(hitsets.nunique()),
        "winners_covered_by_qualified": len(winners_covered),
        "top_hitsets": hitsets.value_counts().head(10).to_dict(),
        "placebo_match_cells": {f"{a}|{b}": [int(r.n_qual), int(r.n_pool)] for (a, b), r in match.iterrows()},
        "cell_n_min_among_qualified": int(Q.min_cell_n.min()) if len(Q) else None,
    }
    Q.sort_values("p").to_csv(H / "raw" / "W_qualified.csv", index=False)
    pl = plac.merge(match.reset_index()[["nc_bin", "ex_bin"]], on=["nc_bin", "ex_bin"])
    pl.to_csv(H / "raw" / "placebo_pool.csv", index=False)
    # Q0b 名单：合格 + 同格安慰剂（每格最多 30×合格数，按地址排序确定性截取）+ H1 案例币早买者
    pick = []
    for (a, b), r in match.iterrows():
        c = pl[(pl.nc_bin == a) & (pl.ex_bin == b)].sort_values("usr").head(30 * int(r.n_qual))
        pick.append(c[["usr"]].assign(role="placebo"))
    tr = pd.read_csv(H1)
    fx = tr[(tr.kind == "buy") & (tr.t_rel_entry < 0) & (tr.sol >= 0.1)]
    fix = fx[["trader"]].drop_duplicates().rename(columns={"trader": "usr"}).assign(role="fixture")
    names = pd.concat([Q[["usr"]].assign(role="qualified")] + pick + [fix]).drop_duplicates("usr")
    names.to_csv(H / "raw" / "q0b_wallets.csv", index=False)
    summ["q0b_wallets"] = names.role.value_counts().to_dict()
    (H / "results").mkdir(exist_ok=True)
    (H / "results" / "q0a_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(summ, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

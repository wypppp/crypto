"""DQ-21 R0 汇总与进入 R1 的条件（README v1.2 §8、过程/R0b_预算与门槛.md）。不看收益。

python analyze_r0.py → results/r0_summary.json
输入：results/all_coins.csv、all_wallets.csv（build_r0.py all --services services.csv）、raw/helius_index.csv、
      raw/dune/Q_daily.csv.gz、results/*_audit*.csv。
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import flows as F

H = Path(__file__).resolve().parent
PANEL = 29_024
PANEL_PER_DAY = PANEL / 14
N_R1 = 1_000
P = 5


def wilson_lower(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d


def main():
    S = pd.read_csv(H / "sample.csv")
    C = pd.read_csv(H / "results" / "all_coins.csv")
    W = pd.read_csv(H / "results" / "all_wallets.csv")
    idx = pd.read_csv(H / "raw" / "helius_index.csv")
    strat = S[S.stratum.isin(["random", "winner", "matched"])].drop_duplicates(["mint", "stratum"])
    out = {"strata": {}}
    combos = ["strict", "lenient", "obs_strict", "obs_lenient"]
    for st, g in strat.groupby("stratum"):
        c = C[C.mint.isin(g.mint)]
        w = W[W.mint.isin(g.mint)]
        rec = {"coins": int(len(c)), "applicable": int(c.applicable.sum()),
               "wallet_status": w.status.value_counts().to_dict(),
               "resolved_complete_sol_share_median_applicable": float(c[c.applicable].resolved_sol_share.median())}
        for cb in combos:
            k = int(c[f"trigger_{cb}"].fillna(False).astype(bool).sum())
            rec[f"triggers_{cb}"] = k
            rec[f"trigger_share_{cb}"] = round(k / len(c), 4)
            rec[f"wilson_lower_{cb}"] = round(wilson_lower(k, len(c)), 4)
            rec[f"implied_triggers_in_panel_{cb}"] = round(wilson_lower(k, len(c)) * PANEL)
            rec[f"V1_pos_{cb}"] = int((c[f"V1_{cb}"] > 0).sum())
            rec[f"V2_pos_{cb}"] = int((c[f"V2n_{cb}"] >= 2).sum())
        out["strata"][st] = rec
    rnd = out["strata"]["random"]
    # 条件 1：主样本、主口径（7 天完整窗口）；任一服务判定达到即可
    g1 = {cb: rnd[f"implied_triggers_in_panel_{cb}"] >= N_R1 for cb in ("strict", "lenient")}
    # 条件 2：核验（R0a 第 2 轮、R0b 第 3+4 轮中进入变量的唯一可归因）零错判
    aud = []
    for f in sorted((H / "results").glob("*_audit*.csv")):
        d = pd.read_csv(f).assign(file=f.name)
        aud.append(d)
    A = pd.concat(aud)
    A["in_vars"] = (A.status == "unique") & A.W.map(F.on_curve)
    after_fix = A[A.file.isin(["r0a_audit2.csv", "all_audit3.csv", "all_audit4.csv"]) & A.in_vars]
    g2 = bool(after_fix.independent_supported.all())
    # 条件 3：时效——前 K 个早买者冷启动重建（6 线程并行）在创建后 30 分钟前完成
    back = idx[idx.kind.isin(["back", "back_ext"])].copy()
    back["base"] = back.key.str.replace("__ext", "", regex=False)
    wall = back.groupby("base").wall_s.sum()
    W["key"] = "back__" + W.W + "__" + W.t_buy.astype(str)
    W["wall_s"] = W.key.map(wall)
    tt = W.groupby("mint").agg(kth=("t_buy", "max"), wall=("wall_s", "sum"), n=("W", "size"))
    t0 = C.set_index("mint").t0
    tt["done_s"] = tt.kth - t0.reindex(tt.index) + tt.wall / 6
    g3_share = float((tt.done_s < 1800).mean())
    # 成本：每币平均调用数（前 K 个早买者往前翻页 + 创建者往前/往后）
    pages = back.groupby("base").pages.sum()
    W["pages"] = W.key.map(pages)
    cp = W.groupby("mint").pages.sum()
    pg = idx.set_index("key").pages
    cre = pd.Series({r.mint: pages.get(f"back__{r.creator}__{r.t0}", 0) + pg.get(f"fwd__{r.creator}__{r.t0}", 0)
                     for r in C.itertuples()})
    ap = C[C.applicable].mint
    per_coin = float(cp.reindex(ap).fillna(0).mean() + cre.reindex(ap).fillna(0).mean())
    out["cost"] = {"mean_calls_per_applicable_coin": round(per_coin, 1),
                   "mean_pages_per_cold_walk": round(float(W.pages.mean()), 2)}
    # 09-27 复核后：只处理适用币（成交事件可便宜地排除不适用币），用主样本的适用率与每个适用随机币的调用数
    rc = C[C.mint.isin(S[S.stratum == "random"].mint)]
    a_rnd = float(rc.applicable.mean())
    apr = rc[rc.applicable]
    per_rnd = float(np.mean([cp.get(r.mint, 0) + cre.get(r.mint, 0) for r in apr.itertuples()]))
    out["cost"].update({"random_applicable_share": a_rnd, "calls_per_applicable_random_coin": round(per_rnd, 1)})
    res = {}
    for cb in ("strict", "lenient"):
        pl = rnd[f"wilson_lower_{cb}"]
        M = N_R1 / pl if pl > 0 else float("inf")
        cr_ = None if M == float("inf") else round(M * a_rnd * per_rnd * 10)
        res[cb] = {"M_coins_needed": None if M == float("inf") else round(M), "exceeds_panel": M > PANEL,
                   "applicable_coins_to_process": None if M == float("inf") else round(M * a_rnd),
                   "historical_credits": cr_, "usd_at_5_per_million": None if cr_ is None else round(cr_ / 1e6 * 5)}
    # 持续索引（前向收集）：每日成本
    Qd = pd.read_csv(H / "raw" / "dune" / "Q_daily.csv.gz")
    day = Qd.drop(columns="d").mean()
    rate = []
    for r in idx[idx.kind == "back"].itertuples():
        if pd.notna(r.min_ts) and r.n_tx > 0:
            span_h = max((r.lt - 1 - r.min_ts) / 3600, 1 / 60)
            rate.append(r.n_tx / span_h if str(r.complete) != "True" else r.n_tx / 168)
    rate = np.array(rate)
    def inc_pages(gap_h):
        return float(np.minimum(P, np.maximum(1, np.ceil(rate * gap_h / 100))).mean())
    intra = day.n_pairs_k30 - day.n_wallets_k30                     # 同一天内的重复出现
    gap_intra = 24 / (day.n_pairs_k30 / day.n_wallets_k30)
    daily = 10 * (day.n_new_7d_k30 * out["cost"]["mean_pages_per_cold_walk"]
                  + day.n_back_1d_k30 * inc_pages(24) + day.n_back_2to7d_k30 * inc_pages(96)
                  + intra * inc_pages(gap_intra))
    fwd = {"daily_credits": round(daily), "pairs_k30_per_day": round(day.n_pairs_k30),
           "new_wallets_per_day": round(day.n_new_7d_k30), "intra_day_repeats": round(intra),
           "inc_pages_intra_1d_4d": [round(inc_pages(gap_intra), 2), round(inc_pages(24), 2), round(inc_pages(96), 2)]}
    for cb in ("strict", "lenient"):
        pl = rnd[f"wilson_lower_{cb}"]
        days = N_R1 / (PANEL_PER_DAY * pl) if pl > 0 else float("inf")
        fwd[f"days_to_N_R1_{cb}"] = None if days == float("inf") else round(days, 1)
        fwd[f"total_credits_{cb}"] = None if days == float("inf") else round(days * daily)
        fwd[f"affordable_le_1M_{cb}"] = bool(days * daily <= 1_000_000) if days != float("inf") else False
        fwd[f"usd_at_5_per_million_{cb}"] = None if days == float("inf") else round(days * daily / 1e6 * 5)
    out["gates"] = {"1_triggers": g1, "2_audit_zero_error": g2, "2_audit_n": int(len(after_fix)),
                    "3_share_coins_ready_before_30min": round(g3_share, 3), "3_pass": g3_share >= 0.95,
                    "4_historical": res, "4_forward": fwd}
    (H / "results" / "r0_summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

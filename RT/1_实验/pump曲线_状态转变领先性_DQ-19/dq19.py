"""DQ-19 执行（冻结卡片：卡片_v3.md，sha256 179eb8dc…）。

结果张量用 DQ-8A 的 analyze_dq8a.load_week（运行时把它的旧目录名换成现有路径，不改冻结文件）；
签名字段按同一面板自行读取（与 load_week 的“最近一个有成交的区间”沿用规则一致）。
  python3 dq19.py          → results/dq19.json
DQ19_REPS 可改随机基线与偶然通过率的重复次数（默认 1000）。
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RT1 = H.parent
D8 = RT1 / "pump曲线_检查点动态决策_DQ-8A"
sys.path.insert(0, str(D8))
import analyze_dq8a as A8  # noqa: E402

A8.WEEKS = {"A": (D8 / "raw/F3_devA.csv", RT1 / "pump曲线_退出规则_DQ-7/raw/F2_dev.csv"),
            "B": (D8 / "raw/F3_devB.csv", RT1 / "pump曲线_入场筛选与动态退出_DQ-1F/raw/F1_val.csv")}
TAUS = A8.TAUS
NJ = A8.NJ
C = A8.C
J_SIG = [2, 4, 6]            # 15 分钟、1 小时、4 小时
J_MAP = list(range(9))       # 剩余右尾图：0 … 24 小时
FRESH_S = 1800
REPS = int(os.environ.get("DQ19_REPS", "1000"))
H1_EVENTS = RT1 / "pump曲线_案例时序与点火跟随_H1/h1_events_A.csv"


def load(w):
    D = A8.load_week(w)
    P = pd.read_csv(A8.WEEKS[w][0], low_memory=False).sort_values(["mint", "iv"])
    mints = P.mint.unique()
    assert (mints == D["mints"]).all()
    N = len(mints)
    cols = ["last_dt", "f_trades30", "f_trades30_prev", "f_buy30", "f_sell30", "f_newb30"]
    piv = {c: P.pivot(index="mint", columns="iv", values=c).reindex(index=mints, columns=range(12)).to_numpy(float) for c in cols}
    present = P.assign(one=1.0).pivot(index="mint", columns="iv", values="one").reindex(index=mints, columns=range(12)).notna().to_numpy()
    src = np.zeros((N, NJ), int)
    cur = np.zeros(N, int)
    for j in range(NJ):
        cur = np.where(present[:, j], j, cur)
        src[:, j] = cur
    g = {c: np.take_along_axis(piv[c], src, 1) for c in cols}
    fresh = (TAUS[None, :] - g["last_dt"]) <= FRESH_S
    t1 = np.log1p(np.nan_to_num(g["f_trades30"])) - np.log1p(np.nan_to_num(g["f_trades30_prev"]))
    nb = np.nan_to_num(g["f_newb30"])
    with np.errstate(invalid="ignore", divide="ignore"):
        t2 = np.where(nb > 0, (np.nan_to_num(g["f_buy30"]) - np.nan_to_num(g["f_sell30"])) / np.where(nb > 0, nb, 1), np.nan)
    maxpm = P.groupby("mint").f_maxpm.max().reindex(mints).to_numpy(float)
    # R[:, k]：在 τ_k 空仓买入、一直 b50 持有的净回收（扣 C）
    R = np.full((N, NJ), np.nan)
    for k in range(NJ):
        cl = D["closed"][:, k, k:, 0]
        cv = D["cval"][:, k, k:, 0]
        anyc = cl.any(1)
        first = cl.argmax(1)
        R[:, k] = np.where(anyc, cv[np.arange(N), first], D["term"][:, k]) - C
    b50_check = float(np.nanmax(np.abs(R[:, 0] - (D["b50"] - C))))
    created = None
    return dict(w=w, mints=mints, N=N, fresh=fresh, T1=t1, T2=t2, maxpm=maxpm, R=R, b50_check=b50_check,
                valid=np.isfinite(R), created=created)


def dist(x):
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"n": 0}
    return {"n": int(len(x)), "p_ge1": round(float((x >= 1).mean()), 4), "p_ge2": round(float((x >= 2).mean()), 4),
            "p_ge3": round(float((x >= 3).mean()), 4), "p_ge10": round(float((x >= 10).mean()), 4),
            "median": round(float(np.median(x)), 4), "mean": round(float(x.mean()), 4)}


def residual_map(W):
    out = {}
    tail = W["maxpm"] >= 100
    ten = W["maxpm"] >= 10
    for j in J_MAP:
        R = W["R"][:, j]
        v = W["valid"][:, j]
        out[f"{int(TAUS[j])}s"] = {
            "tail": dist(R[tail & v]), "ge10": dist(R[ten & v]), "risk_set_fresh": dist(R[W["fresh"][:, j] & v]),
            "tail_fresh_share": round(float((W["fresh"][:, j] & tail).sum() / max(tail.sum(), 1)), 4)}
    return out


def thresholds(WA, sig, q):
    th = {}
    for j in J_SIG:
        s = WA[sig][:, j]
        m = WA["fresh"][:, j] & WA["valid"][:, j] & np.isfinite(s)
        th[j] = float(np.quantile(s[m], 1 - q))
    return th


def trigger(W, score, th):
    """首次触发：返回 (选中掩码, 各币触发检查点 or -1)。"""
    at = np.full(W["N"], -1)
    for j in J_SIG:
        s = score[:, j]
        ok = (at < 0) & W["fresh"][:, j] & W["valid"][:, j] & np.isfinite(s) & (s > th[j])
        at[ok] = j
    return at >= 0, at


def evaluate(W, sel, at):
    R = np.where(sel, W["R"][np.arange(W["N"]), np.maximum(at, 0)], np.nan)
    r = R[sel]
    n = int(sel.sum())
    out = {"n_trig": n, "by_checkpoint": {f"{int(TAUS[j])}s": int((at == j).sum()) for j in J_SIG},
           "P_S": round(n / W["N"], 5)}
    for lab, thr in (("tail100", 100), ("ge10", 10)):
        T = W["maxpm"] >= thr
        cap = int((sel & T).sum())
        ps = cap / n if n else 0.0
        out[lab] = {"n_tail": int(T.sum()), "captured": cap, "P_S_given_T": round(cap / max(T.sum(), 1), 4),
                    "P_T_given_S": round(ps, 5), "lift": round(ps / (T.sum() / W["N"]), 3) if T.sum() else None}
    if n == 0:
        return out, r
    pos = np.clip(r - 1, 0, None)
    top = np.argsort(-r)
    out.update({"E": round(float(r.mean()), 4), "median": round(float(np.median(r)), 4),
                "share_gt1": round(float((r > 1).mean()), 4), "n_pos": int((r > 1).sum()),
                "max_single_share_of_pos": round(float(pos.max() / pos.sum()), 4) if pos.sum() > 0 else None,
                "E_drop_top1": round(float(np.delete(r, top[:1]).mean()), 4) if n > 1 else None,
                "E_extra_cost_0.01": round(float(r.mean() - 0.01), 4), "E_extra_cost_0.02": round(float(r.mean() - 0.02), 4)})
    return out, r


def random_baseline(W, at, rng, reps):
    counts = {j: int((at == j).sum()) for j in J_SIG}
    Es = np.empty(reps)
    for b in range(reps):
        taken = np.zeros(W["N"], bool)
        vals = []
        for j in J_SIG:
            pool = np.where(W["fresh"][:, j] & W["valid"][:, j] & ~taken)[0]
            k = min(counts[j], len(pool))
            pick = rng.choice(pool, k, replace=False)
            taken[pick] = True
            vals.append(W["R"][pick, j])
        v = np.concatenate(vals)
        Es[b] = v.mean() if len(v) else np.nan
    return Es


def gates(ev, pct95=None):
    g1 = ev.get("E", 0) >= 1.0
    g2 = (ev.get("E_drop_top1") or 0) >= 1.0
    g3 = ev["n_trig"] >= 20
    g4 = None if pct95 is None else ev.get("E", 0) > pct95
    return {"E_ge1": g1, "drop_top1_ge1": g2, "n_ge20": g3, "above_random95": g4}


def chance_pass(WA, WB, rng, reps):
    """两个随机伪签名中至少一个在两周都满足第 1–3 条的比例。"""
    hit = 0
    one = 0
    for _ in range(reps):
        any_pass = False
        for _s in range(2):
            SA = rng.random((WA["N"], NJ))
            SB = rng.random((WB["N"], NJ))
            th = {}
            for j in J_SIG:
                m = WA["fresh"][:, j] & WA["valid"][:, j]
                th[j] = float(np.quantile(SA[m, j], 0.98))
            ok = True
            for W, S in ((WA, SA), (WB, SB)):
                sel, at = trigger(W, S, th)
                ev, _ = evaluate(W, sel, at)
                g = gates(ev)
                ok &= g["E_ge1"] and g["drop_top1_ge1"] and g["n_ge20"]
            if ok:
                any_pass = True
                one += 1
        hit += any_pass
    return {"reps": reps, "p_at_least_one_of_two_passes_gates_1to3_both_weeks": round(hit / reps, 4),
            "p_single_pseudo_signature": round(one / (2 * reps), 4)}


def ignition_diag(WA, sel, at):
    ev = pd.read_csv(H1_EVENTS)
    ev["ign_rel_s"] = (pd.to_datetime(ev.signal_time.str.replace(" UTC", "")) - pd.to_datetime(ev.created_at.str.replace(" UTC", ""))).dt.total_seconds() - 1800
    ign = ev.groupby("mint").ign_rel_s.min()
    tail = WA["maxpm"] >= 100
    rows = []
    for i in np.where(tail)[0]:
        m = WA["mints"][i]
        rows.append({"mint": m[:8], "maxpm_30d": round(float(WA["maxpm"][i]), 1),
                     "ignition_rel_entry_h": round(float(ign[m]) / 3600, 2) if m in ign.index else None,
                     "selected": bool(sel[i]), "trigger_rel_entry_h": round(TAUS[at[i]] / 3600, 2) if sel[i] else None})
    return rows


def main():
    WA, WB = load("A"), load("B")
    rng = np.random.default_rng(20260925)
    out = {"card_sha256": "179eb8dc628a1b1e9bc28b888e6ec38251b67f132186f303a76ac23498a41ec6",
           "checks": {"R0_vs_panel_b50_maxabs": {"A": WA["b50_check"], "B": WB["b50_check"]},
                      "N": {"A": WA["N"], "B": WB["N"]},
                      "tails_ge100": {"A": int((WA["maxpm"] >= 100).sum()), "B": int((WB["maxpm"] >= 100).sum())},
                      "ge10": {"A": int((WA["maxpm"] >= 10).sum()), "B": int((WB["maxpm"] >= 10).sum())},
                      "unvalued_R_by_checkpoint": {w: {f"{int(TAUS[j])}s": int((~W["valid"][:, j]).sum()) for j in J_MAP}
                                                   for w, W in (("A", WA), ("B", WB))}}}
    out["chance_pass"] = chance_pass(WA, WB, rng, REPS)
    out["baseline2_all_fresh_mean"] = {w: {f"{int(TAUS[j])}s": dist(W["R"][W["fresh"][:, j] & W["valid"][:, j], j]) for j in J_SIG}
                                       for w, W in (("A", WA), ("B", WB))}
    sigs = {}
    for sig in ("T1", "T2"):
        for q in (0.02, 0.01, 0.05):
            th = thresholds(WA, sig, q)
            key = f"{sig}_q{q}"
            res = {"thresholds_from_A": {f"{int(TAUS[j])}s": th[j] for j in J_SIG}, "main": q == 0.02}
            for w, W in (("A", WA), ("B", WB)):
                sel, at = trigger(W, W[sig], th)
                ev, _ = evaluate(W, sel, at)
                if q == 0.02:
                    Es = random_baseline(W, at, rng, REPS)
                    p95 = float(np.nanquantile(Es, 0.95))
                    ev["random_baseline"] = {"p50": round(float(np.nanmedian(Es)), 4), "p95": round(p95, 4),
                                             "signature_pctile": round(float((Es < ev.get("E", -1)).mean()), 4)}
                    ev["gates"] = gates(ev, p95)
                    if w == "A":
                        res["ignition_diag_A"] = ignition_diag(WA, sel, at)
                res[w] = ev
            if q == 0.02:
                gA, gB = res["A"]["gates"], res["B"]["gates"]
                allp = all(gA.values()) and all(gB.values())
                only_conc = (not allp) and all(v for k, v in gA.items() if k != "drop_top1_ge1") and \
                    all(v for k, v in gB.items() if k != "drop_top1_ge1")
                res["verdict"] = "信号候选" if allp else ("集中度导致无法升级" if only_conc else "不通过")
            sigs[key] = res
    out["signatures"] = sigs
    out["residual_map"] = {"A": residual_map(WA), "B": residual_map(WB)}
    (H / "results").mkdir(exist_ok=True)
    (H / "results" / "dq19.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "residual_map"}, indent=1, ensure_ascii=False)[:9000])


if __name__ == "__main__":
    main()

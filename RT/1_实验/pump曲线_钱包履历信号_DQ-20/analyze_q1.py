"""DQ-20 第 1 段判定（卡片_v3.1.md，与卡片一同冻结；B 周只运行一次）。

python analyze_q1.py B            正式判定：raw/dune/Q1.csv.gz × F3 B 面板 → results/q1.json
python analyze_q1.py A --smoke    冒烟：A 面板 + 合成的 Q1 列（不含任何 B 周数据），只检查代码能跑通

估值：DQ-19 的 R_j（F3 面板，在入场后 τ_j 新买 0.5 SOL，按 b50 持有，扣 0.004）；入场 = 创建后 30 分钟，
τ = 0（主口径）、5 分钟、15 分钟（敏感性，即创建后 35、45 分钟，此时 30 分钟的买家构成已完整，不含未来信息）。
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent / "pump曲线_状态转变领先性_DQ-19"))
import dq19 as Q  # noqa: E402

SEED = 20260927
DRAWS = 1000
K_NN = 10
MATCH_VARS = ["lx", "tr30", "bshare", "vol30", "nb30", "ins", "lnbuy", "lsol"]


def f3_entry(w):
    P = pd.read_csv(Q.A8.WEEKS[w][0], low_memory=False)
    e = P[P.iv == 0].set_index("mint")
    tot = e.f_buy30.fillna(0) + e.f_sell30.fillna(0)
    return pd.DataFrame({
        "venue": e.l_venue, "lx": np.log(e.l_x), "tr30": np.log1p(e.f_trades30.fillna(0)),
        "bshare": np.where(tot > 0, e.f_buy30.fillna(0) / tot.where(tot > 0, 1), 0.5),
        "vol30": np.log1p(tot), "nb30": np.log1p(e.f_newb30.fillna(0)), "ins": e.f_ins_exit.fillna(0).clip(-1, 2)})


def load_q1(w, smoke):
    if smoke:
        rng = np.random.default_rng(1)
        Wk = Q.load(w)
        n = Wk["N"]
        df = pd.DataFrame({"mint": Wk["mints"], "n_buyers": rng.poisson(6, n), "sol_total": rng.gamma(2, 3, n)})
        df["n_hi30"] = rng.binomial(df.n_buyers, 0.3)
        df["w_idx_list"] = np.where(rng.random(n) < 0.02, "0", None)
        df["created_at"] = "2026-06-01 00:00:00"
        return Wk, df
    return Q.load(w), pd.read_csv(H / "raw" / "dune" / "Q1.csv.gz")


def stats(r, maxpm):
    r = np.asarray(r)
    if len(r) == 0:
        return {"n": 0}
    pos = np.clip(r - 1, 0, None)
    order = np.argsort(-r)
    return {"n": int(len(r)), "E": round(float(r.mean()), 4), "median": round(float(np.median(r)), 4),
            "share_gt1": round(float((r > 1).mean()), 4),
            "E_drop_top1": round(float(np.delete(r, order[:1]).mean()), 4) if len(r) > 1 else None,
            "max_single_share_of_pos": round(float(pos.max() / pos.sum()), 4) if pos.sum() > 0 else None,
            "E_cost_0.01": round(float(r.mean() - 0.01), 4), "E_cost_0.02": round(float(r.mean() - 0.02), 4),
            "n_ge10x": int((maxpm >= 10).sum()), "n_ge100x": int((maxpm >= 100).sum())}


def matched_control(U, trig, rng):
    """精确匹配（入场场所 × 创建日），组内按标准化欧氏距离取 10 个最近的非触发币；
    每次抽取为每个触发币从其 10 个近邻中均匀取一个，共 DRAWS 次，返回各次的平均 R_0。"""
    Z = U[MATCH_VARS].to_numpy(float)
    Z = (Z - Z.mean(0)) / np.where(Z.std(0) > 0, Z.std(0), 1)
    cand = ~trig & U.elig.to_numpy()
    nn = []
    for i in np.where(trig)[0]:
        same = cand & (U.venue.to_numpy() == U.venue.iat[i]) & (U.day.to_numpy() == U.day.iat[i])
        if same.sum() < K_NN:
            same = cand & (U.venue.to_numpy() == U.venue.iat[i])
        idx = np.where(same)[0]
        d = ((Z[idx] - Z[i]) ** 2).sum(1)
        nn.append(idx[np.argsort(d)[:K_NN]])
    R0 = U.R0.to_numpy()
    means = np.empty(DRAWS)
    for b in range(DRAWS):
        pick = np.array([row[rng.integers(len(row))] for row in nn])
        means[b] = R0[pick].mean()
    return means


def evaluate(U, trig, rng, maxpm):
    r0 = U.R0.to_numpy()[trig]
    out = {"R0": stats(r0, maxpm[trig]),
           "R_entry+5m": stats(U.R5.to_numpy()[trig], maxpm[trig]),
           "R_entry+15m": stats(U.R15.to_numpy()[trig], maxpm[trig])}
    if trig.sum() >= 1:
        m = matched_control(U, trig, rng)
        out["control"] = {"mean": round(float(m.mean()), 4), "p95": round(float(np.quantile(m, 0.95)), 4),
                          "signal_pctile": round(float((m < r0.mean()).mean()), 4)}
    base = U.elig.to_numpy()
    tail_rate = float((maxpm[base] >= 100).mean()) if base.any() else 0
    ten_rate = float((maxpm[base] >= 10).mean()) if base.any() else 0
    out["lift_ge100x"] = round(float((maxpm[trig] >= 100).mean()) / tail_rate, 3) if tail_rate and trig.any() else None
    out["lift_ge10x"] = round(float((maxpm[trig] >= 10).mean()) / ten_rate, 3) if ten_rate and trig.any() else None
    return out


def gates(ev):
    s = ev["R0"]
    if s.get("n", 0) == 0:
        return {"E_ge1": False, "drop_top1_ge1": False, "n_ge20": False, "above_control_p95": False}
    return {"E_ge1": s["E"] >= 1.0, "drop_top1_ge1": (s["E_drop_top1"] or 0) >= 1.0, "n_ge20": s["n"] >= 20,
            "above_control_p95": s["E"] > ev["control"]["p95"]}


def main():
    w = sys.argv[1]
    smoke = "--smoke" in sys.argv
    if w == "B" and smoke:
        raise SystemExit("冒烟只用 A")
    Wk, q = load_q1(w, smoke)
    U = pd.DataFrame({"mint": Wk["mints"], "R0": Wk["R"][:, 0], "R5": Wk["R"][:, 1], "R15": Wk["R"][:, 2],
                      "maxpm": Wk["maxpm"]}).set_index("mint")
    U = U.join(f3_entry(w)).join(q.set_index("mint")[["n_buyers", "sol_total", "n_hi30", "w_idx_list", "created_at"]])
    U["n_buyers"] = U.n_buyers.fillna(0)
    U["n_hi30"] = U.n_hi30.fillna(0)
    U["sol_total"] = U.sol_total.fillna(0)
    U["lnbuy"] = np.log1p(U.n_buyers)
    U["lsol"] = np.log1p(U.sol_total)
    U["day"] = pd.to_datetime(U.created_at).dt.date.astype(str)
    U["elig"] = U.n_buyers >= 3
    U = U.reset_index()
    maxpm = U.maxpm.to_numpy()
    rng = np.random.default_rng(SEED)
    share = np.where(U.n_buyers > 0, U.n_hi30 / U.n_buyers.where(U.n_buyers > 0, 1), 0)
    res = {"week": w, "smoke": smoke, "N_panel": int(len(U)), "N_elig": int(U.elig.sum()),
           "no_q1_row": int(U.created_at.isna().sum()),
           "all_elig_R0": stats(U.R0.to_numpy()[U.elig.to_numpy()], maxpm[U.elig.to_numpy()])}
    for thr in (0.5, 0.3, 0.7):
        trig = U.elig.to_numpy() & (share >= thr)
        ev = evaluate(U, trig, rng, maxpm)
        if thr == 0.5:
            ev["gates"] = gates(ev)
            g = ev["gates"]
            allp = all(g.values())
            only_conc = (not allp) and all(v for k, v in g.items() if k != "drop_top1_ge1")
            ev["verdict"] = "信号候选" if allp else ("集中度导致无法升级" if only_conc else "不通过")
        res[f"S_C_share_ge_{thr}"] = ev
    wl = U.w_idx_list.fillna("").astype(str)
    trig_w = wl.str.len().to_numpy() > 0
    res["S_W_descriptive"] = evaluate(U, trig_w, rng, maxpm)
    res["S_W_descriptive"]["by_w_idx"] = {str(i): stats(U.R0.to_numpy()[wl.str.split(",").apply(lambda x: str(i) in x).to_numpy()],
                                                       maxpm[wl.str.split(",").apply(lambda x: str(i) in x).to_numpy()])
                                          for i in range(10)}
    out = H / "results" / ("q1_smoke_A.json" if smoke else f"q1_{w}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "S_W_descriptive"}, indent=1, ensure_ascii=False, default=str)[:3000])


if __name__ == "__main__":
    main()

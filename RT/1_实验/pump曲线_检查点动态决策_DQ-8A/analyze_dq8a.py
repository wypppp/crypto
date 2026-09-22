"""DQ-8A 正式分析：检查点面板 → 逐币事件张量 → 分状态回归逆向动态规划（按 mint 5 折交叉拟合）→ 上界 / 策略 / b50 → 判据与报告。
口径全部来自 frozen_config.json 与冻结版卡片。用法：
  python3 analyze_dq8a.py dev     只用 A 周：A 内交叉拟合（描述）、上界、b50，并做一致性自检
  python3 analyze_dq8a.py final   A、B 两周：A→B、B→A、判据、报告
"""
import hashlib, json, sys
import numpy as np, pandas as pd
from pathlib import Path

H = Path(__file__).resolve().parent
CFG = json.loads((H / "frozen_config.json").read_text())
TAUS = np.array(CFG["taus_s"], dtype=float); NJ = len(TAUS); T_END = float(CFG["horizon_s"])
C = CFG["round_trip_cost"]; ALPHA = CFG["ridge_alpha"]; KEEP = (0.50, 0.30)  # hold50, hold70 保留比例
WEEKS = {"A": (H / "raw/F3_devA.csv", H.parent / "dq7/raw/F2_dev.csv"),
         "B": (H / "raw/F3_devB.csv", H.parent / "dq1f/raw/F1_val.csv")}


# ---------------- AMM ----------------
def sell_ratio(x, y, xr, v, fee, tok, feeb):
    x, y, xr, v, fee, tok, feeb = (np.asarray(a, dtype=float) for a in (x, y, xr, v, fee, tok, feeb))
    with np.errstate(invalid="ignore", divide="ignore"):
        curve = np.where(y > tok, (x * y / (y - tok) - x) * (1 - fee / 1e4), np.nan)
        curve = np.minimum(curve, np.nan_to_num(xr) + 0.5 * (1 - feeb / 1e4))
        pool = (x - x * y / (y + tok)) * (1 - fee / 1e4)
    return np.where(v == 0, curve, pool) / 0.5


def buy_tok(x, y, fee):
    return y - x * y / (x + 0.5 * (1 - fee / 1e4))


# ---------------- 面板 → 张量 ----------------
def load_week(w):
    pf, ef = WEEKS[w]
    P = pd.read_csv(pf, low_memory=False).sort_values(["mint", "iv"])
    E = pd.read_csv(ef, low_memory=False); E = E[E.mint != "__SUMMARY__"]
    E = E[["mint", "dev_prior_launches", "net_sol_pre"]].apply(lambda s: pd.to_numeric(s, errors="ignore") if s.name != "mint" else s)
    mints = P.mint.unique(); N = len(mints); idx = {m: i for i, m in enumerate(mints)}
    E = E.set_index("mint").reindex(mints)
    miss_entry = int(E.dev_prior_launches.isna().sum())
    devp = E.dev_prior_launches.fillna(0).to_numpy(float); nsol = E.net_sol_pre.fillna(0).to_numpy(float)

    ST = ["x", "y", "xr", "venue", "fee_bps"]
    info = np.full((N, NJ, 5), np.nan); info_f = np.full((N, NJ, 10), np.nan); info_last = np.full((N, NJ), np.nan)
    exe = np.full((N, NJ, 5), np.nan)            # 检查点 j 决策在 τ_j+5 的成交状态（j>=1）；j=0 为入场状态
    last_state = np.full((N, 5), np.nan)
    tokk = np.full((N, NJ), np.nan); feebk = np.full((N, NJ), np.nan); pmb = np.full((N, NJ), np.nan); rt_buy = np.full((N, NJ), np.nan)
    closed = np.zeros((N, NJ, NJ, 2), bool); cval = np.full((N, NJ, NJ, 2), np.nan); ctime = np.full((N, NJ, NJ, 2), np.nan)
    open70 = np.zeros((N, NJ, NJ), bool)          # open70[i,k,j]：origin k 在 j 时于 70% 路径下仍持有
    term = np.full((N, NJ), np.nan); sv_exec = np.full((N, NJ, NJ), np.nan)  # sv_exec[i,j,k]
    peak_hold = np.full((N, NJ, NJ), np.nan); x0 = np.zeros(N); b50p = np.zeros(N); unval = 0
    fcols = ["f_pm", "f_runmax", "f_newb30", "f_trades30", "f_trades30_prev", "f_buy30", "f_sell30", "f_nb_sell30", "f_ins_exit", "f_maxpm"]

    for m, g in P.groupby("mint", sort=False):
        i = idx[m]; rows = {int(r.iv): r for r in g.itertuples(index=False)}
        r0 = rows[0]; x0[i] = r0.l_x; px0 = r0.l_x / r0.l_y
        # 信息状态与成交状态
        cur = None
        for j in range(NJ):
            if j in rows: cur = rows[j]
            info[i, j] = [getattr(cur, "l_" + c) for c in ST]; info_last[i, j] = cur.last_dt
            info_f[i, j] = [getattr(cur, c) for c in fcols]
        exe[i, 0] = info[i, 0]
        for j in range(1, NJ):
            nb = rows.get(j + 1)
            exe[i, j] = [getattr(nb, "e_" + c) for c in ST] if (nb is not None and not pd.isna(nb.e_x)) else info[i, j]
        lb = rows[max(rows)]; last_state[i] = [getattr(lb, "l_" + c) for c in ST]
        maxpm = {b: rows[b].f_maxpm for b in rows}
        firsts = {b: rows[b].first_dt for b in rows}
        # 解析沉寂行与新仓位触发
        dead = []
        for b in rows:
            s = rows[b].dead_rows
            if isinstance(s, str) and s:
                for seg in s.split(";"):
                    d = seg.split(","); dead.append((float(d[0]), b, [float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])]))
        dead.sort()
        trig = {}
        for b in rows:
            s = rows[b].trig_new
            if isinstance(s, str) and s:
                for seg in s.split(";"):
                    k, sm, dt, v = seg.split(","); k = int(k); sm = int(sm); v = float(v)
                    if v < 0: unval += 1; v = 0.0
                    trig[(k, 0 if sm == 50 else 1, b)] = (float(dt), v)
        # 各 origin 的买入
        for k in range(NJ):
            st = exe[i, k]
            tokk[i, k] = buy_tok(st[0], st[1], st[4]); feebk[i, k] = st[4]
            pmb[i, k] = (st[0] / st[1]) / px0
            rt_buy[i, k] = sell_ratio(*st, tokk[i, k], st[4])
            term[i, k] = sell_ratio(*last_state[i], tokk[i, k], feebk[i, k])
            for j in range(k + 1, NJ):
                sv_exec[i, j, k] = sell_ratio(*exe[i, j], tokk[i, k], feebk[i, k])
                pk = pmb[i, k] if k else 1.0
                pk = max([pk] + [maxpm[b] for b in range(k + 1, j + 1) if b in maxpm and not pd.isna(maxpm[b])])
                peak_hold[i, j, k] = info_f[i, j, 1] if k == 0 else pk
        # 区间事件：origin k、区间 j（检查点 j → j+1，对应面板区间 j+1；k=0 的区间 0 另含 iv0 的入场行沉寂）
        for k in range(NJ):
            t_buy = 0.0 if k == 0 else TAUS[k] + 5
            special = None
            if k >= 1:
                nb = rows.get(k + 1)
                nxt = nb.first_after5_dt if (nb is not None and not pd.isna(nb.first_after5_dt)) else np.nan
                if pd.isna(nxt):
                    later = [firsts[b] for b in rows if b > k + 1]
                    nxt = min(later) if later else T_END
                if nxt - t_buy > CFG["inactivity_s"]:
                    special = (t_buy, sell_ratio(*exe[i, k], tokk[i, k], feebk[i, k]))
            alive70 = True
            for j in range(k, NJ):
                bset = [0, 1] if (k == 0 and j == 0) else [j + 1]
                # 沉寂候选（与止损模式无关）：(行时点, 回收, 实际离场时点)
                dc = None
                if special is not None and j == k:
                    dc = (special[0], special[1], special[0] + CFG["inactivity_s"])
                else:
                    for dt, b, stt in dead:
                        if b in bset and (k == 0 or dt > t_buy):
                            v = float(rows[b].dead_sm) if k == 0 else float(sell_ratio(*stt, tokk[i, k], feebk[i, k]))
                            dc = (dt, v, dt + CFG["inactivity_s"])
                            break
                # 每个区间独立记录"若本区间以模式 s 持有"的首个事件（策略可在检查点切换模式）
                for s in (0, 1):
                    tc = None
                    if k == 0:
                        rb = rows.get(j + 1)
                        col_dt, col_v = ("t50_dt", "t50_v") if s == 0 else ("t70_dt", "t70_v")
                        if rb is not None and not pd.isna(getattr(rb, col_dt)):
                            tc = (float(getattr(rb, col_dt)), float(getattr(rb, col_v)))
                    else:
                        tc = trig.get((k, s, j + 1))
                    ev = None
                    if tc is not None and (dc is None or tc[0] <= dc[0]):
                        ev = (tc[1], tc[0])
                    elif dc is not None:
                        ev = (dc[1], dc[2])
                    if ev is not None:
                        closed[i, k, j, s] = True; cval[i, k, j, s] = ev[0]; ctime[i, k, j, s] = min(ev[1], T_END)
                if closed[i, k, j, 1]:
                    alive70 = False
                if j + 1 < NJ:
                    open70[i, k, j + 1] = alive70
            if k == 0:
                open70[i, 0, 0] = True
        # 面板 b50（Gate 1 口径）
        b50p[i] = cval[i, 0, :, 0][closed[i, 0, :, 0]][0] if closed[i, 0, :, 0].any() else term[i, 0]
    for k in range(NJ):
        open70[:, k, k] = True

    # 特征（市场状态部分，按检查点 j）
    fresh = (TAUS[None, :] - info_last) <= 1800
    f = info_f
    tot30 = np.nan_to_num(f[..., 5]) + np.nan_to_num(f[..., 6])
    feat = {
        "f1": np.log(f[..., 0]),
        "f2flat": np.log(f[..., 0] / f[..., 1]),
        "f3": np.where(fresh, np.log1p(np.nan_to_num(f[..., 2])), 0),
        "f4": np.where(fresh, np.log1p(np.nan_to_num(f[..., 3])), 0),
        "f5": np.where(fresh, np.log1p(np.nan_to_num(f[..., 4])), 0),
        "f6": np.where(fresh, np.where(tot30 > 0, np.nan_to_num(f[..., 5]) / np.where(tot30 > 0, tot30, 1), 0.5), 0),
        "f7": np.where(fresh, np.log1p(tot30), 0),
        "f8": np.clip(np.nan_to_num(f[..., 8]), -1, 2),
        "f9": np.where(fresh, np.where(np.nan_to_num(f[..., 6]) > 0, np.nan_to_num(f[..., 7]) / np.where(np.nan_to_num(f[..., 6]) > 0, f[..., 6], 1), 0), 0),
        "f10": (info[..., 3] == 1).astype(float),
        "f11": np.log1p(np.maximum(TAUS[None, :] - info_last, 0)),
    }
    tok_info = buy_tok(info[..., 0], info[..., 1], info[..., 4])
    rt_info = sell_ratio(info[..., 0], info[..., 1], info[..., 2], info[..., 3], info[..., 4], tok_info, info[..., 4])
    feat["f16"] = 1 - rt_info
    p2 = ((x0 >= 59.1866) & (devp <= 11)).astype(float)
    static = np.stack([np.log(x0), np.log1p(devp), np.log1p(np.maximum(nsol, 0)), p2], axis=1)  # f12..f15
    folds = np.array([int(hashlib.sha256(m.encode()).hexdigest()[:8], 16) % 5 for m in mints])
    return dict(w=w, mints=mints, N=N, closed=closed, cval=cval, ctime=ctime, open70=open70, term=term, sv_exec=sv_exec,
                peak_hold=peak_hold, pmb=pmb, rt_buy=rt_buy, feat=feat, static=static, p2=p2.astype(bool), folds=folds,
                b50=b50p, miss_entry=miss_entry, unvalued=unval, info_pm=f[..., 0])


def X_of(D, j, state, k=None, quad=False):
    F = D["feat"]; N = D["N"]
    f2 = F["f2flat"][:, j] if state == "flat" else np.log(D["info_pm"][:, j] / D["peak_hold"][:, j, k])
    cols = [F["f1"][:, j], f2] + [F[c][:, j] for c in ("f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11")] + [D["static"][:, q] for q in range(4)] + [F["f16"][:, j]]
    X = np.stack(cols, axis=1)
    if quad:
        a, b, c = X[:, 0], X[:, 1], X[:, 2]
        X = np.concatenate([X, np.stack([a * a, b * b, c * c, a * b, a * c, b * c], axis=1)], axis=1)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


# ---------------- 岭回归 ----------------
def ridge_fit(X, y):
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1
    Z = (X - mu) / sd; ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + ALPHA * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return (mu, sd, ym, beta)


def ridge_pred(M, X):
    mu, sd, ym, beta = M
    return ym + ((X - mu) / sd) @ beta


def fit_predict(Xs, ys, folds, mode, models, key):
    """mode='fit'：OOF 预测 + 全样本模型存入 models[key]；mode='apply'：用 models[key] 预测。"""
    if mode == "apply":
        return ridge_pred(models[key], Xs) if key in models else np.full(len(Xs), -np.inf)
    pred = np.full(len(Xs), -np.inf)
    ok = np.isfinite(ys)
    if ok.sum() < 50:
        return pred
    for fo in range(5):
        tr = ok & (folds != fo); te = folds == fo
        if tr.sum() >= 50 and te.any():
            pred[te] = ridge_pred(ridge_fit(Xs[tr], ys[tr]), Xs[te])
    models[key] = ridge_fit(Xs[ok], ys[ok])
    return pred


# ---------------- 逆向动态规划 ----------------
def run_S1(D, mode, models, quad=False):
    N = D["N"]; cl, cv = D["closed"], D["cval"]
    W = np.zeros((N, NJ + 1)); W[:, NJ] = D["term"][:, 0]; act = np.zeros((N, NJ), int)
    for j in range(NJ - 1, -1, -1):
        G = [np.where(cl[:, 0, j, s], cv[:, 0, j, s], W[:, j + 1]) for s in (0, 1)]
        if j >= 1:
            sell = D["sv_exec"][:, j, 0]
            X = X_of(D, j, "hold", 0, quad); smp = D["open70"][:, 0, j]
            preds = []
            for s in (0, 1):
                if mode == "oracle":
                    preds.append((G[s] - sell) / sell); continue
                y = np.where(smp, (G[s] - sell) / sell, np.nan)
                preds.append(fit_predict(X, y, D["folds"], mode, models, ("S1", j, s, quad)))
            choice = np.argmax(np.stack([np.zeros(N)] + preds, 1), 1)
            W[:, j] = np.choose(choice, [sell, G[0], G[1]]); act[:, j] = choice
        else:
            X = X_of(D, 0, "hold", 0, quad)
            if mode == "oracle":
                preds = [G[0], G[1]]
            else:
                preds = [fit_predict(X, G[s], D["folds"], mode, models, ("S1", 0, s, quad)) for s in (0, 1)]
            choice = np.argmax(np.stack(preds, 1), 1)
            W[:, 0] = np.choose(choice, G); act[:, 0] = choice + 1
    return W[:, 0] - C, act


def run_S2(D, mode, models, quad=False):
    N = D["N"]; cl, cv = D["closed"], D["cval"]
    Wf = np.zeros((N, NJ + 1)); Wh = np.full((N, NJ + 1, NJ), np.nan); Wh[:, NJ, :] = D["term"]
    act_h = np.zeros((N, NJ, NJ), int); act_f = np.zeros((N, NJ), int)
    for j in range(NJ - 1, -1, -1):
        # 持仓（origin k < j）
        if j >= 1:
            Xs, Ys, Fo, meta = [[], []], [[], []], [], []
            G_all = {}
            for k in range(j):
                sellv = D["sv_exec"][:, j, k]
                G = [np.where(cl[:, k, j, s], cv[:, k, j, s] + Wf[:, j + 1], Wh[:, j + 1, k]) for s in (0, 1)]
                G_all[k] = (G, sellv)
                X = X_of(D, j, "hold", k, quad); smp = D["open70"][:, k, j]
                for s in (0, 1):
                    Xs[s].append(X); Ys[s].append(np.where(smp, (G[s] - (sellv + Wf[:, j + 1])) / sellv, np.nan))
                Fo.append(D["folds"])
            Xc = np.concatenate(Xs[0]); Fc = np.concatenate(Fo)
            preds = []
            for s in (0, 1):
                yc = np.concatenate(Ys[s])
                if mode == "oracle":
                    preds.append(yc)
                else:
                    preds.append(fit_predict(Xc, yc, Fc, mode, models, ("S2h", j, s, quad)))
            for k in range(j):
                G, sellv = G_all[k]
                sl = slice(k * N, (k + 1) * N)
                p0, p1 = preds[0][sl], preds[1][sl]
                if mode == "oracle":
                    p0 = (G[0] - (sellv + Wf[:, j + 1])) / sellv; p1 = (G[1] - (sellv + Wf[:, j + 1])) / sellv
                choice = np.argmax(np.stack([np.zeros(N), np.nan_to_num(p0, nan=-np.inf), np.nan_to_num(p1, nan=-np.inf)], 1), 1)
                Wh[:, j, k] = np.choose(choice, [sellv + Wf[:, j + 1], G[0], G[1]]); act_h[:, j, k] = choice
        # 空仓买入（origin j）
        Gb = [np.where(cl[:, j, j, s], cv[:, j, j, s] + Wf[:, j + 1], Wh[:, j + 1, j]) - 1 - C for s in (0, 1)]
        X = X_of(D, j, "flat", None, quad)
        if mode == "oracle":
            pb = [Gb[s] - Wf[:, j + 1] for s in (0, 1)]
        else:
            pb = [fit_predict(X, Gb[s] - Wf[:, j + 1], D["folds"], mode, models, ("S2f", j, s, quad)) for s in (0, 1)]
        choice = np.argmax(np.stack([np.zeros(N), pb[0], pb[1]], 1), 1)
        Wf[:, j] = np.choose(choice, [Wf[:, j + 1], Gb[0], Gb[1]]); act_f[:, j] = choice
    return 1 + Wf[:, 0], act_h, act_f


# ---------------- 前向模拟（行为统计 + 与逆向值核对）----------------
def forward(D, space, act):
    N = D["N"]; cl, cv, ct = D["closed"], D["cval"], D["ctime"]
    val = np.ones(N) if space == "S2" else np.zeros(N)
    hold = np.zeros(N, bool); org = np.zeros(N, int); mode = np.zeros(N, int); tb = np.zeros(N)
    nbuy = np.zeros(N, int); first = np.full(N, -1); htime = np.zeros(N); impact = np.zeros(N)
    acts_rec = np.zeros((N, NJ), int) - 1
    if space == "S1":
        hold[:] = True; nbuy[:] = 1; first[:] = 0; impact += 1 - D["rt_buy"][:, 0]
    for j in range(NJ):
        sold_now = np.zeros(N, bool)
        if space == "S1":
            a = act[:, j]
        else:
            a = act[0][np.arange(N), j, org]
        # 已持仓（origin < j）
        h = hold & (org < j) if space == "S2" else hold & (j >= 1)
        sell = h & (a == 0)
        sv = D["sv_exec"][np.arange(N), j, org]
        val[sell] += sv[sell] - (1 + C if space == "S2" else 0) ; htime[sell] += TAUS[j] + 5 - tb[sell]
        hold[sell] = False; sold_now |= sell
        keep = h & (a > 0); mode[keep] = a[keep] - 1; acts_rec[h, j] = a[h]
        if space == "S1" and j == 0:
            mode[:] = act[:, 0] - 1; acts_rec[:, 0] = act[:, 0]
        # 空仓买入
        if space == "S2":
            fl = ~hold & ~sold_now; af = act[1][:, j]; buy = fl & (af > 0)
            hold[buy] = True; org[buy] = j; mode[buy] = af[buy] - 1; tb[buy] = 0 if j == 0 else TAUS[j] + 5
            nbuy[buy] += 1; first[buy & (first < 0)] = j; impact[buy] += 1 - D["rt_buy"][buy, j]
        # 区间事件
        hh = np.where(hold)[0]
        if len(hh):
            c = cl[hh, org[hh], j, mode[hh]]
            ids = hh[c]
            v = cv[ids, org[ids], j, mode[ids]]
            val[ids] += v - (1 + C if space == "S2" else 0)
            htime[ids] += ct[ids, org[ids], j, mode[ids]] - tb[ids]
            hold[ids] = False
    rem = np.where(hold)[0]
    val[rem] += D["term"][rem, org[rem]] - (1 + C if space == "S2" else 0); htime[rem] += T_END - tb[rem]
    if space == "S1":
        val -= C
    return dict(val=val, nbuy=nbuy, first=first, htime=htime, impact=impact, acts=acts_rec)


# ---------------- 报告工具 ----------------
def boot_q(d, q, B=2000, seed=20260917):
    rng = np.random.default_rng(seed); n = len(d)
    means = np.array([d[rng.integers(0, n, n)].mean() for _ in range(B)])
    return float(np.quantile(means, q))


def summarize(D, V_pol, V_or, fw, label, sub=None):
    m = np.ones(D["N"], bool) if sub is None else sub
    b = D["b50"][m] - C; p = V_pol[m]; o = V_or[m]; d = p - b
    gap = o.mean() - b.mean(); delta = d.mean()
    order = np.argsort(-np.abs(d))
    out = dict(label=label, n=int(m.sum()), V_b50=float(b.mean()), V_oracle=float(o.mean()), V_policy=float(p.mean()),
               oracle_gap=float(gap), policy_delta=float(delta), capture=float(delta / gap) if abs(gap) > 1e-12 else None,
               delta_boot_p10=boot_q(d, 0.10), delta_boot_p05=boot_q(d, 0.05),
               delta_drop_top1=float(np.delete(d, order[:1]).mean()), delta_drop_top5=float(np.delete(d, order[:5]).mean()),
               delta_drop_top10=float(np.delete(d, order[:10]).mean()),
               top10_contrib=float(d[order[:10]].sum() / len(d)),
               round_trips_per_opp=float(fw["nbuy"][m].mean()), gross_notional_sol=float(0.5 * fw["nbuy"][m].sum()),
               extra_cost_total=float(C * fw["nbuy"][m].sum()), self_impact_mean_per_buy=float(fw["impact"][m].sum() / max(fw["nbuy"][m].sum(), 1)),
               hold_hours_mean=float(fw["htime"][m].mean() / 3600))
    return out


def behavior(D, fw, space, V_pol, sub=None):
    m = np.ones(D["N"], bool) if sub is None else sub
    d = (V_pol - (D["b50"] - C))[m]; out = {}
    acts = fw["acts"][m]
    out["actions_by_checkpoint"] = {int(j): {n: int((acts[:, j] == a).sum()) for a, n in ((0, "exit"), (1, "hold50"), (2, "hold70"))} for j in range(NJ)}
    if space == "S2":
        fe = fw["first"][m]; nb = fw["nbuy"][m]
        out["first_entry_dist"] = {("never" if k < 0 else int(k)): int((fe == k).sum()) for k in sorted(set(fe.tolist()))}
        out["delta_contrib_by_first_entry"] = {("never" if k < 0 else int(k)): float(d[fe == k].sum() / len(d)) for k in sorted(set(fe.tolist()))}
        out["delta_contrib_by_n_buys"] = {int(k) if k < 3 else "3+": float(d[(nb == k) if k < 3 else (nb >= 3)].sum() / len(d)) for k in (0, 1, 2, 3)}
        out["buys_dist"] = {int(k): int((nb == k).sum()) for k in sorted(set(nb.tolist()))}
    return out


def check_consistency(D, name, V, fw):
    diff = np.abs(fw["val"] - V)
    return {"space": name, "max_abs_forward_vs_backward": float(np.nanmax(diff)), "n_gt_1e-6": int((diff > 1e-6).sum())}


def dev_mode():
    A = load_week("A")
    rep = {"week": "A", "N": A["N"], "missing_entry_features": A["miss_entry"], "unvalued_triggers": A["unvalued"]}
    F2 = pd.read_csv(WEEKS["A"][1], low_memory=False); F2 = F2[F2.mint != "__SUMMARY__"].set_index("mint")
    ref = pd.to_numeric(F2.b50, errors="coerce").reindex(A["mints"]).to_numpy()
    ok = np.isfinite(ref)
    rep["b50_tensor_vs_F2"] = {"match_rate": float((np.abs(A["b50"][ok] - ref[ok]) <= 1e-5).mean()), "mean_diff": float(A["b50"][ok].mean() - ref[ok].mean())}
    models = {}
    for space in ("S1", "S2"):
        if space == "S1":
            Vo, _ = run_S1(A, "oracle", {}); Vp, act = run_S1(A, "fit", models); fw = forward(A, "S1", act)
            fwo = forward(A, "S1", run_S1(A, "oracle", {})[1])
        else:
            Vo, aho, afo = run_S2(A, "oracle", {}); Vp, ah, af = run_S2(A, "fit", models); fw = forward(A, "S2", (ah, af))
            fwo = forward(A, "S2", (aho, afo))
        rep[f"{space}_consistency_policy"] = check_consistency(A, space, Vp, fw)
        rep[f"{space}_consistency_oracle"] = check_consistency(A, space, Vo, fwo)
        rep[f"{space}_A_crossfit_P0"] = summarize(A, Vp, Vo, fw, f"{space} A 内交叉拟合（描述）")
    (H / "results/dev_A_crossfit.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def final_mode():
    A = load_week("A"); B = load_week("B")
    R = {"missing_entry_features": {"A": A["miss_entry"], "B": B["miss_entry"]}, "unvalued_triggers": {"A": A["unvalued"], "B": B["unvalued"]}}
    res = {}
    for space in ("S1", "S2"):
        for quad in (False, True):
            tag = f"{space}{'_quad' if quad else ''}"
            out = {}
            for tr, te in (("A", "B"), ("B", "A")):
                Dtr, Dte = (A, B) if tr == "A" else (B, A)
                models = {}
                if space == "S1":
                    run_S1(Dtr, "fit", models, quad); Vp, act = run_S1(Dte, "apply", models, quad); fw = forward(Dte, "S1", act)
                    Vo, _ = run_S1(Dte, "oracle", {})
                else:
                    run_S2(Dtr, "fit", models, quad); Vp, ah, af = run_S2(Dte, "apply", models, quad); fw = forward(Dte, "S2", (ah, af))
                    Vo = run_S2(Dte, "oracle", {})[0]
                cons = check_consistency(Dte, space, Vp, fw)
                out[f"{tr}->{te}"] = {"P0": summarize(Dte, Vp, Vo, fw, f"{tag} {tr}→{te} P0"),
                                      "P2": summarize(Dte, Vp, Vo, fw, f"{tag} {tr}→{te} P2", Dte["p2"]),
                                      "behavior_P0": behavior(Dte, fw, space, Vp), "behavior_P2": behavior(Dte, fw, space, Vp, Dte["p2"]),
                                      "consistency": cons}
                if not quad and tr == "A":
                    d = Vp[Dte["p2"]] - (Dte["b50"][Dte["p2"]] - C); o = np.argsort(-d)
                    out[f"{tr}->{te}"]["P2_delta_drop_top1_positive"] = float(np.delete(d, o[:1]).mean())
            res[tag] = out
    G = {}
    for space in ("S1", "S2"):
        ab = res[space]["A->B"]; ba = res[space]["B->A"]
        c1 = ab["P0"]["policy_delta"] >= 0.03; c2 = ab["P0"]["delta_boot_p10"] > 0; c3 = ba["P0"]["policy_delta"] > 0
        n = int(c1) + int(c2) + int(c3)
        border = (0.015 <= ab["P0"]["policy_delta"] < 0.03) or n == 2
        anomaly = (not (c1 and c2 and c3)) and ab["P2"]["policy_delta"] >= 0.10 and ab["P2_delta_drop_top1_positive"] > 0
        G[space] = dict(cond1=c1, cond2=c2, cond3=c3, PASS_DEVELOPMENT=bool(c1 and c2 and c3), borderline=bool(border and not (c1 and c2 and c3)), p2_anomaly=bool(anomaly),
                        AtoB_delta=ab["P0"]["policy_delta"], B_boot_p10=ab["P0"]["delta_boot_p10"], BtoA_delta=ba["P0"]["policy_delta"])
    passed = [s for s in ("S1", "S2") if G[s]["PASS_DEVELOPMENT"]]
    if len(passed) == 2:
        d1, d2 = G["S1"]["AtoB_delta"], G["S2"]["AtoB_delta"]
        primary = "S1" if abs(d1 - d2) < 0.01 else ("S1" if d1 > d2 else "S2")
    else:
        primary = passed[0] if passed else None
    G["confirmatory_primary"] = primary
    if passed:
        G["route"] = "P0 PASS → 见卡片第十节（按 P2 结果决定 DQ-8B 或确认卡）"
    elif any(G[s]["p2_anomaly"] for s in ("S1", "S2")):
        G["route"] = "P0 FAIL 但触发 P2 anomaly → DQ-8B / P2 异质性调查"
    elif any(G[s]["borderline"] for s in ("S1", "S2")):
        G["route"] = "临界 → 可触发 DQ-8B，封存周不碰"
    else:
        G["route"] = "P0 FAIL 且无 P2 anomaly → STOP 当前 pump +30m 动态决策路线，转 BSC G0"
    R["results"] = res; R["gates"] = G
    (H / "results/final_dq8a.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))
    print(json.dumps(G, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"dev": dev_mode, "final": final_mode}[sys.argv[1]]()

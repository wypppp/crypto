"""DQ-21 R0：由早买名单与 Helius 走查构造钱包出资状态、主出资方与 V1–V3（README v1.2 §3、§4、§8）。不看收益。

python build_r0.py r0a [--K 30] [--services services.csv]
输出 results/{stage}_wallets.csv（每个早买者/创建者一行）、results/{stage}_coins.csv（每币一行）、
     results/{stage}_inflows.csv.gz（全部流入记录，供抽查）、results/{stage}_summary.json。
services.csv（可选）：address,class（strict = 已知标签；lenient = 画像为服务型），缺省时服务集合为空。
"""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

import flows as F

H = Path(__file__).resolve().parent
RAW = H / "raw" / "helius"
WEEK = 7 * 86400
PRICE0 = 30 / 1.073e9          # pump 曲线初始价格（SOL/枚，按初始虚拟储备 30 SOL、10.73 亿枚）


def load_walk(key, reuse):
    """走查的完整交易；有续翻（__ext，R0a 中 P=3 截断后续翻到 P）时合并，按签名去重。"""
    k = reuse.get(key, key)
    f = RAW / f"{k}.jsonl.gz"
    if not f.exists():
        return None
    txs = [json.loads(l) for l in gzip.open(f, "rt")]
    fe = RAW / f"{k}__ext.jsonl.gz"
    if fe.exists():
        seen = {x["transaction"]["signatures"][0] for x in txs}
        txs += [x for x in (json.loads(l) for l in gzip.open(fe, "rt")) if x["transaction"]["signatures"][0] not in seen]
    return txs


def walk_meta(idx, key, reuse):
    """走查的页数与是否翻完（有续翻时以续翻为准，页数相加）。"""
    k = reuse.get(key, key)
    if k not in idx.index:
        return None
    m = idx.loc[k].to_dict()
    if f"{k}__ext" in idx.index:
        e = idx.loc[f"{k}__ext"]
        m["complete"], m["pages"], m["n_tx"] = e["complete"], m["pages"] + e["pages"], m["n_tx"] + e["n_tx"]
    return m


def before_anchor(txs, slot, txi, sig, gte):
    """锚点交易及之前（同 slot 只取交易序号不大于锚点的），且不早于 gte。"""
    out = []
    for x in txs:
        ts = x.get("blockTime") or 0
        if ts < gte:
            continue
        if x["slot"] < slot or x["transaction"]["signatures"][0] == sig or (
                x["slot"] == slot and txi is not None and x.get("transactionIndex") is not None
                and x["transactionIndex"] <= txi):
            out.append(x)
    return out


def wallet_record(W, txs, meta, gte):
    inf, lk = [], []
    for x in txs:
        a, b = F.wallet_flows(x, W)
        inf += a
        lk += b
    return inf, lk


def primary_funder(inf, services):
    u = [r for r in inf if r["status"] == "unique"]
    if not u:
        return None, 0.0
    agg = {}
    for r in u:
        a = agg.setdefault(r["source"], [0, 0])
        a[0] += r["amount"]
        a[1] = max(a[1], r["ts"] or 0)
    ns = {s: v for s, v in agg.items() if s not in services}
    if not ns:
        return "service", sum(v[0] for v in agg.values()) / 1e9
    s = max(ns, key=lambda k: (ns[k][0], ns[k][1]))
    return s, ns[s][0] / 1e9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["r0a", "r0b", "all"])
    ap.add_argument("--K", type=int, default=30)
    ap.add_argument("--services", default=None)
    a = ap.parse_args()
    services = {}
    if a.services:
        sv = pd.read_csv(H / a.services)
        services = {"strict": set(sv[sv["class"] == "strict"].address),
                    "lenient": set(sv.address)}
    else:
        services = {"strict": set(), "lenient": set()}
    S = pd.read_csv(H / "sample.csv")
    coins = {"r0a": S[S.r0a], "r0b": S[~S.r0a], "all": S}[a.stage].mint.unique()
    q = pd.read_csv(H / "raw" / "dune" / "Q_buyers.csv.gz")
    q["t"] = pd.to_datetime(q.ts).astype("int64") // 10**9
    idx = pd.read_csv(H / "raw" / "helius_index.csv").set_index("key")
    rf = H / "raw" / "helius_reuse.csv"
    reuse = dict(pd.read_csv(rf)[["key", "reused_from"]].values) if rf.exists() else {}

    W_rows, C_rows, all_inf = [], [], []
    for mint in coins:
        c = q[(q.kind == "create") & (q.mint == mint)].iloc[0]
        C, t0 = c.usr, int(c.t)
        t_dec = t0 + 1800
        allb = q[(q.kind == "buy") & (q.mint == mint)]
        b = allb[allb.buyer_rank <= a.K].sort_values("buyer_rank")
        # 创建者：往前 7 天与创建后 30 分钟
        kb, kf = f"back__{C}__{t0}", f"fwd__{C}__{t0}"
        cb = load_walk(kb, reuse)
        cf = load_walk(kf, reuse)
        c_inf, c_lk = wallet_record(C, before_anchor(cb or [], int(c.slot), None, c.tx_id, t0 - WEEK), None, None)
        f_inf, f_lk = wallet_record(C, [x for x in (cf or []) if t0 <= (x.get("blockTime") or 0) < t_dec], None, None)
        for r in c_inf:
            all_inf.append({**r, "W": C, "mint": mint, "role": "creator"})
        c_meta = walk_meta(idx, kb, reuse)
        c_complete = c_meta is not None and str(c_meta["complete"]) == "True"
        # 创建者主出资方：主口径只在 7 天窗口翻完时成立；obs 为观察到的窗口内
        pf_c = {}
        for m in services:
            p = primary_funder(c_inf, services[m])[0]
            pf_c[m] = p if c_complete else None
            pf_c["obs_" + m] = p
        c_links = {(l["cp"], l["ts"]) for l in c_lk + f_lk} | {(r["source"], r["ts"]) for r in c_inf + f_inf}
        wrows = []
        for r in b.itertuples():
            key = f"back__{r.usr}__{int(r.t)}"
            txs = load_walk(key, reuse)
            m = walk_meta(idx, key, reuse)
            if txs is None:
                wrows.append({"mint": mint, "W": r.usr, "rank": r.buyer_rank, "sol": r.sol_amt, "t_buy": int(r.t),
                              "status": "not_fetched"})
                continue
            win = before_anchor(txs, int(r.slot), int(r.txi) if pd.notna(r.txi) else None, r.tx_id, int(r.t) - WEEK)
            inf, lk = wallet_record(r.usr, win, m, int(r.t) - WEEK)
            for x in inf:
                all_inf.append({**x, "W": r.usr, "mint": mint, "role": "buyer"})
            complete = str(m["complete"]) == "True" if m is not None else False
            u = [x for x in inf if x["status"] == "unique"]
            # 状态（09-27 复核后）：窗口是否翻完 × 是否看到唯一可归因来源；程序账户买家单列
            if not F.on_curve(r.usr):
                status, u = "program_account", []
            elif complete:
                status = "resolved_complete" if u else ("nonunique_complete" if inf else "no_inflow_complete")
            else:
                status = "partial_with_candidate" if u else "partial_no_candidate"
            # 与创建者的直接往来是观察到的事实，截断窗口里看到的也算
            direct = [l for l in lk if l["cp"] == C] + [x for x in u if x["source"] == C]
            post = [ts for (cp, ts) in c_links if cp == r.usr and ts is not None and ts < t_dec
                    and ts >= int(r.t) - WEEK]
            link_ts = min([l["ts"] for l in direct if l["ts"]] + post) if (direct or post) else None
            row = {"mint": mint, "W": r.usr, "rank": r.buyer_rank, "sol": r.sol_amt, "t_buy": int(r.t),
                   "price": r.price, "status": status, "walk_complete": complete, "walk_pages": m["pages"] if m is not None else None,
                   "walk_ntx": m["n_tx"] if m is not None else None, "n_inflow": len(inf), "n_unique": len(u),
                   "direct_creator_link": link_ts is not None, "link_ts": link_ts,
                   "evidence_paths": "|".join(sorted({x["evidence"] for x in u}))}
            for mode in services:
                p, amt = primary_funder(u, services[mode]) if status != "program_account" else (None, 0.0)
                row[f"pf_{mode}"], row[f"pf_amt_{mode}"] = (p, amt) if status == "resolved_complete" else (None, 0.0)
                row[f"pf_obs_{mode}"] = p      # 观察到的窗口内（完整或截断），不是 7 天口径
            wrows.append(row)
        Wd = pd.DataFrame(wrows)
        W_rows += wrows
        n_all = len(allb)
        rec = {"mint": mint, "creator": C, "t0": t0, "n_early": n_all, "n_firstK": len(b),
               "applicable": len(b) >= 3,
               "kth_buy_s": int(b.t.max() - t0) if len(b) else None,
               "cov_count": len(b) / n_all if n_all else None,
               "cov_sol": b.sol_amt.sum() / allb.sol_amt.sum() if n_all else None,
               "creator_back_complete": c_complete}
        for k, v in pf_c.items():
            rec[f"creator_pf_{k}"] = v
        if len(Wd) and "pf_strict" in Wd:
            sol_all = Wd.sol.sum()
            for st in ("resolved_complete", "partial_with_candidate", "partial_no_candidate", "no_inflow_complete",
                       "nonunique_complete", "program_account"):
                rec[f"n_{st}"] = int((Wd.status == st).sum())
            res = Wd[Wd.status == "resolved_complete"]
            rec["resolved_sol_share"] = res.sol.sum() / sol_all if sol_all else None
            for var in [m for m in services] + ["obs_" + m for m in services]:
                pf, cpf = Wd[f"pf_{var}"], pf_c[var]
                resolved = Wd[pf.notna()]
                linked = Wd.direct_creator_link | (pf == C) | ((pf == cpf) & pf.notna() & (cpf not in (None, "service")))
                rec[f"V1_{var}"] = Wd.sol[linked].sum() / sol_all if sol_all else 0.0
                rec[f"V1n_{var}"] = int(linked.sum())
                grp = Wd[pf.notna() & (pf != "service")].groupby(f"pf_{var}")
                sizes = grp.size()
                big = sizes[sizes >= 2]
                rec[f"V2_{var}"] = max((grp.get_group(f).sol.sum() for f in big.index), default=0.0) / sol_all if sol_all else 0.0
                rec[f"V2n_{var}"] = int(big.max()) if len(big) else 0
                nsvc = int((pf == "service").sum())
                rec[f"V3_{var}"] = (pf[pf.notna() & (pf != "service")].nunique() + nsvc) / len(resolved) if len(resolved) else np.nan
                rec[f"trigger_{var}"] = bool(rec[f"V1_{var}"] > 0 or rec[f"V2n_{var}"] >= 2)
                # 首次可观察：V1 为关联买家 max(买入, 直接往来) 的最早者；V2 为某主出资方第二个买家的买入时刻；另记当时价格倍数
                tl = [(max(x.t_buy, x.link_ts) if x.direct_creator_link and pd.notna(x.link_ts) else x.t_buy, x.price)
                      for x in Wd[linked].itertuples()]
                rec[f"V1_first_s_{var}"] = min(tl)[0] - t0 if tl else None
                rec[f"V1_first_px_{var}"] = min(tl)[1] / PRICE0 if tl and pd.notna(min(tl)[1]) else None
                t2 = [tuple(grp.get_group(f).sort_values("t_buy")[["t_buy", "price"]].iloc[1]) for f in big.index]
                rec[f"V2_first_s_{var}"] = min(t2)[0] - t0 if t2 else None
                rec[f"V2_first_px_{var}"] = min(t2)[1] / PRICE0 if t2 and pd.notna(min(t2)[1]) else None
            rec["price_mult_at_kth"] = float(b.price.iloc[-1] / PRICE0) if len(b) and pd.notna(b.price.iloc[-1]) else None
        C_rows.append(rec)
    out = H / "results"
    out.mkdir(exist_ok=True)
    pd.DataFrame(W_rows).to_csv(out / f"{a.stage}_wallets.csv", index=False)
    Cd = pd.DataFrame(C_rows)
    Cd.to_csv(out / f"{a.stage}_coins.csv", index=False)
    pd.DataFrame(all_inf).to_csv(out / f"{a.stage}_inflows.csv.gz", index=False)
    keep = ["mint", "n_early", "applicable", "creator_back_complete", "n_resolved_complete", "n_partial_with_candidate",
            "n_partial_no_candidate", "trigger_strict", "V1n_strict", "V2n_strict", "trigger_obs_strict", "V1n_obs_strict", "V2n_obs_strict"]
    print(Cd[[c for c in keep if c in Cd]].to_string(max_colwidth=12))


if __name__ == "__main__":
    main()

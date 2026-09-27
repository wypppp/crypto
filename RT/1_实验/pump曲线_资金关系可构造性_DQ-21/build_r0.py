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
    k = reuse.get(key, key)
    f = RAW / f"{k}.jsonl.gz"
    if not f.exists():
        return None
    return [json.loads(l) for l in gzip.open(f, "rt")]


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
        pf_c = {m: primary_funder(c_inf, services[m])[0] for m in services}
        c_links = {(l["cp"], l["ts"]) for l in c_lk + f_lk} | {(r["source"], r["ts"]) for r in c_inf + f_inf}
        wrows = []
        for r in b.itertuples():
            key = f"back__{r.usr}__{int(r.t)}"
            txs = load_walk(key, reuse)
            m = idx.loc[reuse.get(key, key)] if reuse.get(key, key) in idx.index else None
            if txs is None:
                wrows.append({"mint": mint, "W": r.usr, "rank": r.buyer_rank, "sol": r.sol_amt, "t_buy": int(r.t),
                              "status": "not_fetched"})
                continue
            win = before_anchor(txs, int(r.slot), int(r.txi) if pd.notna(r.txi) else None, r.tx_id, int(r.t) - WEEK)
            inf, lk = wallet_record(r.usr, win, m, int(r.t) - WEEK)
            for x in inf:
                all_inf.append({**x, "W": r.usr, "mint": mint, "role": "buyer"})
            complete = bool(m["complete"]) if m is not None else False
            u = [x for x in inf if x["status"] == "unique"]
            # 优先级：唯一可归因 > 截断（没翻到 7 天前，出资段可能在更早处）> 只有非唯一流入 > 无流入
            status = "resolved" if u else ("truncated" if not complete else ("nonunique_only" if inf else "no_inflow"))
            if not F.on_curve(r.usr):      # 买家本身是程序账户（PDA），出资方无意义
                status, u = "program_account", []
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
                row[f"pf_{mode}"], row[f"pf_amt_{mode}"] = primary_funder(inf, services[mode]) if status != "program_account" else (None, 0.0)
            wrows.append(row)
        Wd = pd.DataFrame(wrows)
        W_rows += wrows
        n_all = len(allb)
        rec = {"mint": mint, "creator": C, "t0": t0, "n_early": n_all, "n_firstK": len(b),
               "applicable": len(b) >= 3,
               "kth_buy_s": int(b.t.max() - t0) if len(b) else None,
               "cov_count": len(b) / n_all if n_all else None,
               "cov_sol": b.sol_amt.sum() / allb.sol_amt.sum() if n_all else None,
               "creator_back_complete": bool(idx.loc[kb, "complete"]) if kb in idx.index else None}
        for mode in services:
            rec[f"creator_pf_{mode}"] = pf_c[mode]
        if len(Wd) and "pf_strict" in Wd:
            sol_all = Wd.sol.sum()
            res = Wd[Wd.status == "resolved"]
            rec["n_resolved"] = len(res)
            rec["resolved_sol_share"] = res.sol.sum() / sol_all if sol_all else None
            for mode in services:
                pf, cpf = Wd[f"pf_{mode}"], pf_c[mode]
                linked = Wd.direct_creator_link | (pf == C) | ((pf == cpf) & pf.notna() & (cpf not in (None, "service")))
                rec[f"V1_{mode}"] = Wd.sol[linked].sum() / sol_all if sol_all else 0.0
                rec[f"V1n_{mode}"] = int(linked.sum())
                grp = Wd[pf.notna() & (pf != "service")].groupby(f"pf_{mode}")
                sizes = grp.size()
                big = sizes[sizes >= 2]
                rec[f"V2_{mode}"] = max((grp.get_group(f).sol.sum() for f in big.index), default=0.0) / sol_all if sol_all else 0.0
                rec[f"V2n_{mode}"] = int(big.max()) if len(big) else 0
                nsvc = int((pf == "service").sum())
                rec[f"V3_{mode}"] = (pf[pf.notna() & (pf != "service")].nunique() + nsvc) / len(res) if len(res) else np.nan
                rec[f"trigger_{mode}"] = bool(rec[f"V1_{mode}"] > 0 or rec[f"V2n_{mode}"] >= 2)
                # 首次可观察：V1 为关联买家的 max(买入, 直接往来) 最早者；V2 为某主出资方第二个买家的买入时刻
                tl = [max(x.t_buy, x.link_ts) if x.direct_creator_link and pd.notna(x.link_ts) else x.t_buy
                      for x in Wd[linked].itertuples()]
                rec[f"V1_first_s_{mode}"] = min(tl) - t0 if tl else None
                t2 = [grp.get_group(f).t_buy.sort_values().iloc[1] for f in big.index]
                rec[f"V2_first_s_{mode}"] = min(t2) - t0 if t2 else None
            rec["price_mult_at_kth"] = float(b.price.iloc[-1] / PRICE0) if len(b) and pd.notna(b.price.iloc[-1]) else None
        C_rows.append(rec)
    out = H / "results"
    out.mkdir(exist_ok=True)
    pd.DataFrame(W_rows).to_csv(out / f"{a.stage}_wallets.csv", index=False)
    Cd = pd.DataFrame(C_rows)
    Cd.to_csv(out / f"{a.stage}_coins.csv", index=False)
    pd.DataFrame(all_inf).to_csv(out / f"{a.stage}_inflows.csv.gz", index=False)
    print(Cd.drop(columns=["creator"]).to_string(max_colwidth=12))


if __name__ == "__main__":
    main()

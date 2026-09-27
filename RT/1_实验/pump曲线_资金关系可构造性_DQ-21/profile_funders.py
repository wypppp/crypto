"""DQ-21 服务节点判定（过程/R0b_预算与门槛.md §3）。

python profile_funders.py --cap 1500
输入：results/all_wallets.csv、results/all_coins.csv（build_r0.py all，服务集合为空时的结果）、
      raw/dune/Q_labels.csv.gz（严格标签，可缺）。
画像对象：严格判定后仍为非服务，且满足任一条：≥2 个早买钱包的主出资方；同时是创建者与 ≥1 个早买者的主出资方；
          样本内为 ≥20 个钱包、跨 ≥5 个币出资。
画像数据：该地址截至它在样本中第一次出资时刻的最近 1 页（100 笔）成功交易。
服务型（宽松）：该页 ≥0.01 SOL 的 SOL/wSOL 转出中，不同接收方 ≥30 个，且最常见金额（0.001 SOL 取整）占比 ≤20%。
输出：services.csv（address,class）、results/service_profiles.csv。
"""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import flows as F
import helius as HL

H = Path(__file__).resolve().parent
RAW = H / "raw" / "helius" / "profile"


def profile(addr, first_ts):
    f = RAW / f"{addr}.jsonl.gz"
    if f.exists():
        txs = [json.loads(l) for l in gzip.open(f, "rt")]
    else:
        r = HL.gtfa(addr, first_ts - 30 * 86400, first_ts + 1, "desc")
        txs = r.get("data", [])
        with gzip.open(f, "wt") as g:
            for x in txs:
                g.write(json.dumps(x) + "\n")
    outs, payer = [], 0
    for x in txs:
        v = F.tx_view(x)
        payer += v["payer"] == addr
        for kind, s, d, amt, mt in F.decode_moves(x, v):
            if s == addr and d != addr and kind in ("sys", "wsol") and amt >= 10_000_000:
                outs.append((d, round(amt / 1e9, 3)))
    rec = Counter(d for d, _ in outs)
    amts = Counter(a for _, a in outs)
    top_share = max(amts.values()) / len(outs) if outs else None
    return {"address": addr, "n_tx": len(txs), "n_out": len(outs), "n_recipients": len(rec),
            "top_amount_share": round(top_share, 3) if top_share is not None else None,
            "payer_share": round(payer / len(txs), 3) if txs else None,
            "service_like": bool(len(rec) >= 30 and top_share is not None and top_share <= 0.2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=1500)
    a = ap.parse_args()
    HL.STATE["cap"] = a.cap
    RAW.mkdir(parents=True, exist_ok=True)
    W = pd.read_csv(H / "results" / "all_wallets.csv")
    C = pd.read_csv(H / "results" / "all_coins.csv")
    I = pd.read_csv(H / "results" / "all_inflows.csv.gz")
    lf = H / "raw" / "dune" / "Q_labels.csv.gz"
    strict = set(pd.read_csv(lf).address) if lf.exists() else set()
    pf = W[W.pf_strict.notna() & (W.pf_strict != "service")]
    n_w = pf.groupby("pf_strict").W.nunique()
    cand = set(n_w[n_w >= 2].index)
    cpf = set(C.creator_pf_strict.dropna()) - {"service"}
    cand |= cpf & set(pf.pf_strict)
    u = I[(I.role == "buyer") & (I.status == "unique")]
    fan = u.groupby("source").agg(nw=("W", "nunique"), nc=("mint", "nunique"))
    cand |= set(fan[(fan.nw >= 20) & (fan.nc >= 5)].index)
    cand -= strict
    first = u.groupby("source").ts.min()
    cfirst = I[(I.role == "creator") & (I.status == "unique")].groupby("source").ts.min()
    rows = []
    for addr in sorted(cand):
        ts = min(x for x in (first.get(addr), cfirst.get(addr)) if pd.notna(x))
        try:
            rows.append(profile(addr, int(ts)))
        except HL.BudgetExceeded:
            rows.append({"address": addr, "error": "budget"})
    P = pd.DataFrame(rows)
    P.to_csv(H / "results" / "service_profiles.csv", index=False)
    sv = [{"address": x, "class": "strict"} for x in sorted(strict)]
    sv += [{"address": r.address, "class": "lenient"} for r in P.itertuples() if getattr(r, "service_like", False) is True]
    pd.DataFrame(sv, columns=["address", "class"]).to_csv(H / "services.csv", index=False)
    print("candidates", len(cand), "strict labels", len(strict), "service_like", int(P.get("service_like", pd.Series()).fillna(False).sum()),
          "calls", HL.STATE["calls"])
    print(P.to_string(max_colwidth=14))


if __name__ == "__main__":
    main()

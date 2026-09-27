"""DQ-21 R0a 通过条件第 1 条：Dune 早买名单与 Helius 解析的买入逐笔一致率 >= 99%。

对每个 R0a 币，用币地址在 [创建, 创建+30 分钟) 的成功交易（fetch_r0.py 的 coin 走查；F101 六币用 H1 本地 full24h）
解码 pump 曲线 TradeEvent 与 pump 迁移池的 BuyEvent，按与 Q_buyers.sql 相同的口径（>=0.1 SOL、非创建者、每个钱包第一笔）
重建早买名单，与 Dune 比较：钱包集合、首笔签名、金额。coin 走查未取完时，只比较已覆盖时段内的买入。

python check_buyers.py → results/r0a_buyer_check.json
"""
import gzip
import json
from pathlib import Path

import pandas as pd

import evt_decode as E

H = Path(__file__).resolve().parent
H1RAW = H.parent / "pump曲线_案例时序与点火跟随_H1" / "raw"


def load_txs(mint, t0):
    f = H1RAW / f"full24h_{mint}.jsonl.gz"
    if f.exists():
        return [json.loads(l) for l in gzip.open(f, "rt")], True, "h1_local"
    if not (H / "raw" / "helius_index.csv").exists():
        return None, False, "missing"
    idx = pd.read_csv(H / "raw" / "helius_index.csv")
    r = idx[(idx.kind == "coin") & (idx.addr == mint)]
    if r.empty:
        return None, False, "missing"
    r = r.iloc[0]
    txs = [json.loads(l) for l in gzip.open(H / "raw" / "helius" / f"{r.key}.jsonl.gz", "rt")]
    return txs, bool(r.complete), "helius"


def helius_buyers(txs, mint, t0, dev):
    pools, rows = set(), []
    for x in txs:
        if x["meta"].get("err"):
            continue
        for e in E.iter_events(x):
            if e["name"] == "CreatePoolEvent" and e["base_mint"] == mint and e["index"] == 0 and e["outer"] == E.PUMP:
                pools.add(e["pool"])
    for x in txs:
        ts = x.get("blockTime")
        if x["meta"].get("err") or ts is None or not (t0 <= ts < t0 + 1800):
            continue
        for e in E.iter_events(x):
            if e["name"] == "TradeEvent" and e["mint"] == mint and e["is_buy"]:
                amt = e["sol_amount"] / 1e9
            elif e["name"] == "BuyEvent" and e["pool"] in pools:
                amt = e["quote_amount_in"] / 1e9
            else:
                continue
            rows.append({"usr": e["user"], "sol": amt, "slot": x["slot"], "txi": x.get("transactionIndex"),
                         "iix": (e["oix"], e["iix"]), "sig": x["transaction"]["signatures"][0], "ts": ts})
    b = pd.DataFrame(rows)
    if b.empty:
        return b
    b = b[(b.sol >= 0.1) & (b.usr != dev)].sort_values(["slot", "txi", "iix"])
    return b.drop_duplicates("usr", keep="first")


def main():
    S = pd.read_csv(H / "sample.csv")
    q = pd.read_csv(H / "raw" / "dune" / "Q_buyers.csv.gz")
    q["t"] = pd.to_datetime(q.ts).astype("int64") // 10**9
    out, tot = [], {"dune": 0, "matched_wallet": 0, "matched_sig": 0, "amount_ok": 0, "helius_only": 0}
    for mint in S[S.r0a].mint.unique():
        c = q[(q.kind == "create") & (q.mint == mint)].iloc[0]
        d = q[(q.kind == "buy") & (q.mint == mint)]
        txs, complete, src = load_txs(mint, c.t)
        if txs is None:
            out.append({"mint": mint, "source": src})
            continue
        hb = helius_buyers(txs, mint, c.t, c.usr)
        hi = max((x.get("blockTime") or 0) for x in txs) if txs else c.t
        dd = d if complete else d[d.t < hi]          # 未取完：只比较已覆盖时段
        hh = hb if complete or hb.empty else hb[hb.ts < hi]
        m = dd.merge(hh, on="usr", how="left", suffixes=("", "_h"))
        rec = {"mint": mint, "source": src, "coin_walk_complete": complete, "dune_n": int(len(d)), "compared_n": int(len(dd)),
               "matched_wallet": int(m.sig.notna().sum()),
               "matched_sig": int((m.tx_id == m.sig).sum()),
               "amount_ok": int(((m.sol_amt - m.sol).abs() < 1e-6).sum()),
               "helius_only": int((~hh.usr.isin(dd.usr)).sum()) if len(hh) else 0}
        out.append(rec)
        tot["dune"] += rec["compared_n"]
        for k in ("matched_wallet", "matched_sig", "amount_ok", "helius_only"):
            tot[k] += rec[k]
    tot["match_rate"] = round((tot["matched_sig"]) / (tot["dune"] + tot["helius_only"]), 4) if tot["dune"] else None
    res = {"by_coin": out, "total": tot, "gate_ge_0.99": (tot["match_rate"] or 0) >= 0.99}
    (H / "results").mkdir(exist_ok=True)
    (H / "results" / "r0a_buyer_check.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res["total"]), "gate", res["gate_ge_0.99"])
    for r in out:
        print(r)


if __name__ == "__main__":
    main()

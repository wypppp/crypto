#!/usr/bin/env python3
"""R1a v3：由早买者名单（raw/dune/R1A_BUYERS.csv.gz）按 S0 v1.3 口径重算 t3、各入场时刻的合格早买者与 Zero 层，
生成 Helius 取数计划。不看收益。

- 排序：(slot, txi, oix, iix)；clock_ts = 按此顺序的时间戳累计最大值（S0 v1.3）。
- 合格早买：买入、≥0.1 SOL、非创建者（创建事件 user）；每个钱包取第一笔合格买入。
- t3 = 第 3 个合格早买者的 clock_ts；与 S1 的 t3_s 逐币核对（不一致即停）。
- 入场时刻 T_d（d = 5、30 秒）：clock_ts ≤ t3 + d 的最后一笔；截至 T_d 的早买者 = 其第一笔合格买入在该笔及之前。
- Zero：与创建同 slot 的合格早买者数 ÷ 截至 T 的合格早买者数；平手依次按创建者自买额（截至 T）降序、mint_hash 升序。
- 取数计划：每币创建者 1 页（锚点 = 创建交易），截至 T30 的前 K=30 个早买者各 1 页（锚点 = 其第一笔合格买入）。

python plan_r1a.py → raw/r1a/r1a_coins_pre.csv（每币）、raw/r1a/r1a_buyers.csv（每币×早买者）、raw/r1a/r1a_fetch_plan.csv
"""

from __future__ import annotations

import pandas as pd

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "raw" / "r1a"
K = 30
DELAYS = (5, 30)


def main() -> None:
    d = pd.read_csv(HERE / "raw" / "dune" / "R1A_BUYERS.csv.gz")
    d["t"] = (
        pd.to_datetime(d.ts.str.replace(" UTC", ""), utc=True).astype("int64") // 10**9
    )
    smp = pd.read_csv(HERE / "r1a_sample.csv")
    cr = d[d.kind == "create"].set_index("mint")
    tr = d[d.kind == "trade"].sort_values(["mint", "slot", "txi", "oix", "iix"])
    coins, buyers, plan = [], [], []
    bad = []
    for s in smp.itertuples():
        c = cr.loc[s.mint]
        dev, t0 = c.usr, int(c.t)
        x = tr[tr.mint == s.mint].reset_index(drop=True)
        x["rn"] = range(len(x))
        x["clock"] = x.t.cummax()
        q = x[
            x.is_buy.astype(bool) & (x.sol_amt >= 0.1) & x.usr.notna() & (x.usr != dev)
        ]
        firstq = q.groupby("usr", sort=False).rn.min().sort_values()
        fq = x.loc[firstq.values].copy()
        if len(fq) < 3:
            bad.append((s.mint, "fewer than 3 qualified"))
            continue
        t3 = int(fq.clock.iloc[2])
        if t3 - t0 != int(s.t3_s):
            bad.append((s.mint, f"t3 {t3 - t0} vs S1 {s.t3_s}"))
        rec = {
            "mint": s.mint,
            "dev": dev,
            "created_slot": int(c.slot),
            "t0": t0,
            "t3_s": t3 - t0,
        }
        for dly in DELAYS:
            e = x[x.clock <= t3 + dly]
            e_rn = int(e.rn.max())
            by_t = fq[fq.rn <= e_rn]
            rec[f"n_q_d{dly}"] = len(by_t)
            rec[f"n_same_slot_d{dly}"] = int((by_t.slot == int(c.slot)).sum())
            rec[f"dev_buy_sol_d{dly}"] = float(
                x[(x.rn <= e_rn) & x.is_buy.astype(bool) & (x.usr == dev)].sol_amt.sum()
            )
            rec[f"zero_d{dly}"] = rec[f"n_same_slot_d{dly}"] / len(by_t)
            rec[f"e_rn_d{dly}"] = e_rn
        coins.append(rec)
        e30 = rec["e_rn_d30"]
        e5 = rec["e_rn_d5"]
        first = fq[fq.rn <= e30].head(K)
        plan.append(
            {
                "mint": s.mint,
                "order": s.order,
                "role": "creator",
                "W": dev,
                "t": t0,
                "slot": int(c.slot),
                "txi": int(c.txi),
                "sig": c.tx_id,
            }
        )
        for rank, b in enumerate(first.itertuples(), 1):
            buyers.append(
                {
                    "mint": s.mint,
                    "W": b.usr,
                    "rank": rank,
                    "sol": b.sol_amt,
                    "t_buy": int(b.t),
                    "slot": int(b.slot),
                    "txi": int(b.txi),
                    "sig": b.tx_id,
                    "by_d5": b.rn <= e5,
                    "same_slot_as_create": int(b.slot) == int(c.slot),
                }
            )
            plan.append(
                {
                    "mint": s.mint,
                    "order": s.order,
                    "role": "buyer",
                    "W": b.usr,
                    "t": int(b.t),
                    "slot": int(b.slot),
                    "txi": int(b.txi),
                    "sig": b.tx_id,
                }
            )
    if bad:
        print("MISMATCH", len(bad), bad[:10])
        raise SystemExit("t3 与 S1 不一致，停止")
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(coins).to_csv(OUT / "r1a_coins_pre.csv", index=False)
    pd.DataFrame(buyers).to_csv(OUT / "r1a_buyers.csv", index=False)
    P = pd.DataFrame(plan)
    P["key"] = P.W + "__" + P.t.astype(str)
    P.to_csv(OUT / "r1a_fetch_plan.csv", index=False)
    C = pd.DataFrame(coins)
    print(
        "coins",
        len(C),
        "buyers",
        len(buyers),
        "plan rows",
        len(P),
        "unique pages",
        P.key.nunique(),
        "n_q_d30 median/p90",
        C.n_q_d30.median(),
        C.n_q_d30.quantile(0.9),
        "capped at K",
        int((C.n_q_d30 > K).sum()),
    )


if __name__ == "__main__":
    main()

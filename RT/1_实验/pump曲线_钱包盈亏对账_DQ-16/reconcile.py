"""DQ-16 §6 (r1): reconcile Dune aggregates (raw/dune/Q1.csv, Q2.csv) against the Helius truth (results/truth_*.csv).

Every comparison is an outer join: a cell missing on either side counts as a mismatch, never drops out.
C1 coverage (signer set, touch set, pump/PumpSwap trade set)  C2 balances (SOL-equivalent total, token deltas)
C3 opening/closing inventory  C4 cost attribution (fees, failed fees, tips; unattributed residual reported)
C5 scope (share of activity in txs that also invoke other DEX programs; reported only).
No PnL ranking, no persistence, no time buckets.
"""
import base64, json, sys
from decimal import Decimal as Dec
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
DUNE = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "raw" / "dune"      # test: mock directory
R = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "results"
sys.path.insert(0, str(HERE))
TOL = 1000
WSOL = "So11111111111111111111111111111111111111112"
NATIVE = "So11111111111111111111111111111111111111111"   # tokens_solana.transfers: native SOL (token_version native)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def pool_mints(pools):
    """PumpSwap Pool account: base_mint at byte offset 43, quote_mint at 75 (checked on Fkt8xV… -> BUvu…/wSOL).
    r3: 355/507 pools on 06-07 have base = wSOL, so map each pool to its non-wSOL side and flag reversed pools."""
    cache = R / "pool_mint2.csv"
    m = pd.read_csv(cache).set_index("pool")[["base", "quote"]].to_dict("index") if cache.exists() else {}
    todo = [p for p in pools if p not in m]
    if todo:
        import helius as H
        for i in range(0, len(todo), 100):
            vals = H.rpc("getMultipleAccounts", [todo[i:i + 100], {"encoding": "base64"}])["value"]
            for p, v in zip(todo[i:i + 100], vals):
                raw = base64.b64decode(v["data"][0]) if v else None
                m[p] = {"base": b58(raw[43:75]) if raw else None, "quote": b58(raw[75:107]) if raw else None}
        pd.DataFrame.from_dict(m, orient="index").rename_axis("pool").to_csv(cache)
    return {p: (d["quote"] if d["base"] == WSOL else d["base"], d["base"] == WSOL) for p, d in m.items()}

def D(x):
    return Dec(str(x)) if pd.notna(x) and str(x) not in ("", "nan", "None") else Dec(0)

def outer(a, b, cols):
    return a.merge(b, how="outer", on=cols, suffixes=("_t", "_d"), indicator=True)

def main():
    tt = pd.read_csv(R / "truth_tx.csv"); tk = pd.read_csv(R / "truth_tok.csv")
    q1 = pd.read_csv(DUNE / "Q1.csv", dtype=str)
    q2 = pd.read_csv(DUNE / "Q2.csv", dtype=str)
    for q in (q1, q2):
        q["k"] = pd.to_numeric(q.k, errors="coerce")
    S = tt[tt.in_signers]
    T = tt[~tt.fee_payer & tt.touched]
    tk = tk.merge(tt[["k", "sig", "ok", "in_signers", "fee_payer", "pump", "amm"]], on=["k", "sig"])
    tk["ui_pre"] = [Dec(int(p)) / (Dec(10) ** int(d)) for p, d in zip(tk.pre_raw, tk.decimals)]
    tk["ui_post"] = [Dec(int(p)) / (Dec(10) ** int(d)) for p, d in zip(tk.post_raw, tk.decimals)]
    out, fails = {}, {}

    # ---- C1 coverage
    a = S.groupby("k").agg(n=("sig", "size"), s_slot=("slot", "sum")).reset_index()
    d = q2[q2.kind == "wal"][["k", "n", "s_slot"]].astype({"n": float, "s_slot": float})
    j = outer(a, d, ["k"]); bad = j[(j.n_t != j.n_d) | (j.s_slot_t != j.s_slot_d)]
    j.to_csv(R / "c1a_signerset.csv", index=False)
    out["C1a 签名交易集合一致的地址"] = f"{len(j) - len(bad)}/{len(j)}"; fails["C1a"] = len(bad)
    a = T.groupby("k").agg(n=("sig", "size"), s_slot=("slot", "sum")).reset_index()
    d = q1[q1.kind == "touchset"][["k", "n", "s_slot"]].astype({"n": float, "s_slot": float})
    j = outer(a, d, ["k"])
    bad = j[(j.n_t.fillna(0) != j.n_d.fillna(0)) | (j.s_slot_t.fillna(0) != j.s_slot_d.fillna(0))]
    j.to_csv(R / "c1b_touchset.csv", index=False)
    out["C1b 他人签名、触及本地址的交易集合一致的地址"] = f"{len(j) - len(bad)}/{len(j)}"; fails["C1b"] = len(bad)
    trade = tk[tk.ok & (tk.pump | tk.amm) & (tk.pre_raw != tk.post_raw)]
    a = trade.groupby(["k", "mint"]).agg(n=("sig", "nunique"), s_slot=("slot", "sum")).reset_index()
    ev = q1[q1.kind == "ev"].copy()
    pm = pool_mints(sorted(ev[ev.v1 == "amm"].key.unique()))
    ev["mint"] = [key if v == "curve" else pm.get(key, (None, False))[0] for key, v in zip(ev.key, ev.v1)]
    ev["reversed"] = [v == "amm" and pm.get(key, (None, False))[1] for key, v in zip(ev.key, ev.v1)]
    # user-side SOL: normal pools use v5 (user quote in/out); base=wSOL pools: wSOL received on buys - paid on sells
    ev["sol"] = [D(b) - D(sl) if r else D(x) for r, b, sl, x in zip(ev.reversed, ev.v3, ev.v4, ev.v5)]
    out["C1c 其中 base=wSOL 的反向池（池数/总池数）"] = f"{sum(r for _, r in pm.values())}/{len(pm)}"
    ev[["n", "s_slot"]] = ev[["n", "s_slot"]].astype(float)
    d = ev.groupby(["k", "mint"]).agg(n=("n", "sum"), s_slot=("s_slot", "sum")).reset_index()
    j = outer(a, d, ["k", "mint"])
    j["bad"] = (j.n_t.fillna(0) != j.n_d.fillna(0)) | (j.s_slot_t.fillna(0) != j.s_slot_d.fillna(0))
    vol = trade.merge(tt[["k", "sig", "F"]], on=["k", "sig"]).assign(v=lambda x: x.F.abs()).groupby(["k", "mint"]).v.sum()
    j = j.merge(vol.rename("vol").reset_index(), on=["k", "mint"], how="left")
    j.to_csv(R / "c1c_trades.csv", index=False)
    share = j[j.bad].vol.sum() / max(j.vol.sum(), 1)
    out["C1c pump/PumpSwap 成交（地址×币）一致"] = f"{(~j.bad).sum()}/{len(j)}"
    out["C1c 不一致格的真值成交额占比"] = round(share, 5); fails["C1c"] = share > 0.01

    # ---- C2 balances
    w = q2[q2.kind == "wal"].set_index("k"); wa = q2[q2.kind == "wacc"].set_index("k")
    tot_d = {k: D(w.v4.get(k)) + D(wa.v1.get(k)) + D(wa.v2.get(k)) for k in set(w.index) | set(wa.index)}
    tot_t = S.groupby("k").F.sum().to_dict()
    ks = sorted(set(tot_d) | set(tot_t) | set(tt.k))
    c2a = pd.DataFrame({"k": ks, "truth": [int(tot_t.get(k, 0)) for k in ks], "dune": [int(tot_d.get(k, 0)) for k in ks]})
    c2a["in_dune"] = [k in tot_d for k in ks]
    c2a["diff"] = c2a.truth - c2a.dune; c2a.to_csv(R / "c2a_sol.csv", index=False)
    okc = (c2a["diff"] == 0) & (c2a.in_dune | (c2a.truth == 0))
    out["C2a 签名交易 SOL 等值总变化一致的地址"] = f"{okc.sum()}/{len(c2a)}"; fails["C2a"] = (~okc).sum()
    ts = tk[tk.in_signers].assign(dui=lambda x: x.ui_post - x.ui_pre).groupby(["k", "mint"]).dui.sum().reset_index()
    wm = q2[q2.kind == "wm"][["k", "key", "v1", "v2", "v3"]].rename(columns={"key": "mint"})
    j = outer(ts, wm, ["k", "mint"])
    j["ok"] = [D(t) == D(dv) and m == "both" for t, dv, m in zip(j.dui, j.v1, j._merge)]
    j.to_csv(R / "c2b_tokens.csv", index=False)
    out["C2b 签名交易代币净变化一致（地址×币）"] = f"{j.ok.sum()}/{len(j)}"; fails["C2b"] = (~j.ok).sum()
    tch = q1[q1.kind == "touch"].copy()
    tch["mint"] = tch.key.str.split("|").str[0]
    tch["net"] = [D(i) - D(o) for i, o in zip(tch.v1, tch.v2)]
    nat = tch[tch.mint.isin(["null", WSOL, NATIVE])].groupby("k").net.sum()
    tt_t = T.groupby("k").F.sum(); ntouch = T.groupby("k").size()
    c2c = pd.DataFrame({"k": ks})
    c2c["truth"] = [int(tt_t.get(k, 0)) for k in ks]
    c2c["dune"] = [int(nat.get(k, Dec(0))) for k in ks]
    c2c["diff"] = c2c.truth - c2c.dune
    c2c["ok"] = [abs(df) <= TOL * max(int(ntouch.get(k, 0)), 1) for k, df in zip(c2c.k, c2c["diff"])]
    c2c.to_csv(R / "c2c_touch_sol.csv", index=False)
    out["C2c 他人签名交易的 SOL 变化一致的地址（容差 1000/笔）"] = f"{c2c.ok.sum()}/{len(c2c)}"; fails["C2c"] = (~c2c.ok).sum()
    tt_tok = tk[~tk.fee_payer].assign(d=lambda x: x.post_raw - x.pre_raw).groupby(["k", "mint"]).d.sum().reset_index()
    tt_tok = tt_tok[tt_tok.d != 0]
    tt_tok["d"] = [Dec(int(v)) for v in tt_tok.d]                 # exact: raw amounts exceed 2**53, outer join would cast to float
    dtok = tch[~tch.mint.isin(["null", WSOL, NATIVE])].groupby(["k", "mint"]).net.sum().reset_index()
    dtok = dtok[dtok.net != 0]                                    # symmetric with the truth side (net != 0 only)
    j = outer(tt_tok, dtok, ["k", "mint"])
    j["ok"] = [D(a_) == D(b_) and m == "both" for a_, b_, m in zip(j.d, j.net, j._merge)]
    j.to_csv(R / "c2d_touch_tokens.csv", index=False)
    out["C2d 他人签名交易的代币净变化一致（地址×币）"] = f"{j.ok.sum()}/{len(j)}"; fails["C2d"] = (~j.ok).sum()

    # ---- C3 opening / closing inventory within signer transactions
    s = tk[tk.in_signers].sort_values(["k", "mint", "slot", "txi"])
    inv = s.groupby(["k", "mint"]).agg(first_pre=("ui_pre", "first"), last_post=("ui_post", "last")).reset_index()
    j = outer(inv, wm[["k", "mint", "v2", "v3"]], ["k", "mint"])
    j["ok"] = [D(a_) == D(b_) and D(c_) == D(e_) and m == "both"
               for a_, b_, c_, e_, m in zip(j.first_pre, j.v2, j.last_post, j.v3, j._merge)]
    first_other = tk.sort_values(["k", "mint", "slot", "txi"]).groupby(["k", "mint"]).in_signers.first().eq(False).sum()
    j.to_csv(R / "c3_inventory.csv", index=False)
    out["C3 期初/期末库存一致（地址×币，签名交易内）"] = f"{j.ok.sum()}/{len(j)}"; fails["C3"] = (~j.ok).sum()
    out["C3 首次触及来自他人签名交易的（地址×币）"] = int(first_other)

    # ---- C4 cost attribution
    fee_t = S.groupby("k").fee_paid.sum(); ffail_t = S[~S.ok].groupby("k").fee_paid.sum(); nfail_t = S[~S.ok].groupby("k").size()
    tip_t = tt.groupby("k").tip.sum()
    tip_d = q1[q1.kind == "tip"].set_index("k").v1
    c4 = pd.DataFrame({"k": ks})
    c4["fee_ok"] = [abs(int(fee_t.get(k, 0)) - int(D(w.v2.get(k)))) <= TOL for k in ks]
    c4["failfee_ok"] = [abs(int(ffail_t.get(k, 0)) - int(D(w.v3.get(k)))) <= TOL and int(nfail_t.get(k, 0)) == int(D(w.v1.get(k)))
                        for k in ks]
    c4["tip_ok"] = [abs(int(tip_t.get(k, 0)) - int(D(tip_d.get(k)))) <= TOL for k in ks]
    evsol = ev.groupby("k").sol.sum()
    evvol = ev.assign(s=[abs(x) for x in ev.sol]).groupby("k").s.sum()
    c4["resid"] = [int(Dec(int(tot_t.get(k, 0))) + nat.get(k, Dec(0)) - evsol.get(k, Dec(0))
                       + int(fee_t.get(k, 0)) + int(tip_t.get(k, 0))) for k in ks]
    c4["trade_vol"] = [int(evvol.get(k, Dec(0))) for k in ks]
    c4["resid_share"] = c4.resid.abs() / c4.trade_vol.replace(0, pd.NA)
    c4.to_csv(R / "c4_costs.csv", index=False)
    out["C4 手续费一致的地址"] = f"{c4.fee_ok.sum()}/{len(c4)}"
    out["C4 失败交易笔数与费用一致的地址"] = f"{c4.failfee_ok.sum()}/{len(c4)}"
    out["C4 Jito tip 一致的地址"] = f"{c4.tip_ok.sum()}/{len(c4)}"
    out["C4 非 pump 成交的 SOL 流（充提、其他场所、终端费等）≤ 成交额 0.1% 的地址"] = f"{(c4.resid_share.fillna(0) <= 0.001).sum()}/{len(c4)}"
    fails["C4"] = (~(c4.fee_ok & c4.failfee_ok & c4.tip_ok)).sum()

    # ---- C5 scope
    touched = tt[tt.touched]
    out["C5 同时调用其他 DEX 的交易占触及交易"] = round(touched.other_dex.mean(), 4)
    out["C5 其他 DEX 交易的 |F| 占比"] = round(touched[touched.other_dex].F.abs().sum() / max(touched.F.abs().sum(), 1), 4)

    core = fails["C1a"] == 0 and fails["C2a"] == 0 and fails["C2b"] == 0 and fails["C3"] == 0
    rest = fails["C1b"] == 0 and not fails["C1c"] and fails["C2c"] == 0 and fails["C2d"] == 0 and fails["C4"] == 0
    out["判定"] = "能测（余额口径）" if core and rest else "部分能测" if core else "不能测"
    for k_, v in out.items():
        print(f"{k_:48s} {v}")
    json.dump({k_: (v if isinstance(v, (str, int, float)) else str(v)) for k_, v in out.items()},
              open(R / "reconcile_summary.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()

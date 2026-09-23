"""DQ-16 §6: reconcile the Dune ledger (raw/dune/Q1.csv, Q2.csv) against the Helius truth (results/truth_*.csv).

Criteria (frozen in README §6): 1 coverage, 2 amounts, 3 cost decomposition, 4 inventory/transfers, 5 failed-tx fees.
No PnL ranking, no persistence, no time buckets. Writes results/reconcile_*.csv and prints the verdict table.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"
TIPS = {"HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh"}
WSOL = "So11111111111111111111111111111111111111112"
TOL = 1000                                                       # lamports

def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def load():
    tt = pd.read_csv(R / "truth_tx.csv"); tk = pd.read_csv(R / "truth_tok.csv")
    q1 = pd.read_csv(HERE / "raw" / "dune" / "Q1.csv", dtype=str)
    q2 = pd.read_csv(HERE / "raw" / "dune" / "Q2.csv", dtype=str) if (HERE / "raw" / "dune" / "Q2.csv").exists() else None
    return tt, tk, q1, q2

def dune_trades(q1):
    ev = q1[q1.src.isin(["curve", "amm_buy", "amm_sell"])].copy()
    buy = ev.is_buy.str.lower().eq("true")
    sol, tok = num(ev.sol_raw), num(ev.tok_raw)
    fa, fb, uq = num(ev.fee_a), num(ev.fee_b), num(ev.user_quote)
    curve = ev.src.eq("curve")
    cfee = sol * (fa + fb) / 1e4                                  # curve: fee_a/fee_b are basis points
    ev["sol_user"] = np.where(curve, np.where(buy, -(sol + cfee), sol - cfee), np.where(buy, -uq, uq))
    ev["tok_user"] = np.where(buy, tok, -tok)
    return ev

def main():
    tt, tk, q1, q2 = load()
    ev = dune_trades(q1)
    out = {}
    # ---- 1 coverage
    trade_sigs = set(tk[(tk.ok) & tk.cls.isin(["pump", "amm"])].groupby(["wallet", "sig"]).size().index)
    dune_sigs = set(ev.groupby(["wallet", "sig"]).size().index)
    vol = tt.set_index(["wallet", "sig"]).F.abs()
    miss = trade_sigs - dune_sigs
    out["1_missing_txs"] = f"{len(miss)}/{len(trade_sigs)}"
    out["1_missing_sol_share"] = round(vol.reindex(list(miss)).sum() / max(vol.reindex(list(trade_sigs)).sum(), 1), 5)
    out["1_extra_in_dune"] = len(dune_sigs - trade_sigs)
    # ---- 2 amounts (per wallet, sig, mint for tokens; per wallet, sig for SOL)
    dt = ev.groupby(["wallet", "sig", "mint"]).tok_user.sum().rename("dune_tok")
    ht = tk.set_index(["wallet", "sig", "mint"]).d_tok.rename("truth_tok")
    j = pd.concat([ht, dt], axis=1).dropna()
    out["2_token_exact"] = f"{(j.truth_tok == j.dune_tok).sum()}/{len(j)}"
    ds = ev.groupby(["wallet", "sig"]).sol_user.sum().rename("dune_sol")
    hs = tt.set_index(["wallet", "sig"]).eval("F + fee + tip").rename("truth_sol_ex_cost")
    js = pd.concat([hs, ds], axis=1).dropna()
    js["resid"] = js.truth_sol_ex_cost - js.dune_sol
    out["2_sol_within_tol"] = f"{(js.resid.abs() <= TOL).sum()}/{len(js)}"
    js.to_csv(R / "reconcile_sol.csv")
    j.to_csv(R / "reconcile_tok.csv")
    # ---- 3 cost decomposition per wallet
    tr = q1[q1.src.eq("transfer")].copy()
    tr["amt"] = num(tr.tok_raw)
    native = tr.token_version.fillna("").str.contains("native", case=False)
    tipq = tr[native & tr.to_owner.isin(TIPS)].groupby("wallet").amt.sum().rename("dune_tip")
    tip_h = tt.groupby("wallet").tip.sum().rename("truth_tip")
    fee_h = tt.groupby("wallet").fee.sum().rename("truth_fee")
    fee_d = num(q2.fee).groupby(q2.wallet).sum().rename("dune_fee") if q2 is not None else None
    tv = (-ds.clip(upper=0)).groupby(level=0).sum() + ds.clip(lower=0).groupby(level=0).sum()
    unexpl = js.resid.groupby(level=0).apply(lambda s: s.abs().sum()).rename("unexplained_abs")
    c3 = pd.concat([tip_h, tipq, fee_h, fee_d, tv.rename("trade_volume"), unexpl], axis=1).fillna(0)
    c3["unexpl_share"] = c3.unexplained_abs / c3.trade_volume.replace(0, np.nan)
    c3.to_csv(R / "reconcile_cost.csv")
    out["3_tip_match_wallets"] = f"{(c3.truth_tip - c3.dune_tip).abs().le(TOL).sum()}/{len(c3)}"
    out["3_fee_match_wallets"] = f"{(c3.truth_fee - c3.dune_fee).abs().le(TOL).sum()}/{len(c3)}"
    out["3_wallets_unexpl_le_0.1pct"] = f"{(c3.unexpl_share.fillna(0) <= 0.001).sum()}/{len(c3)}"
    # ---- 4 transfers (non-trade token movements)
    xt = tk[~tk.set_index(["wallet", "sig"]).index.isin(list(trade_sigs)) & (tk.mint != WSOL)]
    out["4_truth_nontrade_token_rows"] = len(xt)
    tr_tok = tr[~native & ~tr.set_index(["wallet", "sig"]).index.isin(list(dune_sigs))]
    out["4_dune_nontrade_transfer_rows"] = len(tr_tok)
    outflow = tk[tk.d_tok < 0].groupby("wallet").d_tok.sum().abs()
    out_x = xt[xt.d_tok < 0].groupby("wallet").d_tok.sum().abs()
    out["4_transfer_out_share_of_token_outflow(median wallet)"] = round((out_x / outflow).fillna(0).median(), 4)
    # ---- 5 failed tx fees
    if q2 is not None:
        f_h = tt[~tt.ok].groupby("wallet").fee.sum()
        f_d = num(q2[q2.success.str.lower().eq("false")].fee).groupby(q2.wallet).sum()
        c5 = pd.concat([f_h.rename("truth"), f_d.rename("dune")], axis=1).fillna(0)
        out["5_failed_fee_match_wallets"] = f"{(c5.truth - c5.dune).abs().le(TOL).sum()}/{len(c5)}"
    for k, v in out.items():
        print(f"{k:55s} {v}")
    json.dump(out, open(R / "reconcile_summary.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()

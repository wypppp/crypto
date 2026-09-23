"""Mock test for reconcile.py: build 'perfect Dune' Q1/Q2 aggregates from the truth using the SQL's definitions,
expect verdict 能测; then inject errors and expect the matching criterion to fail. Runs in a scratch directory."""
import shutil, subprocess, sys, tempfile, json
from decimal import Decimal as Dec
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
tt = pd.read_csv(HERE / "results" / "truth_tx.csv"); tk = pd.read_csv(HERE / "results" / "truth_tok.csv")
tk = tk.merge(tt[["k", "sig", "ok", "in_signers", "fee_payer", "pump", "amm", "F", "fee_paid", "tip"]], on=["k", "sig"])
ui = lambda raw, d: str(Dec(int(raw)) / (Dec(10) ** int(d)))
S, T = tt[tt.in_signers], tt[~tt.fee_payer & tt.touched]
q2 = []
for k, g in S.groupby("k"):
    q2.append(dict(kind="wal", k=k, n=len(g), s_slot=g.slot.sum(), v1=(~g.ok).sum(), v2=g.fee_paid.sum(),
                   v3=g[~g.ok].fee_paid.sum(), v4=g.d_wallet.sum()))
    q2.append(dict(kind="wacc", k=k, v1=g.d_lam_wsol.sum(), v2=g.d_lam_tok.sum(), v3=str(Dec(int(g.d_wsol_raw.sum())) / Dec(10**9))))
for (k, m), g in tk[tk.in_signers].sort_values(["slot", "txi"]).groupby(["k", "mint"]):
    dui = sum(Dec(int(b)) / Dec(10) ** int(d) - Dec(int(a)) / Dec(10) ** int(d) for a, b, d in zip(g.pre_raw, g.post_raw, g.decimals))
    q2.append(dict(kind="wm", k=k, key=m, n=len(g), s_slot=g.slot.sum(), v1=str(dui),
                   v2=ui(g.pre_raw.iloc[0], g.decimals.iloc[0]), v3=ui(g.post_raw.iloc[-1], g.decimals.iloc[-1])))
q1 = []
tr = tk[tk.ok & (tk.pump | tk.amm) & (tk.pre_raw != tk.post_raw)]
for (k, m), g in tr.groupby(["k", "mint"]):
    q1.append(dict(kind="ev", k=k, key=m, n=g.sig.nunique(), s_slot=g.slot.sum(), v1="curve",
                   v5=str(int((g.F + g.fee_paid + g.tip).sum()))))
for k, v in tt.groupby("k").tip.sum().items():
    q1.append(dict(kind="tip", k=k, n=1, v1=v))
for k, g in T.groupby("k"):
    q1.append(dict(kind="touchset", k=k, n=len(g), s_slot=g.slot.sum()))
    q1.append(dict(kind="touch", k=k, key="null|native", v1=g.F.clip(lower=0).sum(), v2=(-g.F.clip(upper=0)).sum()))
tn = tk[~tk.fee_payer].assign(d=lambda x: x.post_raw - x.pre_raw)
for (k, m), g in tn.groupby(["k", "mint"]):
    q1.append(dict(kind="touch", k=k, key=f"{m}|spl_token", v1=g.d.clip(lower=0).sum(), v2=(-g.d.clip(upper=0)).sum()))
cols = ["kind", "k", "key", "n", "s_slot", "v1", "v2", "v3", "v4", "v5", "v6"]
strs = lambda rows: [{c: (None if v is None else str(int(v)) if hasattr(v, "__int__") and not isinstance(v, (str, float)) else v)
                      for c, v in r.items()} for r in rows]                 # keep integers exact (no float round-trip)
Q1, Q2 = pd.DataFrame(strs(q1), dtype=object).reindex(columns=cols), pd.DataFrame(strs(q2), dtype=object).reindex(columns=cols)

def run(q1, q2, label):
    d = Path(tempfile.mkdtemp()); (d / "dune").mkdir(); (d / "res").mkdir()
    for f in ("truth_tx.csv", "truth_tok.csv"):
        shutil.copy(HERE / "results" / f, d / "res" / f)
    q1.to_csv(d / "dune" / "Q1.csv", index=False); q2.to_csv(d / "dune" / "Q2.csv", index=False)
    subprocess.run([sys.executable, str(HERE / "reconcile.py"), str(d / "dune"), str(d / "res")], check=True, capture_output=True)
    s = json.load(open(d / "res" / "reconcile_summary.json"))
    shutil.rmtree(d)
    print(f"--- {label}: {s['判定']}")
    return s

base = run(Q1, Q2, "perfect")
for k_, v in base.items():
    print("   ", k_, v)
i = Q2.index[Q2.kind.eq("wm")][0]
s = run(Q1, Q2.drop(i), "drop one wm row");            print("    C2b", s["C2b 签名交易代币净变化一致（地址×币）"], "C3", s["C3 期初/期末库存一致（地址×币，签名交易内）"])
q = Q2.copy(); j = q.index[q.kind.eq("wal")][0]; q.loc[j, "v4"] = int(q.loc[j, "v4"]) + 5000
s = run(Q1, q, "wallet SOL +5000");                     print("    C2a", s["C2a 签名交易 SOL 等值总变化一致的地址"])
q = Q1.copy(); j = q[q.kind.eq("ev")].n.astype(float).idxmax(); q.loc[j, "n"] = float(q.loc[j, "n"]) - 1
s = run(q, Q2, "one trade missing in biggest ev cell");  print("    C1c", s["C1c pump/PumpSwap 成交（地址×币）一致"], s["C1c 不一致格的真值成交额占比"])
q = Q1.copy(); j = q.index[q.kind.eq("tip")][0]; q.loc[j, "v1"] = float(q.loc[j, "v1"]) + 5000
s = run(q, Q2, "tip +5000");                             print("    C4 tip", s["C4 Jito tip 一致的地址"])

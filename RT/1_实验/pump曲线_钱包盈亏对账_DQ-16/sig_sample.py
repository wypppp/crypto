"""DQ-16 r2: freeze a stratified signature sample for per-signature checking, BEFORE any Dune result is downloaded.
Strata (seed 20260923): signer-set succeeded 60, signer-set failed 40, touch-set 40, same-wallet duplicate-slot 60."""
import pandas as pd
from pathlib import Path
HERE = Path(__file__).parent
t = pd.read_csv(HERE / "results" / "truth_tx.csv")
dup = t.duplicated(["k", "slot"], keep=False)
strata = {"signer_ok": t[t.in_signers & t.ok & ~dup], "signer_failed": t[t.in_signers & ~t.ok & ~dup],
          "touch": t[~t.fee_payer & t.touched & ~t.in_signers & ~dup], "dup_slot": t[dup]}
n = {"signer_ok": 60, "signer_failed": 40, "touch": 40, "dup_slot": 60}
out = pd.concat([g.sample(min(n[s], len(g)), random_state=20260923).assign(stratum=s) for s, g in strata.items()])
out[["stratum", "k", "wallet", "sig", "slot", "txi", "ok", "in_signers", "fee_payer"]].to_csv(HERE / "raw" / "sig_sample.csv", index=False)
print(out.stratum.value_counts().to_dict(), "dup-slot txs in truth:", int(dup.sum()))

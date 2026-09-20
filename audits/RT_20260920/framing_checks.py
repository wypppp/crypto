"""Check metric denominators and correction propagation, without new hypotheses.

Uses published rounded thresholds only to expose their denominator mismatch;
does not endorse those thresholds or simulate new trading strategies.
"""
from pathlib import Path
import json
import hashlib
import pandas as pd

HERE = Path(__file__).resolve().parent
RT = HERE / "snapshot/RT"
result = {"metric_denominators": {}}
thresholds = {"A": [1.0074, 1.0344, 1.0688], "B": [1.0035, 1.0125, 1.0267]}
for week, path, ret, ms in [
    ("A", "dq7/raw/F2_dev.csv", "b50", "ms_30d"),
    ("B", "dq1f/raw/F1_val.csv", "x50_24h", "ms_60d"),
]:
    d = pd.read_csv(RT / path)
    d = d[d.mint != "__SUMMARY__"].copy()
    r = d[ret] - .004
    loser = (d[ms] < 10) & r.ge(.5) & r.lt(.9)
    q = d.net_sol_pre
    rows = []
    for i, (name, keep) in enumerate([
        ("all", pd.Series(True, index=d.index)),
        ("top20", q.ge(q.quantile(.8))),
        ("top5", q.ge(q.quantile(.95))),
    ]):
        n = int(keep.sum())
        p = float(loser[keep].mean())
        loss_mean = float(r[keep & loser].mean())
        base = float(r[keep].mean())
        target = thresholds[week][i]
        cash = base + p * (1 - loss_mean)
        selected = (base - p * loss_mean) / (1 - p)
        direct_selected = float(r[keep & ~loser].mean())
        assert abs(selected - direct_selected) < 1e-12
        rows.append({
            "layer": name, "n": n, "loser_fraction": p, "loser_mean": loss_mean,
            "base": base, "published_rounded_threshold": target,
            "cash_replacement_mean": cash, "selected_only_mean": selected,
            "required_fraction_cash_convention": max(0, (target-base)/(p*(1-loss_mean))),
            "required_fraction_selected_convention": max(0, (target-base)/(p*(target-loss_mean))),
            "note": "Oracle removal is a diagnostic bound, not an implementable selector. Thresholds are not revalidated."
        })
    result["metric_denominators"][week] = rows

index = json.loads((HERE / "history/index.json").read_text())
commits = ["1eeaeff0", "9b23b2d0", "c8a558e2", "637eb077", "e47bc55d"]
result["correction_propagation"] = []
for c in commits:
    row = {"commit": c}
    for key, p in [("status", "RT/右尾_STATUS.md"), ("facts", "RT/右尾_事实库.md"),
                   ("diagnostics", "RT/diag/收益公式改善目标表.md")]:
        found = next(x for x in index if x["commit"].startswith(c) and x["path"] == p)
        src = HERE / "history" / c / p
        actual = hashlib.sha256(src.read_bytes()).hexdigest()
        assert actual == found["sha256"]
        row[key + "_sha256"] = actual
    result["correction_propagation"].append(row)
assert len({x["status_sha256"] for x in result["correction_propagation"]}) == 1
assert len({x["facts_sha256"] for x in result["correction_propagation"]}) == 4

out = HERE / "checks/framing_results.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))

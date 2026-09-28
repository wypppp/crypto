#!/usr/bin/env python3
"""Zero-API R0 sensitivity: remove nonce-authority-as-funder edges.

V1 keeps independently saved direct creator links; it checks whether any such
link could itself be a nonce-authority-as-funder edge. This does not establish
economic ownership or replace an event-time R1 signal construction.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

H = Path(__file__).resolve().parent


def csv_rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as src:
        yield from csv.DictReader(src)


def primary(flows: list[dict], services: set[str], exclude_nonce: bool) -> str | None:
    sums: dict[str, list[int]] = {}
    for r in flows:
        if exclude_nonce and "nonce" in r["evidence"].split("+"):
            continue
        a = sums.setdefault(r["source"], [0, 0])
        a[0] += int(r["amount"])
        a[1] = max(a[1], int(float(r["ts"] or 0)))
    if not sums:
        return None
    nonservice = {s: v for s, v in sums.items() if s not in services}
    if not nonservice:
        return "service"
    return max(nonservice, key=lambda s: (nonservice[s][0], nonservice[s][1]))


def main() -> None:
    services = {r["address"] for r in csv_rows(H / "services.csv") if r["class"] == "strict"}
    strata = {r["mint"]: r["stratum"] for r in csv_rows(H / "sample.csv")}
    coins = list(csv_rows(H / "results/all_coins.csv"))
    wallets = list(csv_rows(H / "results/all_wallets.csv"))
    flows = defaultdict(list)
    for r in csv_rows(H / "results/all_inflows.csv.gz"):
        if r["status"] == "unique":
            flows[(r["mint"], r["W"])].append(r)

    pf_match = Counter()
    nonce_in_primary = Counter()
    new_pf: dict[tuple[str, str], str | None] = {}
    for r in wallets:
        if r["status"] != "resolved_complete":
            continue
        key = (r["mint"], r["W"])
        old = primary(flows[key], services, False)
        saved = r["pf_strict"] or None
        pf_match["buyers_checked"] += 1
        if old != saved:
            pf_match["buyers_mismatch"] += 1
        new_pf[key] = primary(flows[key], services, True)
        if saved not in (None, "service"):
            selected = [x for x in flows[key] if x["source"] == saved]
            if any("nonce" in x["evidence"].split("+") for x in selected):
                nonce_in_primary["buyers_with_nonce_primary"] += 1
                if all("nonce" in x["evidence"].split("+") for x in selected):
                    nonce_in_primary["buyers_nonce_only_primary"] += 1
            nonce_in_primary["buyers_with_nonservice_primary"] += 1

    new_creator_pf: dict[str, str | None] = {}
    for r in coins:
        if r["creator_back_complete"].lower() != "true":
            continue
        key = (r["mint"], r["creator"])
        old = primary(flows[key], services, False)
        saved = r["creator_pf_strict"] or None
        pf_match["creators_checked"] += 1
        if old != saved:
            pf_match["creators_mismatch"] += 1
        new_creator_pf[r["mint"]] = primary(flows[key], services, True)

    by_mint = defaultdict(list)
    for r in wallets:
        by_mint[r["mint"]].append(r)
    counts = defaultdict(Counter)
    changed = []
    intensity_changes = []
    v1_changes = []
    v1_direct_nonce_ambiguity = 0
    for c in coins:
        mint = c["mint"]
        if c["applicable"].lower() != "true":
            continue
        group_old, group_new = defaultdict(list), defaultdict(list)
        for w in by_mint[mint]:
            if w["status"] != "resolved_complete":
                continue
            p0 = w["pf_strict"] or None
            p1 = new_pf.get((mint, w["W"]))
            if p0 not in (None, "service"):
                group_old[p0].append(float(w["sol"]))
            if p1 not in (None, "service"):
                group_new[p1].append(float(w["sol"]))
        old_signal = any(len(v) >= 2 for v in group_old.values())
        new_signal = any(len(v) >= 2 for v in group_new.values())
        recorded = int(float(c["V2n_strict"] or 0)) >= 2
        if old_signal != recorded:
            raise RuntimeError(f"V2n reproduction failed for {mint}")
        all_sol = sum(float(w["sol"]) for w in by_mint[mint])
        old_intensity = max((sum(v) for v in group_old.values() if len(v) >= 2), default=0) / all_sol
        new_intensity = max((sum(v) for v in group_new.values() if len(v) >= 2), default=0) / all_sol
        if abs(old_intensity - float(c["V2_strict"] or 0)) > 1e-9:
            raise RuntimeError(f"V2 intensity reproduction failed for {mint}")
        z = counts[strata.get(mint, "unknown")]
        z["applicable"] += 1
        z["old_v2"] += old_signal
        z["without_nonce_v2"] += new_signal
        z["lost_v2"] += old_signal and not new_signal
        z["gained_v2"] += new_signal and not old_signal
        if old_signal != new_signal:
            changed.append({"mint": mint, "stratum": strata.get(mint),
                            "old_v2": old_signal, "without_nonce_v2": new_signal})
        if abs(old_intensity - new_intensity) > 1e-9:
            intensity_changes.append({"mint": mint, "stratum": strata.get(mint),
                                      "old_v2": old_intensity, "without_nonce_v2": new_intensity})
        creator, cpf_old = c["creator"], c["creator_pf_strict"] or None
        cpf_new = new_creator_pf.get(mint)
        v1_old, v1_new = [], []
        for w in by_mint[mint]:
            key = (mint, w["W"])
            direct = w["direct_creator_link"].lower() == "true"
            if direct and any(x["source"] == creator and "nonce" in x["evidence"].split("+")
                              for x in flows[key]):
                v1_direct_nonce_ambiguity += 1
            p0 = w["pf_strict"] or None
            p1 = new_pf.get(key)
            v1_old.append(direct or p0 == creator or (p0 is not None and cpf_old not in (None, "service") and p0 == cpf_old))
            v1_new.append(direct or p1 == creator or (p1 is not None and cpf_new not in (None, "service") and p1 == cpf_new))
        if sum(v1_old) != int(float(c["V1n_strict"] or 0)):
            raise RuntimeError(f"V1 count reproduction failed for {mint}")
        if v1_old != v1_new:
            v1_changes.append({"mint": mint, "stratum": strata.get(mint),
                               "old_v1n": sum(v1_old), "without_nonce_v1n": sum(v1_new)})

    if pf_match["buyers_mismatch"] or pf_match["creators_mismatch"]:
        raise RuntimeError(f"saved primary funder not reproduced: {dict(pf_match)}")
    out = {
        "scope": "R0 cached complete-window buyers; V1/V2 with saved direct links",
        "interpretation": "Deleting nonce-authority edges is a sensitivity analysis; it is not proof that non-nonce funders are economic owners.",
        "pf_reproduction": dict(pf_match),
        "nonce_in_saved_primary": dict(nonce_in_primary),
        "v2_by_stratum": {k: dict(v) for k, v in sorted(counts.items())},
        "changed_mints": changed,
        "v2_intensity_changed_n": len(intensity_changes),
        "v2_intensity_changes": intensity_changes,
        "v1_changes_keeping_saved_direct_links": v1_changes,
        "v1_direct_links_with_nonce_source_creator": v1_direct_nonce_ambiguity,
    }
    path = H / "results/r0_nonce_control_sensitivity.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "changed_mints"}, ensure_ascii=False, indent=2))
    print("saved", path)


if __name__ == "__main__":
    main()

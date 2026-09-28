#!/usr/bin/env python3
"""Compare first cached gTFA page (<=100 tx) with saved R0 funder labels.

No API calls. This audits identity stability, not end-to-end online latency.
"""
from __future__ import annotations

import csv
import gzip
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_nonce_control_sensitivity import primary

H = Path(__file__).resolve().parent


def rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as src:
        yield from csv.DictReader(src)


def first_page_signatures(kind: str, address: str, ts: int) -> set[str] | None:
    path = H / "raw/helius" / f"{kind}__{address}__{ts}.jsonl.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt") as src:
        return {json.loads(line)["transaction"]["signatures"][0]
                for line in itertools.islice(src, 100)}


def main() -> None:
    services = {r["address"] for r in rows(H / "services.csv") if r["class"] == "strict"}
    wallets = list(rows(H / "results/all_wallets.csv"))
    coins = list(rows(H / "results/all_coins.csv"))
    strata = {r["mint"]: r["stratum"] for r in rows(H / "sample.csv")}
    all_flows = defaultdict(list)
    for r in rows(H / "results/all_inflows.csv.gz"):
        if r["status"] == "unique":
            all_flows[(r["mint"], r["W"])].append(r)

    buyer_stats = Counter()
    one_pf = {}
    for w in wallets:
        if w["status"] == "program_account":
            continue
        key = (w["mint"], w["W"])
        sigs = first_page_signatures("back", w["W"], int(w["t_buy"]))
        if sigs is None:
            buyer_stats["missing_cache"] += 1
            continue
        buyer_stats["cached_wallet_coin"] += 1
        f = [x for x in all_flows[key] if x["sig"] in sigs]
        p = primary(f, services, False)
        one_pf[key] = p
        if w["status"] == "resolved_complete":
            buyer_stats["seven_day_resolved"] += 1
            saved = w["pf_strict"] or None
            if p == saved:
                buyer_stats["same_primary_as_7day"] += 1
            if p is None:
                buyer_stats["onepage_no_unique_source"] += 1
            elif p == "service":
                buyer_stats["onepage_service_only"] += 1

    creator_stats = Counter()
    creator_pf = {}
    for c in coins:
        m, addr, ts = c["mint"], c["creator"], int(c["t0"])
        sigs = first_page_signatures("back", addr, ts)
        if sigs is None:
            creator_stats["missing_cache"] += 1
            continue
        f = [x for x in all_flows[(m, addr)] if x["sig"] in sigs]
        p = primary(f, services, False)
        creator_pf[m] = p
        creator_stats["cached_creator"] += 1
        if c["creator_back_complete"].lower() == "true":
            creator_stats["seven_day_complete"] += 1
            if p == (c["creator_pf_strict"] or None):
                creator_stats["same_primary_as_7day"] += 1

    by_mint = defaultdict(list)
    for w in wallets:
        by_mint[w["mint"]].append(w)
    signal_stats = defaultdict(Counter)
    changed = []
    for c in coins:
        if c["applicable"].lower() != "true":
            continue
        mint = c["mint"]
        groups_complete = defaultdict(list)
        groups_all = defaultdict(list)
        for w in by_mint[mint]:
            p = one_pf.get((mint, w["W"]))
            if p not in (None, "service"):
                groups_all[p].append(float(w["sol"]))
                if w["status"] == "resolved_complete":
                    groups_complete[p].append(float(w["sol"]))
        sol_all = sum(float(w["sol"]) for w in by_mint[mint])
        v2_complete = max((sum(v) for v in groups_complete.values() if len(v) >= 2), default=0) / sol_all
        v2_all = max((sum(v) for v in groups_all.values() if len(v) >= 2), default=0) / sol_all
        old = float(c["V2_strict"] or 0)
        z = signal_stats[strata.get(mint, "unknown")]
        z["applicable"] += 1
        z["old_v2_trigger"] += old > 0
        z["onepage_complete_v2_trigger"] += v2_complete > 0
        z["onepage_all_v2_trigger"] += v2_all > 0
        if (old > 0) != (v2_complete > 0):
            z["changed_complete_trigger"] += 1
            changed.append({"mint": mint, "stratum": strata.get(mint),
                            "seven_day_v2": old, "onepage_complete_v2": v2_complete,
                            "onepage_all_v2": v2_all})
        if (old > 0) != (v2_all > 0):
            z["changed_all_trigger"] += 1

    out = {
        "scope": "R0 cached first full-transaction page (up to 100 transactions), same service labels; funder identity and V2 only. Complete-wallet version holds the original eligible wallet set fixed; all-wallet version adds previously truncated wallets.",
        "limitations": "No V1 direct-link replay, no signal-time freshness, no end-to-end execution latency, and incomplete 7-day truth for truncated wallets.",
        "buyers": dict(buyer_stats),
        "creators": dict(creator_stats),
        "v2_by_stratum": {k: dict(v) for k, v in sorted(signal_stats.items())},
        "changed_mints": changed,
    }
    path = H / "results/r0_onepage_funder_sensitivity.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "changed_mints"}, ensure_ascii=False, indent=2))
    print("saved", path)


if __name__ == "__main__":
    main()

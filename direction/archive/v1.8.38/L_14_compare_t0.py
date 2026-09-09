"""Complete comparison of independently downloaded L13 results with frozen L12 evidence.

Original summaries are comparison references only. This module never downloads data
or supplies records to L13's recomputation. Run from the package directory.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(manifest, config, upstream, original, reference, independent):
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append({"check": label, "actual": actual, "expected": expected})

    selected = manifest["selected"]
    old = {r["base_asset"]: r for r in original["records"]}
    fetch = {r["base_asset"]: r for r in upstream["fetch_list"]}
    iv = config["mother_universe"]["independent_verification"]["selected"]
    expected_selection = sorted(set(iv["lag_positive"] + iv["premarket"] + iv["ontime"]))
    check("frozen sample", selected, expected_selection)
    check("sample count", len(selected), iv["n_total"])
    eligible = [r for r in original["records"] if r["status"] == "VERIFIED_COMPLETE"]
    check("all positive lags", sorted(iv["lag_positive"]),
          sorted(r["base_asset"] for r in eligible if r["lag_seconds"] > 0))
    check("all formal transitions", sorted(iv["premarket"]),
          sorted(r["base_asset"] for r in eligible if r["kind"] == "PREMARKET_TO_SPOT"))
    ranked = sorted((r["base_asset"] for r in eligible if r["lag_seconds"] == 0),
                    key=lambda b: hashlib.sha256(b.encode()).hexdigest())[:20]
    check("on-time hash ranking", iv["ontime"], ranked)
    check("no holdout", [b for b in selected if hashlib.sha256(b.encode()).digest()[0] % 5 == 0], [])
    check("independent config", independent["config_sha256"], manifest["inputs"]["L_config.json"])
    check("same upstream config", upstream["config_sha256"], original["config_sha256"])
    check("independent errors", independent["errors"], [])
    check("independent event count", independent["n_events"], len(selected))
    recomputed = independent["recomputed"]
    check("independent event identities", sorted(recomputed), selected)
    check("reference event identities", sorted(reference["pairs"]), selected)
    pair_count = 0
    for b in selected:
        if b not in recomputed:
            continue
        v, o, f = recomputed[b], old[b], fetch[b]
        check(b + " original complete", o["status"], "VERIFIED_COMPLETE")
        check(b + " fetch eligibility", f["embargo"], "FETCHABLE")
        expected_pairs = sorted(set(f["announced_pairs"]))
        check(b + " no missing pairs", v["pairs_failed"], [])
        check(b + " exact pair membership", sorted(v["pairs"]), expected_pairs)
        check(b + " reference membership", sorted(reference["pairs"][b]), expected_pairs)
        check(b + " original verified membership", sorted(o["pairs_verified"]), expected_pairs)
        for symbol in expected_pairs:
            if symbol not in v["pairs"]:
                continue
            r, ref = v["pairs"][symbol], reference["pairs"][b][symbol]
            pair_count += 1
            for field in ("symbol", "day", "n_rows", "day_min_ts_us", "first_at_or_after", "official_checksum"):
                check(b + "/" + symbol + " " + field, r[field], ref[field])
            check(b + "/" + symbol + " downloaded hash", r["sha256"], ref["local_sha256"])
            check(b + "/" + symbol + " checksum", r["sha256"], r["official_checksum"])
            check(b + "/" + symbol + " threshold", v["threshold_us"], ref["threshold_us"])
        candidates = {s: r["first_at_or_after"] for s, r in v["pairs"].items() if r["first_at_or_after"] is not None}
        minimum = min((r["ts_us"] for r in candidates.values()), default=None)
        tied = sorted(s for s, r in candidates.items() if r["ts_us"] == minimum)
        check(b + " recomputed minimum", v["T0_us"], minimum)
        check(b + " original minimum", o["T0_exact_us"], minimum)
        check(b + " independent ties", v["tied"], tied)
        check(b + " original ties", sorted(o["T0_tied_pairs"]), tied)
        # Tied pairs can have different prices, quantities and trade IDs. Compare
        # the original winning record with the same pair, not an arbitrary tie.
        check(b + " original winning pair among ties", o["T0_pair"] in tied, True)
        check(b + " original full winning trade", o["T0_trade"], candidates.get(o["T0_pair"]))
        if tied:
            check(b + " L13 full winning trade", v["trade"], candidates[tied[0]])
    check("pair count", pair_count, sum(len(set(fetch[b]["announced_pairs"])) for b in selected))
    check("reported pair count", independent["n_pairs"], pair_count)
    return {"stage": "INDEPENDENT_T0_FULL_COMPARISON", "n_events": len(selected),
            "n_pairs": pair_count, "failures": failures, "passed": not failures,
            "scope": "37 fixed stratified non-holdout events; shared official data source; not validation of all 205 events"}


def atomic_json(path, obj):
    fd, temp = tempfile.mkstemp(dir=Path(path).parent, prefix=".compare-")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, allow_nan=False)
            fh.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    manifest = json.loads(Path("L_t0_verification_manifest.json").read_text())
    for name, expected in manifest["inputs"].items():
        if sha(name) != expected:
            raise SystemExit("FAIL-CLOSED: input hash mismatch: " + name)
    names = ["L_config.json", "L_u_master.json", "L_t0_exact_v2.json", "L_t0_reference.json", "L_t0_verify.json"]
    report = compare(manifest, *(json.loads(Path(n).read_text()) for n in names))
    report["input_sha256"] = {n: sha(n) for n in names + ["L_t0_verification_manifest.json"]}
    report["comparator_sha256"] = sha(__file__)
    if not report["passed"]:
        atomic_json("L_t0_verify_complete.failed.json", report)
        raise SystemExit("FAIL-CLOSED: " + str(len(report["failures"])) + " comparison failures; successful output preserved")
    atomic_json("L_t0_verify_complete.json", report)
    print("PASS:", report["n_events"], "events /", report["n_pairs"], "pairs; complete records, counts, timestamps and hashes agree")


if __name__ == "__main__":
    main()

"""Check DQ-18 P1 December acceptance rows before any pool-price follow-up."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
THRESHOLDS = (1_000_000, 5_000_000, 20_000_000, 100_000_000)
ORIGINAL_COUNTS = {1_000_000: 627, 5_000_000: 339,
                   20_000_000: 262, 100_000_000: 222}
WHITEWHALE = "a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump"


def rows(name):
    return json.loads((ROOT / "raw" / "s2" / name).read_text())["rows"]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python audit_s2_p1.py RESULT_LABEL")
    label = sys.argv[1]
    result = rows(label + ".json")
    by_key = {(r["variant_name"], r["mint"], int(float(r["threshold_usd"]))): r
              for r in result}
    assert len(by_key) == len(result), "duplicate variant-mint-threshold rows"

    print("total first-in-month rows", len(result))
    for variant in ("original", "loose", "p1", "strict"):
        counts = Counter(int(float(r["threshold_usd"])) for r in result
                         if r["variant_name"] == variant)
        print(variant, {threshold: counts[threshold] for threshold in THRESHOLDS})
        if variant == "original":
            assert all(counts[t] == ORIGINAL_COUNTS[t] for t in THRESHOLDS), \
                "original rule does not reproduce prior A-stage counts"

    whale = by_key.get(("p1", WHITEWHALE, 20_000_000))
    print("WHITEWHALE P1 $20m", None if whale is None else whale["signal_time"])
    assert whale and whale["signal_time"].startswith("2025-12-26 23:00:00")

    diagnostic = rows("A_202512_dust.json")
    dust = sorted({r["mint"] for r in diagnostic if r["mint"] != WHITEWHALE})
    for mint in dust:
        original = [r for r in result if r["variant_name"] == "original"
                    and r["mint"] == mint]
        p1 = [r for r in result if r["variant_name"] == "p1"
              and r["mint"] == mint]
        old_hours = {r["hour_start"] for r in original}
        new_hours = {r["hour_start"] for r in p1}
        print("dust", mint, "original", sorted(old_hours), "P1", sorted(new_hours))
        assert not old_hours.intersection(new_hours), \
            "dust original-hour crossing survived P1"

    candidates = [r for r in result if r["variant_name"] == "p1"
                  and int(float(r["threshold_usd"])) == 1_000_000]
    candidates.sort(key=lambda r: (hashlib.md5(
        (r["mint"] + ":20260924").encode()).hexdigest(), r["mint"]))
    selected = [{"mint": r["mint"], "hour_start": r["hour_start"],
                 "signal_time": r["signal_time"],
                 "md5_sort_key": hashlib.md5(
                     (r["mint"] + ":20260924").encode()).hexdigest()}
                for r in candidates[:10]]
    payload = json.dumps(selected, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
    out = ROOT / "raw" / "s2" / "P1_202512_sample10.json"
    out.write_bytes(payload + b"\n")
    print("sample10", [r["mint"] for r in selected])
    print("sample_file", out, "sha256", hashlib.sha256(payload + b"\n").hexdigest())

    old = [r for r in result if r["variant_name"] == "original"]
    print("original-hour diagnostic, overlapping counts by threshold")
    for threshold in THRESHOLDS:
        group = [r for r in old if int(float(r["threshold_usd"])) == threshold]
        print(threshold, {
            "curve_only_with_no_graduated_valid": sum(
                (r["n_curve_valid"] or 0) > 0
                and (r["n_graduated_before_size"] or 0) == 0 for r in group),
            "some_graduated_trades_below_single_min": sum(
                (r["n_graduated_before_size"] or 0) > (r["n_p1_valid"] or 0)
                for r in group),
            "p1_hour_activity_insufficient": sum(
                (r["n_p1_valid"] or 0) < 5
                or (r["p1_usd_volume"] or 0) < 100 for r in group),
            "p1_vwap_below_threshold_after_activity": sum(
                (r["n_p1_valid"] or 0) >= 5
                and (r["p1_usd_volume"] or 0) >= 100
                and (r["p1_vwap_cap_usd"] or 0) < threshold for r in group),
            "p1_median_below_threshold_after_activity": sum(
                (r["n_p1_valid"] or 0) >= 5
                and (r["p1_usd_volume"] or 0) >= 100
                and (r["p1_median_cap_usd"] or 0) < threshold for r in group),
        })


if __name__ == "__main__":
    main()

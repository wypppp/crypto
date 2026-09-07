"""Bounded negative tests for the full independent comparison; no network access."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    source = Path(__file__).resolve().parent
    files = ["L_14_compare_t0.py", "L_t0_verification_manifest.json", "L_config.json",
             "L_u_master.json", "L_t0_exact_v2.json", "L_t0_reference.json", "L_t0_verify.json"]
    with tempfile.TemporaryDirectory(prefix="t0_full_comparison_test_") as tmp:
        p = Path(tmp)
        for name in files:
            shutil.copy2(source / name, p / name)

        def run():
            return subprocess.run([sys.executable, "-B", "L_14_compare_t0.py"], cwd=p,
                                  capture_output=True, text=True)

        good = run()
        assert good.returncode == 0, good.stdout + good.stderr
        result = p / "L_t0_verify_complete.json"
        before = hashlib.sha256(result.read_bytes()).hexdigest()
        raw = json.loads((p / "L_t0_verify.json").read_text())
        old = {r["base_asset"]: r for r in json.loads((p / "L_t0_exact_v2.json").read_text())["records"]}
        base = next(b for b, v in raw["recomputed"].items() if len(v["pairs"]) > 1)
        pair = next(s for s in raw["recomputed"][base]["pairs"] if s != old[base]["T0_pair"])
        cases = []
        for case in ("nonwinning_pair_trade", "pair_row_count", "missing_pair"):
            changed = copy.deepcopy(raw)
            pairs = changed["recomputed"][base]["pairs"]
            if case == "nonwinning_pair_trade":
                pairs[pair]["first_at_or_after"]["qty"] = "999999999"
            elif case == "pair_row_count":
                pairs[pair]["n_rows"] += 1
            else:
                del pairs[pair]
            (p / "L_t0_verify.json").write_text(json.dumps(changed))
            failure = run()
            assert failure.returncode != 0, case
            detail = json.loads((p / "L_t0_verify_complete.failed.json").read_text())
            assert detail["failures"], case
            assert hashlib.sha256(result.read_bytes()).hexdigest() == before, case
            cases.append({"case": case, "rejected": True, "successful_output_preserved": True,
                          "failed_checks": [x["check"] for x in detail["failures"]]})
        (p / "L_t0_verify.json").write_text(json.dumps(raw))
        (p / "L_config.json").write_text((p / "L_config.json").read_text() + "\n")
        failure = run()
        assert failure.returncode != 0 and "input hash mismatch" in failure.stderr
        assert hashlib.sha256(result.read_bytes()).hexdigest() == before
        cases.append({"case": "input_hash_changed", "rejected": True, "successful_output_preserved": True})
        report = {"baseline_passed": True, "cases": cases, "network_used": False}
        (source / "L14_test_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("PASS: unchanged input + four negative cases; successful output preserved")


if __name__ == "__main__":
    main()

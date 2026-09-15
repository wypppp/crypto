#!/usr/bin/env python3
"""勘误 E2/E3 的数字，从两轮真链的逐条证据与运行清单重新计数。只读；输出 recount_numbers.json。"""
import json
from pathlib import Path

W = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
rounds = {"round1": W / "runs" / "realchain_20260911", "round2": W / "runs" / "realchain2_20260911"}
per_run, errors = [], []
for rnd, d in rounds.items():
    for f in sorted(d.glob("*.evidence.jsonl")):
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        rpc = [r for r in rows if r.get("kind") == "rpc"]
        bad = [r for r in rpc if (r.get("record") or {}).get("error")]
        per_run.append({"round": rnd, "run": f.name[:-len(".evidence.jsonl")], "rpc": len(rpc),
                        "rpc_errors": len(bad),
                        "run_footer": any(r.get("kind") == "run_footer" for r in rows)})
        errors += [{"round": rnd, "run": f.name[:-len(".evidence.jsonl")], "at": r.get("at"),
                    "stage": r.get("stage"), "candidate": r.get("candidate"),
                    "kind": r["record"]["error"].get("kind"),
                    "message": str(r["record"]["error"].get("message"))[:70]} for r in bad]
n_rpc = sum(x["rpc"] for x in per_run)
n_err = sum(x["rpc_errors"] for x in per_run)
complete = [x for x in per_run if x["run_footer"]]
wall = {r["tag"]: r["wall_s"] for r in
        (json.loads(x) for x in (rounds["round2"] / "runs.jsonl").read_text().splitlines() if x.strip())}
exits_r1 = {r["tag"]: r["exit"] for r in
            (json.loads(x) for x in (rounds["round1"] / "runs.jsonl").read_text().splitlines() if x.strip())}
serial = wall["serial"] + wall["resume_serial"]
parallel = wall["parallel"] + wall["resume_parallel"] + wall["resume_parallel2"]
res = {
    "per_run": per_run, "errors": errors,
    "all_rpc_execution_evidence": {"errors": n_err, "rpc": n_rpc, "rate": round(n_err / n_rpc, 5)},
    "complete_runs_only": {"errors": sum(x["rpc_errors"] for x in complete),
                           "rpc": sum(x["rpc"] for x in complete)},
    "iid_scenario_only": {"formula": "1-(1-6/2290)^105",
                          "value": round(1 - (1 - 6 / 2290) ** 105, 6),
                          "note": "requires independent, stable-rate calls and ~105 calls/candidate; "
                                  "NOT a measured candidate failure rate"},
    "round1_exit_codes": exits_r1,
    "round2_wall_s": {"first_pass_ratio": round(wall["parallel"] / wall["serial"], 4),
                      "serial_incl_resumes": round(serial, 1),
                      "parallel_incl_resumes": round(parallel, 1),
                      "ratio_incl_resumes": round(parallel / serial, 4)},
}
(OUT / "recount_numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: res[k] for k in ("all_rpc_execution_evidence", "complete_runs_only",
                                      "iid_scenario_only", "round1_exit_codes", "round2_wall_s")},
                 ensure_ascii=False, indent=1))

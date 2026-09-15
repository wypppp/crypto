"""真链串行 vs 两路并行同快照对照（规格 v1.15 §6.0）。

比较逐候选的全部结果字段；**只有**下列字段允许不同，并逐一说明原因：
  elapsed_s            —— 耗时，规格明确允许不同
  rpc_calls            —— 并行共享区块缓存，命中数不同会让 RPC 次数不同（用 block_cache_hit 证据核对）
  carried_from_checkpoint —— 续跑带出标记，仅续跑有
其余任何字段不同都判为**不一致**。不做"近似相等"。
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import evidence as E

R = Path(__file__).resolve().parent
ALLOWED = {"elapsed_s", "rpc_calls", "carried_from_checkpoint"}


def load(tag):
    doc = json.loads((R / f"{tag}.json").read_text(encoding="utf-8"))
    return doc, {r["index"]: r for r in doc["results"]}


def diff(a, b, path=""):
    """逐路径列出差异。"""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in ALLOWED and path == "":
                continue
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append((p, "<缺>", b[k]))
            elif k not in b:
                out.append((p, a[k], "<缺>"))
            else:
                out += diff(a[k], b[k], p)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, f"len={len(a)}", f"len={len(b)}"))
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append((path, a, b))
    return out


def evidence_summary(tag, doc):
    recs, d = E.read_evidence(R / f"{tag}.evidence.jsonl", report=True)
    mine = [r for r in recs if r.get("run_id") == doc["run_id"]]
    kinds = {}
    for r in mine:
        kinds[r.get("kind")] = kinds.get(r.get("kind"), 0) + 1
    gov = next((r for r in mine if r.get("kind") == "governor_report"), {})
    return {
        "complete": d.get("complete"),
        "bad_lines": d.get("bad_lines"),
        "unmatched_rpc_begin": d.get("unmatched_rpc_begin"),
        "orphan_rpc_end": d.get("orphan_rpc_end"),
        "has_run_footer": kinds.get("run_footer", 0) == 1,
        "block_cache_hit": kinds.get("block_cache_hit", 0),
        "etherscan": kinds.get("etherscan", 0),
        "rpc_records": kinds.get("rpc", 0),
        "rss_peak_kb": (gov.get("final") or {}).get("rss_peak_kb"),
        "cpu_s": (gov.get("final") or {}).get("cpu_s"),
        "stopped": gov.get("stopped"),
        "hard_backstop_verified": {k: v.get("verified") for k, v in
                                   ((gov.get("limits") or {}).get("hard_backstop", {})
                                    .get("applied", {}) or {}).items()},
    }


def main():
    runs = [json.loads(l) for l in (R / "runs.jsonl").read_text().splitlines() if l.strip()]
    ds, S = load("serial")
    dp, P = load("parallel")
    report = {"runs": runs, "pin": {}, "candidates": [], "mismatches": [], "allowed_diffs": [],
              "evidence": {}, "gate": {}, "resume": {}}

    # 同快照
    report["pin"] = {"serial": ds["finalized_snapshot"], "parallel": dp["finalized_snapshot"],
                     "same": ds["finalized_snapshot"] == dp["finalized_snapshot"]}
    # 同样本
    same_set = sorted(S) == sorted(P)
    report["same_candidate_set"] = same_set

    for idx in sorted(set(S) | set(P)):
        a, b = S.get(idx), P.get(idx)
        if a is None or b is None:
            report["mismatches"].append({"candidate": idx, "path": "<缺候选>",
                                         "serial": a is not None, "parallel": b is not None})
            continue
        ds_ = diff(a, b)
        for p, x, y in ds_:
            report["mismatches"].append({"candidate": idx, "path": p, "serial": x, "parallel": y})
        for k in ALLOWED:
            if a.get(k) != b.get(k):
                report["allowed_diffs"].append({"candidate": idx, "field": k,
                                                "serial": a.get(k), "parallel": b.get(k)})
        report["candidates"].append({
            "index": idx, "state": a.get("state"), "state_parallel": b.get("state"),
            "validation_passed": a.get("validation_passed"),
            "economic_eligible": a.get("economic_eligible"),
            "identical_except_allowed": not ds_})

    for tag, doc in (("serial", ds), ("parallel", dp)):
        report["evidence"][tag] = evidence_summary(tag, doc)
        g = doc.get("gate_stats") or {}
        report["gate"][tag] = {k: g.get(k) for k in
                               ("http_sent", "http_reserved", "http_rejected_after_wait",
                                "logical_requests", "max_calls")}
        report[f"acceptance_{tag}"] = {k: doc["acceptance"].get(k) for k in
                                       ("set_complete", "validation_passed", "process_completed",
                                        "incomplete", "missing_candidates", "worker_errors",
                                        "measurement_semantics_verified",
                                        "economic_results_eligible")}

    # 续跑
    rp = R / "resume_serial.json"
    if rp.is_file():
        dr, Rr = load("resume_serial")
        a = dr["acceptance"]
        carried_eq = all(
            not diff({k: v for k, v in Rr[i].items() if k != "carried_from_checkpoint"},
                     {k: v for k, v in S[i].items()})
            for i in S if i in Rr)
        report["resume"] = {
            "skipped": a.get("skipped_already_completed"),
            "carried": a.get("carried_from_checkpoint"),
            "evidence_chain_problems": a.get("evidence_chain_problems"),
            "checkpoint_results_unusable": a.get("checkpoint_results_unusable"),
            "validation_passed": a.get("validation_passed"),
            "carried_results_identical_to_serial": carried_eq,
            "new_rpc_after_startup": sum(1 for r in E.read_evidence(R / "resume_serial.evidence.jsonl")[0]
                                         if r.get("run_id") == dr["run_id"] and r.get("kind") == "rpc"
                                         and r.get("candidate") is not None),
            "evidence": evidence_summary("resume_serial", dr)}

    report["verdict"] = {
        "same_snapshot": report["pin"]["same"],
        "same_candidate_set": same_set,
        "field_mismatches": len(report["mismatches"]),
        "both_evidence_complete": all(v["complete"] for v in report["evidence"].values()),
        "both_exit_0": all(r["exit"] == 0 for r in runs if r["tag"] in ("serial", "parallel")),
    }
    (R / "compare_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                      default=str))
    print(json.dumps(report["verdict"], ensure_ascii=False))
    return 0 if (report["verdict"]["same_snapshot"] and same_set
                 and not report["mismatches"]) else 1


if __name__ == "__main__":
    sys.exit(main())

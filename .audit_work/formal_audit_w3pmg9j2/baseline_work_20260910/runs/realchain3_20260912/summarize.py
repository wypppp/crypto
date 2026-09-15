#!/usr/bin/env python3
"""第三轮真链对照的只读汇总：逐条 RPC 执行记录的错误清点、墙钟、产物 hash。

只读运行目录与本目录；不改任何历史文件，不联网。用法：
    python3 summarize.py <运行目录> [输出目录，默认本目录]
"""
import collections
import hashlib
import json
import sys
from pathlib import Path


def main():
    run = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parent
    man = [json.loads(x) for x in (run / "runs.jsonl").read_text().splitlines() if x.strip()]
    runs = [r for r in man if r.get("kind") == "run"]
    tags = [r["tag"] for r in runs]
    rpc = errs = eth = 0
    kinds, stages, per_run, when = collections.Counter(), collections.Counter(), collections.Counter(), []
    for t in tags:
        for line in (run / f"{t}.evidence.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") == "rpc":
                rpc += 1
                e = (r.get("record") or {}).get("error")      # 错误在 record 里，不在顶层
                if e:
                    errs += 1
                    per_run[t] += 1
                    kinds[e.get("kind") if isinstance(e, dict) else str(e)[:24]] += 1
                    stages[r.get("stage")] += 1
                    when.append({"run": t, "at": r.get("at"), "candidate": r.get("candidate"),
                                 "stage": r.get("stage"), "method": (r.get("record") or {}).get("method")})
            elif r.get("kind") == "etherscan":
                eth += 1
    s = sum(r["wall_s"] for r in runs if r["parallel"] == 1)
    p = sum(r["wall_s"] for r in runs if r["parallel"] > 1)
    first = {r["tag"]: r["wall_s"] for r in runs}
    inv = {
        "run_dir": run.name,
        "attempts": [{"tag": r["tag"], "parallel": r["parallel"], "exit": r["exit"],
                      "wall_s": r["wall_s"]} for r in runs],
        "rpc_records": rpc, "rpc_errors": errs,
        "rpc_error_fraction": round(errs / rpc, 6) if rpc else None,
        "rpc_error_kinds": dict(kinds), "rpc_error_stages": dict(stages),
        "rpc_errors_per_run": dict(per_run), "rpc_error_events": when,
        "etherscan_records": eth,
        "note_denominator": "分母只含逐条 RPC 执行记录；Etherscan 记录单列，不并入",
        "wall_s": {"serial_total_incl_resumes": round(s, 1),
                   "parallel_total_incl_resumes": round(p, 1),
                   "parallel_over_serial_pct": round(p / s * 100, 1) if s else None,
                   "first_pass_serial": first.get("serial"), "first_pass_parallel": first.get("parallel"),
                   "first_pass_pct": round(first["parallel"] / first["serial"] * 100, 1)
                   if first.get("serial") and first.get("parallel") else None},
        "note_wall": "首遍两侧完成集合不同（各有候选因传输错误未完成），首遍比值不能当加速比；"
                     "含续跑的合计也只是本次墙钟观察，不是吞吐结论",
    }
    (out / "rpc_error_inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n")
    h = {}
    for f in sorted(run.rglob("*")):
        if f.is_file():
            h[f"{run.name}/{f.relative_to(run)}"] = hashlib.sha256(f.read_bytes()).hexdigest()
    for f in sorted(out.glob("*")):
        if f.is_file() and f.name != "artifact_hashes.json":
            h[f"{out.name}/{f.name}"] = hashlib.sha256(f.read_bytes()).hexdigest()
    (out / "artifact_hashes.json").write_text(json.dumps(h, ensure_ascii=False, indent=2) + "\n")
    print(f"RPC {rpc} 条，错误 {errs} 条 = {errs / rpc * 100:.3f}%；Etherscan {eth} 条")
    print(f"墙钟 串行 {s:.1f}s / 并行 {p:.1f}s = {p / s * 100:.1f}%（均含续跑）")
    print(f"产物 hash {len(h)} 项")


if __name__ == "__main__":
    main()

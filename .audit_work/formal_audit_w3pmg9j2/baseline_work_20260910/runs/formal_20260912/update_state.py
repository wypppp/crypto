#!/usr/bin/env python3
"""扫描正式采集的各运行目录，汇总每批状态 -> collection_state.json。只读，随时可重跑。

批次目录按驱动的命名规则 runs/<name>_<attempt_id>/ 识别：
  formal_sub<NN>_*  串并行对照子集批（双侧 + 比较器）
  formal_main<NN>_* 主采集批（并行一侧）
"""
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent
SAMPLES = RUNS.parent / "pilot" / "formal_20260912"


def scan(run_dir):
    man = [json.loads(x) for x in (run_dir / "runs.jsonl").read_text().splitlines() if x.strip()]
    runs = [r for r in man if r.get("kind") == "run"]
    end = next((r for r in reversed(man) if r.get("kind") == "driver_end"), {})
    rpc = err = eth = 0
    for r in runs:
        ev = run_dir / f"{r['tag']}.evidence.jsonl"
        if not ev.is_file():
            continue
        for line in ev.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") == "rpc":
                rpc += 1
                if (rec.get("record") or {}).get("error"):
                    err += 1
            elif rec.get("kind") == "etherscan":
                eth += 1
    # 每侧最后一次运行的结果文件即该侧累计交付
    finals = {}
    for side in ("serial", "parallel"):
        tags = [r["tag"] for r in runs if (r["parallel"] == 1) == (side == "serial")]
        if not tags:
            continue
        doc = run_dir / f"{tags[-1]}.json"
        if doc.is_file():
            j = json.loads(doc.read_text())
            a = j.get("acceptance") or {}
            states = {}
            for x in j.get("results") or []:
                states[x["state"]] = states.get(x["state"], 0) + 1
            finals[side] = {"tag": tags[-1], "n_results": len(j.get("results") or []),
                            "states": states, "set_complete": a.get("set_complete"),
                            "validation_passed": a.get("validation_passed"),
                            "economic_results_eligible": a.get("economic_results_eligible"),
                            "incomplete": a.get("incomplete"),
                            "validation_unavailable": a.get("validation_unavailable"),
                            "validation_failed": a.get("validation_failed")}
    cmp_rep = sorted(run_dir.glob("compare_*.json"))
    verdict = json.loads(cmp_rep[0].read_text())["verdict"] if cmp_rep else None
    return {"run_dir": run_dir.name,
            "attempts": [{"tag": r["tag"], "parallel": r["parallel"], "exit": r["exit"],
                          "wall_s": r["wall_s"]} for r in runs],
            "wall_s_total": round(sum(r["wall_s"] for r in runs), 1),
            "rpc_records": rpc, "rpc_errors": err, "etherscan_records": eth,
            "driver_exit": end.get("driver_exit"), "compare_exit": end.get("compare_exit"),
            "compare_verdict": verdict, "finals": finals}


def main():
    man = json.loads((SAMPLES / "MANIFEST.json").read_text())
    state = {"snapshot_pin": None, "formal_sample_sha256": man["formal_sample_300.json"],
             "batches": {}, "subsets": {}}
    for d in sorted(RUNS.iterdir()):
        m = re.match(r"formal_(sub|main)(\d+)_", d.name)
        if not (d.is_dir() and m and (d / "runs.jsonl").is_file()):
            continue
        info = scan(d)
        meta = json.loads((d / "driver.json").read_text())
        info["sample"] = Path(meta["sample"]).name
        info["pin"] = meta["pin"]
        state["snapshot_pin"] = state["snapshot_pin"] or meta["pin"]
        (state["subsets"] if m.group(1) == "sub" else state["batches"])[m.group(2)] = info
    done_main = sum(1 for v in state["batches"].values() if v["driver_exit"] == 0)
    state["progress"] = {
        "subset_batches_declared": len(man["subset_batches"]),
        "subset_batches_passed": sum(1 for v in state["subsets"].values() if v["driver_exit"] == 0),
        "main_batches_declared": len(man["batches"]), "main_batches_passed": done_main,
        "rpc_records_so_far": sum(v["rpc_records"] for v in
                                  list(state["batches"].values()) + list(state["subsets"].values())),
        "rpc_errors_so_far": sum(v["rpc_errors"] for v in
                                 list(state["batches"].values()) + list(state["subsets"].values())),
        "wall_s_so_far": round(sum(v["wall_s_total"] for v in
                                   list(state["batches"].values()) + list(state["subsets"].values())), 1),
    }
    p = state["progress"]
    if p["rpc_records_so_far"]:
        p["rpc_error_fraction_so_far"] = round(p["rpc_errors_so_far"] / p["rpc_records_so_far"], 6)
    Path("collection_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(p, ensure_ascii=False, indent=2))
    for kind, group in (("对照子集", state["subsets"]), ("主采集", state["batches"])):
        for k, v in sorted(group.items()):
            vd = v["compare_verdict"]
            print(f"  {kind}{k}: driver={v['driver_exit']} 尝试={[(a['tag'], a['exit']) for a in v['attempts']]} "
                  f"RPC={v['rpc_records']}(错{v['rpc_errors']}) 墙钟={v['wall_s_total']}s "
                  f"比较={'通过' if vd and vd.get('passed') else vd and vd.get('failed')}")


if __name__ == "__main__":
    main()

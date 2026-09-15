#!/usr/bin/env python3
"""正式采集总账。只读，随时可重跑。

    python3 update_state.py --init    # 一次性：由冻结样本清单生成 campaign.json（已存在则拒绝）
    python3 update_state.py           # 扫描所有尝试 -> collection_state.json

设计要点（审查 v1.19-formal P1-3 / P1-4）：
* **批次绑定看内容，不看目录名**：由 `driver.json` 里的样本文件名 + 样本 sha256 + pin 绑定到
  campaign 声明的批次。改个目录名不能把 15 候选的对照批冒充成 20 候选的主批。
* **成本枚举所有已启动尝试**：用 `realchain_tools.run_compare.spent()` 遍历目录下全部证据文件，
  含中断、无 footer、末尾半行的；未收尾的子进程同样消耗了配额。同一批次的多个运行目录**累加**，不覆盖。
* **完成判定引用对应 invocation 的验收报告**：取最后一次 driver_end 的 invocation_id，
  读同名 `compare_<invocation_id>.json`，要求 verdict.passed、模式与声明一致、
  最终结果候选集合恰为该批声明成员。
* 已发生成本、完成状态、未知请求分别记录，互不冒充。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent
W = RUNS.parent
SAMPLES = W / "pilot" / "formal_20260912"
sys.path.insert(0, str(W / "realchain_tools"))
import run_compare as RC        # noqa: E402  复用驱动那份成本统计，规则只此一处


def init():
    out = HERE / "campaign.json"
    if out.exists():
        sys.exit(f"{out} 已存在，拒绝覆盖（campaign 声明一经生成即冻结）")
    man = json.loads((SAMPLES / "MANIFEST.json").read_text(encoding="utf-8"))
    drv = json.loads(next(RUNS.glob("formal_sub01_*/driver.json")).read_text(encoding="utf-8"))
    camp = {
        "declared_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "pin": drv["pin"], "formal_sample_sha256": man["formal_sample_300.json"],
        "universe_sha256": man["universe_sha256"], "seed": man["seed"],
        "code_sha256": {k: v for k, v in drv["code_sha256"].items() if k != "sample"},
        # 验收工具版本也登记：验收口径变了必须重新验收，不能沿用旧报告
        "verification_tool_sha256": {
            "compare_runs.py": __import__("hashlib").sha256(
                (W / "realchain_tools" / "compare_runs.py").read_bytes()).hexdigest(),
            "evidence.py": __import__("hashlib").sha256(
                (W / "evidence.py").read_bytes()).hexdigest()},
        "plan": "A：全量并行一侧测一遍 + 30 个子集串并行对照",
        "batches": [{"id": f"main{i + 1:02d}", "kind": "main", "sample": b["file"],
                     "sample_sha256": b["sha256"], "n": b["n"], "indices": b["indices"],
                     "sides": ["parallel"], "mode": "single:parallel"}
                    for i, b in enumerate(man["batches"])]
        + [{"id": f"sub{i + 1:02d}", "kind": "subset_pair", "sample": b["file"],
            "sample_sha256": b["sha256"], "n": b["n"], "indices": b["indices"],
            "sides": ["serial", "parallel"], "mode": "pair"}
           for i, b in enumerate(man["subset_batches"])],
    }
    out.write_text(json.dumps(camp, ensure_ascii=False, indent=2) + "\n")
    print(f"campaign.json 已生成：{len(camp['batches'])} 个批次声明，pin={camp['pin'][:22]}…")


def scan_dir(d, camp):        # noqa: C901
    """一个运行目录的观察。绑定失败也返回，记录为 unbound —— 不静默丢弃它的成本。"""
    drv = json.loads((d / "driver.json").read_text(encoding="utf-8"))
    rows = RC._read_manifest(d / "runs.jsonl")
    sample_name = Path(drv["sample"]).name
    sample_sha = (drv.get("code_sha256") or {}).get("sample")
    match = [b for b in camp["batches"]
             if b["sample"] == sample_name and b["sample_sha256"] == sample_sha]
    ends = [r for r in rows if r.get("kind") == "driver_end"]
    last = ends[-1] if ends else None
    inv = last.get("invocation_id") if last else None
    # 先取本次 invocation 的自动报告；它若出自旧版验收工具（无 mode / hash 不符），
    # 再找显式的重新验收报告 recompare_*.json。两者都必须由登记的验收工具版本产出。
    want_tool = camp.get("verification_tool_sha256") or {}
    cands = ([d / f"compare_{inv}.json"] if inv else []) + sorted(d.glob("recompare_*.json"))
    verdict = mode = None
    report_used = tool_ok = None
    for rp in cands:
        if not rp.is_file():
            continue
        rep = json.loads(rp.read_text(encoding="utf-8"))
        tool = rep.get("tool_sha256") or {}
        ok = bool(want_tool) and all(tool.get(k) == v for k, v in want_tool.items())
        if report_used is None or ok:
            verdict, mode, report_used, tool_ok = rep.get("verdict"), rep.get("mode"), rp.name, ok
        if ok:
            break
    # 各侧最终结果（该侧最后一次完成的运行）
    finals, states = {}, {}
    for side in ("serial", "parallel"):
        tags = [r["tag"] for r in rows if r.get("kind") == "run" and r.get("side") == side]
        if not tags:
            continue
        doc = d / f"{tags[-1]}.json"
        if doc.is_file():
            j = json.loads(doc.read_text(encoding="utf-8"))
            a = j.get("acceptance") or {}
            finals[side] = {"tag": tags[-1], "indices": sorted(r["index"] for r in j["results"]),
                            "set_complete": a.get("set_complete"),
                            "validation_passed": a.get("validation_passed"),
                            "economic_results_eligible": a.get("economic_results_eligible")}
            for r in j["results"]:
                states[r["state"]] = states.get(r["state"], 0) + 1
    obs = {"run_dir": d.name, "sample": sample_name, "sample_sha256": sample_sha,
           "pin": drv.get("pin"), "sides_declared_by_driver": drv.get("sides"),
           "batch_id": match[0]["id"] if len(match) == 1 else None,
           "bound": len(match) == 1,
           "attempts": [{"tag": r["tag"], "side": r.get("side"), "exit": r.get("exit"),
                         "wall_s": r.get("wall_s")} for r in rows if r.get("kind") == "run"],
           "started_not_finished": sorted({r["tag"] for r in rows if r.get("kind") == "run_start"}
                                          - {r["tag"] for r in rows if r.get("kind") == "run"}),
           "budget_stops": [r.get("over") for r in rows if r.get("kind") == "budget_stop"],
           "driver_exit": last.get("driver_exit") if last else None,
           "compare_invocation": inv, "compare_verdict": verdict, "compare_mode": mode,
           "compare_report": report_used, "compare_tool_current": tool_ok,
           "spent": RC.spent(d), "finals": finals, "states": states}
    return obs


def judge(batch, obs_list):
    """该批次是否**真的**完成。返回 (完成?, 理由清单)。"""
    problems, done = [], False
    if not obs_list:
        return False, ["no run directory bound to this batch"]
    for o in obs_list:
        why = []
        if o["driver_exit"] != 0:
            why.append(f"driver_exit={o['driver_exit']}")
        if o["pin"] != batch_pin:
            why.append(f"pin {o['pin']} != campaign pin")
        if not (o["compare_verdict"] or {}).get("passed"):
            why.append(f"compare not passed ({o['compare_invocation']})")
        if o["compare_mode"] != batch["mode"]:
            why.append(f"mode {o['compare_mode']} != declared {batch['mode']}")
        if not o["compare_tool_current"]:
            why.append(f"verification report {o['compare_report']} not from the registered "
                       f"verification tool version - re-verify with the current comparator")
        for side in batch["sides"]:
            f = o["finals"].get(side)
            if not f:
                why.append(f"no final result for side {side}")
            elif f["indices"] != sorted(batch["indices"]):
                why.append(f"{side}: result candidates != declared members "
                           f"({len(f['indices'])} vs {batch['n']})")
            elif not (f["set_complete"] and f["validation_passed"]):
                why.append(f"{side}: acceptance not clean")
        if o["started_not_finished"]:
            why.append(f"unfinished attempts: {o['started_not_finished']}")
        if why:
            problems.append({"run_dir": o["run_dir"], "problems": why})
        else:
            done = True
    return done, problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--init" in argv:
        return init()
    # 可注入路径：便于用受控假目录测试总账本身（默认就是本目录 / 上级 runs）
    global RUNS, SAMPLES
    here = HERE
    if "--runs-root" in argv:
        RUNS = Path(argv[argv.index("--runs-root") + 1]).resolve()
    if "--state-dir" in argv:
        here = Path(argv[argv.index("--state-dir") + 1]).resolve()
    if "--samples-name" in argv:
        SAMPLES = SAMPLES.parent / argv[argv.index("--samples-name") + 1]
    camp_p = here / "campaign.json"
    if not camp_p.is_file():
        sys.exit("缺 campaign.json，先运行 update_state.py --init")
    camp = json.loads(camp_p.read_text(encoding="utf-8"))
    global batch_pin
    batch_pin = camp["pin"]
    obs = [scan_dir(d, camp) for d in sorted(RUNS.iterdir())
           if d.is_dir() and (d / "driver.json").is_file() and (d / "runs.jsonl").is_file()
           and Path(json.loads((d / "driver.json").read_text())["sample"]).parent.name
           == SAMPLES.name]
    by_batch = {}
    for o in obs:
        by_batch.setdefault(o["batch_id"], []).append(o)     # None = 未绑定，同样保留
    batches = []
    for b in camp["batches"]:
        done, problems = judge(b, by_batch.get(b["id"], []))
        batches.append({**{k: b[k] for k in ("id", "kind", "sample", "n", "mode")},
                        "done": done, "problems": problems,
                        "run_dirs": [o["run_dir"] for o in by_batch.get(b["id"], [])]})
    # 成本：所有目录累加（含未绑定、含中断证据）
    cost = {"rpc": 0, "etherscan": 0, "wall_s": 0.0, "unmatched_rpc_begin": 0}
    for o in obs:
        for k in cost:
            cost[k] += o["spent"][k]
    cost["wall_s"] = round(cost["wall_s"], 1)
    done_ids = {b["id"] for b in batches if b["done"]}
    covered = sorted({i for b in camp["batches"] if b["id"] in done_ids and b["kind"] == "main"
                      for i in b["indices"]})
    all_main = sorted({i for b in camp["batches"] if b["kind"] == "main" for i in b["indices"]})
    state = {
        "campaign": {k: camp[k] for k in ("pin", "formal_sample_sha256", "plan")},
        "cost_so_far": cost,
        "cost_note": "已落盘的执行记录；unmatched_rpc_begin 是只有 begin、结果未知的请求，"
                     "既不算成功也不能当未发生。不等于账户计费总量",
        "progress": {
            "main_declared": sum(1 for b in camp["batches"] if b["kind"] == "main"),
            "main_done": sum(1 for b in batches if b["done"] and b["kind"] == "main"),
            "subset_declared": sum(1 for b in camp["batches"] if b["kind"] == "subset_pair"),
            "subset_done": sum(1 for b in batches if b["done"] and b["kind"] == "subset_pair"),
            "main_candidates_covered": len(covered), "main_candidates_total": len(all_main),
            "missing_candidates": sorted(set(all_main) - set(covered))[:20],
        },
        "unbound_run_dirs": [o["run_dir"] for o in by_batch.get(None, [])],
        "batches": batches, "observations": obs,
    }
    (here / "collection_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    p = state["progress"]
    print(json.dumps({"cost_so_far": cost, "progress": p,
                      "unbound_run_dirs": state["unbound_run_dirs"]}, ensure_ascii=False, indent=2))
    for b in batches:
        if b["run_dirs"] or b["done"]:
            print(f"  {b['id']}({b['n']}个,{b['mode']}): done={b['done']} dirs={b['run_dirs']}"
                  + (f" 问题={b['problems']}" if b["problems"] else ""))


if __name__ == "__main__":
    main()

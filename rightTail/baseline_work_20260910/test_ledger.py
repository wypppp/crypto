#!/usr/bin/env python3
"""正式采集总账（runs/formal_20260912/update_state.py）的守卫。

对应审核 v1.19-formal P1-3（漏计未收尾子进程的成本）与 P1-4（跨批"完成"没有绑定冻结样本）。
全部用受控假目录，不联网、不读真实运行目录、不改任何交付文件。
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent
LEDGER = W / "runs" / "formal_20260912" / "update_state.py"
ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name}" + (f"  — {detail}" if detail else ""))
    else:
        fail += 1
        print(f"  [FAIL] {name}" + (f"  — {detail}" if detail else ""))


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else json.dumps(b).encode()).hexdigest()


TOOL = {"compare_runs.py": sha((W / "realchain_tools" / "compare_runs.py").read_bytes()),
        "evidence.py": sha((W / "evidence.py").read_bytes())}
PIN = "25957718:0x" + "ab" * 32


def make_run_dir(root, name, *, sample, sample_sha, indices, sides=("parallel",), pin=PIN,
                 n_rpc=10, footer=True, finished=True, mode="single:parallel", tool=TOOL,
                 verdict_passed=True, invocation="inv1"):
    d = root / name
    d.mkdir(parents=True)
    (d / "driver.json").write_text(json.dumps({
        "attempt_id": "a1", "sample": f"pilot/formal_TEST/{sample}", "pin": pin, "sides": list(sides),
        "code_sha256": {"pilot_measure.py": "p", "evidence.py": "e", "spec": "s",
                        "sample": sample_sha, "primitives": "pr"},
        "runtime_params": {"slot_limit": 32}}))
    rows = []
    for side in sides:
        tag = side
        rows.append({"kind": "run_start", "tag": tag, "side": side, "invocation_id": invocation})
        if finished:
            rows.append({"kind": "run", "tag": tag, "side": side, "exit": 0, "wall_s": 12.5,
                         "parallel": 1 if side == "serial" else 2, "invocation_id": invocation})
        ev = [{"seq": i, "kind": "rpc", "run_id": "r", "record": {"method": "eth_getCode"}}
              for i in range(n_rpc)]
        ev.append({"seq": n_rpc, "kind": "etherscan", "run_id": "r", "candidate": indices[0]})
        if footer:
            ev.append({"seq": n_rpc + 1, "kind": "run_footer", "run_id": "r"})
        (d / f"{tag}.evidence.jsonl").write_text("".join(json.dumps(x) + "\n" for x in ev))
        (d / f"{tag}.json").write_text(json.dumps({
            "run_id": "r", "parallel": 1 if side == "serial" else 2,
            "finalized_snapshot": {"number": int(pin.split(":")[0]), "hash": pin.split(":")[1]},
            "acceptance": {"set_complete": True, "validation_passed": True,
                           "economic_results_eligible": False},
            "results": [{"index": i, "state": "measured_exit"} for i in indices]}))
    rows.append({"kind": "driver_end", "invocation_id": invocation, "driver_exit": 0,
                 "compare_exit": 0})
    (d / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    rep = {"mode": mode, "verdict": {"passed": verdict_passed, "failed": [], "required_absent": [],
                                     "n_checks": 30}}
    if tool:
        rep["tool_sha256"] = tool
    (d / f"compare_{invocation}.json").write_text(json.dumps(rep))
    return d


def ledger(tmp):
    p = subprocess.run([sys.executable, str(LEDGER), "--runs-root", str(tmp / "runs"),
                        "--state-dir", str(tmp / "state"), "--samples-name", "formal_TEST"],
                       capture_output=True, text=True, timeout=120)
    st = tmp / "state" / "collection_state.json"
    return p, (json.loads(st.read_text()) if st.is_file() else {})


def setup(main_idx, sub_idx):
    """临时 campaign：一个 20 候选主批 + 一个 15 候选对照批。"""
    tmp = Path(tempfile.mkdtemp(prefix="rta-ledger-"))
    (tmp / "runs").mkdir()
    (tmp / "state").mkdir()
    main_sha, sub_sha = sha({"m": main_idx}), sha({"s": sub_idx})
    camp = {"pin": PIN, "formal_sample_sha256": "f", "plan": "test",
            "verification_tool_sha256": TOOL,
            "batches": [
                {"id": "main01", "kind": "main", "sample": "batch_01.json", "sample_sha256": main_sha,
                 "n": len(main_idx), "indices": main_idx, "sides": ["parallel"],
                 "mode": "single:parallel"},
                {"id": "sub01", "kind": "subset_pair", "sample": "subset_pair_01.json",
                 "sample_sha256": sub_sha, "n": len(sub_idx), "indices": sub_idx,
                 "sides": ["serial", "parallel"], "mode": "pair"}]}
    (tmp / "state" / "campaign.json").write_text(json.dumps(camp, ensure_ascii=False, indent=2))
    return tmp, main_sha, sub_sha


MAIN = list(range(100, 120))      # 20 个
SUB = list(range(200, 215))       # 15 个

print("1 正对照：按声明完成的主批被计为完成")
tmp, msha, ssha = setup(MAIN, SUB)
make_run_dir(tmp / "runs", "formal_main01_x", sample="batch_01.json", sample_sha=msha, indices=MAIN)
p, st = ledger(tmp)
check("完整主批：done=True、候选覆盖 20/20、成本计入",
      st["progress"]["main_done"] == 1 and st["progress"]["main_candidates_covered"] == 20
      and st["cost_so_far"]["rpc"] == 10 and st["cost_so_far"]["etherscan"] == 1,
      f"progress={st['progress']['main_done']} cost={st['cost_so_far']}")
shutil.rmtree(tmp)

print("\n2 P1-4：只改目录名不能把 15 候选的对照批冒充 20 候选的主批")
tmp, msha, ssha = setup(MAIN, SUB)
make_run_dir(tmp / "runs", "formal_main01_controlled", sample="subset_pair_01.json",
             sample_sha=ssha, indices=SUB, sides=("serial", "parallel"), mode="pair")
p, st = ledger(tmp)
b = {x["id"]: x for x in st["batches"]}
check("目录名冒充：main01 仍未完成、主批候选覆盖 0，且该目录按内容绑定到 sub01",
      b["main01"]["done"] is False and st["progress"]["main_candidates_covered"] == 0
      and b["sub01"]["run_dirs"] == ["formal_main01_controlled"] and b["sub01"]["done"] is True,
      f"main01={b['main01']['done']} covered={st['progress']['main_candidates_covered']} "
      f"sub01_dirs={b['sub01']['run_dirs']}")
shutil.rmtree(tmp)

print("\n3 P1-3：未收尾的子运行成本必须计入，且该批不算完成")
tmp, msha, ssha = setup(MAIN, SUB)
d = make_run_dir(tmp / "runs", "formal_main01_y", sample="batch_01.json", sample_sha=msha,
                 indices=MAIN, n_rpc=10)
# 再加一份"启动了但没收尾"的证据：无 footer、清单只有 run_start、末尾半行
(d / "parallel_resume1.evidence.jsonl").write_text(
    "".join(json.dumps({"seq": i, "kind": "rpc", "run_id": "r2",
                        "record": {"method": "eth_getBlockByNumber"}}) + "\n" for i in range(698))
    + '{"seq": 698, "kind": "rpc", "run_id": "r2", "reco')
rows = [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines()]
rows.insert(-1, {"kind": "run_start", "tag": "parallel_resume1", "side": "parallel",
                 "invocation_id": "inv1"})
(d / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
p, st = ledger(tmp)
b = {x["id"]: x for x in st["batches"]}
o = st["observations"][0]
check("未收尾子运行的 698 次 RPC 计入成本（旧版只按清单遍历会漏掉）",
      st["cost_so_far"]["rpc"] == 708 and o["spent"]["unmatched_rpc_begin"] == 0
      and "parallel_resume1.evidence.jsonl" in o["spent"]["incomplete_evidence"],
      f"rpc={st['cost_so_far']['rpc']} incomplete={o['spent']['incomplete_evidence']}")
check("有已启动未收尾的尝试时该批不算完成，并列出它",
      b["main01"]["done"] is False and o["started_not_finished"] == ["parallel_resume1"],
      f"done={b['main01']['done']} unfinished={o['started_not_finished']}")
shutil.rmtree(tmp)

print("\n4 其它不得放行的情形")
for name, kw, want in [
        ("候选数不足（15 报成主批的 20）", dict(indices=SUB[:15]), "result candidates"),
        ("pin 与 campaign 不符", dict(pin="25000000:0x" + "cd" * 32), "pin"),
        ("验收报告没有工具 hash（旧版验收工具）", dict(tool=None), "registered"),
        ("验收模式与声明不符", dict(mode="pair"), "mode"),
        ("验收结论不是通过", dict(verdict_passed=False), "compare not passed")]:
    tmp, msha, ssha = setup(MAIN, SUB)
    make_run_dir(tmp / "runs", "formal_main01_z", sample="batch_01.json", sample_sha=msha,
                 **{"indices": MAIN, **kw})
    p, st = ledger(tmp)
    b = {x["id"]: x for x in st["batches"]}
    probs = json.dumps(b["main01"]["problems"], ensure_ascii=False)
    check(f"{name}：不计为完成且说明原因",
          b["main01"]["done"] is False and want in probs,
          f"done={b['main01']['done']} problems={probs[:110]}")
    shutil.rmtree(tmp)

print("\n5 样本 sha 与声明不符：不绑定任何批次，但成本仍然入账")
tmp, msha, ssha = setup(MAIN, SUB)
make_run_dir(tmp / "runs", "formal_main01_w", sample="batch_01.json", sample_sha="deadbeef",
             indices=MAIN, n_rpc=33)
p, st = ledger(tmp)
check("未绑定目录被单列且成本入账（不静默丢弃）",
      st["unbound_run_dirs"] == ["formal_main01_w"] and st["cost_so_far"]["rpc"] == 33
      and st["progress"]["main_done"] == 0,
      f"unbound={st['unbound_run_dirs']} cost={st['cost_so_far']['rpc']}")
shutil.rmtree(tmp)

print("\n6 同一批次的多个运行目录：成本累加，不被后者覆盖")
tmp, msha, ssha = setup(MAIN, SUB)
make_run_dir(tmp / "runs", "formal_main01_a", sample="batch_01.json", sample_sha=msha,
             indices=MAIN, n_rpc=40, finished=False, footer=False, invocation="i1")
make_run_dir(tmp / "runs", "formal_main01_b", sample="batch_01.json", sample_sha=msha,
             indices=MAIN, n_rpc=10, invocation="i2")
p, st = ledger(tmp)
b = {x["id"]: x for x in st["batches"]}
check("两个目录的成本相加（40+10 次 RPC），批次因其中一个完成而完成、两目录都列出",
      st["cost_so_far"]["rpc"] == 50 and sorted(b["main01"]["run_dirs"]) ==
      ["formal_main01_a", "formal_main01_b"] and b["main01"]["done"] is True,
      f"rpc={st['cost_so_far']['rpc']} dirs={b['main01']['run_dirs']} done={b['main01']['done']}")
shutil.rmtree(tmp)

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

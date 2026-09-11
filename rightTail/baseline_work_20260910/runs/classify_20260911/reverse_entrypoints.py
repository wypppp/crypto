#!/usr/bin/env python3
"""验收入口的新旧对照：同一组受控场景，分别交给**旧**入口（历史原字节）与**新**入口。

旧比较器 `runs/realchain2_20260911/compare.py` 与旧驱动 `run_compare.sh` 都在临时副本里执行
（审核 v1.16 的做法），绝不在交付目录执行。新入口是 `realchain_tools/`。
只写本目录的 reverse_entrypoints.json 与临时目录；不读凭据、不联网。
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

W = Path(__file__).resolve().parents[2]
R = W / "runs" / "realchain2_20260911"
T = W / "realchain_tools"
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(W))

CHAIN = ("serial", "resume_serial", "parallel", "resume_parallel", "resume_parallel2")
PIN = "25950799:0xe7e5d3e8b2be05e6e1c537f1a8ea534121c5defc9b6e7ea8edc54d01dd446e82"
EXP = [x.split()[0] for x in (R / "code_hashes_at_launch.txt").read_text().splitlines()]
before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in R.iterdir() if p.is_file()}

old = types.ModuleType("old_compare")
old.__file__ = str(R / "compare.py")
exec(compile((R / "compare.py").read_text(), old.__file__, "exec"), old.__dict__)


def mutate(dst, scene):
    def jl(p, fn):
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        p.write_text("".join(json.dumps(x) + "\n" for x in fn(rows)))
    if scene in ("one_wei", "validation_flip"):
        p = dst / "resume_parallel2.json"
        d = json.loads(p.read_text())
        c = next(x for x in d["results"] if x["index"] == 478595)
        if scene == "one_wei":
            c["exit"]["cash_in"] += 1
        else:
            c["state_validation_exit"]["passed"] = not c["state_validation_exit"]["passed"]
        p.write_text(json.dumps(d))
    if scene == "missing_footer":
        jl(dst / "serial.evidence.jsonl", lambda rs: [x for x in rs if x["kind"] != "run_footer"])
    if scene == "final_exit_1":
        jl(dst / "runs.jsonl",
           lambda rs: [dict(x, exit=1) if x["tag"] == "resume_parallel2" else x for x in rs])
    if scene == "missing_final_run_entries":
        jl(dst / "runs.jsonl",
           lambda rs: [x for x in rs if x["tag"] not in ("resume_serial", "resume_parallel2")])


comparator = []
for scene in ("baseline", "one_wei", "validation_flip", "missing_footer", "final_exit_1",
              "missing_final_run_entries"):
    with tempfile.TemporaryDirectory(prefix="rta-rev-cmp-") as td:
        dst = Path(td) / "run"
        dst.mkdir()
        for tag in CHAIN:
            for suf in (".json", ".evidence.jsonl"):
                shutil.copyfile(R / (tag + suf), dst / (tag + suf))
        for f in ("runs.jsonl", "serial.checkpoint.jsonl", "parallel.checkpoint.jsonl"):
            shutil.copyfile(R / f, dst / f)
        mutate(dst, scene)
        old.R = dst
        with contextlib.redirect_stdout(io.StringIO()):
            old_rc = old.main("resume_serial", "resume_parallel2", CHAIN)
        p = subprocess.run([sys.executable, str(T / "compare_runs.py"), "--dir", str(dst),
                            "--serial", "serial,resume_serial",
                            "--parallel", "parallel,resume_parallel,resume_parallel2",
                            "--sample", str(W / "pilot" / "dev_sample.json"), "--pin", PIN,
                            "--expect-script-sha", EXP[0], "--expect-evidence-sha", EXP[1],
                            "--expect-spec-sha", EXP[2], "--out", str(Path(td) / "new.json")],
                           capture_output=True, text=True, timeout=300)
        rep = json.loads((Path(td) / "new.json").read_text())
        comparator.append({"scene": scene, "old_exit": old_rc, "new_exit": p.returncode,
                           "new_failed": rep["verdict"]["failed"][:6]})
        print(json.dumps(comparator[-1], ensure_ascii=False), flush=True)

# ---- 驱动：三个子运行都失败（替身返回 2）----
driver = {}
with tempfile.TemporaryDirectory(prefix="rta-rev-drv-") as td:
    root = Path(td)
    r = root / "runs" / "realchain2_20260911"
    r.mkdir(parents=True)
    shutil.copyfile(R / "run_compare.sh", r / "run_compare.sh")
    (r / "launch.py").write_text("import sys\nprint('CONTROLLED_PRECONDITION_FAILURE')\nsys.exit(2)\n")
    (r / "runs.jsonl").write_text(json.dumps({"tag": "prior_attempt", "exit": 1}) + "\n")
    (r / "serial.stdout.log").write_text("HISTORICAL_STDOUT\n")
    (root / "bin").mkdir()
    (root / "bin" / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (root / "bin" / "sleep").chmod(0o755)
    env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ["PATH"])
    p = subprocess.run(["bash", str(r / "run_compare.sh")], env=env, capture_output=True,
                       text=True, timeout=30)
    rows = [json.loads(x) for x in (r / "runs.jsonl").read_text().splitlines()]
    driver["old"] = {"driver_exit": p.returncode, "child_exits": [x["exit"] for x in rows
                                                                  if x.get("tag") != "prior_attempt"],
                     "prior_manifest_row_retained": any(x.get("tag") == "prior_attempt" for x in rows),
                     "historical_stdout_retained":
                         "HISTORICAL_STDOUT" in (r / "serial.stdout.log").read_text()}

with tempfile.TemporaryDirectory(prefix="rta-rev-drv2-") as td:
    runs = Path(td) / "runs"
    prior = runs / "prior_attempt"
    prior.mkdir(parents=True)
    (prior / "runs.jsonl").write_text(json.dumps({"tag": "prior_attempt", "exit": 1}) + "\n")
    (prior / "serial.stdout.log").write_text("HISTORICAL_STDOUT\n")
    prior_hash = {f.name: f.read_bytes() for f in prior.iterdir()}
    env = {k: v for k, v in os.environ.items() if k not in ("ETH_RPC_URL", "ETHERSCAN_API_KEY")}
    env["RT_FAKE_PLAN"] = json.dumps({"serial": "exit:2", "parallel": "exit:2"})
    p = subprocess.run([sys.executable, str(T / "run_compare.py"), "--name", "t",
                        "--runs-root", str(runs), "--sample", str(W / "pilot" / "dev_sample.json"),
                        "--pin", PIN, "--launch", str(T / "fake_launch.py"), "--gap-s", "0",
                        "--max-resumes", "1", "--compare"],
                       env=env, capture_output=True, text=True, timeout=120, cwd=W)
    new_dir = [d for d in runs.iterdir() if d.name != "prior_attempt"]
    rows = [json.loads(x) for x in (new_dir[0] / "runs.jsonl").read_text().splitlines()] \
        if len(new_dir) == 1 else []
    driver["new"] = {"driver_exit": p.returncode,
                     "child_exits": [x["exit"] for x in rows if x.get("kind") == "run"],
                     "new_attempt_dir_created": len(new_dir) == 1,
                     "prior_dir_bytes_retained":
                         {f.name: f.read_bytes() for f in prior.iterdir()} == prior_hash}

after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in R.iterdir()
         if p.is_file() and p.name in before}
res = {"comparator": comparator, "driver": driver,
       "delivery_dir_unchanged": after == before}
print(json.dumps(driver, ensure_ascii=False, indent=1))
print("delivery_dir_unchanged", res["delivery_dir_unchanged"])
(OUT / "reverse_entrypoints.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
ok = (res["delivery_dir_unchanged"]
      and all(c["new_exit"] == (0 if c["scene"] == "baseline" else 1) for c in comparator)
      and [c["old_exit"] for c in comparator] == [0, 1, 1, 0, 0, 0]
      and driver["old"]["driver_exit"] == 0 and driver["new"]["driver_exit"] == 1)
sys.exit(0 if ok else 1)

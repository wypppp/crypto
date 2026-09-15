#!/usr/bin/env python3
"""审核 v1.17 的工具反例：同一组场景分别交给 **v1.17 审核快照**的比较器/驱动与当前的。

旧工具在临时沙箱里运行（沙箱 = 审核快照源码 + 指向冻结包与台账的链接）；
第二轮真链证据只以符号链接读入，被改动的检查点先解除链接再写副本。
只写本目录的 reverse_tools_v117.json 与临时目录；不读凭据、不联网。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parents[2]
AUD = W / "audit_v117_20260911"
R2 = W / "runs" / "realchain2_20260911"
OUT = Path(__file__).resolve().parent
PIN = "25950799:0xe7e5d3e8b2be05e6e1c537f1a8ea534121c5defc9b6e7ea8edc54d01dd446e82"
EXP = [x.split()[0] for x in (R2 / "code_hashes_at_launch.txt").read_text().splitlines()]
PRIM = hashlib.sha256((W.parent / "baseline_20260909" / "verify_capabilities.py").read_bytes()).hexdigest()
RUNTIME = json.dumps({"slot_limit": 32, "diagnostics": True, "cutoff_block": 24781026,
                      "amount_wei": 50000000000000000})
before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in R2.iterdir() if p.is_file()}

tmp = Path(tempfile.mkdtemp(prefix="rta-rev117-"))
old = tmp / "bw"                               # v1.17 审核快照沙箱
(old / "realchain_tools").mkdir(parents=True)
(tmp / "baseline_20260909").symlink_to(W.parent / "baseline_20260909")
for name, src in [("pilot_measure.py", "pilot_measure.audited.py"), ("evidence.py", "evidence.audited.py"),
                  ("fake_chain.py", "fake_chain.audited.py"), ("audit_flow.py", "audit_flow.audited.py")]:
    shutil.copyfile(AUD / src, old / name)
for name, src in [("compare_runs.py", "compare_runs.audited.py"), ("run_compare.py", "run_compare.audited.py"),
                  ("fake_launch.py", "fake_launch.audited.py")]:
    shutil.copyfile(AUD / src, old / "realchain_tools" / name)
shutil.copyfile(W / "MEASUREMENT_SPEC.v1.17.md", old / "MEASUREMENT_SPEC.v1.17.md")
(old / "universe_run").symlink_to(W / "universe_run")
(old / "runs").mkdir()


def r2_copy(mode):
    d = Path(tempfile.mkdtemp(prefix="rta-rev117-in-", dir=tmp))
    for p in R2.iterdir():
        if p.is_file():
            (d / p.name).symlink_to(p)
    if mode != "baseline":
        cp = d / "serial.checkpoint.jsonl"
        rows = [json.loads(x) for x in cp.read_text().splitlines() if x.strip()]
        if mode == "primitives_changed":
            rows[0]["primitives_sha256"] = "0" * 64
        if mode == "runtime_changed":
            rows[0]["runtime_params"]["slot_limit"] = 0
        if mode == "bindings_deleted":
            del rows[0]["primitives_sha256"], rows[0]["runtime_params"]
        cp.unlink()
        cp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def cmp(tools_root, d, new):
    out = Path(tempfile.mkdtemp(prefix="rta-rev117-o-", dir=tmp)) / "r.json"
    cmd = [sys.executable, str(tools_root / "realchain_tools" / "compare_runs.py"), "--dir", str(d),
           "--serial", "serial,resume_serial", "--parallel", "parallel,resume_parallel,resume_parallel2",
           "--sample", str(W / "pilot" / "dev_sample.json"), "--pin", PIN,
           "--expect-script-sha", EXP[0], "--expect-evidence-sha", EXP[1], "--expect-spec-sha", EXP[2],
           "--out", str(out)]
    if new:
        cmd[-2:-2] = ["--expect-primitives-sha", PRIM, "--expect-runtime-params", RUNTIME]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.read_text())
    return {"exit": p.returncode, "n_checks": rep["verdict"]["n_checks"],
            "failed": rep["verdict"]["failed"][:6]}


binding = []
for mode in ("baseline", "primitives_changed", "runtime_changed", "bindings_deleted"):
    d = r2_copy(mode)
    row = {"case": mode, "old": cmp(old, d, False), "new": cmp(W, d, True)}
    binding.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)

# ---- 启动即断连 + 续跑补齐 ----
sample = tmp / "sample.json"
sys.path.insert(0, str(W))
import evidence as E  # noqa: E402
import pilot_measure as P  # noqa: E402
sample.write_text(json.dumps(dict(universe_sha256=E.sha256_file(P.UNIVERSE), n=2, sample=[
    dict(index=i, pair="0x" + "ab" * 20, token="0x" + "cd" * 20, created_block=24140000) for i in (1, 2)])))
fpin = f"25900000:0x{25900000:064x}"
wrapper = tmp / "old_startup_launch.py"        # 与审核探针同法：只给首次串行的 eth_chainId 注入传输错误
wrapper.write_text(f'''import sys, runpy
from pathlib import Path
from unittest.mock import patch
W = Path({str(old)!r})
sys.path.insert(0, str(W))
import pilot_measure as P
from fake_chain import FakeRpc
tag = Path(sys.argv[sys.argv.index("--out") + 1]).stem
orig = FakeRpc.request
def request(self, method, params):
    if tag == "serial" and method == "eth_chainId":
        self.records.append(dict(method=method, params=params,
                                 error=dict(kind="transport", message="controlled startup EOF")))
        raise P.V.RpcFailure("transport", "controlled startup EOF")
    return orig(self, method, params)
with patch.object(FakeRpc, "request", request):
    runpy.run_path(str(W / "realchain_tools/fake_launch.py"), run_name="__main__")
''')


def drive(root, launch, plan):
    runs = Path(tempfile.mkdtemp(prefix="rta-rev117-runs-", dir=tmp))
    env = {k: v for k, v in os.environ.items() if k not in ("ETH_RPC_URL", "ETHERSCAN_API_KEY")}
    env["RT_FAKE_PLAN"] = json.dumps(plan)
    p = subprocess.run([sys.executable, str(root / "realchain_tools" / "run_compare.py"), "--name", "s",
                        "--runs-root", str(runs), "--sample", str(sample), "--pin", fpin,
                        "--launch", str(launch), "--gap-s", "0", "--max-resumes", "1", "--compare"],
                       capture_output=True, text=True, timeout=300, env=env, cwd=root)
    d = next(runs.iterdir())
    m = [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines() if x.strip()]
    rep = json.loads(next(d.glob("compare_*.json")).read_text()) if list(d.glob("compare_*.json")) else {}
    return {"driver_exit": p.returncode,
            "attempts": [(r["tag"], r["exit"]) for r in m if r.get("kind") == "run"],
            "compare_exit": m[-1].get("compare_exit"),
            "compare_failed": (rep.get("verdict") or {}).get("failed", [])[:6],
            "roles": {t: v.get("role") for t, v in (rep.get("runs") or {}).items()}}


startup = {"old": drive(old, wrapper, {}),
           "new": drive(W, W / "realchain_tools" / "fake_launch.py", {"serial": "startup_fail"})}
print(json.dumps(startup, ensure_ascii=False, indent=1))

after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in R2.iterdir()
         if p.is_file() and p.name in before}
res = {"binding": binding, "startup_recovery": startup, "delivery_dir_unchanged": after == before}
(OUT / "reverse_tools_v117.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
shutil.rmtree(tmp, ignore_errors=True)
ok = (res["delivery_dir_unchanged"]
      and [r["old"]["exit"] for r in binding] == [0, 0, 0, 0]
      and [r["new"]["exit"] for r in binding] == [0, 1, 1, 1]
      and startup["old"]["driver_exit"] == 1 and startup["old"]["compare_exit"] == 1
      and startup["new"]["driver_exit"] == 0 and startup["new"]["compare_exit"] == 0)
print("delivery_dir_unchanged", res["delivery_dir_unchanged"], "OK" if ok else "UNEXPECTED")
sys.exit(0 if ok else 1)

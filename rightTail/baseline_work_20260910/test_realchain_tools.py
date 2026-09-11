#!/usr/bin/env python3
"""真链对照验收入口（realchain_tools/）的受控测试 —— 审核 v1.16 两项 P1。

A. 比较器 compare_runs.py：用第二轮**既有真链证据**的副本做正对照，再逐项破坏
   （含审核的 5 个放行反例），断言退出码与失败项。
B. 驱动 run_compare.py：用 fake_launch.py（不读凭据、不联网）驱动，断言子运行失败
   反映到退出码、历史清单与日志不被截断/覆盖、续跑必须显式指定。
C. 历史交付目录一个字节都不能变（本测试结束时核对）。

全部离线。副本目录里未改动的文件是指向原件的符号链接，被改动的文件先解除链接
再写新文件 —— 绝不透过链接写回原件；C 节兜底核对。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent
T = W / "realchain_tools"
R2 = W / "runs" / "realchain2_20260911"
sys.path.insert(0, str(T))
import compare_runs as C  # noqa: E402

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


R2_BEFORE = tree_hashes(R2)
PIN = "25950799:0xe7e5d3e8b2be05e6e1c537f1a8ea534121c5defc9b6e7ea8edc54d01dd446e82"
EXPECT = dict(zip(("script", "evidence", "spec", "sample"),
                  [line.split()[0] for line in
                   (R2 / "code_hashes_at_launch.txt").read_text().splitlines()]))
SERIAL = "serial,resume_serial"
PARALLEL = "parallel,resume_parallel,resume_parallel2"


def r2_copy(src=None):
    src = Path(src or R2)
    d = Path(tempfile.mkdtemp(prefix="rta-cmp-"))
    for p in src.iterdir():
        if p.is_file():
            (d / p.name).symlink_to(p.resolve())
    return d


PRIM = hashlib.sha256((W.parent / "baseline_20260909" / "verify_capabilities.py")
                      .read_bytes()).hexdigest()
RUNTIME = {"slot_limit": 32, "diagnostics": True, "cutoff_block": 24781026,
           "amount_wei": 50000000000000000}


def mutate(d, name, fn):
    """解除链接后写新文件；fn 收旧文本、返回新文本（返回 None ⇒ 删除该文件）。"""
    p = d / name
    old = p.read_text(encoding="utf-8")
    p.unlink()
    new = fn(old)
    if new is not None:
        p.write_text(new, encoding="utf-8")


def jl_edit(fn):
    def _f(text):
        rows = [json.loads(x) for x in text.splitlines() if x.strip()]
        return "".join(json.dumps(r) + "\n" for r in fn(rows))
    return _f


def j_edit(fn):
    def _f(text):
        d = json.loads(text)
        fn(d)
        return json.dumps(d)
    return _f


def compare(d, serial=SERIAL, parallel=PARALLEL, extra=(), out=None, sample=None, pin=PIN,
            spec=None, prim=None, runtime=None, script=None, evidence=None):
    out = out or Path(tempfile.mkdtemp(prefix="rta-cmp-out-")) / "report.json"
    rt = runtime if isinstance(runtime, str) else json.dumps(runtime or RUNTIME)
    cmd = [sys.executable, str(T / "compare_runs.py"), "--dir", str(d),
           "--serial", serial, "--parallel", parallel,
           "--sample", str(sample or W / "pilot" / "dev_sample.json"), "--pin", pin,
           "--expect-script-sha", script or EXPECT["script"],
           "--expect-evidence-sha", evidence or EXPECT["evidence"],
           "--expect-spec-sha", spec or EXPECT["spec"],
           "--expect-primitives-sha", prim or PRIM, "--expect-runtime-params", rt,
           "--out", str(out), *extra]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    try:
        rep = json.loads(out.read_text()) if out.is_file() else {}
    except ValueError:
        rep = {}                       # 例如"输出已存在"用例里预置的非 JSON 文件
    return p.returncode, rep, p


def failed(rep):
    return (rep.get("verdict") or {}).get("failed", [])


# ======================================================================= A
print("A 比较器：正对照 + 逐项破坏（副本目录，原件只读）")
rc, rep, _ = compare(r2_copy())
check("正对照：第二轮既有证据全部必需检查通过、退出 0",
      rc == 0 and rep["verdict"]["passed"] and not rep["verdict"]["required_absent"],
      f"rc={rc} failed={failed(rep)[:4]} n={rep.get('verdict', {}).get('n_checks')}")
check("正对照：8 个候选逐一回溯并比较", len(rep.get("candidates", [])) == 8,
      str(len(rep.get("candidates", []))))

CASES = []


def case(name, want_fail_prefix, prep, **kw):
    CASES.append((name, want_fail_prefix, prep, kw))


# —— 审核 v1.16 的五个反例（旧比较器对后三个仍退出 0）——
def _one_wei(d):
    def f(doc):
        c = next(x for x in doc["results"] if x["index"] == 478595)
        c["exit"]["cash_in"] += 1
    mutate(d, "resume_parallel2.json", j_edit(f))


def _vflip(d):
    def f(doc):
        c = next(x for x in doc["results"] if x["index"] == 478595)
        c["state_validation_exit"]["passed"] = not c["state_validation_exit"]["passed"]
    mutate(d, "resume_parallel2.json", j_edit(f))


case("cash_in 改 1 wei", "results_identical_except_allowed", _one_wei)
case("出场校验 passed 翻转", "results_identical_except_allowed", _vflip)
case("删除一份证据的 footer", "evidence_complete:serial",
     lambda d: mutate(d, "serial.evidence.jsonl",
                      jl_edit(lambda rs: [r for r in rs if r["kind"] != "run_footer"])))
case("最终并行运行退出码改为 1", "final_exit_0:parallel",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: [dict(r, exit=1) if r["tag"] == "resume_parallel2" else r for r in rs])))
case("删除两份最终运行的执行记录（旧版空 all() 放行）", "manifest_entry_unique:resume_serial",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: [r for r in rs if r["tag"] not in ("resume_serial", "resume_parallel2")])))
# —— 其余必需条件 ——
case("清单里同一运行出现两次（归属歧义）", "manifest_entry_unique:parallel",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: rs + [r for r in rs if r["tag"] == "parallel"])))
case("清单里有来历不明的运行", "manifest_all_attributed",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: rs + [{"tag": "stray", "parallel": 1, "exit": 0}])))
case("清单文件缺失", "manifest_readable", lambda d: mutate(d, "runs.jsonl", lambda t: None))
case("两侧误用同一检查点", "chain_checkpoint_consistent",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: [dict(r, checkpoint="runs/x/serial.checkpoint.jsonl") for r in rs])))
case("最终结果少了一个候选", "final_results_one_per_candidate:parallel",
     lambda d: mutate(d, "resume_parallel2.json",
                      j_edit(lambda doc: doc["results"].pop())))
case("带出来的结果与检查点不符（改的是允许不同的 elapsed_s）", "final_results_traced:serial",
     lambda d: mutate(d, "resume_serial.json", j_edit(
         lambda doc: next(r for r in doc["results"]
                          if r.get("carried_from_checkpoint")).update(elapsed_s=-1.0))))
case("被带出结果所依据的旧证据文件被删", "final_results_traced:serial",
     lambda d: mutate(d, "serial.evidence.jsonl", lambda t: None))
case("证据文件被换成另一次运行的（归属错）", "evidence_attributed:parallel",
     lambda d: (mutate(d, "parallel.evidence.jsonl", lambda t: None),
                (d / "parallel.evidence.jsonl").symlink_to(R2 / "serial.evidence.jsonl")))
case("最终结果文件与其证据 footer 不一致", "footer_matches_result:resume_parallel2",
     lambda d: mutate(d, "resume_parallel2.json", j_edit(
         lambda doc: doc["acceptance"].update(incomplete=[1]))))
case("检查点缺失", "checkpoint_binding:parallel",
     lambda d: mutate(d, "parallel.checkpoint.jsonl", lambda t: None))
case("清单里的并行路数与结果不符", "run_parallel_matches_side:parallel",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: [dict(r, parallel=1) if r["tag"] == "parallel" else r for r in rs])))
case("期望的规格 hash 不符", "binding_matches_expected", lambda d: None, spec="0" * 64)
case("快照不符", "binding_matches_expected", lambda d: None, pin="25950799:0x" + "0" * 64)
case("并行一侧没声明任何运行（空链）", "chains_declared", lambda d: None, parallel=",")

# —— 审核 v1.17：检查点的 primitives_sha256 / runtime_params 漏验（旧版 53 项全过、退出 0）——
def _cp_edit(side, fn):
    def prep(d):
        def f(rows):
            fn(rows[0])
            return rows
        mutate(d, f"{side}.checkpoint.jsonl", jl_edit(f))
    return prep


case("串行检查点 primitives_sha256 改成全 0", "checkpoint_binding:serial",
     _cp_edit("serial", lambda b: b.update(primitives_sha256="0" * 64)))
case("串行检查点 runtime_params.slot_limit 32→0", "checkpoint_binding:serial",
     _cp_edit("serial", lambda b: b["runtime_params"].update(slot_limit=0)))
case("串行检查点删掉 primitives_sha256 与 runtime_params", "checkpoint_binding:serial",
     _cp_edit("serial", lambda b: (b.pop("primitives_sha256"), b.pop("runtime_params"))))
case("并行检查点 runtime_params.diagnostics 翻转", "checkpoint_binding:parallel",
     _cp_edit("parallel", lambda b: b["runtime_params"].update(diagnostics=False)))
case("期望的原语 hash 不符", "checkpoint_binding", lambda d: None, prim="1" * 64)
case("期望的 runtime_params 不符", "checkpoint_binding", lambda d: None,
     runtime=dict(RUNTIME, slot_limit=31))
case("旧版规则：检查点与运行头 params 不符（两处同时改成一致的假值也要抓到）",
     "run_binding_matches:serial",
     _cp_edit("serial", lambda b: b["runtime_params"].update(slot_limit=0)),
     runtime=dict(RUNTIME, slot_limit=0))
case("旧版规则：检查点原语与结果文件的 package_script_sha256 不符",
     "run_binding_matches:resume_serial",
     lambda d: mutate(d, "resume_serial.json", j_edit(
         lambda doc: doc.update(package_script_sha256="2" * 64))))

_smp_dup = Path(tempfile.mkdtemp(prefix="rta-smp-")) / "dup.json"
_s = json.loads((W / "pilot" / "dev_sample.json").read_text())
_s["sample"][1]["index"] = _s["sample"][0]["index"]
_smp_dup.write_text(json.dumps(_s))
case("样本里有重复 index", "sample_well_formed", lambda d: None, sample=_smp_dup)

for name, want, prep, kw in CASES:
    d = r2_copy()
    prep(d)
    rc, rep, p = compare(d, **kw)
    f_ = failed(rep)
    check(f"{name}：退出 1 且点名 {want}",
          rc == 1 and any(x == want or x.startswith(want) for x in f_),
          f"rc={rc} failed={f_[:4]} err={p.stderr[-120:]!r}" if rc != 1 or not f_ else
          f"failed={f_[:3]}")

rc, _, p = compare(r2_copy(), runtime="not-json")
check("--expect-runtime-params 不是 JSON 对象：退出 2", rc == 2, f"rc={rc}")
rc, rep, _ = compare(r2_copy())
check("正对照：5 次历史运行都走明确的旧版绑定规则（不是跳过）",
      {v.get("binding_rule") for v in rep.get("runs", {}).values()}
      == {"legacy_v1.16_header_params_and_result_doc"}
      and all(rep["checks"].get(f"run_binding_matches:{t}", {}).get("ok")
              for t in SERIAL.split(",") + PARALLEL.split(",")),
      str({t: v.get("binding_rule") for t, v in rep.get("runs", {}).items()}))

# 忽略标签必须显式给出才生效
d = r2_copy()
mutate(d, "runs.jsonl", jl_edit(lambda rs: rs + [{"tag": "stray", "parallel": 1, "exit": 0}]))
rc, rep, _ = compare(d, extra=("--ignore-tag", "stray"))
check("来历不明的运行被显式 --ignore-tag 后不再阻断", rc == 0, f"rc={rc} {failed(rep)[:3]}")

# 输出已存在 ⇒ 拒绝覆盖
_o = Path(tempfile.mkdtemp(prefix="rta-cmp-o-")) / "exists.json"
_o.write_text("KEEP\n")
rc, _, p = compare(r2_copy(), out=_o)
check("报告路径已存在：退出 2、原文件不动", rc == 2 and _o.read_text() == "KEEP\n", f"rc={rc}")

# 空检查集合不能算通过
_ck = C.Checks()
check("没有任何检查时判不通过（空 all() 不放行）", _ck.verdict()["passed"] is False)
_ck.add("manifest_readable", True)
check("必需检查缺席时判不通过", _ck.verdict()["passed"] is False
      and "final_exit_0" in _ck.verdict()["required_absent"])
_ck2 = C.Checks()
_ck2.add("x", 1)
check("只有真正的 True 才算通过（1 / 非空对象不算）", _ck2.items["x"]["ok"] is False)

# ======================================================================= B
print("\nB 驱动：失败反映到退出码；历史只追加、不覆盖；续跑需显式指定")
ROOT = Path(tempfile.mkdtemp(prefix="rta-drv-"))
RUNS = ROOT / "runs"
RUNS.mkdir()
sys.path.insert(0, str(W))
import evidence as E  # noqa: E402
import pilot_measure as P  # noqa: E402
SMP = ROOT / "sample.json"
SMP.write_text(json.dumps(dict(
    universe_sha256=E.sha256_file(P.UNIVERSE), n=2,
    sample=[dict(index=i, pair="0x" + "ab" * 20, token="0x" + "cd" * 20,
                 created_block=24140000) for i in (1, 2)])))
FPIN = f"25900000:0x{25900000:064x}"


def drive(plan=None, *args, fresh=True, name="t"):
    env = dict(os.environ, RT_FAKE_PLAN=json.dumps(plan or {}))
    env.pop("ETH_RPC_URL", None)
    env.pop("ETHERSCAN_API_KEY", None)
    base = [sys.executable, str(T / "run_compare.py"), "--launch", str(T / "fake_launch.py"),
            "--gap-s", "0"]
    if fresh:
        base += ["--name", name, "--runs-root", str(RUNS), "--sample", str(SMP), "--pin", FPIN]
    p = subprocess.run(base + list(args), capture_output=True, text=True, timeout=600, env=env,
                       cwd=W)
    return p


def only_dir(before):
    new = sorted(set(RUNS.iterdir()) - set(before))
    return new[0] if len(new) == 1 else None


def manifest(d):
    return [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines() if x.strip()]


# B1 审核反例：子运行全部失败（替身返回 2）
_b = set(RUNS.iterdir())
p = drive({"serial": "exit:2", "parallel": "exit:2"})
A1 = only_dir(_b)
runs1 = [r for r in manifest(A1) if r.get("kind") == "run"] if A1 else []
check("子运行全部返回 2：驱动退出 1（旧驱动退出 0）", p.returncode == 1,
      f"rc={p.returncode} {p.stderr[-200:]}")
check("清单记下每个子运行的真实退出码", [r["exit"] for r in runs1] == [2, 2],
      str([r.get("exit") for r in runs1]))
check("清单末尾写明 driver_exit=1", manifest(A1)[-1].get("driver_exit") == 1 if A1 else False)
A1_HASH = tree_hashes(A1)

# B2 再全新执行一次：必须新建目录，旧目录一个字节不动
_b = set(RUNS.iterdir())
p = drive({"serial": "exit:1", "parallel": "exit:3"})
A2 = only_dir(_b)
check("第二次全新执行：新建另一个运行目录", A2 is not None and A2 != A1, str(A2))
check("第二次全新执行：第一次目录的所有文件原字节保留", tree_hashes(A1) == A1_HASH)
check("子运行 1 / 3（未完成 / 停机）同样让驱动退出 1", p.returncode == 1, f"rc={p.returncode}")

# B3 显式续跑：只追加，旧日志与旧清单前缀原样
(A1 / "parallel_resume1.stdout.log").write_text("PRE-EXISTING, MUST SURVIVE\n")
_pre = tree_hashes(A1)
_man_before = (A1 / "runs.jsonl").read_bytes()
p = drive({"parallel_resume2": "exit:2"}, "--continue-dir", str(A1), "--resume", "parallel",
          fresh=False)
m3 = manifest(A1)
new_runs = [r for r in m3 if r.get("kind") == "run"][len(runs1):]
check("续跑：清单只追加（旧内容是新清单的字节前缀）",
      (A1 / "runs.jsonl").read_bytes().startswith(_man_before)
      and len((A1 / "runs.jsonl").read_bytes()) > len(_man_before))
check("续跑：已有同名文件的标签被跳过，新运行用 parallel_resume2",
      [r["tag"] for r in new_runs] == ["parallel_resume2"], str([r["tag"] for r in new_runs]))
check("续跑：此前所有文件原字节保留（含预置的同名日志）",
      all(tree_hashes(A1).get(k) == v for k, v in _pre.items() if k != "runs.jsonl"))
check("续跑：沿用本目录这一侧的检查点，而不是新建或借用别处的",
      new_runs and new_runs[0]["checkpoint"] == runs1[1]["checkpoint"],
      str([r.get("checkpoint") for r in new_runs]))
check("续跑失败：驱动退出 1", p.returncode == 1, f"rc={p.returncode}")

# B4 用法：续跑必须显式指定；全新执行不能带 --resume；续跑不能改 sample/pin
p1 = drive(None, "--continue-dir", str(A1), fresh=False)
p2 = drive(None, "--resume", "serial")
p3 = drive(None, "--continue-dir", str(A1), "--resume", "serial", "--pin", FPIN, fresh=False)
check("续跑未指明哪一侧 / 全新执行带 --resume / 续跑改 pin：一律退出 2",
      (p1.returncode, p2.returncode, p3.returncode) == (2, 2, 2),
      str((p1.returncode, p2.returncode, p3.returncode)))

# B5 正对照：受控链上两侧都完成 + 比较器通过 ⇒ 0
_b = set(RUNS.iterdir())
p = drive({}, "--compare")
A5 = only_dir(_b)
_cmp = sorted(A5.glob("compare_*.json")) if A5 else []
_crep = json.loads(_cmp[0].read_text()) if _cmp else {}
check("正对照：两侧完成、比较器通过 ⇒ 驱动退出 0",
      p.returncode == 0 and (_crep.get("verdict") or {}).get("passed") is True,
      f"rc={p.returncode} {failed(_crep)[:3]} {p.stderr[-200:]}")

# B6 一侧首跑未完成、自动续跑一次补齐 ⇒ 0；首跑里被中断的候选记 unavailable、续跑重测
_b = set(RUNS.iterdir())
p = drive({"serial": "flaky"}, "--max-resumes", "1", "--compare")
A6 = only_dir(_b)
m6 = [r for r in manifest(A6) if r.get("kind") == "run"] if A6 else []
_s1 = json.loads((A6 / "serial.json").read_text()) if A6 else {}
_c1 = next((r for r in _s1.get("results", []) if r["index"] == 1), {})
check("自动续跑：串行 1→0，并行 0，比较器通过，驱动退出 0",
      [(r["tag"], r["exit"]) for r in m6] == [("serial", 1), ("serial_resume1", 0),
                                               ("parallel", 0)] and p.returncode == 0,
      f"{[(r['tag'], r['exit']) for r in m6]} rc={p.returncode}")
check("首跑被接口故障打断的候选：data_missing + validation unavailable",
      _c1.get("state") == "data_missing" and _c1.get("validation_status") == "unavailable",
      f"{_c1.get('state')} / {_c1.get('validation_status')}")

# B7 不给续跑额度：同样的故障 ⇒ 驱动退出 1，且不去跑比较器
_b = set(RUNS.iterdir())
p = drive({"serial": "flaky"}, "--compare")
A7 = only_dir(_b)
end7 = manifest(A7)[-1] if A7 else {}
check("一侧最终未完成：驱动退出 1、比较器不运行",
      p.returncode == 1 and end7.get("compare_exit") is None
      and end7.get("last_exit_per_side") == {"serial": 1, "parallel": 0},
      f"rc={p.returncode} {end7}")

# B8 子运行"都退出 0"但没产出可验收的证据 ⇒ 比较器失败 ⇒ 驱动退出 1
_b = set(RUNS.iterdir())
p = drive({"serial": "exit:0", "parallel": "exit:0"}, "--compare")
A8 = only_dir(_b)
end8 = manifest(A8)[-1] if A8 else {}
check("子运行都报 0 但证据缺失：比较器退出 1、驱动退出 1",
      p.returncode == 1 and end8.get("compare_exit") == 1, f"rc={p.returncode} {end8}")

def compare_ctrl(d, meta, serial, parallel, extra=()):
    """对受控链运行目录做对照，期望值取自该目录 driver.json。"""
    cs = meta["code_sha256"]
    return compare(d, serial=serial, parallel=parallel, extra=extra, sample=SMP, pin=FPIN,
                   spec=cs["spec"], prim=cs["primitives"], runtime=meta["runtime_params"],
                   script=cs["pilot_measure.py"], evidence=cs["evidence.py"])


def ev_edit(fn):
    """逐条就地改证据记录（fn 的返回值忽略）；保持 seq 不变，避免牵连结构完整性检查。"""
    def _each(rs):
        for r in rs:
            fn(r)
        return rs
    return jl_edit(_each)


# B10 新格式运行：证据里的 run_binding 与检查点逐键核对（审核 v1.17 P1）
META5 = json.loads((A5 / "driver.json").read_text()) if A5 else {}
rc, rep, _ = compare_ctrl(r2_copy(A5), META5, "serial", "parallel")
check("新格式正对照：两次运行都走 run_binding 规则、退出 0",
      rc == 0 and {v.get("binding_rule") for v in rep.get("runs", {}).values()} == {"run_binding"},
      f"rc={rc} {failed(rep)[:3]}")
check("驱动记下的期望 runtime_params 来自 pilot_measure 自身推导（slot_limit=32、含 cutoff/amount）",
      META5.get("runtime_params", {}).get("slot_limit") == 32
      and set(META5.get("runtime_params", {})) == {"slot_limit", "diagnostics", "cutoff_block",
                                                   "amount_wei"}
      and META5.get("code_sha256", {}).get("primitives") == PRIM, str(META5.get("runtime_params")))
for _nm, _fn in [
        ("证据 run_binding 的 runtime_params 被改",
         lambda r: r["runtime_params"].update(slot_limit=0) if r.get("kind") == "run_binding" else None),
        ("证据 run_binding 的原语 hash 被改",
         lambda r: r.update(primitives_sha256="3" * 64) if r.get("kind") == "run_binding" else None),
        ("证据 run_binding 删掉一个键",
         lambda r: r.pop("runtime_params") if r.get("kind") == "run_binding" else None),
        ("新版本运行缺 run_binding（不得退回旧版规则）",
         lambda r: r.update(kind="run_binding_renamed") if r.get("kind") == "run_binding" else None)]:
    d = r2_copy(A5)
    mutate(d, "serial.evidence.jsonl", ev_edit(_fn))
    rc, rep, _ = compare_ctrl(d, META5, "serial", "parallel")
    check(f"{_nm}：退出 1、点名 run_binding_matches:serial",
          rc == 1 and "run_binding_matches:serial" in failed(rep), f"rc={rc} {failed(rep)[:4]}")

# B11 启动即前置失败、续跑补齐：尝试历史 ≠ 结果证据链（审核 v1.17 P2）
_b = set(RUNS.iterdir())
p = drive({"serial": "startup_fail"}, "--max-resumes", "1", "--compare")
A11 = only_dir(_b)
m11 = [r for r in manifest(A11) if r.get("kind") == "run"] if A11 else []
_c11 = sorted(A11.glob("compare_*.json")) if A11 else []
_r11 = json.loads(_c11[0].read_text()) if _c11 else {}
check("启动断连后续跑补齐：serial 2 → serial_resume1 0、parallel 0，比较器通过、驱动退出 0",
      [(r["tag"], r["exit"]) for r in m11] == [("serial", 2), ("serial_resume1", 0), ("parallel", 0)]
      and p.returncode == 0 and (_r11.get("verdict") or {}).get("passed") is True,
      f"{[(r['tag'], r['exit']) for r in m11]} rc={p.returncode} {failed(_r11)[:4]}")
check("首次启动尝试被识别为惰性启动失败，原 abort 证据原样保留",
      (_r11.get("runs") or {}).get("serial", {}).get("role") == "startup_abort"
      and any(json.loads(x).get("reason") == "endpoint_unreachable"
              for x in (A11 / "serial.evidence.jsonl").read_text().splitlines() if x.strip()),
      str((_r11.get("runs") or {}).get("serial", {}).get("role")))
META11 = json.loads((A11 / "driver.json").read_text()) if A11 else {}
_ab_rid = next((json.loads(x)["run_id"] for x in (A11 / "serial.evidence.jsonl").read_text()
                .splitlines() if x.strip() and json.loads(x).get("kind") == "abort"), None)


def _append_candidate_start(t):
    rows = [json.loads(x) for x in t.splitlines() if x.strip()]
    rows.append(dict(rows[-1], seq=max(r["seq"] for r in rows) + 1, kind="candidate_start",
                     candidate=1))
    return "".join(json.dumps(r) + "\n" for r in rows)


_NEG11 = [
    ("伪装的启动失败其实开工过候选", "startup_abort_inert:serial",
     lambda d: mutate(d, "serial.evidence.jsonl", _append_candidate_start), "serial,serial_resume1"),
    ("检查点里有尝试引用该启动失败运行", "startup_abort_inert:serial",
     lambda d: mutate(d, "serial.checkpoint.jsonl", lambda t: t + json.dumps(
         {"kind": "attempt", "candidate": 1, "attempt": 9, "state": "data_missing",
          "completed": False, "evidence_run_id": _ab_rid}) + "\n"), "serial,serial_resume1"),
    ("abort 原因不是启动阶段的端点/预算/停机（chain_id_mismatch）", "result_doc_present:serial",
     lambda d: mutate(d, "serial.evidence.jsonl", ev_edit(
         lambda r: r.update(reason="chain_id_mismatch") if r.get("kind") == "abort" else None)),
     "serial,serial_resume1"),
    ("清单把该尝试的退出码改成 0", "result_doc_present:serial",
     lambda d: mutate(d, "runs.jsonl", jl_edit(
         lambda rs: [dict(r, exit=0) if r.get("tag") == "serial" else r for r in rs])),
     "serial,serial_resume1"),
    ("启动失败尝试的证据文件缺失", "result_doc_present:serial",
     lambda d: mutate(d, "serial.evidence.jsonl", lambda t: None), "serial,serial_resume1"),
    ("整条串行链只剩那次启动失败", "final_exit_0:serial", lambda d: None, "serial"),
]
for _nm, _want, _prep, _chain in _NEG11:
    d = r2_copy(A11)
    _prep(d)
    rc, rep, _ = compare_ctrl(d, META11, _chain, "parallel",
                              extra=("--ignore-tag", "serial_resume1") if _chain == "serial" else ())
    check(f"P2 负对照 · {_nm}：退出 1、点名 {_want}",
          rc == 1 and any(x == _want or x.startswith(_want) for x in failed(rep)),
          f"rc={rc} {failed(rep)[:4]}")

# B12 审核对照：首遍有候选完成并被带出时，不能把首遍排除出结果链
META6 = json.loads((A6 / "driver.json").read_text()) if A6 else {}
rc, rep, _ = compare_ctrl(r2_copy(A6), META6, "serial_resume1", "parallel",
                          extra=("--ignore-tag", "serial"))
check("有继承结果的首遍被 --ignore-tag 排除：退出 1（带出结果的来源不在链内）",
      rc == 1 and "final_results_traced:serial" in failed(rep), f"rc={rc} {failed(rep)[:4]}")

# B13 续跑不得改测量参数（会让检查点绑定不符）
p13 = drive(None, "--continue-dir", str(A1), "--resume", "serial", "--extra=--slot-limit",
            "--extra=2", fresh=False)
check("续跑改 --extra：退出 2", p13.returncode == 2, f"rc={p13.returncode}")

# B14 驱动续跑与比较器对同一份矛盾绑定结论一致（审核 v1.18 P1，v1.19 共用守卫）
#      放在最后：它会改写 A5 自己的（临时）证据。
_b14 = A5 / "serial.evidence.jsonl"
_b14.write_text("".join(json.dumps(dict(r, runtime_params=dict(r["runtime_params"], slot_limit=999))
                                   if r.get("kind") == "run_binding" else r) + "\n"
                        for r in (json.loads(x) for x in _b14.read_text().splitlines() if x.strip())))
p14 = drive({}, "--continue-dir", str(A5), "--resume", "serial", "--compare", fresh=False)
_r14 = json.loads((A5 / "serial_resume1.json").read_text()) if (A5 / "serial_resume1.json").is_file() else {}
_a14 = _r14.get("acceptance") or {}
check("驱动续跑：原证据 run_binding 与检查点矛盾 ⇒ 续跑退出 1、驱动退出 1、比较器不运行",
      p14.returncode == 1 and manifest(A5)[-1].get("last_exit_per_side", {}).get("serial") == 1
      and manifest(A5)[-1].get("compare_exit") is None,
      f"rc={p14.returncode} end={manifest(A5)[-1]}")
check("驱动续跑：续跑交付点名 evidence_run_binding_mismatch、处置为带出但阻断",
      {p.get("reason") for p in _a14.get("evidence_chain_problems") or []}
      >= {"evidence_run_binding_mismatch"}
      and str(_a14.get("evidence_chain_action", "")).startswith("carried_but_blocked"),
      str(sorted({p.get("reason") for p in _a14.get("evidence_chain_problems") or []})))
rc, rep, _ = compare_ctrl(r2_copy(A5), META5, "serial,serial_resume1", "parallel")
check("同一条链交给比较器：同样退出 1，点名 run_binding_matches:serial",
      rc == 1 and "run_binding_matches:serial" in failed(rep), f"rc={rc} {failed(rep)[:5]}")

# B9 替身不读凭据：驱动环境里没有凭据变量，输出里也没有 .env 的任何值
_envtxt = Path("/home/ancillary/.env").read_text(encoding="utf-8") \
    if Path("/home/ancillary/.env").is_file() else ""
_secrets = [ln.split(":", 1)[1].strip() for ln in _envtxt.splitlines() if ":" in ln]
_secrets = [s for s in _secrets if len(s) >= 8]
_leak = [str(f.relative_to(ROOT)) for f in ROOT.rglob("*") if f.is_file()
         and any(s in f.read_text(errors="replace") for s in _secrets)]
check("驱动测试产物里没有任何 .env 凭据值（只报数量）", not _leak, f"{len(_leak)} 个文件")

# ======================================================================= C
print("\nC 历史交付目录原字节")
check("runs/realchain2_20260911 整个目录前后一致（含旧比较器与旧驱动）",
      tree_hashes(R2) == R2_BEFORE, str(sorted(set(tree_hashes(R2).items())
                                              ^ set(R2_BEFORE.items())))[:200])
shutil.rmtree(ROOT, ignore_errors=True)

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

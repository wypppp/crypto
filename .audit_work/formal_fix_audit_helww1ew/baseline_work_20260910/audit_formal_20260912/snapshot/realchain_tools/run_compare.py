#!/usr/bin/env python3
"""真链串行 / 两路并行同快照对照的**驱动**（规格 v1.17 §6.0 第 7 条；v1.18 补期望绑定）。

取代 `runs/realchain2_20260911/run_compare.sh`（原字节保留，**不要再对交付目录执行它**）。
审核 v1.16 用固定返回 2 的 launch 替身实测旧脚本：三个子运行全部失败，驱动仍退出 0；
启动即 `: > runs.jsonl` 清空旧清单，日志用 `>` 覆盖。本驱动的规则：

* **每次全新执行都新建运行目录** `runs/<name>_<attempt_id>/`；目录已存在就拒绝。
* **续跑必须显式指定**：`--continue-dir <那次的目录> --resume serial|parallel`。
  沿用该目录里清单记录的检查点，新运行用新标签（`<side>_resume<N>`），
  清单只追加；所有输出文件以独占方式创建（已存在即报错），旧证据与日志一个字节都不动。
* 全新执行**绝不**碰任何旧检查点 —— 检查点只在本次目录里新建。
* **退出码反映子运行结果**：两侧最终运行都退出 0（给了 `--compare` 时比较器也须退出 0）
  才返回 0；否则 1；用法错误 2。
* 凭据只由 launch 脚本经环境变量交给子进程；本驱动不读凭据，清单里只记不含凭据的命令行。

用法（从 baseline_work_20260910 目录）：
    python3 realchain_tools/run_compare.py --name realchain3 \
        --sample pilot/dev_sample.json --pin NUMBER:HASH [--max-resumes 2] [--compare]
    python3 realchain_tools/run_compare.py --continue-dir runs/realchain3_<id> --resume parallel
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[1]
DEFAULT_LAUNCH = W / "runs" / "realchain_20260911" / "launch.py"
#: 与第二轮一致的资源参数；可用 --extra 追加
COMMON = ["--max-rss-mb", "2048", "--max-wall-s", "3600", "--hard-rss-mb", "8192",
          "--hard-cpu-s", "3600"]
SIDES = {"serial": 1, "parallel": 2}


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _append(manifest, row):
    """只追加。每行写完即 fsync —— 驱动中途被杀，已完成的运行记录也在。"""
    with open(manifest, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read_manifest(manifest):
    if not Path(manifest).is_file():
        return []
    return [json.loads(x) for x in Path(manifest).read_text(encoding="utf-8").splitlines()
            if x.strip()]


def _free_tag(run_dir, side, rows):
    """该侧下一个未用过的标签。清单里有、或同名文件已存在，都算用过。"""
    used = {r.get("tag") for r in rows}
    n = 0
    while True:
        tag = side if n == 0 else f"{side}_resume{n}"
        if tag not in used and not any(run_dir.glob(f"{tag}.*")):
            return tag
        n += 1


def run_one(a, run_dir, manifest, ids, side, tag, checkpoint):
    out, ev = run_dir / f"{tag}.json", run_dir / f"{tag}.evidence.jsonl"
    so, se = run_dir / f"{tag}.stdout.log", run_dir / f"{tag}.stderr.log"
    for p in (out, ev):
        if p.exists():
            raise FileExistsError(f"{p} 已存在，拒绝覆盖")
    rel = lambda p: os.path.relpath(p, W)  # noqa: E731
    cmd = ([sys.executable, str(a.launch), "--", sys.executable, "pilot_measure.py", "measure",
            "--sample", a.sample, "--pin-finalized", a.pin] + COMMON + list(a.extra or [])
           + ["--parallel", str(SIDES[side]), "--out", rel(out), "--evidence", rel(ev),
              "--checkpoint", rel(checkpoint)])
    t0, started = time.monotonic(), _now()
    # 'x'：日志文件已存在即报错 —— 永远不覆盖旧日志
    with open(so, "x", encoding="utf-8") as fo, open(se, "x", encoding="utf-8") as fe:
        try:
            rc = subprocess.call(cmd, cwd=W, stdout=fo, stderr=fe)
        except OSError as e:
            fe.write(f"driver: failed to start child: {e}\n")
            rc = 127
    row = {"kind": "run", **ids, "tag": tag, "side": side, "parallel": SIDES[side],
           "exit": rc, "wall_s": round(time.monotonic() - t0, 1),
           "started_at": started, "ended_at": _now(),
           "checkpoint": rel(checkpoint), "out": rel(out), "evidence": rel(ev),
           "stdout": rel(so), "stderr": rel(se),
           # 命令行里本就没有凭据（launch 从 .env 读、经环境变量传）；解释器路径换成名字
           "cmd": ["python3", rel(a.launch)] + cmd[2:3] + ["python3"] + cmd[4:]}
    _append(manifest, row)
    print(json.dumps({k: row[k] for k in ("tag", "parallel", "exit", "wall_s")}), flush=True)
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--name", help="全新执行：在 --runs-root 下新建 <name>_<attempt_id>/")
    g.add_argument("--continue-dir", help="续跑：沿用这次目录的检查点，只追加新运行")
    ap.add_argument("--resume", action="append", choices=sorted(SIDES),
                    help="续跑哪一侧（可重复）；--continue-dir 时必需")
    ap.add_argument("--runs-root", default=str(W / "runs"))
    ap.add_argument("--sample")
    ap.add_argument("--pin", help="finalized 快照 NUMBER:HASH；两侧必须同一快照")
    ap.add_argument("--launch", default=str(DEFAULT_LAUNCH))
    ap.add_argument("--gap-s", type=float, default=30.0, help="两次运行之间的间隔（秒）")
    ap.add_argument("--max-resumes", type=int, default=0,
                    help="某侧未以 0 结束时，本次调用内自动续跑的最多次数")
    ap.add_argument("--extra", action="append", help="追加给 pilot_measure 的参数（可重复）")
    ap.add_argument("--sides", default=",".join(SIDES),      # 顺序即执行顺序：serial 先
                    help="全新执行跑哪几侧，逗号分隔（默认两侧做对照）。只给一侧时本目录就是单侧采集，"
                         "--compare 会以比较器的单侧模式验收（跳过对照类检查）")
    ap.add_argument("--compare", action="store_true",
                    help="两侧都以 0 结束后调用 compare_runs.py；其退出码计入本驱动")
    a = ap.parse_args(argv)
    a.launch = str(Path(a.launch).resolve())

    if a.continue_dir:
        run_dir = Path(a.continue_dir).resolve()
        manifest = run_dir / "runs.jsonl"
        meta_p = run_dir / "driver.json"
        if not (manifest.is_file() and meta_p.is_file()):
            print(f"run_compare: {run_dir} 不是本驱动建的运行目录", file=sys.stderr)
            return 2
        if not a.resume:
            print("run_compare: --continue-dir 需要显式 --resume serial|parallel", file=sys.stderr)
            return 2
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if a.sample or a.pin:
            print("run_compare: 续跑沿用原目录的 sample/pin，不接受重新指定", file=sys.stderr)
            return 2
        a.sample, a.pin, attempt_id = meta["sample"], meta["pin"], meta["attempt_id"]
        # 续跑沿用原目录的测量参数；另给一套会让检查点绑定不符，干脆在这里拒绝
        if a.extra is not None and list(a.extra) != list(meta.get("extra") or []):
            print("run_compare: 续跑沿用原目录的 --extra，不接受改动", file=sys.stderr)
            return 2
        a.extra = list(meta.get("extra") or [])
        declared = list(meta.get("sides") or SIDES)      # 旧目录没记 sides ⇒ 视为两侧
        bad = [x for x in a.resume if x not in declared]
        if bad:
            print(f"run_compare: {bad} 不在本目录声明的侧 {declared} 内", file=sys.stderr)
            return 2
        todo = list(dict.fromkeys(a.resume))
    else:
        if not (a.sample and a.pin):
            print("run_compare: 全新执行需要 --sample 与 --pin", file=sys.stderr)
            return 2
        if a.resume:
            print("run_compare: --resume 只能配合 --continue-dir", file=sys.stderr)
            return 2
        declared = [x for x in dict.fromkeys((a.sides or "").split(",")) if x]
        if not declared or any(x not in SIDES for x in declared):
            print(f"run_compare: --sides 必须是 {sorted(SIDES)} 的非空子集", file=sys.stderr)
            return 2
        attempt_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") \
            + "-" + secrets.token_hex(3)
        run_dir = Path(a.runs_root).resolve() / f"{a.name}_{attempt_id}"
        try:
            run_dir.mkdir(parents=False, exist_ok=False)     # 已存在 ⇒ 拒绝
        except FileExistsError:
            print(f"run_compare: {run_dir} 已存在，拒绝复用", file=sys.stderr)
            return 2
        manifest = run_dir / "runs.jsonl"
        spec, prim, runtime = _expected_binding(a)
        meta = {"attempt_id": attempt_id, "sample": a.sample, "pin": a.pin,
                "created_at": _now(), "launch": os.path.relpath(a.launch, W),
                "spec": spec, "extra": list(a.extra or []), "sides": declared,
                # 比较器以这里记下的值为期望：整组运行必须用**创建目录时**的代码与参数跑。
                # 原语 hash 与 runtime_params 由 pilot_measure 自己的函数推导，不另抄一份。
                "code_sha256": {"pilot_measure.py": _sha(W / "pilot_measure.py"),
                                "evidence.py": _sha(W / "evidence.py"),
                                "spec": _sha(W / spec),
                                "sample": _sha(W / a.sample),
                                "primitives": prim},
                "runtime_params": runtime}
        with open(run_dir / "driver.json", "x", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        todo = list(declared)

    ids = {"attempt_id": attempt_id, "invocation_id": secrets.token_hex(4)}
    rows = _read_manifest(manifest)
    _append(manifest, {"kind": "driver_start", **ids, "at": _now(), "sides": todo,
                       "continue": bool(a.continue_dir), "max_resumes": a.max_resumes,
                       "manifest_rows_before": len(rows)})

    final = {}
    first = True
    for side in todo:
        prior = [r for r in rows if r.get("kind") == "run" and r.get("side") == side]
        if a.continue_dir:
            if not prior:
                print(f"run_compare: {side} 在该目录没有先前运行，无从续跑", file=sys.stderr)
                final[side] = None
                continue
            checkpoint = W / prior[-1]["checkpoint"]     # 显式沿用本目录这一侧的检查点
        else:
            checkpoint = run_dir / f"{side}.checkpoint.jsonl"
            if checkpoint.exists():
                raise FileExistsError(f"{checkpoint} 已存在")
        tries = 0
        while True:
            if not first and a.gap_s > 0:
                time.sleep(a.gap_s)
            first = False
            tag = _free_tag(run_dir, side, rows)
            rc = run_one(a, run_dir, manifest, ids, side, tag, checkpoint)
            rows = _read_manifest(manifest)
            final[side] = rc
            if rc == 0 or tries >= a.max_resumes:
                break
            tries += 1

    # 驱动的结论是**这次运行目录**的状态：两侧各自最后一次运行都退出 0 才算完成。
    # 只续跑了一侧时，另一侧沿用它在清单里的最后结果 —— 不因为"这次没跑它"就当成功。
    allrows = _read_manifest(manifest)
    chains = {s: [r for r in allrows if r.get("kind") == "run" and r.get("side") == s]
              for s in declared}
    last_exit = {s: (c[-1].get("exit") if c else None) for s, c in chains.items()}
    ok = all(v == 0 for v in last_exit.values())
    cmp_rc = None
    if ok and a.compare:
        report = run_dir / f"compare_{ids['invocation_id']}.json"
        cs = meta["code_sha256"]
        cmp_rc = subprocess.call(
            [sys.executable, str(W / "realchain_tools" / "compare_runs.py"),
             "--dir", str(run_dir),
             *[arg for s_ in declared
               for arg in (f"--{s_}", ",".join(r["tag"] for r in chains[s_]))],
             "--sample", str(W / a.sample), "--pin", a.pin,
             "--expect-script-sha", cs["pilot_measure.py"],
             "--expect-evidence-sha", cs["evidence.py"],
             "--expect-spec-sha", cs["spec"],
             "--expect-primitives-sha", cs["primitives"],
             "--expect-runtime-params", json.dumps(meta["runtime_params"]),
             "--out", str(report)], cwd=W)
        ok = cmp_rc == 0
    _append(manifest, {"kind": "driver_end", **ids, "at": _now(), "this_call_exit": final,
                       "last_exit_per_side": last_exit, "compare_exit": cmp_rc,
                       "driver_exit": 0 if ok else 1})
    print(json.dumps({"run_dir": os.path.relpath(run_dir, W), "this_call_exit": final,
                      "last_exit_per_side": last_exit, "compare_exit": cmp_rc,
                      "driver_exit": 0 if ok else 1}, ensure_ascii=False))
    return 0 if ok else 1


def _expected_binding(a):
    """默认规格文件名、原语 hash、runtime_params —— 用 pilot_measure 自己的解析器与函数，
    按本驱动将要传给子进程的同一组参数推导。只读，不执行测量。"""
    sys.path.insert(0, str(W))
    import pilot_measure as P
    ns = P.build_parser().parse_args(
        ["measure", "--sample", a.sample, "--out", "unused.json", "--pin-finalized", a.pin]
        + COMMON + list(a.extra or []))
    return P.OPTIONAL_DEFAULTS["spec"], P.primitives_sha256(), P.runtime_params_of(ns)


if __name__ == "__main__":
    sys.exit(main())

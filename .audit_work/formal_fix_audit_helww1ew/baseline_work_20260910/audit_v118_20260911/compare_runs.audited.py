#!/usr/bin/env python3
"""真链串行 / 并行同快照对照的**验收比较器**（规格 v1.18 §6.0 第 6、8 条）。

取代 `runs/realchain2_20260911/compare.py` 作为以后的验收入口（旧脚本原字节保留，不再改）。
审核 v1.16 实测旧比较器：证据缺 footer、最终运行退出 1、最终运行记录被删，都仍退出 0 ——
它的返回值只看"两份结果 JSON 彼此相同"，验收条件只写进报告、不进退出码；
最终运行记录缺失时 `all([])` 又恒为真。

本比较器的规则：

* **退出码 0 当且仅当全部必需检查都存在且都通过。** 必需检查按名字登记在
  `REQUIRED`；任何一项缺席（没被求值）同样判失败 —— 空集合不能算通过。
* 每项检查要么是 True、要么是 False，求值中出现异常记 False 并写明原因，不中途崩溃。
* 只读输入；报告写到 `--out`，**该路径已存在则拒绝**（不覆盖任何历史产物）。

必需条件（与审核 v1.16 所列一一对应）：
  最终运行记录存在、唯一、归属清楚  —— manifest_*、result_doc_present、evidence_attributed
  样本 / 版本 / 快照绑定             —— binding_*、checkpoint_binding（全部 BINDING_KEYS，v1.18）、
                                        run_binding_matches（每次运行的证据 ↔ 检查点，v1.18）、
                                        sample_well_formed
  启动失败尝试 ≠ 结果证据链（v1.18）  —— startup_abort_inert（只对满足严格惰性条件的尝试）
  累计结果完整且与证据对应           —— final_results_one_per_candidate、final_acceptance_clean、
                                        final_results_traced
  证据完整且有 footer                —— evidence_complete、footer_matches_result
  最终运行退出 0                     —— final_exit_0
  两侧一致                           —— same_snapshot、same_candidate_set、
                                        results_identical_except_allowed、rpc_plus_cache_equal

退出码：0 通过；1 有必需检查未通过；2 用法错误（参数缺失、输出已存在、期望参数不是 JSON）。
全部离线，不发任何网络请求。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import evidence as E  # noqa: E402

#: 两侧结果**只有**这三个顶层字段允许不同：耗时；RPC 次数（共享区块缓存命中不同，
#: 由 rpc_plus_cache_equal 另行核对）；续跑带出标记。其余任何差异都判不一致。
ALLOWED = {"elapsed_s", "rpc_calls", "carried_from_checkpoint"}

#: 必需检查的**基名**。带 `:<tag>` / `:<side>` 后缀的实例至少要出现一个，且全部为 True。
REQUIRED = [
    "manifest_readable", "chains_declared", "manifest_entry_unique", "manifest_all_attributed",
    "chain_checkpoint_consistent", "final_exit_0",
    "result_doc_present", "evidence_complete", "evidence_attributed", "footer_matches_result",
    "run_parallel_matches_side",
    "binding_consistent", "binding_matches_expected", "checkpoint_binding",
    "sample_well_formed", "final_results_one_per_candidate", "final_acceptance_clean",
    "final_results_traced",
    "same_snapshot", "same_candidate_set", "results_identical_except_allowed",
    "rpc_plus_cache_equal", "run_binding_matches",
]

#: 最终累计验收里必须为空的清单字段
_MUST_BE_EMPTY = ("incomplete", "missing_candidates", "duplicate_results", "unexpected_results",
                  "sample_field_mismatch", "worker_errors", "not_started",
                  "evidence_chain_problems", "checkpoint_results_unusable",
                  "validation_failed", "validation_unavailable")


#: 惰性启动失败：只接受这几种 (abort 原因, 退出码)，且阶段在启动的两步里
STARTUP_ABORTS = {("endpoint_unreachable", 2), ("budget_exhausted", 2),
                  ("shutdown_during_startup", 3)}
STARTUP_STAGES = {"chain_id", "snapshot"}

#: 运行证据里还没有 run_binding 记录的规格版本（v1.16、v1.17）。只有这些版本
#: 允许走"旧版规则"；更新的版本缺 run_binding 一律失败，不跳过。
LEGACY_SPEC_SHA256 = {
    "2a6c5dcf613d263f8ec9067b047805e0c675a6b6df159896414b0bde4b756606": "v1.16",
    "7cf15793c7626ce725c133ce748920998083bb46b32ef6913f17604a1ada3542": "v1.17",
}


def _startup_abort_inert(tag, tags, m, rr, diag, ckpt_rows):
    """该尝试确实没有做任何候选工作、也没有任何结果依赖它。返回 (ok, detail)。"""
    problems = []
    runs = set(diag.get("runs", {}))
    rid = next(iter(runs), None)
    if len(runs) != 1:
        problems.append(f"evidence must hold exactly one run, found {len(runs)}")
    if tags and tag == tags[-1]:
        problems.append("the last run of a side cannot be a startup abort")
    ab = [r for r in rr if r.get("kind") == "abort"]
    if len(ab) != 1 or (ab[0].get("reason"), m.get("exit")) not in STARTUP_ABORTS \
            or ab[0].get("stage") not in STARTUP_STAGES:
        problems.append({"abort": [(x.get("reason"), x.get("stage")) for x in ab],
                         "exit": m.get("exit")})
    work = sorted({r.get("kind") for r in rr if r.get("kind") in
                   ("run_header", "run_binding", "candidate_start", "candidate_result",
                    "candidate_end", "etherscan", "checkpoint_state")})
    if work:
        problems.append({"work_records": work})
    stray_rpc = [r.get("stage") for r in rr if r.get("kind") == "rpc"
                 and (r.get("candidate") is not None or r.get("stage") not in STARTUP_STAGES)]
    if stray_rpc:
        problems.append({"rpc_outside_startup": stray_rpc[:5]})
    if diag.get("bad_lines") or diag.get("seq_gaps") or diag.get("unmatched_rpc_begin") \
            or diag.get("orphan_rpc_end") or diag.get("duplicate_pending_id"):
        problems.append("evidence structure damaged")
    refs = [x.get("candidate") for x in (ckpt_rows or [])
            if rid is not None and x.get("evidence_run_id") == rid]
    if refs:
        problems.append({"checkpoint_attempts_referencing_it": refs})
    return not problems, {"run_id": rid, "problems": problems,
                          "abort": [(x.get("reason"), x.get("stage")) for x in ab]}


def _run_binding_ok(rr, rid, header, doc, cb):
    """本运行的证据与检查点绑定在**全部** BINDING_KEYS 上一致。返回 (ok, detail)。

    * v1.18 起证据里有 `run_binding` 记录：逐键比对，缺键即失败；
    * v1.16 / v1.17 的运行没有这条记录（不改写历史运行头）：走**明确的旧版规则** ——
      原语 hash 用结果文件里运行结束时独立计算的 `package_script_sha256` 对照，
      runtime_params 逐键对照运行头 `params`；其余 7 键由运行头与 checkpoint_binding 覆盖。
      其它版本缺 run_binding 一律失败。
    """
    keys = E.Checkpoint.BINDING_KEYS
    rb = [r for r in rr if r.get("kind") == "run_binding" and r.get("run_id") == rid]
    if not cb or cb.get("kind") != "binding":
        return False, {"rule": None, "problem": "checkpoint binding row missing"}
    if rb:
        if len(rb) != 1:
            return False, {"rule": "run_binding", "problem": f"{len(rb)} run_binding records"}
        missing = [k for k in keys if k not in rb[0] or k not in cb]
        diff = {k: [rb[0].get(k), cb.get(k)] for k in keys
                if k in rb[0] and k in cb and rb[0][k] != cb[k]}
        extra = ([] if doc.get("package_script_sha256") in (None, cb.get("primitives_sha256"))
                 else ["result doc package_script_sha256 != checkpoint primitives_sha256"])
        return (not missing and not diff and not extra,
                {"rule": "run_binding", "missing": missing, "diff": diff, "other": extra})
    legacy = LEGACY_SPEC_SHA256.get(header.get("spec_sha256"))
    if legacy is None:
        return False, {"rule": None,
                       "problem": "run_binding record missing and spec is not a legacy version"}
    problems = []
    if "primitives_sha256" not in cb:
        problems.append("checkpoint primitives_sha256 missing")
    elif doc.get("package_script_sha256") != cb["primitives_sha256"]:
        problems.append({"primitives": [doc.get("package_script_sha256"),
                                        cb.get("primitives_sha256")]})
    rp, hp = cb.get("runtime_params"), header.get("params") or {}
    if not isinstance(rp, dict) or not rp:
        problems.append("checkpoint runtime_params missing")
    else:
        for k, v in rp.items():
            hv = hp.get(k, "<absent>")
            if k == "diagnostics" and hv != "<absent>":
                hv = bool(hv)
            if hv != v:
                problems.append({"runtime_param": k, "header": hv, "checkpoint": v})
    return not problems, {"rule": f"legacy_{legacy}_header_params_and_result_doc",
                          "problems": problems}


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Checks:
    def __init__(self):
        self.items = {}

    def add(self, name, ok, detail=None):
        ok = ok is True                      # 只有真正的 True 才算通过；None / 真值对象都不算
        if name in self.items:               # 同名重复登记 ⇒ 取与
            prev = self.items[name]
            ok = ok and prev["ok"]
            detail = [prev.get("detail"), detail]
        self.items[name] = {"ok": ok, "detail": detail}
        return ok

    def guard(self, name, fn):
        """执行 fn()，返回 (ok, detail)。异常 ⇒ 记失败，不中断其余检查。"""
        try:
            ok, detail = fn()
        except Exception as e:                                        # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {str(e)[:200]}"
        self.add(name, ok, detail)
        return ok

    def verdict(self):
        base = lambda n: n.split(":", 1)[0]  # noqa: E731
        absent = [r for r in REQUIRED if not any(base(n) == r for n in self.items)]
        failed = sorted(n for n, v in self.items.items() if not v["ok"])
        return {"passed": bool(self.items) and not absent and not failed,
                "required_absent": absent, "failed": failed,
                "n_checks": len(self.items)}


def diff(a, b, path=""):
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
    elif a != b or type(a) is not type(b):
        out.append((path, a, b))
    return out


def _load_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


def _local(run_dir, recorded):
    """清单 / 检查点里记的路径只取文件名，在本次对照目录里定位。
    这样副本目录也能核对，同时保证引用的文件**确实属于这组运行**。"""
    return Path(run_dir) / Path(str(recorded)).name


def compare(a):
    ck = Checks()
    rep = {"inputs": {"dir": str(a.dir), "manifest": str(a.manifest),
                      "serial": a.serial, "parallel": a.parallel,
                      "sample": str(a.sample), "pin": a.pin,
                      "expect": {"script_sha256": a.expect_script_sha,
                                 "evidence_module_sha256": a.expect_evidence_sha,
                                 "spec_sha256": a.expect_spec_sha,
                                 "primitives_sha256": a.expect_primitives_sha,
                                 "runtime_params": a.expect_runtime_params}},
           "runs": {}, "mismatches": [], "allowed_diffs": [], "candidates": []}
    run_dir = Path(a.dir)
    sides = {"serial": list(a.serial), "parallel": list(a.parallel)}

    # ---- 清单：存在、每个声明的运行恰好一条、没有来历不明的条目 ----
    manifest = []
    if ck.guard("manifest_readable", lambda: (True, None) if Path(a.manifest).is_file()
                else (False, "manifest missing")):
        try:
            # 运行记录：旧清单无 kind 字段；新驱动写 kind=run，另有 driver_start/driver_end
            manifest = [m for m in _load_jsonl(a.manifest) if m.get("kind", "run") == "run"]
        except Exception as e:                                        # noqa: BLE001
            ck.add("manifest_readable", False, f"unparseable: {e}")
    all_tags = sides["serial"] + sides["parallel"]
    ck.add("chains_declared",
           bool(sides["serial"]) and bool(sides["parallel"])
           and len(all_tags) == len(set(all_tags)),
           {"serial": sides["serial"], "parallel": sides["parallel"]})
    entry = {}
    for t in all_tags:
        hits = [m for m in manifest if m.get("tag") == t]
        ck.add(f"manifest_entry_unique:{t}", len(hits) == 1, f"{len(hits)} entries")
        if len(hits) == 1:
            entry[t] = hits[0]
    ignored = set(a.ignore_tag or [])
    stray = [m.get("tag") for m in manifest if m.get("tag") not in set(all_tags) | ignored]
    attempt_ids = {m.get("attempt_id") for m in entry.values()}
    ck.add("manifest_all_attributed", not stray and len(attempt_ids) <= 1,
           {"unattributed_tags": stray, "attempt_ids": sorted(map(str, attempt_ids))})

    for side, tags in sides.items():
        cps = {str(entry[t].get("checkpoint")) for t in tags if t in entry}
        ck.add(f"chain_checkpoint_consistent:{side}",
               len(cps) == 1 and all(t in entry for t in tags), sorted(cps))
    cp_s = {str(entry[t].get("checkpoint")) for t in sides["serial"] if t in entry}
    cp_p = {str(entry[t].get("checkpoint")) for t in sides["parallel"] if t in entry}
    ck.add("chain_checkpoint_consistent:independent", bool(cp_s) and not (cp_s & cp_p),
           "serial and parallel must use separate checkpoints")
    for side, tags in sides.items():
        last = entry.get(tags[-1]) if tags else None
        ck.add(f"final_exit_0:{side}", last is not None and last.get("exit") == 0
               and isinstance(last.get("exit"), int),
               None if last is None else {"tag": tags[-1], "exit": last.get("exit")})

    # ---- 检查点（先读：判定"惰性启动失败"要用到它）----
    ckpt = {}
    for side, tags in sides.items():
        m = entry.get(tags[-1]) if tags else None
        cp = _local(run_dir, m.get("checkpoint")) if m else None
        if cp is not None and cp.is_file():
            try:
                ckpt[side] = _load_jsonl(cp)
            except Exception:                                         # noqa: BLE001
                ckpt[side] = None

    # ---- 每次运行：先定角色，再按角色核对 ----
    # 角色（审查 v1.17 P2：尝试历史 ≠ 结果所依赖的证据链）：
    #   startup_abort —— 启动阶段前置失败、**没有任何候选工作**的尝试：只有一个启动阶段 abort、
    #                    无运行头 / 绑定 / 候选记录 / Etherscan、RPC 全在启动阶段且不属于任何候选、
    #                    检查点里没有任何尝试引用它、不是该侧最后一次运行。
    #                    它保留为诊断历史，只核对这些"惰性"条件，不要求结果文件、运行头、footer。
    #   run           —— 其余一切运行，照旧逐项要求完整。任何结果被复用的运行都必须是完整 run
    #                    （由 final_results_traced 另行保证），所以不能靠"忽略失败尝试"绕过验收。
    docs, recs, headers, roles = {}, {}, {}, {}
    for side, tags in sides.items():
        for t in tags:
            m = entry.get(t, {})
            out_p = _local(run_dir, m.get("out") or f"{t}.json")
            ev_p = _local(run_dir, m.get("evidence") or f"{t}.evidence.jsonl")
            info = rep["runs"].setdefault(t, {"side": side, "out": out_p.name,
                                              "evidence": ev_p.name,
                                              "exit": m.get("exit"),
                                              "wall_s": m.get("wall_s")})
            rr, diag = ([], {}) if not ev_p.is_file() else E.read_evidence(ev_p, report=True)
            if ev_p.is_file():
                recs[t] = rr
                info["evidence_diag"] = {k: diag.get(k) for k in
                                         ("complete", "bad_lines", "runs_without_footer",
                                          "runs_without_header", "unmatched_rpc_begin",
                                          "orphan_rpc_end", "empty")}
            aborts = [r for r in rr if r.get("kind") == "abort"]
            looks_startup = (m.get("exit") not in (0, None) and len(aborts) >= 1
                             and any((x.get("reason"), m.get("exit")) in STARTUP_ABORTS
                                     for x in aborts))
            if looks_startup:
                roles[t] = info["role"] = "startup_abort"
                ok, detail = _startup_abort_inert(t, tags, m, rr, diag, ckpt.get(side))
                ck.add(f"startup_abort_inert:{t}", ok, detail)
                ck.add(f"run_parallel_matches_side:{t}",
                       m.get("parallel") == (1 if side == "serial" else m.get("parallel"))
                       and isinstance(m.get("parallel"), int)
                       and (m.get("parallel") == 1) == (side == "serial"),
                       {"manifest": m.get("parallel")})
                continue
            roles[t] = info["role"] = "run"
            if ck.guard(f"result_doc_present:{t}", lambda: (out_p.is_file(), out_p.name)):
                try:
                    docs[t] = json.loads(out_p.read_text(encoding="utf-8"))
                except Exception as e:                                # noqa: BLE001
                    ck.add(f"result_doc_present:{t}", False, f"unparseable: {e}")
            if not ev_p.is_file():
                for n in ("evidence_complete", "evidence_attributed", "footer_matches_result",
                          "run_binding_matches"):
                    ck.add(f"{n}:{t}", False, "evidence file missing")
                continue
            doc = docs.get(t) or {}
            rid = doc.get("run_id")
            hh = [r for r in rr if r.get("kind") == "run_header"]
            ff = [r for r in rr if r.get("kind") == "run_footer"]
            ck.add(f"evidence_complete:{t}",
                   diag.get("complete") is True and len(ff) == 1 and not aborts,
                   {"complete": diag.get("complete"), "footers": len(ff),
                    "aborts": [x.get("reason") for x in aborts]})
            ck.add(f"evidence_attributed:{t}",
                   rid is not None and len(hh) == 1 and hh[0].get("run_id") == rid
                   and set(diag.get("runs", {})) == {rid},
                   {"doc_run_id": rid, "headers": len(hh),
                    "runs_in_file": sorted(map(str, diag.get("runs", {})))})
            if hh:
                headers[t] = hh[0]
            ck.add(f"footer_matches_result:{t}",
                   len(ff) == 1 and ff[0].get("run_id") == rid
                   and ff[0].get("acceptance") == doc.get("acceptance")
                   and bool(doc.get("acceptance")), None)
            want_par = (lambda p: p == 1) if side == "serial" else (lambda p: p >= 2)
            p_doc, p_man = doc.get("parallel"), m.get("parallel")
            ck.add(f"run_parallel_matches_side:{t}",
                   isinstance(p_doc, int) and want_par(p_doc) and p_man == p_doc,
                   {"doc": p_doc, "manifest": p_man})
            ok, detail = _run_binding_ok(rr, rid, hh[0] if hh else {}, doc,
                                         (ckpt.get(side) or [{}])[0])
            info["binding_rule"] = detail.get("rule")
            ck.add(f"run_binding_matches:{t}", ok, detail)

    # ---- 绑定：所有完整运行彼此一致，且等于显式给出的期望值 ----
    def bind_of(h):
        s = h.get("finalized_snapshot") or {}
        return {"script_sha256": h.get("script_sha256"),
                "evidence_module_sha256": h.get("evidence_module_sha256"),
                "spec_sha256": h.get("spec_sha256"),
                "sample_sha256": h.get("sample_sha256"),
                "universe_sha256": h.get("universe_sha256_now"),
                "universe_match": h.get("universe_match"),
                "chain_id": h.get("chain_id"),
                "finalized_number": s.get("number"), "finalized_hash": s.get("hash"),
                "params": h.get("params")}
    binds = {t: bind_of(h) for t, h in headers.items()}
    ref = next(iter(binds.values()), None)
    full_runs = [t for t in all_tags if roles.get(t) == "run"]
    ck.add("binding_consistent",
           ref is not None and len(binds) == len(full_runs) and bool(full_runs)
           and all(b == ref for b in binds.values()),
           {t: {k: v for k, v in b.items() if ref is None or v != ref.get(k)}
            for t, b in binds.items()})
    try:
        pin_n, pin_h = a.pin.split(":", 1)
        pin_n = int(pin_n)
    except ValueError:
        pin_n, pin_h = None, None
    sample_sha = sha256(a.sample) if Path(a.sample).is_file() else None
    expect = {"script_sha256": a.expect_script_sha,
              "evidence_module_sha256": a.expect_evidence_sha,
              "spec_sha256": a.expect_spec_sha, "sample_sha256": sample_sha,
              "finalized_number": pin_n, "finalized_hash": pin_h,
              "universe_match": True, "chain_id": 1}
    got = {k: (ref or {}).get(k) for k in expect}
    ck.add("binding_matches_expected",
           ref is not None and all(v is not None for v in expect.values()) and got == expect,
           {k: {"expected": expect[k], "got": got[k]} for k in expect if got[k] != expect[k]})

    # ---- 检查点绑定：**全部** BINDING_KEYS 必须在场，且等于运行头 / 显式期望 ----
    # 旧版只取了 7 个键，漏了 primitives_sha256 与 runtime_params：把它们改掉或删掉，
    # 比较器照样 53 项全过（审查 v1.17 P1）。键表直接取测量程序自己的 BINDING_KEYS，不另抄一份。
    want_cb = {k: (ref or {}).get(k) for k in
               ("script_sha256", "evidence_module_sha256", "spec_sha256", "sample_sha256",
                "universe_sha256", "finalized_number", "finalized_hash")}
    want_cb.update(primitives_sha256=a.expect_primitives_sha,
                   runtime_params=a.expect_runtime_params)
    for side in sides:
        rows = ckpt.get(side)
        b = (rows or [{}])[0]
        missing = [k for k in E.Checkpoint.BINDING_KEYS if k not in b]
        uncovered = [k for k in E.Checkpoint.BINDING_KEYS if k not in want_cb]
        diffs = {k: [b.get(k), want_cb.get(k)] for k in E.Checkpoint.BINDING_KEYS
                 if k in b and b.get(k) != want_cb.get(k)}
        ck.add(f"checkpoint_binding:{side}",
               bool(rows) and b.get("kind") == "binding" and ref is not None
               and not missing and not uncovered and not diffs
               and all(v is not None for v in want_cb.values()),
               {"missing": missing, "not_checked": uncovered, "diff": diffs}
               if rows else "checkpoint missing or unreadable")

    # ---- 样本 ----
    sample = {}

    def _sample():
        s = json.loads(Path(a.sample).read_text(encoding="utf-8"))
        idx = [c["index"] for c in s["sample"]]
        sample.update({c["index"]: c for c in s["sample"]})
        return (len(idx) > 0 and s.get("n") == len(idx) == len(set(idx)),
                {"n": s.get("n"), "rows": len(idx), "unique": len(set(idx))})
    ck.guard("sample_well_formed", _sample)

    # ---- 最终累计结果：一候选恰好一条、与样本逐项一致、验收干净、逐条回溯到证据 ----
    finals = {}
    for side, tags in sides.items():
        t = tags[-1] if tags else None
        doc = docs.get(t) or {}
        res = doc.get("results") or []
        idx = [r.get("index") for r in res]
        finals[side] = {r.get("index"): r for r in res}
        field_bad = [(r.get("index"), f) for r in res for f in ("pair", "token", "created_block")
                     if r.get(f) != (sample.get(r.get("index")) or {}).get(f)]
        ck.add(f"final_results_one_per_candidate:{side}",
               bool(sample) and len(idx) == len(set(idx)) and sorted(idx) == sorted(sample)
               and not field_bad,
               {"n": len(idx), "unique": len(set(idx)), "sample_n": len(sample),
                "field_mismatch": field_bad[:10]})
        acc = doc.get("acceptance") or {}
        # v1.16 及以前的结果没有 validation_unavailable 字段（那时校验不可能是"未知"）。
        # 缺这个字段可以接受，但下面另行要求**每条**结果 validation_passed 恰为 True，
        # 所以缺字段不会放过任何未完成的校验。其余清单字段缺失一律算不干净。
        bad = {k: acc.get(k) for k in _MUST_BE_EMPTY if acc.get(k) != []
               and not (k == "validation_unavailable" and k not in acc)}
        flags = {"set_complete": acc.get("set_complete"),
                 "process_completed": acc.get("process_completed"),
                 "validation_passed": acc.get("validation_passed"),
                 "shutdown_stopped": (acc.get("shutdown") or {}).get("stopped")}
        # 经济资格与测量语义必须仍是 false；它们变 true 说明结果文件不是本流程产的
        closed = {"measurement_semantics_verified": acc.get("measurement_semantics_verified"),
                  "economic_results_eligible": acc.get("economic_results_eligible")}
        ck.add(f"final_acceptance_clean:{side}",
               bool(acc) and not bad and flags == {"set_complete": True,
                                                   "process_completed": True,
                                                   "validation_passed": True,
                                                   "shutdown_stopped": False}
               and closed == {"measurement_semantics_verified": False,
                              "economic_results_eligible": False}
               and all(r.get("economic_eligible") is False for r in res) and bool(res)
               and all(r.get("validation_passed") is True for r in res),
               {"non_empty": bad, "flags": flags, "closed": closed,
                "validation_not_true": [r.get("index") for r in res
                                        if r.get("validation_passed") is not True]})

        def _trace(side=side, tags=tags, res=res):
            rows = ckpt.get(side) or []
            if not rows or not res:
                return False, "no checkpoint rows or no results"
            binding = rows[0]
            done = {}
            for x in rows[1:]:
                if x.get("kind") == "attempt" and x.get("completed") is True:
                    done[x.get("candidate")] = x
            # 结果只能依赖完整运行；惰性启动失败永远不是结果祖先
            ev_of = {rep["runs"][t]["evidence"]: t for t in tags
                     if t in rep["runs"] and roles.get(t) == "run"}
            problems = []
            for r in res:
                i = r.get("index")
                x = done.get(i)
                if x is None:
                    problems.append({"candidate": i, "reason": "no completed attempt"})
                    continue
                bare = {k: v for k, v in r.items() if k != "carried_from_checkpoint"}
                if bare != x.get("result"):
                    problems.append({"candidate": i, "reason": "result differs from checkpoint"})
                if E.result_sha256_of(bare) != x.get("result_sha256"):
                    problems.append({"candidate": i, "reason": "result hash mismatch"})
                evn = Path(str(x.get("evidence_file"))).name
                src = ev_of.get(evn)
                if src is None:
                    problems.append({"candidate": i, "reason": "evidence not in this chain",
                                     "evidence": evn})
                    continue
                if x.get("evidence_run_id") != (docs.get(src) or {}).get("run_id"):
                    problems.append({"candidate": i, "reason": "evidence run_id not that run"})
                carried = bool(r.get("carried_from_checkpoint"))
                if carried == (src == tags[-1]):
                    problems.append({"candidate": i, "reason": "carried flag vs source run",
                                     "source": src, "carried": carried})
                problems += [dict(p, candidate=i) for p in E.verify_evidence_supports(
                    run_dir / evn, run_id=x.get("evidence_run_id"), candidate=i,
                    result_sha256=x.get("result_sha256"), binding=binding)]
                r["_source_run"] = src
            return not problems and len(res) == len(sample), problems[:20]
        ck.guard(f"final_results_traced:{side}", _trace)

    # ---- 两侧比较 ----
    S, P = finals.get("serial") or {}, finals.get("parallel") or {}
    ds = docs.get(sides["serial"][-1]) if sides["serial"] else None
    dp = docs.get(sides["parallel"][-1]) if sides["parallel"] else None
    snap_s = (ds or {}).get("finalized_snapshot") or {}
    snap_p = (dp or {}).get("finalized_snapshot") or {}
    ck.add("same_snapshot", bool(snap_s) and snap_s == snap_p
           and snap_s.get("number") == pin_n and snap_s.get("hash") == pin_h,
           {"serial": snap_s, "parallel": snap_p})
    ck.add("same_candidate_set", bool(S) and sorted(S) == sorted(P),
           {"serial_only": sorted(set(S) - set(P)), "parallel_only": sorted(set(P) - set(S))})
    for i in sorted(set(S) & set(P)):
        x = {k: v for k, v in S[i].items() if k != "_source_run"}
        y = {k: v for k, v in P[i].items() if k != "_source_run"}
        for p_, u, v in diff(x, y):
            rep["mismatches"].append({"candidate": i, "path": p_, "serial": u, "parallel": v})
        for k in sorted(ALLOWED):
            if x.get(k) != y.get(k):
                rep["allowed_diffs"].append({"candidate": i, "field": k,
                                             "serial": x.get(k), "parallel": y.get(k)})
    ck.add("results_identical_except_allowed",
           bool(S) and bool(set(S) & set(P)) and not rep["mismatches"],
           f"{len(rep['mismatches'])} mismatches")

    # 缓存口径：缓存命中记录没有 candidate 字段，按同一 worker 的 candidate_start/end 区间归属
    def _usage(tag, cand):
        rows = [z for z in recs.get(tag, []) if z.get("run_id") == (docs.get(tag) or {}).get("run_id")]
        active, rpc, hit = {}, 0, 0
        for z in rows:
            w = z.get("worker")
            if z.get("kind") == "candidate_start":
                if w in active:
                    raise ValueError(f"{tag}: nested candidate_start on worker {w}")
                active[w] = z.get("candidate")
            cur = active.get(w)
            if z.get("kind") == "rpc" and z.get("candidate") == cand:
                rpc += 1
            if z.get("kind") == "block_cache_hit" and cur == cand:
                hit += 1
            if z.get("kind") == "candidate_end":
                if active.pop(w, None) != z.get("candidate"):
                    raise ValueError(f"{tag}: unmatched candidate_end on worker {w}")
        if active:
            raise ValueError(f"{tag}: candidate spans left open {active}")
        return rpc, hit

    def _cache():
        rows, ok = [], bool(S) and bool(set(S) & set(P))
        for i in sorted(set(S) & set(P)):
            ts, tp = S[i].get("_source_run"), P[i].get("_source_run")
            if not ts or not tp:
                return False, f"candidate {i}: source run unknown (trace failed)"
            rs, hs = _usage(ts, i)
            rp, hp = _usage(tp, i)
            same = (rs == S[i].get("rpc_calls") and rp == P[i].get("rpc_calls")
                    and rs + hs == rp + hp)
            ok = ok and same
            rows.append({"candidate": i, "serial": [rs, hs], "parallel": [rp, hp], "ok": same})
            rep["candidates"].append({"index": i, "state": S[i].get("state"),
                                      "source": [ts, tp], "rpc": [rs, rp], "cache_hits": [hs, hp]})
        return ok, rows
    ck.guard("rpc_plus_cache_equal", _cache)

    for side in finals:
        for r in finals[side].values():
            r.pop("_source_run", None)
    rep["checks"] = ck.items
    rep["verdict"] = ck.verdict()
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True, help="这组运行的结果 / 证据 / 检查点所在目录")
    ap.add_argument("--manifest", help="运行清单 runs.jsonl（默认 <dir>/runs.jsonl）")
    ap.add_argument("--serial", required=True,
                    help="串行一侧的运行标签，按执行顺序逗号分隔；最后一个是最终累计运行")
    ap.add_argument("--parallel", required=True, help="并行一侧，同上")
    ap.add_argument("--ignore-tag", action="append",
                    help="清单里与本对照无关、明确排除的运行标签（可重复）")
    ap.add_argument("--sample", required=True)
    ap.add_argument("--pin", required=True, help="finalized 快照 NUMBER:HASH")
    ap.add_argument("--expect-script-sha", required=True)
    ap.add_argument("--expect-evidence-sha", required=True)
    ap.add_argument("--expect-spec-sha", required=True)
    ap.add_argument("--expect-primitives-sha", required=True,
                    help="冻结包测量原语 verify_capabilities.py 的 sha256")
    ap.add_argument("--expect-runtime-params", required=True,
                    help='检查点绑定的测量参数，JSON，例如 \'{"slot_limit": 32, ...}\'')
    ap.add_argument("--out", required=True, help="报告路径；已存在则拒绝（不覆盖）")
    a = ap.parse_args(argv)
    a.manifest = a.manifest or str(Path(a.dir) / "runs.jsonl")
    try:
        a.expect_runtime_params = json.loads(a.expect_runtime_params)
        assert isinstance(a.expect_runtime_params, dict) and a.expect_runtime_params
    except (ValueError, AssertionError):
        print("compare_runs: --expect-runtime-params 必须是非空 JSON 对象", file=sys.stderr)
        return 2
    a.serial = [x for x in a.serial.split(",") if x]
    a.parallel = [x for x in a.parallel.split(",") if x]
    out = Path(a.out)
    if out.exists():
        print(f"compare_runs: 输出 {out} 已存在，拒绝覆盖", file=sys.stderr)
        return 2
    rep = compare(a)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        f.write(json.dumps(rep, ensure_ascii=False, indent=2, default=str) + "\n")
    v = rep["verdict"]
    print(json.dumps({"passed": v["passed"], "failed": v["failed"][:20],
                      "required_absent": v["required_absent"], "n_checks": v["n_checks"]},
                     ensure_ascii=False))
    return 0 if v["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

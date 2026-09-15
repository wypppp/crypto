print("\n28 续跑与比较器共用同一套完整绑定核验")
# 审核 v1.18 P1：只改原运行证据里的 run_binding（参数 / 原语 hash / 让它缺席），
# measure 续跑仍退出 0、跳过两个候选、evidence_chain_problems=[]；同一份交付比较器退出 1。
# 完整核对原先只在比较器里。现在规则在 evidence.verify_run_binding 一处，续跑守卫与比较器都调用它。
import subprocess as _sp28
import hashlib as _hl28


def _rb_edit28(path, fn):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    for r in rows:
        if r.get("kind") == "run_binding":
            fn(r)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


_MODES28 = [
    ("无改动正对照", None, None),
    ("run_binding.runtime_params.slot_limit 2→999",
     lambda r: r["runtime_params"].update(slot_limit=999), "evidence_run_binding_mismatch"),
    ("run_binding.primitives_sha256 改成全 0",
     lambda r: r.update(primitives_sha256="0" * 64), "evidence_run_binding_mismatch"),
    ("run_binding 缺席（kind 改名，seq 保持连续）",
     lambda r: r.update(kind="run_binding_removed"), "evidence_run_binding_missing"),
]
for _nm, _fn, _want in _MODES28:
    d = tmp()
    ck = d / "shared.ck"
    rc1, _d1, _, _ = A.flow(d, "first", checkpoint=ck)
    if _fn:
        _rb_edit28(d / "first.jsonl", _fn)
    _ev_ok = E.read_evidence(d / "first.jsonl", report=True)[1]["complete"] is True
    _ck_before = (ck.read_text().splitlines())
    rc2, doc2, _, _ = A.flow(d, "resume", checkpoint=ck)
    a2 = acc(doc2, "acceptance", {})
    probs = acc(a2, "evidence_chain_problems", []) or []
    reasons = sorted({p.get("reason") for p in probs})
    check(f"{_nm}：首跑退出 0、改动后原证据结构仍完整", rc1 == 0 and _ev_ok, f"rc={rc1} ev={_ev_ok}")
    if _fn is None:
        check(f"{_nm}：续跑退出 0、跳过 [1,2]、证据链无问题、处置 none",
              rc2 == 0 and acc(a2, "skipped_already_completed") == [1, 2] and probs == []
              and acc(a2, "evidence_chain_action") == "none",
              f"rc={rc2} skipped={acc(a2, 'skipped_already_completed')} probs={reasons}")
    else:
        check(f"{_nm}：续跑退出 1（旧版退出 0）", rc2 == 1, f"rc={rc2}")
        check(f"{_nm}：证据链问题逐候选点名 {_want}",
              sorted({p.get("candidate") for p in probs if p.get("reason") == _want}) == [1, 2],
              str(reasons))
        check(f"{_nm}：验收不通过、处置写明带出但阻断且需新检查点",
              acc(a2, "validation_passed") is False
              and str(acc(a2, "evidence_chain_action", "")).startswith("carried_but_blocked"),
              f"{acc(a2, 'validation_passed')} {acc(a2, 'evidence_chain_action')}")
        check(f"{_nm}：结果与失败历史照常保留（两条带出结果、检查点原有记录一行不少）",
              len(doc2["results"]) == 2 and all(r.get("carried_from_checkpoint")
                                                for r in doc2["results"])
              and ck.read_text().splitlines()[:len(_ck_before)] == _ck_before,
              f"n={len(doc2['results'])}")
    # 同一份交付交给比较器：结论与续跑一致，且点名的问题来自同一套规则
    rcp, _dp, _, _ = A.flow(d, "parallel", parallel=2, checkpoint=d / "parallel.ck")
    b = json.loads(ck.read_text().splitlines()[0])
    man = d / "manifest.jsonl"
    man.write_text("".join(json.dumps(dict(kind="run", tag=t, parallel=p_, exit=e_,
                                           checkpoint=str(d / c_), out=str(d / (t + ".json")),
                                           evidence=str(d / (t + ".jsonl")))) + "\n"
                           for t, p_, e_, c_ in [("first", 1, rc1, "shared.ck"),
                                                 ("resume", 1, rc2, "shared.ck"),
                                                 ("parallel", 2, rcp, "parallel.ck")]))
    _cmd = [sys.executable, str(Path(A.__file__).resolve().parent / "realchain_tools" / "compare_runs.py"),
            "--dir", str(d), "--manifest", str(man), "--serial", "first,resume",
            "--parallel", "parallel", "--sample", str(d / "sample.json"),
            "--pin", f"{b['finalized_number']}:{b['finalized_hash']}",
            "--expect-script-sha", b["script_sha256"], "--expect-evidence-sha", b["evidence_module_sha256"],
            "--expect-spec-sha", b["spec_sha256"], "--expect-primitives-sha", b["primitives_sha256"],
            "--expect-runtime-params", json.dumps(b["runtime_params"]), "--out", str(d / "cmp.json")]
    _r = _sp28.run(_cmd, capture_output=True, text=True, timeout=180)
    _rep = json.loads((d / "cmp.json").read_text()) if (d / "cmp.json").is_file() else {}
    _failed = (_rep.get("verdict") or {}).get("failed", [])
    _cmp_reasons = sorted({p.get("reason") for p in (
        (_rep.get("checks") or {}).get("run_binding_matches:first", {}).get("detail") or {}).get("problems", [])})
    if _fn is None:
        check(f"{_nm}：比较器同样通过（退出 0）", _r.returncode == 0, f"rc={_r.returncode} {_failed[:3]}")
    else:
        check(f"{_nm}：比较器同样拒绝，且点名 run_binding_matches:first 与结果回溯",
              _r.returncode == 1 and "run_binding_matches:first" in _failed
              and "final_results_traced:serial" in _failed, f"rc={_r.returncode} {_failed[:5]}")
        check(f"{_nm}：两个入口给出的绑定问题原因相同（同一套规则）",
              _cmp_reasons == [_want] and [x for x in reasons if x.startswith("evidence_run_binding")]
              == [_want], f"resume={reasons} comparator={_cmp_reasons}")

# 旧版规则只对精确的 (脚本, 规格) 两对开放；常量必须等于真实文件的 hash
_sha28 = lambda p: _hl28.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
_W28 = Path(A.__file__).resolve().parent
_pairs28 = {v: k for k, v in getattr(E, "LEGACY_BINDING_RULES", {}).items()}
check("旧版规则常量 = v1.16/v1.17 审核快照脚本与对应规格的真实 hash（防手抄错）",
      _pairs28.get("v1.16") == (_sha28(_W28 / "audit_v116_20260911/pilot_measure.audited.py"),
                                _sha28(_W28 / "MEASUREMENT_SPEC.v1.16.md"))
      and _pairs28.get("v1.17") == (_sha28(_W28 / "audit_v117_20260911/pilot_measure.audited.py"),
                                    _sha28(_W28 / "MEASUREMENT_SPEC.v1.17.md"))
      and len(_pairs28) == 2, str({k: (a[:12], b_[:12]) for k, (a, b_) in _pairs28.items()}))
_R2_28 = _W28 / "runs/realchain2_20260911"
_ev28 = [json.loads(x) for x in (_R2_28 / "serial.evidence.jsonl").read_text().splitlines() if x.strip()]
_ck28 = json.loads((_R2_28 / "serial.checkpoint.jsonl").read_text().splitlines()[0])
_doc28 = json.loads((_R2_28 / "serial.json").read_text())
_vrb = getattr(E, "verify_run_binding", None)
if _vrb:
    _p28, _rule28 = _vrb(_ev28, _doc28["run_id"], _ck28, result_doc=_doc28)
    check("真链 v1.16 证据走旧版规则且通过（只读原件）",
          _p28 == [] and _rule28 == "legacy_v1.16_header_params_and_result_doc", f"{_p28} {_rule28}")
    _p28b, _ = _vrb(_ev28, _doc28["run_id"], _ck28)
    check("旧版规则拿不到结果文件时判问题、不跳过",
          [x.get("reason") for x in _p28b] == ["legacy_rule_needs_result_document"], str(_p28b))
    _ev28c = [dict(r, script_sha256="f" * 64) if r.get("kind") == "run_header" else r for r in _ev28]
    _p28c, _ = _vrb(_ev28c, _doc28["run_id"], _ck28, result_doc=_doc28)
    check("(脚本, 规格) 不是登记的旧版对 ⇒ 缺 run_binding 即问题",
          [x.get("reason") for x in _p28c] == ["evidence_run_binding_missing"], str(_p28c))
    _p28d, _ = _vrb(_ev28, _doc28["run_id"], dict(_ck28, runtime_params=dict(
        _ck28["runtime_params"], slot_limit=0)), result_doc=_doc28)
    check("旧版规则：检查点 runtime_params 与运行头 params 不符被抓到",
          "legacy_runtime_param_mismatch" in [x.get("reason") for x in _p28d], str(_p28d)[:120])
else:
    check("evidence.verify_run_binding 存在（共用规则）", False, "absent")


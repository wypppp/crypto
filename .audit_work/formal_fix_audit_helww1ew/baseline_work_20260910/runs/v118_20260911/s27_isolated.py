print("\n27 已证不符 + 后续中断：不符与中断原因都保留，不折成'未知'")
# 审核 v1.17 P1：两侧已证不符后 getPair 断连、钱包代码已变后读余额预算耗尽、
# 入场钱包已有代码后预算耗尽 —— 旧版只剩 unavailable/null、failures 为空。
# 原因：校验与恢复的局部累积随异常丢失，收尾再写空占位。这里用完整 measure 流程逐条核对。
_mark27, _req27, _call27 = E.RpcTap.mark, A.FakeRpc.request, A.FakeRpc.call
_BAD27 = "0x" + "0" * 24 + "99" * 20


def _flow27(tag, rules):
    """rules 按顺序逐条触发、每条一次，只作用于候选 1。
    每条 dict(stage, op='request'|'call', method=None, sel=None, who=None, action)。
    action ∈ transport / budget（RpcFailure kind=budget）/ gate_budget（闸门 BudgetExhausted）
    / shutdown / ("return", 值)。"""
    todo, fired = list(rules), []

    def mark(self, *a, **k):
        r = _mark27(self, *a, **k)
        self.rpc._s27, self.rpc._c27 = self.stage, self.candidate
        return r

    def hit(raw, op, method, sel=None, who=None):
        if not todo or getattr(raw, "_c27", None) != 1:
            return None
        r = todo[0]
        if (raw._s27 != r["stage"] or op != r["op"]
                or (r.get("method") and r["method"] != method)
                or (r.get("sel") and P.V.selector(r["sel"]) != sel)
                or (r.get("who") and (who or "").lower() != r["who"].lower())):
            return None
        todo.pop(0)
        act = r["action"]
        fired.append((r["stage"], method, r.get("sel"), act if isinstance(act, str) else act[0]))
        raw.records.append({"method": method, "params": [who], "audit27": True})
        if act == "transport":
            raise P.V.RpcFailure("transport", "controlled TLS EOF")
        if act == "budget":
            raise P.V.RpcFailure("budget", "controlled budget stop")
        if act == "gate_budget":
            raise E.BudgetExhausted("controlled shared budget exhausted")
        if act == "shutdown":
            raise E.Shutdown("controlled_stop", {"where": r["stage"]})
        return act

    def request(self, method, params):
        act = hit(self, "request", method, who=(params or [None])[0])
        return act[1] if act is not None else _req27(self, method, params)

    def call(self, to, data, block, overrides=None):
        act = hit(self, "call", "eth_call", sel=data[2:10])
        return act[1] if act is not None else _call27(self, to, data, block, overrides)

    d = tmp()
    with patch.object(E.RpcTap, "mark", mark), patch.object(A.FakeRpc, "request", request), \
            patch.object(A.FakeRpc, "call", call):
        rc, doc, rows, _ = A.flow(d, tag)
    ck = [json.loads(x) for x in (d / (tag + ".ck")).read_text().splitlines() if x.strip()]
    att = [x for x in ck if x.get("candidate") == 1]
    res = {r["index"]: r for r in doc["results"]}
    return dict(rc=rc, doc=doc, rows=rows, c1=res.get(1) or {}, c2=res.get(2) or {},
                fired=fired, left=todo, ck_done=bool(att) and att[-1].get("completed") is True,
                ev_ok=E.read_evidence(d / (tag + ".jsonl"), report=True)[1]["complete"] is True)


_W27 = P.V.WALLET
_CASES27 = [
    # name, rules, part, want_failure_substr, want_unavailable_kind, want_prior_state
    ("两侧不符后 getPair 断连",
     [dict(stage="state_validation", op="call", sel="token0()", action=("return", _BAD27)),
      dict(stage="state_validation", op="call", sel="getPair(address,address)", action="transport")],
     "state_validation", "pair sides", "transport", None),
    ("两侧不符后 getPair 预算耗尽（闸门）",
     [dict(stage="state_validation", op="call", sel="token0()", action=("return", _BAD27)),
      dict(stage="state_validation", op="call", sel="getPair(address,address)",
           action="gate_budget")],
     "state_validation", "pair sides", "budget", "budget_exhausted"),
    ("恢复复读钱包代码已变后读余额预算耗尽（RpcFailure budget）",
     [dict(stage="restore_check", op="request", method="eth_getCode", who=_W27,
           action=("return", "0x60")),
      dict(stage="restore_check", op="request", method="eth_getBalance", who=_W27,
           action="budget")],
     "restore_check", "code persisted", "budget", "budget_exhausted"),
    ("恢复复读钱包代码已变后预算耗尽（闸门）",
     [dict(stage="restore_check", op="request", method="eth_getCode", who=_W27,
           action=("return", "0x60")),
      dict(stage="restore_check", op="request", method="eth_getBalance", who=_W27,
           action="gate_budget")],
     "restore_check", "code persisted", "budget", "budget_exhausted"),
    ("入场钱包已有代码后读余额预算耗尽",
     [dict(stage="state_validation", op="request", method="eth_getCode", who=_W27,
           action=("return", "0x60")),
      dict(stage="state_validation", op="request", method="eth_getBalance", who=_W27,
           action="budget")],
     "state_validation", "already has code", "budget", "budget_exhausted"),
    ("出场钱包已有代码后停机",
     [dict(stage="state_validation_exit", op="request", method="eth_getCode", who=_W27,
           action=("return", "0x60")),
      dict(stage="state_validation_exit", op="request", method="eth_getBalance", who=_W27,
           action="shutdown")],
     "state_validation_exit", "already has code", "shutdown", "aborted_by_shutdown"),
]
for _nm, _rules, _part, _fs, _uk, _prior in _CASES27:
    f = _flow27("t27", _rules)
    c, a = f["c1"], acc(f["doc"], "acceptance", {})
    p_ = c.get(_part) or {}
    check(f"{_nm}：两条注入依次命中", len(f["fired"]) == 2 and not f["left"], str(f["fired"]))
    check(f"{_nm}：已证不符保留在 failures",
          any(_fs in x for x in p_.get("failures") or []), str(p_.get("failures"))[:120])
    check(f"{_nm}：后续中断记为 unavailable（{_uk}）",
          any(u.get("error_kind") == _uk for u in p_.get("unavailable") or [])
          and not any(u.get("error_kind") == "not_completed" for u in p_.get("unavailable") or []),
          str([(u.get("step"), u.get("error_kind")) for u in p_.get("unavailable") or []]))
    check(f"{_nm}：结论 failed / state_validation_failed / validation_passed=False",
          p_.get("status") == "failed" and c.get("state") == "state_validation_failed"
          and c.get("validation_status") == "failed" and c.get("validation_passed") is False,
          f"{p_.get('status')} {c.get('state')} {c.get('validation_status')}")
    _iam = (c.get("data") or {}).get("interrupted_after_mismatch")
    # 主流程里被打断时，原因原本就写在 data（budget / shutdown）；恢复阶段的原因写在
    # restore_check.unavailable（上一条已核）。两处都不得因改判 failed 而被抹掉。
    _own = {"budget_exhausted": "budget", "aborted_by_shutdown": "shutdown"}.get(_prior)
    check(f"{_nm}：中断原因另记（prior_state={_prior}），原有 data 不丢",
          (_iam is None) if _prior is None else
          (bool(_iam) and _iam.get("prior_state") == _prior and _part in _iam.get("mismatch_in", [])
           and (_part == "restore_check" or _own in (c.get("data") or {}))),
          str(c.get("data"))[:160])
    check(f"{_nm}：验收列入 validation_failed、不列 unavailable；退出 1；检查点未完成；证据完整",
          acc(a, "validation_failed") == [1] and acc(a, "validation_unavailable") == []
          and f["rc"] == 1 and not f["ck_done"] and f["ev_ok"],
          f"failed={acc(a, 'validation_failed')} unav={acc(a, 'validation_unavailable')} "
          f"rc={f['rc']} ck={f['ck_done']} ev={f['ev_ok']}")
    _kind = "wallet_restore_check" if _part == "restore_check" else "state_validation"
    _ev = [r for r in f["rows"] if r.get("kind") == _kind and r.get("candidate") == 1]
    check(f"{_nm}：证据里的校验摘要也带着不符",
          any(any(_fs in x for x in (r.get("failures") or [])) for r in _ev),
          str([(r.get("status") or r.get("passed"), r.get("failures")) for r in _ev])[:140])
    check(f"{_nm}：另一候选不受影响",
          f["c2"].get("state") == "measured_exit" and f["c2"].get("validation_passed") is True)

# 无不符的对照：同样的中断不应凭空变成 failed
f = _flow27("t27c", [dict(stage="restore_check", op="request", method="eth_getBalance",
                          who=_W27, action="gate_budget")])
c = f["c1"]
_rc27 = c.get("restore_check") or {}
check("对照：恢复复读无不符、只预算耗尽 ⇒ budget_exhausted / unavailable，failures 为空",
      len(f["fired"]) == 1 and c.get("state") == "budget_exhausted"
      and _rc27.get("status") == "unavailable" and not _rc27.get("failures")
      and not (c.get("data") or {}).get("interrupted_after_mismatch"),
      f"{c.get('state')} {_rc27.get('status')}")
f = _flow27("t27d", [dict(stage="state_validation", op="call", sel="getPair(address,address)",
                          action="transport")])
c = f["c1"]
check("对照：两侧正确、只 getPair 断连 ⇒ data_missing / unavailable，closure 保留已取得的两侧",
      c.get("state") == "data_missing" and c.get("validation_status") == "unavailable"
      and (c.get("state_validation") or {}).get("identity_closure", {}).get("token1") == A.TOKEN,
      f"{c.get('state')} {(c.get('state_validation') or {}).get('identity_closure')}")


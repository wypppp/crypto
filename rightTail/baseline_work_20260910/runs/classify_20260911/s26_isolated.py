print("\n26 校验四态：接口故障 ≠ 状态不符；未完成 ≠ 通过；各原因各记各的")
# 审核 v1.16 P1：受控传输错误打在校验各阶段，旧版要么记"没做完却 validation_passed=true"，
# 要么把接口故障写成 state_validation_failed，出场取代码失败后恢复检查还凭空报出 4 条
# "persisted"。这里走**完整 measure 流程**，逐项核对状态、四态、退出码、成本、证据与检查点，
# 并配上真实不符／真实状态变化／no_mint 三组对照 —— 否则"全记 data_missing"也能蒙混过关。
_mark26, _req26, _call26 = E.RpcTap.mark, A.FakeRpc.request, A.FakeRpc.call


def _flow26(tag, rules=(), d=None, **kw):
    """rules：按顺序逐条触发、每条一次，只作用于候选 1。
    每条 (stage, op, method, action)；method=None 表示该阶段该类调用的第一个。
    action ∈ transport / budget / shutdown / ("return", 值)。"""
    todo, fired = list(rules), []

    def mark(self, *a, **k):
        r = _mark26(self, *a, **k)
        self.rpc._s26, self.rpc._c26 = self.stage, self.candidate
        return r

    def hit(raw, op, method):
        if not todo or getattr(raw, "_c26", None) != 1:
            return None
        stage, op_, m_, action = todo[0]
        if raw._s26 != stage or op != op_ or (m_ is not None and m_ != method):
            return None
        todo.pop(0)
        fired.append((stage, op, method, action if isinstance(action, str) else action[0]))
        if action == "transport":
            raise P.V.RpcFailure("transport", "controlled TLS EOF")
        if action == "budget":
            raise P.V.RpcFailure("budget", "controlled budget stop")
        if action == "shutdown":
            raise E.Shutdown("controlled_stop", {"where": stage})
        return action

    def request(self, method, params):
        act = hit(self, "request", method)
        if act is not None:
            self.records.append({"method": method, "params": params})
            return act[1]
        return _req26(self, method, params)

    def call(self, to, data, block, overrides=None):
        act = hit(self, "call", "eth_call")
        if act is not None:
            self.records.append({"method": "eth_call", "params": [to, data[:10], block]})
            return act[1]
        return _call26(self, to, data, block, overrides)

    d = d or tmp()
    with patch.object(E.RpcTap, "mark", mark), patch.object(A.FakeRpc, "request", request), \
            patch.object(A.FakeRpc, "call", call):
        rc, doc, rows, _ = A.flow(d, tag, **kw)
    ckp = Path(kw.get("checkpoint") or d / (tag + ".ck"))
    ck = [json.loads(x) for x in ckp.read_text().splitlines() if x.strip()]
    att = [x for x in ck if x.get("candidate") == 1]
    diag = E.read_evidence(d / (tag + ".jsonl"), report=True)[1]
    res = {r["index"]: r for r in doc["results"]}
    return dict(rc=rc, doc=doc, rows=rows, c1=res.get(1) or {}, c2=res.get(2) or {},
                ck_done=bool(att) and att[-1].get("completed") is True, fired=fired,
                ev_ok=diag["complete"] is True, left=todo, d=d)


def _rs(c):
    return c.get("restore_check") or {}


# ---- 26a 五条完整流程：接口故障 ⇒ data_missing + unavailable ----
_SC26 = [("入场取代码", "state_validation", "request", "entry"),
         ("入场身份调用", "state_validation", "call", "entry"),
         ("出场取代码", "state_validation_exit", "request", "exit"),
         ("出场身份调用", "state_validation_exit", "call", "exit"),
         ("恢复复读", "restore_check", "request", "restore")]
for _nm, _stg, _op, _where in _SC26:
    f = _flow26("t26" + _where + _op, [(_stg, _op, None, "transport")])
    c, a = f["c1"], acc(f["doc"], "acceptance", {})
    check(f"{_nm}：注入确实命中", len(f["fired"]) == 1 and not f["left"], str(f["fired"]))
    check(f"{_nm}：state=data_missing（不是 state_validation_failed）",
          c.get("state") == "data_missing", str(c.get("state")))
    check(f"{_nm}：validation_status=unavailable、validation_passed=None（不是 True 也不是 False）",
          c.get("validation_status") == "unavailable" and c.get("validation_passed") is None
          and "validation_passed" in c,
          f"{c.get('validation_status')} / {c.get('validation_passed')!r}")
    check(f"{_nm}：退出 1、检查点未标完成、证据完整、经济资格 false",
          f["rc"] == 1 and not f["ck_done"] and f["ev_ok"] and c.get("economic_eligible") is False,
          f"rc={f['rc']} ck={f['ck_done']} ev={f['ev_ok']}")
    check(f"{_nm}：验收把它单列为'校验未完成'，不列入'校验不符'",
          acc(a, "validation_unavailable") == [1] and acc(a, "validation_failed") == []
          and acc(a, "validation_passed") is False and acc(a, "process_completed") is False,
          f"unavail={acc(a, 'validation_unavailable')} failed={acc(a, 'validation_failed')}")
    check(f"{_nm}：没有凭空的 persisted", not _rs(c).get("persisted"), str(_rs(c).get("persisted")))
    check(f"{_nm}：另一候选不受影响（measured_exit、passed）",
          f["c2"].get("state") == "measured_exit" and f["c2"].get("validation_passed") is True,
          f"{f['c2'].get('state')} / {f['c2'].get('validation_passed')!r}")
    if _where in ("entry", "exit"):
        _stage_key = "state_validation" if _where == "entry" else "state_validation_exit"
        _vu = (c.get("data") or {}).get("validation_unavailable") or {}
        check(f"{_nm}：写明未完成的阶段与 error_kind",
              _vu.get("stage") == _stage_key
              and any(i.get("error_kind") == "transport" for i in _vu.get("items", [])),
              str(_vu)[:120])
        _sv = [r for r in f["rows"] if r.get("kind") == "state_validation"
               and r.get("candidate") == 1]
        check(f"{_nm}：证据里的校验记录是 unavailable 且没有 failures",
              bool(_sv) and _sv[-1].get("status") == "unavailable" and not _sv[-1].get("failures"),
              str([(r.get("status"), r.get("failures")) for r in _sv])[:120])
    if _where == "entry":
        check(f"{_nm}：没买入就没有注入 ⇒ 不做恢复复读、没有成本", not c.get("restore_check")
              and not c.get("cost") and not c.get("entry"), str(_rs(c))[:80])
    if _where == "exit":
        _co = c.get("cost") or {}
        check(f"{_nm}：已发生的买入保留（stage=0、swap=1），成本部分已知、回款未知",
              (c.get("entry") or {}).get("stage") == 0
              and (_co.get("entry_attempts") or {}).get("swap") == 1
              and _co.get("R_wei") is None and _co.get("partial") is True, str(_co)[:120])
        check(f"{_nm}：恢复只复读实际注入过的入场块，且有原值可比 ⇒ passed",
              _rs(c).get("status") == "passed" and _rs(c).get("persisted") == [],
              str(_rs(c))[:120])
    if _where == "restore":
        _co = c.get("cost") or {}
        check(f"{_nm}：恢复 status=unavailable，data 里写明缺哪一步",
              _rs(c).get("status") == "unavailable"
              and bool((c.get("data") or {}).get("restore_unavailable")), str(_rs(c))[:120])
        check(f"{_nm}：已完成的买卖与完整成本保留", (c.get("exit") or {}).get("stage") == 0
              and _co.get("R_wei") is not None
              and (_co.get("exit_attempts") or {}).get("swap") == 1, str(_co)[:100])

# ---- 26b 对照：真实不符 / 真实状态变化 / 并存 / no_mint ----
f = _flow26("t26ident", faults=("bad_sides",))
c = f["c1"]
check("真实身份不符：state_validation_failed、failed、validation_passed=False",
      c.get("state") == "state_validation_failed" and c.get("validation_status") == "failed"
      and c.get("validation_passed") is False, f"{c.get('state')} / {c.get('validation_status')}")
check("真实身份不符：不符写进 failures，没有 unavailable",
      bool((c.get("state_validation") or {}).get("failures"))
      and not (c.get("state_validation") or {}).get("unavailable"),
      str(c.get("state_validation", {}).get("failures"))[:100])
check("真实身份不符：退出 1、检查点不标完成、证据完整、验收列入 validation_failed",
      f["rc"] == 1 and not f["ck_done"] and f["ev_ok"]
      and 1 in (acc(acc(f["doc"], "acceptance"), "validation_failed") or []), f"rc={f['rc']}")

_W26 = P.V.WALLET
f = _flow26("t26persist", [("restore_check", "request", "eth_getCode", ("return", "0x60"))])
c = f["c1"]
check("真实状态变化（注入后钱包出现代码）：注入命中", len(f["fired"]) == 1, str(f["fired"]))
check("真实状态变化：restore failed、persisted 非空、state_validation_failed",
      _rs(c).get("status") == "failed" and bool(_rs(c).get("persisted"))
      and c.get("state") == "state_validation_failed" and c.get("validation_passed") is False,
      f"{_rs(c).get('status')} {_rs(c).get('persisted')} {c.get('state')}")
check("真实状态变化：已完成买卖的成本仍在", (c.get("cost") or {}).get("R_wei") is not None)
check("真实状态变化：退出 1、检查点不标完成、证据完整", f["rc"] == 1 and not f["ck_done"] and f["ev_ok"])

f = _flow26("t26both", [("restore_check", "request", "eth_getCode", ("return", "0x60")),
                        ("restore_check", "request", None, "transport")])
c = f["c1"]
check("并存（先真实不符、后接口故障）：两条注入都命中", len(f["fired"]) == 2, str(f["fired"]))
check("并存：不符与未完成**两者都保留**，结论仍为 failed",
      _rs(c).get("status") == "failed" and bool(_rs(c).get("persisted"))
      and bool(_rs(c).get("unavailable")) and c.get("state") == "state_validation_failed"
      and c.get("validation_status") == "failed",
      f"{_rs(c).get('status')} persisted={len(_rs(c).get('persisted') or [])} "
      f"unavail={len(_rs(c).get('unavailable') or [])}")

f = _flow26("t26dirty", [("state_validation", "request", "eth_getCode", ("return", "0x60")),
                         ("state_validation", "request", None, "transport")])
_sv = f["c1"].get("state_validation") or {}
check("并存（入场：钱包已有代码 + 随后取余额断连）：failures 与 unavailable 都在、判 failed",
      bool(_sv.get("failures")) and bool(_sv.get("unavailable")) and _sv.get("status") == "failed"
      and f["c1"].get("state") == "state_validation_failed",
      f"{_sv.get('status')} f={_sv.get('failures')} u={len(_sv.get('unavailable') or [])}")

f = _flow26("t26nomint", no_mint=True)
_st = {f["c1"].get("state"), f["c2"].get("state")}
check("no_mint 对照：退出 0、两候选 no_mint_by_cutoff、检查点标完成",
      f["rc"] == 0 and _st == {"no_mint_by_cutoff"} and f["ck_done"], f"rc={f['rc']} {_st}")
check("no_mint 对照：没做的校验记 not_applicable、validation_passed=True",
      f["c1"].get("validation_status") == "not_applicable" and f["c1"].get("validation_passed") is True
      and not f["c1"].get("state_validation"),
      f"{f['c1'].get('validation_status')} / {f['c1'].get('validation_passed')!r}")

# ---- 26c 其它原因各记各的，不被归成接口断连 ----
f = _flow26("t26budget", [("state_validation_exit", "request", None, "budget")])
c = f["c1"]
check("校验中预算耗尽：state=budget_exhausted（不是 data_missing）、校验 unavailable",
      c.get("state") == "budget_exhausted" and c.get("validation_status") == "unavailable",
      f"{c.get('state')} / {c.get('validation_status')}")
check("校验中预算耗尽：买入成本保留", ((c.get("cost") or {}).get("entry_attempts") or {}).get("swap") == 1)

f = _flow26("t26stop", [("state_validation_exit", "request", None, "shutdown")])
c = f["c1"]
check("校验中停机：state=aborted_by_shutdown、校验 unavailable（不是 passed）",
      c.get("state") == "aborted_by_shutdown" and c.get("validation_status") == "unavailable"
      and c.get("validation_passed") is None, f"{c.get('state')} / {c.get('validation_status')}")

f = _flow26("t26decode", [("restore_check", "request", "eth_getBlockByNumber",
                           ("return", {"number": "0x1"}))])
c = f["c1"]
check("恢复复读拿到畸形区块（解码错误）：state=decode_error，不是 state_validation_failed",
      len(f["fired"]) == 1 and c.get("state") == "decode_error"
      and _rs(c).get("status") == "unavailable" and c.get("validation_passed") is None,
      f"{c.get('state')} / {_rs(c)}"[:120])

# ---- 26d 未完成的候选续跑时必须重测，不得跳过 ----
_d26 = tmp()
_ck26 = _d26 / "shared.ck"
f1 = _flow26("t26r1", [("state_validation_exit", "request", None, "transport")], d=_d26,
             checkpoint=_ck26)
f2 = _flow26("t26r2", d=_d26, checkpoint=_ck26)
_a2 = acc(f2["doc"], "acceptance", {})
check("续跑：校验未完成的候选 1 没被跳过，而是重测",
      f1["c1"].get("state") == "data_missing" and 1 not in (acc(_a2, "skipped_already_completed") or [])
      and not f2["c1"].get("carried_from_checkpoint") and f2["c1"].get("state") == "measured_exit",
      f"首跑={f1['c1'].get('state')} 跳过={acc(_a2, 'skipped_already_completed')}")
check("续跑：已完成的候选 2 从检查点带出，整体退出 0",
      f2["rc"] == 0 and bool(f2["c2"].get("carried_from_checkpoint")), f"rc={f2['rc']}")

# ---- 26e 单元：缺原值不比较；接口故障的判定规则 ----


class _Clean26:
    records = []

    def request(self, method, params):
        return "0x" if method == "eth_getCode" else "0x0"


class _Log26:
    def write(self, *a, **k):
        pass


_out26 = P.verify_wallet_not_persisted(_Clean26(), _Log26(), 1, [100], {})
_bad26, _un26 = (_out26 if isinstance(_out26, tuple) else (_out26, []))
check("缺注入前原值：不报 persisted", _bad26 == [], str(_bad26)[:100])
check("缺注入前原值：逐项记 baseline_missing（2 个地址 × 代码/余额）",
      sorted((u.get("step"), u.get("error_kind")) for u in _un26)
      == sorted((f"restore:{w}@100:{k}", "baseline_missing")
                for w in ("WALLET", "CALLER") for k in ("code", "balance")), str(_un26)[:100])
_part26 = P.verify_wallet_not_persisted(
    _Clean26(), _Log26(), 1, [100], {"WALLET@100": {"code": "0x"}, "CALLER@100": {"code": "0x"}})
_pb26, _pu26 = (_part26 if isinstance(_part26, tuple) else (_part26, []))
check("只有代码原值：代码照常比较，缺的余额只记缺、不报 persisted",
      _pb26 == [] and sorted(u.get("step") for u in _pu26)
      == ["restore:CALLER@100:balance", "restore:WALLET@100:balance"], f"{_pb26} {_pu26}"[:120])
_if26 = getattr(P, "interface_failure", None)
_RF = P.V.RpcFailure
check("接口故障判定：传输/HTTP/协议/无结果算接口故障；回滚、预算、ABI 不算",
      _if26 is not None
      and all(_if26(_RF(k, "x")) for k in ("transport", "http", "protocol", "missing_result",
                                            "response_limit"))
      and _if26(_RF("rpc", "header not found"))
      and not _if26(_RF("rpc", "execution reverted"))
      and not any(_if26(_RF(k, "x")) for k in ("budget", "abi", "forbidden_method"))
      and not _if26(ValueError("x")))


#!/usr/bin/env python3
"""针对 audit_followup_20260910/REVIEW.md 九个反例的回归测试。

断言的是【修复后】应有的行为。审查方的 reproduce_remaining.py /
reproduce_retry.py 断言的是 bug 存在，修好之后它们必然失败，
因此不能当回归守卫 —— 保留原件作为反例出处，这里是守卫。

全部离线：链、Etherscan、HTTP 传输都是受控实现，绝不触真实端点。
"""
import contextlib, json, os, sys, tempfile, threading, time
from io import StringIO as _io18
from pathlib import Path
from unittest.mock import patch
import urllib.error

import audit_flow as A
import evidence as E
import pilot_measure as P

ok = fail = 0


# 交付与审核产物**不得被测试改写**。在任何一节运行之前给它们拍 sha256 快照，
# 末尾（§24）逐一核对。用绝对路径 —— 反向验证时测试文件被复制到别处运行，
# 若用相对路径就会去核对一个空目录，永远"通过"。
_ARTIFACT_ROOT = Path("/home/ancillary/rightTail/baseline_work_20260910")


def _artifact_snapshot():
    import hashlib as _hl
    snap = {}
    for sub in sorted(_ARTIFACT_ROOT.glob("runs/*")) + sorted(_ARTIFACT_ROOT.glob("audit_*")):
        if not sub.is_dir():
            continue
        for f in sorted(sub.rglob("*")):
            if f.is_file():
                snap[str(f.relative_to(_ARTIFACT_ROOT))] = _hl.sha256(f.read_bytes()).hexdigest()
    return snap


_ARTIFACTS_BEFORE = _artifact_snapshot()


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def tmp():
    return Path(tempfile.mkdtemp(prefix="rta-followup-fix-"))


def acc(doc_or_map, key, default=None):
    """缺字段应当算【失败】，不是让整个套件崩在 KeyError 上 ——
    否则拿旧代码对照时，第一处失败之后的守卫全都跑不到。"""
    return (doc_or_map or {}).get(key, default)


# ---------------------------------------------------------------- 1
print("1 P0 续跑：结果缺失不得判成功，已完成候选必须交付得出来")
d = tmp()
ck = d / "shared.ck"
rc, doc, _, _ = A.flow(d, "first", checkpoint=ck)
check("首次跑通", rc == 0 and len(doc["results"]) == 2, f"rc={rc} n={len(doc['results'])}")
first_idx = [r["index"] for r in doc["results"]]

# 正常续跑：累计交付必须包含全部已完成候选，不被本次 results 覆盖
rc2, doc2, _, _ = A.flow(d, "second", checkpoint=ck)
a2 = doc2["acceptance"]
check("续跑仍交付全部候选", [r["index"] for r in doc2["results"]] == first_idx,
      str([r["index"] for r in doc2["results"]]))
check("带出来的结果有出处标记",
      len(doc2["results"]) == 2
      and all(r.get("carried_from_checkpoint") for r in doc2["results"]),
      f"{len(doc2['results'])} 条")
check("带出来的结果与首跑逐字段一致",
      [{k: v for k, v in r.items() if k != "carried_from_checkpoint"}
       for r in doc2["results"]] == doc["results"])
check("正常续跑退出 0", rc2 == 0, str(rc2))
check("carried 记入验收", sorted(acc(a2, "carried_from_checkpoint", [])) == first_idx,
      str(acc(a2, "carried_from_checkpoint", "<缺字段>")))

# 删掉旧结果与旧证据后续跑：原反例是 exit=0 / results=[] / set_complete=true
(d / "first.json").unlink()
(d / "first.jsonl").unlink()
rc3, doc3, _, _ = A.flow(d, "third", checkpoint=ck)
a3 = doc3["acceptance"]
check("删掉旧结果后续跑退出非零", rc3 != 0, str(rc3))
check("交付不再是空的", len(doc3["results"]) == 2, str(len(doc3["results"])))
_ec3 = acc(a3, "evidence_chain_problems")
check("证据链缺失被点名", isinstance(_ec3, list) and len(_ec3) == 2,
      str(_ec3)[:120] if _ec3 is not None else "<缺字段>")
check("证据链问题写明是文件缺失",
      bool(_ec3) and all(p.get("reason") == "evidence_file_missing" for p in _ec3),
      str(_ec3)[:80] if _ec3 is not None else "<缺字段>")
check("validation_passed=False", acc(a3, "validation_passed") is False)

# ---------------------------------------------------------------- 2
print("\n2 P0 检查点中段损坏必须阻断（尾部半行才是中断的正常后果）")
lines = ck.read_text().splitlines()
lines.insert(1, "BROKEN")
ck.write_text("\n".join(lines) + "\n")
try:
    A.flow(d, "fourth", checkpoint=ck)
    check("中段损坏被拒绝复用", False, "未拒绝，仍然跑完了")
except SystemExit as e:
    check("中段损坏被拒绝复用", "中段损坏" in str(e), str(e)[:90])

# 尾部半行仍应被隔离并放行（不能把正常中断也判死）
d2 = tmp()
ck2 = d2 / "t.ck"
A.flow(d2, "a", checkpoint=ck2)
with ck2.open("a") as fh:
    fh.write('{"kind": "attempt", "candi')          # 半行，无换行
cp = E.Checkpoint(ck2)
check("尾部半行被隔离而非阻断", Path(str(ck2) + ".orphan").is_file())
check("隔离后已完成记录仍可读", len(cp.completed()) == 2, str(cp.completed()))
cp.close()

# 结果被篡改 ⇒ hash 对不上 ⇒ 不算已完成，必须重测
d3 = tmp()
ck3 = d3 / "t.ck"
A.flow(d3, "a", checkpoint=ck3)
rows = ck3.read_text().splitlines()
tampered = False
for i, ln in enumerate(rows):
    r = json.loads(ln)
    if r.get("kind") == "attempt" and r.get("completed"):
        if not isinstance(r.get("result"), dict):
            break                    # 检查点里根本没存结果 —— 下面按失败记
        r["result"]["state"] = "measured_exit_TAMPERED"
        rows[i] = json.dumps(r, ensure_ascii=False)
        tampered = True
        break
check("已完成的尝试里内联存有结果", tampered, "检查点未持久化结果，无从校验")
if tampered:
    ck3.write_text("\n".join(rows) + "\n")
    cp3 = E.Checkpoint(ck3)
    try:
        good, broken = cp3.deliverable()
    except AttributeError as e:
        good, broken = {}, [{"reason": f"no deliverable(): {e}"}]
    cp3.close()
else:
    good, broken = {}, []
check("被篡改的结果不算可交付", len(broken) == 1 and
      broken[0].get("reason") == "result_hash_mismatch", str(broken)[:110])
check("其余候选不受牵连", len(good) == 1, str(sorted(good)))

# ---------------------------------------------------------------- 3
print("\n3 P0 全局预算：启动请求与串行分支都在预算内")
d4 = tmp()
rc4, doc4, _, inst4 = A.flow(d4, "run", parallel=2, max_calls=2)
actual = sum(len(r.records) for r in inst4)
check("实际请求不超过上限", actual <= 2, f"上限 2，实际 {actual}")
check("超预算时退出非零", rc4 != 0, str(rc4))

d5 = tmp()
rc5, doc5, _, inst5 = A.flow(d5, "run", parallel=1, max_calls=2)
actual5 = sum(len(r.records) for r in inst5)
check("串行分支同样受同一预算", actual5 <= 2, f"上限 2，实际 {actual5}")
check("串行也产出闸门统计", doc5.get("gate_stats") is not None)

d6 = tmp()
_, doc6, _, _ = A.flow(d6, "run", parallel=1)
g6 = doc6.get("gate_stats") or {}
check("实际发出/预留/逻辑三个口径分开报",
      all(k in g6 for k in ("http_sent", "http_reserved",
                            "http_rejected_after_wait", "logical_requests")),
      str(sorted(g6)))
check("受控链下实际发出为 0（不拿预留或逻辑数冒充实际）",
      acc(g6, "http_sent") == 0 and acc(g6, "logical_requests", 0) > 0,
      f"sent={acc(g6, 'http_sent', '<缺>')} reserved={acc(g6, 'http_reserved', '<缺>')} "
      f"logical={acc(g6, 'logical_requests', '<缺>')}")

# ---------------------------------------------------------------- 4
print("\n4 P1 买入成本：槽位查询抛异常也不得丢失已知买入腿")
d7 = tmp()
with patch.object(P, "find_slot",
                  side_effect=P.V.RpcFailure("transport", "injected after buy")):
    rc7, doc7, _, _ = A.flow(d7, "run")
r7 = doc7["results"][0]
check("退出非零", rc7 != 0, str(rc7))
check("买入腿仍在", bool(r7.get("entry")) and r7["entry"]["attempts"]["swap"] == 1)
check("成本表存在", r7.get("cost") is not None)
check("买入 gas 非零", (r7["cost"] or {}).get("G_by_scenario", {})
      .get(r7["cost"]["main_scenario"], 0) > 0 if r7.get("cost") else False,
      str((r7.get("cost") or {}).get("G_by_scenario", {}))[:70])
check("回款保持未知", r7["cost"]["R_wei"] is None if r7.get("cost") else False)
check("退出腿标为未尝试",
      r7["cost"]["exit_attempts"]["swap"] == 0 if r7.get("cost") else False)
check("成本标注为部分", r7["cost"].get("partial") is True if r7.get("cost") else False)

# ---------------------------------------------------------------- 5
print("\n5 P1 样本唯一性：一候选恰好一条结果")
d8 = tmp()
dup_sample = dict(universe_sha256=E.sha256_file(P.UNIVERSE), n=2,
                  sample=[dict(index=1, pair=A.PAIR, token=A.TOKEN,
                               created_block=A.MINT - 10)] * 2)
(d8 / "sample.json").write_text(json.dumps(dup_sample))
try:
    rc8, *_ = A.flow(d8, "run")
except FileNotFoundError:
    rc8 = "no-output"          # 拒绝测量 ⇒ 根本没有产出文件
check("重复候选编号被拒绝测量", rc8 in (2, "no-output"), str(rc8))
check("拒绝时不产出结果文件", not (d8 / "run.json").exists())

d9 = tmp()
bad_n = dict(universe_sha256=E.sha256_file(P.UNIVERSE), n=3,
             sample=[dict(index=i, pair=A.PAIR, token=A.TOKEN,
                          created_block=A.MINT - 10) for i in (1, 2)])
(d9 / "sample.json").write_text(json.dumps(bad_n))
try:
    rc9, *_ = A.flow(d9, "run")
except FileNotFoundError:
    rc9 = "no-output"
check("声明数量与条目数不符被拒", rc9 in (2, "no-output"), str(rc9))

# ---------------------------------------------------------------- 6/7
print("\n6/7 P1 证据完整性：空文件与孤立记录不得判为完整")
t = tmp()
f = t / "empty.jsonl"
f.write_text("")
_, dg = E.read_evidence(f, report=True)
check("空文件不算完整", acc(dg, "complete") is False)
check("空文件被点名", acc(dg, "empty") is True, str(acc(dg, "empty", "<缺字段>")))

f.write_text(json.dumps(dict(run_id="r", seq=1, kind="rpc_end", pending_id=1)) + "\n" +
             json.dumps(dict(run_id="r", seq=2, kind="run_footer")) + "\n")
_, dg = E.read_evidence(f, report=True)
check("孤立 rpc_end 不算完整", acc(dg, "complete") is False)
check("孤立 end 被点名", acc(dg, "orphan_rpc_end") == ["('r', 1, None)"],
      str(acc(dg, "orphan_rpc_end", "<缺字段>")))
check("缺运行头被点名", acc(dg, "runs_without_header") == ["r"],
      str(acc(dg, "runs_without_header", "<缺字段>")))

f.write_text("\n".join(json.dumps(x) for x in [
    dict(run_id="r", seq=1, kind="run_header"),
    dict(run_id="r", seq=2, kind="rpc_begin", pending_id=1),
    dict(run_id="r", seq=3, kind="rpc_end", pending_id=1),
    dict(run_id="r", seq=4, kind="rpc_begin", pending_id=1),
    dict(run_id="r", seq=5, kind="rpc_end", pending_id=1),
    dict(run_id="r", seq=6, kind="run_footer")]) + "\n")
_, dg = E.read_evidence(f, report=True)
check("重复 pending_id 不算完整", acc(dg, "complete") is False)
check("重复 pending_id 被点名", bool(acc(dg, "duplicate_pending_id")),
      str(acc(dg, "duplicate_pending_id", "<缺字段>")))

# 正常运行仍应判为完整（不能靠一律判否来过关）
d10 = tmp()
A.flow(d10, "good")
_, dg_good = E.read_evidence(d10 / "good.jsonl", report=True)
check("正常运行仍判完整", acc(dg_good, "complete") is True,
      str({k: acc(dg_good, k, "<缺字段>") for k in
           ("empty", "orphan_rpc_end", "duplicate_pending_id", "runs_without_header")}))

# 进行中的本次运行不应把同一文件里的历史运行判成不完整
try:
    _, dg_ign = E.read_evidence(d10 / "good.jsonl", report=True,
                                ignore_runs=(json.loads(
                                    (d10 / "good.jsonl").read_text().splitlines()[0])["run_id"],))
except TypeError as e:
    dg_ign = {"error": str(e)}
check("支持排除进行中的运行（否则同文件续跑必误判）", "complete" in dg_ign, str(dg_ign)[:90])

# ---------------------------------------------------------------- 8
print("\n8 P1 Mint 元数据规范性")
base = dict(address=A.PAIR, blockNumber=hex(A.MINT),
            topics=[P.MINT_TOPIC, "0x" + "0" * 64], data="0x" + "1" * 128,
            transactionHash="0x" + "22" * 32, blockHash="0x" + "33" * 32, logIndex="0x0")


def why_of(ev):
    """校验函数必须**返回拒收原因**。裸抛异常同样是缺陷（审查反例 6），
    所以这里把异常也变成可断言的结果，而不是让套件崩掉。"""
    try:
        return P._validate_log(ev, A.PAIR, A.MINT - 100, A.MINT + 100)
    except Exception as e:                                        # noqa: BLE001
        return f"<裸抛 {type(e).__name__}>"

check("规范事件仍然通过", why_of(base) is None, str(why_of(base)))
for name, over, want in [
    ("transactionHash='0x'", {"transactionHash": "0x"}, "tx_hash_shape"),
    ("transactionHash 非十六进制", {"transactionHash": "0x" + "zz" * 32}, "tx_hash_shape"),
    ("blockHash='WRONG'", {"blockHash": "WRONG"}, "block_hash_shape"),
    ("logIndex='garbage'", {"logIndex": "garbage"}, "log_index_unparsable"),
    ("logIndex 为负", {"logIndex": -1}, "log_index_unparsable"),
    ("sender topic 非十六进制",
     {"topics": [P.MINT_TOPIC, "0x" + "z" * 64]}, "sender_topic_not_hex"),
]:
    r = dict(base)
    r.update(over)
    why = why_of(r)
    check(f"{name} 被拒且理由明确",
          why is not None and why.startswith(want), f"{why}")

# 审查方原样的畸形事件（三处同时坏）
evil = dict(address=A.PAIR, blockNumber=hex(A.MINT),
            topics=[P.MINT_TOPIC, "0x" + "0" * 64], data="0x" + "1" * 128,
            transactionHash="0x", blockHash="WRONG", logIndex="garbage")
check("审查方原反例事件被拒", why_of(evil) is not None, str(why_of(evil)))

# ---------------------------------------------------------------- 9
print("\n9 汇总里的规格标识必须是实际绑定的那一份")
d11 = tmp()
_, doc11, _, _ = A.flow(d11, "run")
check("规格不再写死 v1 (draft)", doc11["spec"] != "MEASUREMENT_SPEC.md v1 (draft)",
      str(doc11["spec"]))
_sp = doc11.get("spec")
check("规格带路径与 sha256",
      isinstance(_sp, dict) and _sp.get("sha256") ==
      E.sha256_file(Path(__file__).resolve().parent / _sp.get("path", "__missing__")),
      str(_sp))

print("\n10 Etherscan 计数按候选归集（并行下不得串味）")
# 整流程里 P.etherscan 被 mock 整体替换，真函数不跑、计数恒为 0，
# 这种断言等于什么都没测 —— 所以在单元级用真函数验证归集。
from collections import Counter

d12 = tmp()
log12 = E.EvidenceLog(d12 / "es.jsonl")


class _EsResp:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=None): return b'{"status":"1","result":[]}'


with patch.object(P.urllib.request, "urlopen", return_value=_EsResp()):
    for cand, times in ((11, 3), (22, 1)):
        for _ in range(times):
            P.etherscan("K" * 20, log=log12, candidate=cand, stage="t",
                        module="stats", action="ethprice")
log12.close()
_cbc = getattr(log12, "counts_by_candidate", None)
got = ({c: _cbc.get(("etherscan", c), 0) for c in (11, 22)}
       if _cbc is not None else "<无按候选计数>")
check("按候选归集而非全局差值", got == {11: 3, 22: 1}, str(got))
check("全局计数仍是总和", log12.counts["etherscan"] == 4, str(log12.counts))
rows_es, _ = E.read_evidence(d12 / "es.jsonl")
by_ev = Counter(r.get("candidate") for r in rows_es if r.get("kind") == "etherscan")
check("与证据逐条统计一致", dict(by_ev) == {11: 3, 22: 1}, str(dict(by_ev)))

print("\n11 区块缓存命中留有证据（缓存口径可查）")
d13 = tmp()
_, _doc13, rows13, _ = A.flow(d13, "run", parallel=2)
hits = [r for r in rows13 if r.get("kind") == "block_cache_hit"]
check("缓存命中确实产生了记录", len(hits) > 0, f"{len(hits)} 条")
check("命中记录写明取用双方",
      bool(hits) and all("fetched_by_worker" in h and "used_by_worker" in h for h in hits),
      f"{len(hits)} 条")
check("命中记录带块号与块 hash",
      bool(hits) and all(h.get("block") is not None and h.get("block_hash") for h in hits),
      f"{len(hits)} 条")

print("\n12 同快照对照的机制：--pin-finalized")
d14 = tmp()
_, doc14, _, _ = A.flow(d14, "base")
snap = doc14["finalized_snapshot"]
# 指定一个**与默认 finalized 不同**的块，否则"用了指定值"和"忽略了指定值"
# 看起来一样 —— 旧代码同样能通过（受控链只有一个快照）。
alt_n = snap["number"] - 500
alt_h = "0x" + f"{alt_n:064x}"          # 与 fake_chain._block 的推导一致
assert alt_h != snap["hash"]
d15 = tmp()
rc15, doc15, _, _ = A.flow(d15, "ser", parallel=1, pin_finalized=f"{alt_n}:{alt_h}")
d16 = tmp()
rc16, doc16, _, _ = A.flow(d16, "par", parallel=2, pin_finalized=f"{alt_n}:{alt_h}")
check("串行确实改用了指定快照（而非默认 finalized）",
      rc15 == 0 and doc15["finalized_snapshot"]["number"] == alt_n
      and doc15["finalized_snapshot"]["hash"] == alt_h,
      str(doc15["finalized_snapshot"]))
check("并行绑到同一个指定快照",
      rc16 == 0 and doc16["finalized_snapshot"] == doc15["finalized_snapshot"],
      str(doc16["finalized_snapshot"]))
check("与不指定时的默认快照确实不同",
      doc15["finalized_snapshot"] != snap, f"{doc15['finalized_snapshot']} vs {snap}")
check("两次是各自独立的检查点（不是靠跳过凑齐）",
      not doc15["acceptance"]["skipped_already_completed"]
      and not doc16["acceptance"]["skipped_already_completed"],
      f"{doc15['acceptance']['skipped_already_completed']} / "
      f"{doc16['acceptance']['skipped_already_completed']}")
check("两边都真的测了全部候选",
      len(doc15["results"]) == 2 and len(doc16["results"]) == 2)

d17 = tmp()
try:
    rc17, *_ = A.flow(d17, "bad", pin_finalized=f"{snap['number']}:0x" + "ee" * 32)
except FileNotFoundError:
    rc17 = "no-output"
check("指定块的 hash 不符即拒绝（重组保护）", rc17 in (2, "no-output"), str(rc17))

d18 = tmp()
try:
    rc18, *_ = A.flow(d18, "malformed", pin_finalized="not-a-pin")
except FileNotFoundError:
    rc18 = "no-output"
check("格式非法即拒绝", rc18 in (2, "no-output"), str(rc18))

def gas_only_entry(r):
    """只算买入腿的 gas —— 用来证明卖出腿确实被计进去了。"""
    return P.gas_cost(r["cost"]["entry_attempts"], {"swap": 0, "approve": 0},
                      r["cost"]["base_fee_entry"],
                      r["cost"]["base_fee_exit"])[r["cost"]["main_scenario"]]


print("\n13 P0 续跑证据必须绑定到具体运行、候选与结果 hash")


def rewrite_evidence(path, fn):
    """逐行改写证据 JSONL；fn 返回 None 表示删掉该行。"""
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = fn(json.loads(ln))
        if r is not None:
            out.append(json.dumps(r, ensure_ascii=False))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def resume_with(mutate):
    """跑一次 → 按 mutate 改证据 → 续跑。返回 (rc, acceptance)。"""
    dd = tmp()
    cc = dd / "shared.ck"
    rc0, doc0, _, _ = A.flow(dd, "first", checkpoint=cc)
    assert rc0 == 0, rc0
    mutate(dd, doc0)
    rc1, doc1, _, _ = A.flow(dd, "resumed", checkpoint=cc)
    return rc1, doc1["acceptance"], doc1


def reasons(a):
    return sorted({p.get("reason") for p in acc(a, "evidence_chain_problems", [])})


# 控制项：不动任何东西，正常续跑必须仍然通过
rc_ok, a_ok, doc_ok = resume_with(lambda dd, doc: None)
check("正常续跑仍然通过", rc_ok == 0 and not acc(a_ok, "evidence_chain_problems", None),
      f"rc={rc_ok} {reasons(a_ok)}")
check("正常续跑仍交付全部候选", len(doc_ok["results"]) == 2, str(len(doc_ok["results"])))

# 反例本体：换成**另一个运行**的结构完整证据
def swap_unrelated(dd, doc):
    other = dd / "other.jsonl"
    lg = E.EvidenceLog(other)
    lg.write("run_header", note="unrelated run")
    lg.write("run_footer")
    lg.close()
    (dd / "first.jsonl").write_bytes(other.read_bytes())


rc1, a1, _ = resume_with(swap_unrelated)
check("换成另一运行的完整证据被拒", rc1 != 0, str(rc1))
check("理由是 run_id 不在该文件里", reasons(a1) == ["evidence_run_id_absent"], str(reasons(a1)))
check("validation_passed=False", acc(a1, "validation_passed") is False)

# run_id 对，但候选的 candidate_result 被删掉
def drop_result(dd, doc):
    rewrite_evidence(dd / "first.jsonl",
                     lambda r: None if (r.get("kind") == "candidate_result"
                                        and r.get("candidate") == 1) else r)


rc2, a2, _ = resume_with(drop_result)
check("候选结果不在证据里被拒", rc2 != 0, str(rc2))
check("理由是缺该候选的 candidate_result",
      "candidate_result_absent_in_evidence" in reasons(a2), str(reasons(a2)))

# run_id 对、记录在，但内容被改过 ⇒ hash 对不上
def tamper_result(dd, doc):
    def fn(r):
        if r.get("kind") == "candidate_result" and r.get("candidate") == 1:
            r["record"]["state"] = "measured_exit_TAMPERED"
        return r
    rewrite_evidence(dd / "first.jsonl", fn)


rc3, a3, _ = resume_with(tamper_result)
check("证据里的结果被改过即拒", rc3 != 0, str(rc3))
check("理由是结果 hash 不符",
      "candidate_result_hash_mismatch" in reasons(a3), str(reasons(a3)))

# 运行头的绑定与检查点不符
def tamper_binding(dd, doc):
    def fn(r):
        if r.get("kind") == "run_header":
            r["sample_sha256"] = "0" * 64
        return r
    rewrite_evidence(dd / "first.jsonl", fn)


rc4, a4, _ = resume_with(tamper_binding)
check("运行头绑定不符即拒", rc4 != 0, str(rc4))
check("理由是绑定不符", "evidence_binding_mismatch" in reasons(a4), str(reasons(a4)))

# 结果 hash 之所以能对上，是因为检查点与证据存的是同一份（脱敏后）字节
dd5 = tmp()
cc5 = dd5 / "c.ck"
A.flow(dd5, "a", checkpoint=cc5)
att = [json.loads(l) for l in cc5.read_text().splitlines()
       if json.loads(l).get("kind") == "attempt"][0]
evr = [json.loads(l) for l in (dd5 / "a.jsonl").read_text().splitlines()
       if json.loads(l).get("kind") == "candidate_result"
       and json.loads(l).get("candidate") == att["candidate"]][0]
# 不变量（不是本轮反例的守卫）：检查点与证据必须存同一份**脱敏后**字节，
# 否则一旦结果里出现被脱敏的串，两边 hash 就会天然不符，上面那套
# hash 绑定会误伤正常续跑。这条守的是那个前提。
check("不变量：检查点结果 hash == 证据里 candidate_result 的 hash",
      att["result_sha256"] == E.result_sha256(evr["record"]),
      f"{att['result_sha256'][:16]}… vs {E.result_sha256(evr['record'])[:16]}…")
_ck_text = cc5.read_text(encoding="utf-8")
check("不变量：检查点里不含未脱敏的凭据串",
      "FAKE_ONLY_KEY" not in _ck_text and "FAKE_ONLY_SCAN_KEY" not in _ck_text,
      f"检查点 {len(_ck_text)} 字节")

# 绑定字段被**删掉**同样要拒 —— 缺失比不符更可疑，不能因为"没这个字段"就跳过
BIND_FIELDS = ["script_sha256", "evidence_module_sha256", "spec_sha256",
               "sample_sha256", "universe_sha256_now", "finalized_snapshot"]
for field in BIND_FIELDS:
    def drop_field(dd, doc, _f=field):
        def fn(r):
            if r.get("kind") == "run_header":
                r.pop(_f, None)
            return r
        rewrite_evidence(dd / "first.jsonl", fn)

    rc_m, a_m, _ = resume_with(drop_field)
    check(f"运行头缺 {field} 即拒",
          rc_m != 0 and "evidence_binding_field_missing" in reasons(a_m),
          f"rc={rc_m} {reasons(a_m)}")

print("\n14 P1 实际 HTTP 次数不得把未发出的请求算进去")
gate14 = E.SharedGate(10, 10, 0.02)      # 间隔 0.1s，0.02s 后截止
sent14 = []


def t14(*a, **kw):
    sent14.append(1)
    return "ok"


E.install_http_gate(gate14, transport=t14)
try:
    E.urllib.request.urlopen("https://offline.invalid")     # 第一次发出
    try:
        E.urllib.request.urlopen("https://offline.invalid")  # 排队后被时间闸门拒
        rejected = False
    except E.BudgetExhausted:
        rejected = True
finally:
    E.uninstall_http_gate()
s14 = gate14.stats()
check("第二次确实被拒", rejected)
check("传输层只被调用一次", len(sent14) == 1, str(len(sent14)))
check("http_sent 等于传输实际次数", acc(s14, "http_sent") == len(sent14),
      f"sent={acc(s14, 'http_sent', '<缺字段>')} 传输={len(sent14)}")
check("未发出的那次记在 rejected_after_wait",
      acc(s14, "http_rejected_after_wait") == 1,
      str(acc(s14, "http_rejected_after_wait", "<缺字段>")))
check("预留仍为 2（并发安全，不退还）", acc(s14, "http_reserved") == 2,
      str(acc(s14, "http_reserved", "<缺字段>")))
check("恒等式 reserved == sent + rejected",
      acc(s14, "http_reserved") is not None
      and acc(s14, "http_reserved") == acc(s14, "http_sent", -1)
      + acc(s14, "http_rejected_after_wait", -1), str(s14)[:150])
check("stats 不再有含混的 http_calls 字段", "http_calls" not in s14, str(sorted(s14)))

# 控制项：都发得出去时，sent 必须等于 reserved
gate14b = E.SharedGate(10 ** 6, 10, 60)
sent14b = []
E.install_http_gate(gate14b, transport=lambda *a, **kw: sent14b.append(1))
try:
    for _ in range(3):
        E.urllib.request.urlopen("https://offline.invalid")
finally:
    E.uninstall_http_gate()
s14b = gate14b.stats()
check("正常情况下 sent == reserved == 实际传输次数",
      acc(s14b, "http_sent") == acc(s14b, "http_reserved") == len(sent14b) == 3,
      str(s14b)[:150])

print("\n15 P1 诊断失败不得抹掉已到达的卖出阶段")
orig_measure, orig_probe = P.measure, P.V.probe_call


def diag_on(args):
    args.diagnostics = True
    return orig_measure(args)


def make_probe(fail_diag):
    def probe(*args, **kw):
        if kw.get("selling") and args[5] == 1:        # 尺寸诊断用最小单位
            if fail_diag:
                raise P.V.RpcFailure("transport", "injected diagnostic failure")
        r = orig_probe(*args, **kw)
        if kw.get("selling"):
            r.update(stage=20, classification="simulated_revert",
                     token_after=r["token_before"], cash_in=0)
        return r
    return probe


def run_diag(fail_diag):
    dd = tmp()
    with patch.object(P, "measure", side_effect=diag_on), \
         patch.object(P.V, "probe_call", side_effect=make_probe(fail_diag)):
        rc, doc, _, _ = A.flow(dd, "run")
    return rc, doc["results"][0]


rc_f, r_f = run_diag(True)
check("卖出到达的阶段仍在", r_f["exit"]["stage"] == 20, str(r_f["exit"].get("stage")))
check("卖出 swap 记为 1（不是未尝试）", r_f["cost"]["exit_attempts"]["swap"] == 1,
      str(r_f["cost"]["exit_attempts"]))
check("卖出 approve 记为 2", r_f["cost"]["exit_attempts"]["approve"] == 2,
      str(r_f["cost"]["exit_attempts"]))
check("basis 不再写成未尝试",
      "never attempted" not in r_f["cost"]["exit_attempts"].get("basis", ""),
      r_f["cost"]["exit_attempts"].get("basis", ""))

rc_s, r_s = run_diag(False)
check("诊断成功与诊断失败的卖出计次一致",
      r_s["cost"]["exit_attempts"]["swap"] == r_f["cost"]["exit_attempts"]["swap"]
      and r_s["cost"]["exit_attempts"]["approve"] == r_f["cost"]["exit_attempts"]["approve"],
      f"{r_s['cost']['exit_attempts']} vs {r_f['cost']['exit_attempts']}")
check("诊断调用本身不计为交易尝试（诊断成功时也只有 1 次 swap）",
      r_s["cost"]["exit_attempts"]["swap"] == 1, str(r_s["cost"]["exit_attempts"]))
check("成本包含卖出腿（大于只算买入腿）",
      r_f["cost"]["G_by_scenario"][r_f["cost"]["main_scenario"]] >
      gas_only_entry(r_f), str(r_f["cost"]["G_by_scenario"][r_f["cost"]["main_scenario"]]))

print("\n16 资源上限与停机策略")
import os as _os16
import signal as _sig16
import time as _t16

# --- 峰值必须是实测高水位，不是采样 ---
def _peak16():
    fn = getattr(E, "rss_peak_kb", None)          # 旧版没有这个函数
    return fn() if fn else None


_before = _peak16()
_blob = bytearray(64 * 1024 * 1024)
del _blob
_cur_after, _peak_after = E.rss_kb(), _peak16()
check("VmHWM 抓得到采样会漏掉的尖峰",
      _peak_after is not None and _peak_after >= (_before or 0) + 32 * 1024,
      f"之前 {_before} → 峰值 {_peak_after} KB")
check("尖峰过后当前值回落、峰值不回落",
      _cur_after is not None and _peak_after is not None and _peak_after > _cur_after,
      f"当前 {_cur_after} < 峰值 {_peak_after}")
try:
    _basis16 = E.ResourceGovernor().report()["peak_basis"]
except Exception as e:                                            # noqa: BLE001
    _basis16 = f"<无 ResourceGovernor: {type(e).__name__}>"
check("峰值来源标注为内核高水位", "VmHWM" in _basis16, _basis16)


class _NoGov16:
    """旧版没有 ResourceGovernor 时的占位，让后续断言报 FAIL 而不是崩掉。"""
    def __init__(self, **kw):
        pass


_GOV16 = getattr(E, "ResourceGovernor", _NoGov16)

# --- 控制项：不设限额不得被判成停机 ---
d16 = tmp()
rc16, doc16, _, _ = A.flow(d16, "run")
check("不设限额时退出 0 且未停机",
      rc16 == 0 and acc(acc(doc16["acceptance"], "shutdown", {}), "stopped") is False,
      f"rc={rc16} shutdown={acc(doc16['acceptance'], 'shutdown', '<缺字段>')}")
check("无论是否停机都报告资源",
      acc(acc(doc16, "resources", {}), "final", {}).get("rss_peak_kb") is not None,
      str(acc(doc16, "resources", "<缺字段>"))[:80])

# --- 三种限额各自触发，退出码 3 ---
for name, kw, want in [("RSS", dict(max_rss_mb=1), "rss_limit_exceeded"),
                       ("CPU", dict(max_cpu_s=0.001), "cpu_limit_exceeded"),
                       ("墙钟", dict(max_wall_s=0.001), "wall_limit_exceeded")]:
    dd = tmp()
    rc, doc, _, _ = A.flow(dd, "run", **kw)
    a = doc["acceptance"]
    check(f"{name} 越线退出码为 3（不是 0 也不是 1）", rc == 3, str(rc))
    check(f"{name} 越线原因明确", acc(acc(a, "shutdown", {}), "reason") == want,
          str(acc(acc(a, "shutdown", {}), "reason", "<缺字段>")))
    check(f"{name} 越线不得判为完成",
          a["set_complete"] is False and a["process_completed"] is False
          and a["validation_passed"] is False,
          f"set={a['set_complete']} proc={a['process_completed']}")
    check(f"{name} 越线时未开工的候选逐个记名（不是静默缺失）",
          [x["index"] for x in acc(a, "not_started", [])] == [1, 2]
          and not a["missing_candidates"],
          f"未开工={acc(a, 'not_started', '<缺字段>')} 缺失={a['missing_candidates']}")

# --- 跑到一半停机：已完成的保住，中止的不算完成 ---
_orig_probe16 = P.V.probe_call
_holder16 = {}
_n16 = {"n": 0}


class _Spy16(_GOV16):
    def __init__(self, **kw):
        super().__init__(**kw)
        _holder16["gov"] = self


def _probe16(*a, **kw):
    _n16["n"] += 1
    if _n16["n"] == 3 and _holder16.get("gov"):
        _holder16["gov"].request_stop("injected_mid_run", {"note": "regression"})
    return _orig_probe16(*a, **kw)


d17 = tmp()
_ctx17 = (patch.object(E, "ResourceGovernor", _Spy16)
          if hasattr(E, "ResourceGovernor") else contextlib.nullcontext())
with patch.object(P.V, "probe_call", side_effect=_probe16), _ctx17:
    rc17, doc17, _, _ = A.flow(d17, "run", max_wall_s=10 ** 6)
st17 = {r["index"]: r["state"] for r in doc17["results"]}
check("中途停机：先做完的那条保住", st17.get(1) == "measured_exit", str(st17))
check("中途停机：进行中的那条记为 aborted_by_shutdown",
      st17.get(2) == "aborted_by_shutdown", str(st17))
check("中止的候选算未完成，阻断验收",
      2 in doc17["acceptance"]["incomplete"] and rc17 == 3,
      f"rc={rc17} incomplete={doc17['acceptance']['incomplete']}")
_ck17 = [json.loads(l) for l in (d17 / "run.ck").read_text().splitlines() if l.strip()]  # noqa: E501
_att17 = {r["candidate"]: r["completed"] for r in _ck17 if r.get("kind") == "attempt"}
check("检查点里：完成的标完成、中止的不标完成",
      _att17.get(1) is True and _att17.get(2) is False, str(_att17))

# --- 停机后续跑：放宽限额应补齐，且不重做已完成的 ---
d18 = tmp()
ck18 = d18 / "s.ck"
rc18a, doc18a, _, _ = A.flow(d18, "first", checkpoint=ck18, max_rss_mb=1)
rc18b, doc18b, _, _ = A.flow(d18, "second", checkpoint=ck18)
check("停机那次退出 3", rc18a == 3, str(rc18a))
check("放宽限额后续跑补齐并退出 0",
      rc18b == 0 and [r["index"] for r in doc18b["results"]] == [1, 2],
      f"rc={rc18b} {[r['index'] for r in doc18b['results']]}")

# --- 真实 SIGTERM：measure() 内部注册的处理器必须生效 ---
_n19 = {"n": 0}


def _probe19(*a, **kw):
    _n19["n"] += 1
    if _n19["n"] == 3:
        _os16.kill(_os16.getpid(), _sig16.SIGTERM)
        _t16.sleep(0.05)           # 给信号处理器一点时间落地
    return _orig_probe16(*a, **kw)


# 先装一个良性处理器再跑：若被测实现**没有**接管 SIGTERM，
# 信号会落到这个良性处理器上，断言正常报 FAIL；
# 否则默认动作会把测试进程自己打死（旧版实现上实测如此）。
_caught19 = []
_prev19 = _sig16.signal(_sig16.SIGTERM, lambda s, f: _caught19.append(int(s)))
d19 = tmp()
try:
    with patch.object(P.V, "probe_call", side_effect=_probe19):
        rc19, doc19, _, _ = A.flow(d19, "run", max_wall_s=10 ** 6)
finally:
    _sig16.signal(_sig16.SIGTERM, _prev19)
a19 = doc19["acceptance"]
_sd19 = acc(a19, "shutdown", {})
check("SIGTERM 触发有序停机而不是杀进程", rc19 == 3, str(rc19))
check("停机原因记为 signal", acc(_sd19, "reason") == "signal",
      str(acc(_sd19, "reason", "<缺字段>")))
check("记下是哪个信号", acc(_sd19, "detail", {}).get("name") == "SIGTERM",
      str(acc(_sd19, "detail", {}).get("name", "<缺字段>")))
check("信号由被测实现接管（而非落到测试兜底处理器）", not _caught19,
      f"兜底处理器收到 {_caught19}")
# 有序 = 证据仍然完整，不是半行截断
_r19, _d19diag = E.read_evidence(d19 / "run.jsonl", report=True)
check("停机后证据仍然结构完整（有序收尾，不是被打死）",
      _d19diag["complete"] is True,
      str({k: _d19diag[k] for k in ("bad_lines", "unmatched_rpc_begin",
                                    "runs_without_footer")}))

# --- 看门狗确实在跑 ---
d20 = tmp()
_, doc20, rows20, _ = A.flow(d20, "run", max_wall_s=10 ** 6, governor_poll_s=0.01)
check("治理器报告落进证据",
      any(r.get("kind") == "governor_report" for r in rows20))
_res20 = acc(doc20, "resources", {})
check("看门狗巡检次数 > 0（不是装了不跑）",
      acc(_res20, "watchdog_observations", 0) > 0,
      str(acc(_res20, "watchdog_observations", "<缺字段>")))
_soft20 = acc(acc(_res20, "limits", {}), "soft_thresholds", {})
check("限额与实测一起报告",
      _soft20.get("max_wall_s") == 10 ** 6
      and acc(_res20, "final", {}).get("cpu_s") is not None,
      str(acc(_res20, "limits", "<缺字段>"))[:120])

def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:                                             # noqa: BLE001
        return False
    return False


def _run_measure_minimal(ns, chain_id=1):
    """用受控链跑一次 measure()，返回 (退出码, 异常)。"""
    import contextlib as _c, io as _io, os as _os
    from unittest.mock import patch as _p
    from fake_chain import FakeRpc
    cfg = dict(head=25900000, genesis_ts=0, entry_block=A.MINT + 1, pair=A.PAIR,
               token=A.TOKEN, received=10 ** 18, cash=10 ** 15, slot=0,
               chain_id=chain_id,
               supply=lambda b: 0 if int(b, 16) < A.MINT else 10 ** 6)

    def scan(*a, **kw):
        return dict(status="1", result=[dict(
            address=A.PAIR, blockNumber=hex(A.MINT),
            topics=[P.MINT_TOPIC, "0x" + "0" * 64], data="0x" + "1" * 128,
            transactionHash="0x" + "2" * 64, blockHash="0x" + "3" * 64,
            logIndex="0x0")])
    try:
        with _p.object(P.V, "RPC", side_effect=lambda *a, **k: FakeRpc(cfg)), \
             _p.object(P, "etherscan", side_effect=scan), \
             _p.dict(_os.environ, ETH_RPC_URL="https://x.invalid/test/FAKE_ONLY_KEY",
                     ETHERSCAN_API_KEY="FAKE_ONLY_SCAN_KEY"), \
             _c.redirect_stdout(_io.StringIO()), _c.redirect_stderr(_io.StringIO()):
            return P.measure(ns), None
    except AttributeError as e:
        return None, f"AttributeError: {e}"
    except Exception as e:                                        # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


print("\n17 新增 CLI 选项不得让程序化调用者崩掉")
# 这是反复踩到的一类错误：加了 CLI 选项 → 自建 Namespace 的调用者 AttributeError，
# 而崩掉的入口显示"通过 0 / 失败 0"，看起来像没跑而不像失败。
import argparse as _ap17

_defaults17 = {a.dest: a.default for a in
               P.build_parser()._subparsers._group_actions[0]
               .choices["measure"]._actions}
_drift17 = {k: {"登记": v, "argparse": _defaults17.get(k)}
            for k, v in P.OPTIONAL_DEFAULTS.items()
            if k in _defaults17 and _defaults17[k] != v}
check("OPTIONAL_DEFAULTS 与 argparse 默认值一致", not _drift17, str(_drift17))
check("登记表里没有 argparse 不认识的名字",
      all(k in _defaults17 for k in P.OPTIONAL_DEFAULTS),
      str([k for k in P.OPTIONAL_DEFAULTS if k not in _defaults17]))
check("opt() 拒绝未登记的名字",
      _raises(lambda: P.opt(_ap17.Namespace(), "not_registered"), KeyError))

# 只填必需项的最小 Namespace 必须能跑完
_d17b = tmp()
_sample17 = _d17b / "sample.json"
_sample17.write_text(json.dumps(dict(
    universe_sha256=E.sha256_file(P.UNIVERSE), n=1,
    sample=[dict(index=1, pair=A.PAIR, token=A.TOKEN, created_block=A.MINT - 10)])))
_minimal = _ap17.Namespace(
    sample=str(_sample17), out=str(_d17b / "o.json"),
    evidence=str(_d17b / "o.jsonl"), slot_limit=2,
    max_calls=99999, max_seconds=9999, rps=10000)
_rc17b, _err17b = _run_measure_minimal(_minimal)
check("最小 Namespace 不会 AttributeError", _err17b is None, str(_err17b))
check("最小 Namespace 能跑出结果", _rc17b == 0, str(_rc17b))

print("\n18 软阈值 vs 硬兜底、有界停机、统一清理")
import signal as _sig18
import subprocess as _sp18

_ROOT18 = str(Path(__file__).resolve().parent)


def _sub18(code, timeout=120):
    """子进程里跑：RLIMIT 会影响整个进程，不能在测试进程里设。"""
    r = _sp18.run([sys.executable, "-c",
                   f"import sys; sys.path.insert(0, {_ROOT18!r})\n" + code],
                  capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --- 18.1 口径必须诚实：软阈值不得自称硬上限 ---
def _gov18(**kw):
    """按被测版本的签名裁剪参数。

    旧版没有本轮新增的参数；直接传会 TypeError 把整节炸掉，
    看起来像"没跑"而不像"断言失败"。这里只保留它认识的那些，
    让断言照常给出 FAIL。
    """
    import inspect
    try:
        allowed = set(inspect.signature(E.ResourceGovernor.__init__).parameters)
    except (TypeError, ValueError):
        allowed = set(kw)
    return E.ResourceGovernor(**{k: v for k, v in kw.items() if k in allowed})


_g18 = _gov18(max_rss_kb=1, hard_rss_kb=None)
_lim18 = _g18.limits()
check("限额分为软阈值与硬兜底两块",
      "soft_thresholds" in _lim18 and "hard_backstop" in _lim18, str(sorted(_lim18)))
_soft_kind = acc(acc(_lim18, "soft_thresholds", {}), "kind", "<缺字段>")
_hard_kind = acc(acc(_lim18, "hard_backstop", {}), "kind", "<缺字段>")
check("软阈值自陈是协作式、不阻止继续分配",
      "cooperative" in _soft_kind and "do NOT prevent" in _soft_kind,
      _soft_kind[:70])
check("硬兜底自陈是内核强制、与进程内检查无关",
      "kernel-enforced" in _hard_kind, _hard_kind[:70])
_g18.check()
_blob18 = bytearray(8 * 1024 * 1024)
check("软阈值确实拦不住分配（所以不能叫硬上限）",
      _g18.stopping and len(_blob18) == 8 * 1024 * 1024)
del _blob18
check("停机宽限作为上界被单列",
      "stop_grace" in _lim18
      and "upper bound" in acc(acc(_lim18, "stop_grace", {}), "kind", ""),
      str(_lim18.get("stop_grace", "<缺字段>")))

# --- 18.2 硬兜底由内核强制（子进程） ---
_rc_as, _out_as = _sub18(
    "import evidence as E, json\n"
    "g = E.ResourceGovernor(hard_rss_kb=64*1024)\n"
    "g.apply_hard_limits()\n"
    "try:\n"
    "    b = [bytearray(8*1024*1024) for _ in range(200)]\n"
    "    print('NO_LIMIT'); raise SystemExit(9)\n"
    "except MemoryError:\n"
    "    print('MEMORY_ERROR'); raise SystemExit(0)\n")
check("RLIMIT_AS 由内核强制（进程内从未检查也会被拦）",
      _rc_as == 0 and "MEMORY_ERROR" in _out_as, f"rc={_rc_as} {_out_as[-120:]}")

# apply_hard_limits() 会给**当前进程**设 RLIMIT —— 绝不能在测试进程里调用，
# 否则 RLIMIT_CPU 会立刻把测试跑者自己 SIGXCPU/SIGKILL 掉（实测 exit 137）。
# 所有涉及实际设限的断言都在子进程里做。
_rc_cpu, _out_cpu = _sub18(
    "import evidence as E, signal, sys, json\n"
    "g = E.ResourceGovernor(hard_cpu_s=1)\n"
    "a = g.apply_hard_limits()\n"
    "assert 'RLIMIT_CPU' in a and 'error' not in a['RLIMIT_CPU'], a\n"
    "print('HARD_S=%d' % a['RLIMIT_CPU']['hard_s'])\n"
    "signal.signal(signal.SIGXCPU, lambda s, f: (print('SIGXCPU'), sys.exit(0)))\n"
    "x = 0\n"
    "while True:\n"
    "    x += 1\n")
check("RLIMIT_CPU 软限触发可捕获的 SIGXCPU（可转有序停机）",
      _rc_cpu == 0 and "SIGXCPU" in _out_cpu, f"rc={_rc_cpu} {_out_cpu[-120:]}")
_hard_s = next((int(l.split("=")[1]) for l in _out_cpu.splitlines()
                if l.startswith("HARD_S=")), 0)
check("RLIMIT_CPU 设了更高的硬限作为最后兜底（SIGKILL）", _hard_s > 1, str(_hard_s))

# --- 18.3 停机之后的工作有上界 ---
_orig_slot18 = P.find_slot
_mark18 = {}


def _slot18(rpc, *a, **kw):
    if not _mark18:
        _mark18["before"] = len(rpc.records)
        _sig18.raise_signal(_sig18.SIGTERM)
    return _orig_slot18(rpc, *a, **kw)


_prev18 = _sig18.signal(_sig18.SIGTERM, lambda s, f: None)
d18 = tmp()
try:
    with patch.object(P, "find_slot", side_effect=_slot18):
        rc18, doc18, rows18, rs18 = A.flow(d18, "slotstop")
finally:
    _sig18.signal(_sig18.SIGTERM, _prev18)
_after18 = len(rs18[0].records) - _mark18.get("before", 0)
_st18 = {r["index"]: r["state"] for r in doc18["results"]}
_att18 = {r["candidate"]: r["completed"] for r in
          [json.loads(x) for x in (d18 / "slotstop.ck").read_text().splitlines()]
          if r.get("kind") == "attempt"}
_res18 = acc(doc18, "resources", {})
check("槽位扫描中停机：进行中的候选记 aborted_by_shutdown（不是 measured_exit）",
      _st18.get(1) == "aborted_by_shutdown", str(_st18))
check("检查点不把它标为完成", _att18.get(1) is False, str(_att18))
check("已开工的候选不得被记成「未开工」",
      1 not in [x["index"] for x in acc(doc18["acceptance"], "not_started", [])],
      str(acc(doc18["acceptance"], "not_started", "<缺字段>")))
check("停机后的请求次数不超过收尾预算",
      _after18 <= 16, f"信号后 {_after18} 次，预算 16")
check("收尾窗口内的逻辑请求数在预算内",
      0 <= acc(_res18, "winddown_logical_requests", -1) <= 16,
      str(acc(_res18, "winddown_logical_requests", "<缺字段>")))
check("实际 HTTP 与逻辑请求在收尾窗口里分开报",
      "winddown_http_requests" in _res18 and "winddown_logical_requests" in _res18,
      str(sorted(k for k in _res18 if k.startswith("winddown"))))
check("报告给出实测停机耗时（不是靠巡检频率推断）",
      isinstance(acc(_res18, "stop_latency_s"), (int, float)),
      str(acc(_res18, "stop_latency_s", "<缺字段>")))
_r18, _dg18 = E.read_evidence(d18 / "slotstop.jsonl", report=True)
check("有界停机后证据仍然完整", _dg18["complete"] is True,
      str({k: _dg18[k] for k in ("bad_lines", "unmatched_rpc_begin")}))

# --- 18.4 收尾窗口之外一律拒绝；预算耗尽也拒绝 ---
_g4 = _gov18(grace_calls=2)
_g4.request_stop("test")
check("窗口外的请求被拒",
      hasattr(_g4, "gate_request")
      and _raises(lambda: _g4.gate_request("rpc"), E.Shutdown),
      "无 gate_request" if not hasattr(_g4, "gate_request") else "")
if hasattr(_g4, "winddown"):
    with _g4.winddown():
        _g4.gate_request("rpc")
        _g4.gate_request("rpc")
        check("窗口内逻辑请求预算耗尽后被拒",
              _raises(lambda: _g4.gate_request("rpc"), E.Shutdown))
    _g4b = _gov18(grace_calls=2)
    _g4b.request_stop("test")
    if hasattr(_g4b, "gate_http"):
        with _g4b.winddown():
            _g4b.gate_http()
            _g4b.gate_http()
            check("窗口内实际 HTTP 预算耗尽后被拒",
                  _raises(lambda: _g4b.gate_http(), E.Shutdown))
    else:
        check("窗口内实际 HTTP 预算耗尽后被拒", False, "无 gate_http（HTTP 层无闸门）")
else:
    check("窗口内逻辑请求预算耗尽后被拒", False, "无 winddown 窗口")
    check("窗口内实际 HTTP 预算耗尽后被拒", False, "无 winddown 窗口")
_g5 = _gov18(grace_calls=99, grace_seconds=-1)
_g5.request_stop("test")
if hasattr(_g5, "winddown"):
    with _g5.winddown():
        check("窗口内超时也被拒", _raises(lambda: _g5.gate_request("rpc"), E.Shutdown))
else:
    check("窗口内超时也被拒", False, "无 winddown 窗口")
_g6 = _gov18()
if hasattr(_g6, "gate_request"):
    _g6.gate_request("rpc")
check("未停机时闸门不拦", _g6.stopping is False)

# --- 18.5 提前返回也必须撤销全部设施 ---
_before_term = _sig18.getsignal(_sig18.SIGTERM)
_before_int = _sig18.getsignal(_sig18.SIGINT)
# 链身份不符时不写结果文件，所以不能走 A.flow（它会去读那个文件）——
# 直接调 measure()，只看退出码与设施是否清干净。
d19b = tmp()
_sample19 = d19b / "sample.json"
_sample19.write_text(json.dumps(dict(
    universe_sha256=E.sha256_file(P.UNIVERSE), n=1,
    sample=[dict(index=1, pair=A.PAIR, token=A.TOKEN, created_block=A.MINT - 10)])))
_ns19 = _ap17.Namespace(
    sample=str(_sample19), out=str(d19b / "o.json"),
    evidence=str(d19b / "o.jsonl"), slot_limit=2,
    max_calls=99999, max_seconds=9999, rps=10000, max_wall_s=1000)
_rc19b, _err19b = _run_measure_minimal(_ns19, chain_id=2)
check("链身份不符仍返回 2（不伪装成有序停机）", _rc19b == 2,
      f"rc={_rc19b} err={_err19b}")
check("提前返回后信号处理器已还原",
      _sig18.getsignal(_sig18.SIGTERM) is _before_term
      and _sig18.getsignal(_sig18.SIGINT) is _before_int)
check("提前返回后 HTTP 闸门已摘除", E.http_gate_installed() is False)
check("提前返回后看门狗线程已退出",
      not any(t.name == "resource-governor" and t.is_alive()
              for t in threading.enumerate()),
      str([t.name for t in threading.enumerate()]))

print("\n19 硬限安装失败、真实 HTTP 全路径停机、初始化清理")
import resource as _R19
import urllib.error as _ue19


def _fresh_rpc19(grace_calls=0, grace_seconds=0.0, stop=True):
    """真实 RPC 类 + 当前 RpcTap/SharedGate/Governor，只在闸门之下换传输。"""
    td = tmp()
    raw = A.REAL_RPC("https://offline.invalid", max_calls=10, max_seconds=30,
                     rps=10 ** 6)
    lg = E.EvidenceLog(td / "e.jsonl")
    gt = E.SharedGate(10 ** 6, 10, 60)
    gv = E.ResourceGovernor(grace_calls=grace_calls, grace_seconds=grace_seconds)
    gt.governor = gv
    if stop:
        gv.request_stop("controlled_stop")
    return E.RpcTap(raw, lg, gate=gt, worker=0), gt, gv, lg


class _Ok19:
    def __init__(self, rid): self.rid = rid
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, *a):
        return json.dumps({"jsonrpc": "2.0", "id": self.rid, "result": "0x1"}).encode()


# --- 19.1 底层 503 重试也必须过停机闸门 ---
_tap19, _gt19, _gv19, _lg19 = _fresh_rpc19(grace_calls=0, grace_seconds=0.0, stop=False)
_sent19 = []


def _t19(req, *a, **kw):
    _sent19.append(kw.get("timeout"))
    if len(_sent19) == 1:
        _gv19.request_stop("controlled_stop")      # 第一个 HTTP 之后停机
        raise _ue19.HTTPError("https://offline.invalid", 503, "mock", {}, None)
    return _Ok19(json.loads(req.data.decode())["id"])


E.install_http_gate(_gt19, transport=_t19)
try:  # noqa: SIM105
    try:
        _r19 = _tap19.request("eth_chainId", [])
        _out19 = f"returned {_r19}"
    except E.Shutdown as e:
        _out19 = f"Shutdown:{e.detail.get('layer')}"
    except Exception as e:                                        # noqa: BLE001
        _out19 = type(e).__name__
finally:
    E.uninstall_http_gate()
    _lg19.close()
check("停机后底层重试不再发出（只发生 1 次真实 HTTP）", len(_sent19) == 1,
      f"实际 {len(_sent19)} 次")
check("拦截发生在 HTTP 层而不是逻辑层", _out19 == "Shutdown:http", _out19)

# --- 19.2 收尾秒数必须压到在途请求的 timeout 上 ---
_tap20, _gt20, _gv20, _lg20 = _fresh_rpc19(grace_calls=5, grace_seconds=0.02)
_seen20 = []


def _t20(req, *a, **kw):
    _seen20.append(kw.get("timeout"))
    raise _ue19.URLError("mock")


E.install_http_gate(_gt20, transport=_t20)
_t0_20 = time.monotonic()
try:
    with _gv20.winddown():
        try:
            _tap20.request("eth_chainId", [])
        except Exception:                                         # noqa: BLE001
            pass
finally:
    E.uninstall_http_gate()
    _lg20.close()
check("收尾期限传到了传输层的 timeout",
      len(_seen20) == 1 and _seen20[0] is not None and _seen20[0] <= 0.02 + 1e-6,
      f"timeout={_seen20}")
check("实际耗时不超过收尾窗口", time.monotonic() - _t0_20 < 1.0,
      f"{time.monotonic() - _t0_20:.3f}s")

# 控制项：未停机时不得篡改 timeout
_tap21, _gt21, _gv21, _lg21 = _fresh_rpc19(stop=False)
_seen21 = []


def _t21(req, *a, **kw):
    _seen21.append(kw.get("timeout"))
    raise _ue19.URLError("mock")


E.install_http_gate(_gt21, transport=_t21)
try:
    try:
        _tap21.request("eth_chainId", [])
    except Exception:                                             # noqa: BLE001
        pass
finally:
    E.uninstall_http_gate()
    _lg21.close()
check("未停机时 timeout 不被改动", _seen21 and _seen21[0] == 20, str(_seen21))

# --- 19.3 请求过硬兜底却没装上 ⇒ 前置条件不成立 ---
d22 = tmp()
try:
    with patch.object(_R19, "setrlimit",
                      side_effect=PermissionError("controlled setrlimit rejection")):
        _rc22, _doc22, _, _ = A.flow(d22, "run", hard_rss_mb=64)
    _rc22 = (_rc22, acc(_doc22["acceptance"], "validation_passed"))
except FileNotFoundError:
    _rc22 = ("no-output", None)
check("硬兜底安装被拒 ⇒ 拒绝测量（不得 exit 0）",
      _rc22[0] in (2, "no-output"), str(_rc22))
check("被拒时不产出结果文件", not (d22 / "run.json").exists())

def _probs(gov, applied):
    fn = getattr(gov, "hard_limit_problems", None)
    if fn is None:
        return "<无 hard_limit_problems>"
    gov.hard_applied = applied
    return fn()


_g22 = _gov18(hard_rss_kb=64 * 1024)
_p22 = _probs(_g22, {"RLIMIT_AS": {"error": "denied", "verified": False}})
check("安装失败被列为问题而不是角落里的 error",
      isinstance(_p22, list) and len(_p22) == 1, str(_p22))
_g23 = _gov18(hard_rss_kb=64 * 1024)
_p23 = _probs(_g23, {"error": "resource module unavailable"})
check("resource 模块不可用同样算问题",
      isinstance(_p23, list) and len(_p23) == 1, str(_p23))
_p24 = _probs(E.ResourceGovernor(), {})
check("没请求硬兜底就不算问题", _p24 == [], str(_p24))

# 子进程里验证读回核验确实生效（真设限）
_rc24, _out24 = _sub18(
    "import evidence as E, json\n"
    "g = E.ResourceGovernor(hard_rss_kb=256*1024)\n"
    "a = g.apply_hard_limits()\n"
    "print(json.dumps({'verified': a['RLIMIT_AS'].get('verified'),\n"
    "                  'problems': g.hard_limit_problems()}))\n")
check("装得上时读回核验通过、无问题",
      _rc24 == 0 and '"verified": true' in _out24.replace("True", "true").lower()
      and '"problems": []' in _out24, _out24[-120:].replace("\n", " "))

d23 = tmp()
_, _doc23, _, _ = A.flow(d23, "run")
_lim23 = acc(acc(_doc23, "resources", {}), "limits", {})
check("未请求硬兜底时报告如实标注",
      _lim23.get("hard_requested") is False and _lim23.get("hard_problems") == [],
      f"hard_requested={_lim23.get('hard_requested', '<缺字段>')} "
      f"hard_problems={_lim23.get('hard_problems', '<缺字段>')}")

# --- 19.4 初始化阶段抛出也必须撤销设施 ---
E.uninstall_http_gate()
_before_t24 = _sig18.getsignal(_sig18.SIGTERM)
d24 = tmp()
_sample24 = d24 / "sample.json"
_sample24.write_text(json.dumps(dict(
    universe_sha256=E.sha256_file(P.UNIVERSE), n=1,
    sample=[dict(index=1, pair=A.PAIR, token=A.TOKEN, created_block=A.MINT - 10)])))
_ns24 = _ap17.Namespace(
    sample=str(_sample24), out=str(d24 / "o.json"), evidence=str(d24 / "o.jsonl"),
    slot_limit=2, max_calls=99999, max_seconds=9999, rps=10000)
_raised24 = None
import os as _os24
try:
    with patch.object(P.V, "RPC", side_effect=RuntimeError("injected ctor failure")), \
         patch.dict(_os24.environ, ETH_RPC_URL="https://x.invalid/test/FAKE_ONLY_KEY",
                    ETHERSCAN_API_KEY="FAKE_ONLY_SCAN_KEY"), \
         contextlib.redirect_stdout(_io18()), contextlib.redirect_stderr(_io18()):
        P.measure(_ns24)
except RuntimeError as e:
    _raised24 = str(e)
except Exception as e:                                            # noqa: BLE001
    _raised24 = f"{type(e).__name__}: {e}"
check("RPC 构造失败如实抛给调用方", _raised24 == "injected ctor failure", str(_raised24))
check("构造失败后 HTTP 闸门未残留", E.http_gate_installed() is False)
check("构造失败后信号处理器已还原",
      _sig18.getsignal(_sig18.SIGTERM) is _before_t24)
check("构造失败后没有遗留看门狗线程",
      not any(t.name == "resource-governor" and t.is_alive()
              for t in threading.enumerate()),
      str([t.name for t in threading.enumerate()]))

print("\n20 绝对墙钟截止：socket timeout 不是完成期限")
# 真实 urllib + 冻结包 RPC 类 + 当前 HTTP 闸门，连本机 127.0.0.1 临时端口。
# **不替换 urlopen**，不访问任何外部地址。服务端每 ~35ms 吐 4 字节：
# 每段都在 socket timeout 之内，整段却远超收尾期限 —— 这正是 timeout
# 管不住的情形（审查 v1.10 真实实测 0.387s / 0.15s）。
from http.server import HTTPServer as _HS20, BaseHTTPRequestHandler as _BH20


def _loopback_case(mode, grace=0.15, frag_sleep=0.035):
    gov = E.ResourceGovernor(grace_calls=4, grace_seconds=grace)
    sent = []

    class _H(_BH20):
        def log_message(self, *a): pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if mode == "stop_during_request":
                gov.request_stop("controlled_inflight_stop")
            body = json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": "0x1"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for i in range(0, len(body), 4):
                    self.wfile.write(body[i:i + 4])
                    self.wfile.flush()
                    sent.append(time.monotonic())
                    time.sleep(frag_sleep)
            except Exception:                                     # noqa: BLE001
                pass

    srv = _HS20(("127.0.0.1", 0), _H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    gt = E.SharedGate(100000, 10, 5)
    gt.governor = gov
    raw = A.REAL_RPC(f"http://127.0.0.1:{srv.server_port}", max_calls=10,
                     max_seconds=5, timeout=2, rps=100000)
    td = tmp()
    lg = E.EvidenceLog(td / (mode + ".jsonl"))
    tap = E.RpcTap(raw, lg, gate=gt, worker=0)
    E.install_http_gate(gt)
    t0 = time.monotonic()
    try:
        if mode == "stop_before_request":
            gov.request_stop("controlled_stop")
            with gov.winddown():
                try:
                    res = tap.request("eth_chainId", [])
                except E.Shutdown as e:
                    res = f"Shutdown:{e.reason}"
        else:
            try:
                res = tap.request("eth_chainId", [])
            except E.Shutdown as e:
                res = f"Shutdown:{e.reason}"
            except Exception as e:                                # noqa: BLE001
                res = type(e).__name__
        elapsed = time.monotonic() - t0
        rep = gov.report()
    finally:
        E.uninstall_http_gate()
        lg.close()
        gov.close()
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)
    gaps = [b - a for a, b in zip(sent, sent[1:])]
    return dict(result=res, elapsed=elapsed, report=rep,
                max_gap=max(gaps) if gaps else 0.0, fragments=len(sent))


for _mode in ("stop_before_request", "stop_during_request"):
    _c = _loopback_case(_mode)
    check(f"{_mode}：分段间隔确实小于 socket timeout（否则测的不是这个问题）",
          0 < _c["max_gap"] < 0.15, f"最大段间隔 {_c['max_gap']:.4f}s")
    check(f"{_mode}：超过绝对期限即中止，不再返回成功结果",
          _c["result"] == "Shutdown:wall_deadline_exceeded", str(_c["result"]))
    check(f"{_mode}：实际耗时被期限收住（≤ 0.15s + 0.15s 余量）",
          _c["elapsed"] <= 0.30, f"{_c['elapsed']:.3f}s（期限 0.15s）")
    check(f"{_mode}：报告记下到点强制关闭",
          acc(_c["report"], "absolute_deadline_closures", 0) >= 1,
          str(acc(_c["report"], "absolute_deadline_closures", "<缺字段>")))

# 控制项：未停机时同一慢响应必须正常读完，不得被误杀
_ctl = _loopback_case("no_stop")
check("未停机时慢分段响应正常完成（期限不误伤）", _ctl["result"] == "0x1",
      str(_ctl["result"]))
check("未停机时没有强制关闭",
      acc(_ctl["report"], "absolute_deadline_closures", -1) == 0,
      str(acc(_ctl["report"], "absolute_deadline_closures", "<缺字段>")))
check("报告写明期限口径不是 socket timeout",
      "not a completion deadline" in acc(_ctl["report"], "deadline_basis", ""),
      acc(_ctl["report"], "deadline_basis", "<缺字段>")[:60])

# 期限作用在**已经开始**的请求上：登记之后才停机，也要被关掉
# force_exit_after=None：这几个治理器**故意**留着未注销的在途项，
# 而 close() 现在会保留升级链 —— 不关掉兜底的话，5 秒后升级会把
# 测试进程自己 os._exit 掉（实测退出码 3）。
_g20 = _gov18(grace_calls=4, grace_seconds=0.05, force_exit_after=None)
_closed20 = []
if hasattr(_g20, "register_inflight"):
    _g20.register_inflight(lambda: _closed20.append(1))
    _g20.request_stop("late_stop")
    time.sleep(0.25)
    check("停机发生在请求开始之后，仍会到点强制关闭", _closed20 == [1], str(_closed20))
else:
    check("停机发生在请求开始之后，仍会到点强制关闭", False, "无在途登记机制")
_g20.close()

# 停机之后才登记的在途请求：立刻关闭，不等下一个周期
_g21 = _gov18(grace_calls=4, grace_seconds=0.0, force_exit_after=None)
_g21.request_stop("already_stopped")
_closed21 = []
if hasattr(_g21, "register_inflight"):
    _g21.register_inflight(lambda: _closed21.append(1))
    check("已过期时登记的在途请求立刻被关闭", _closed21 == [1], str(_closed21))
else:
    check("已过期时登记的在途请求立刻被关闭", False, "无在途登记机制")
_g21.close()
for _g in (_g20, _g21):
    try:
        _g.cancel_timers(keep_backstop_if_pending=False)
    except TypeError:
        pass

# 最后一级升级：关不掉就强制退出（子进程，因为它会 os._exit）
_rc20, _out20 = _sub18(
    "import evidence as E, time, os, sys\n"
    "fired = []\n"
    "g = E.ResourceGovernor(grace_seconds=0.05, escalate_after=0.1,\n"
    "                       on_escalate=lambda info: (print('ESCALATED %d'\n"
    "                                                       % info['stuck_inflight']),\n"
    "                                                 sys.stdout.flush(),\n"
    "                                                 os._exit(3)))\n"
    "g.register_inflight(lambda: None)   # 关不掉的在途请求\n"
    "g.request_stop('stuck')\n"
    "time.sleep(2)\n"
    "print('NO_ESCALATION'); sys.exit(9)\n", timeout=60)
check("关不掉的在途请求会触发升级并强制退出",
      _rc20 == 3 and "ESCALATED" in _out20, f"rc={_rc20} {_out20.strip()[:80]}")

# 对照：在途请求正常结束（注销登记）⇒ 绝不升级
_rc21, _out21 = _sub18(
    "import evidence as E, time, os, sys\n"
    "g = E.ResourceGovernor(grace_seconds=0.05, escalate_after=0.1,\n"
    "                       on_escalate=lambda info: (print('ESCALATED'),\n"
    "                                                 sys.stdout.flush(),\n"
    "                                                 os._exit(3)))\n"
    "tok = g.register_inflight(lambda: None)\n"
    "g.request_stop('normal')\n"
    "g.unregister_inflight(tok)          # 持有方正常收尾\n"
    "time.sleep(1)\n"
    "print('NO_ESCALATION'); sys.exit(0)\n", timeout=60)
check("在途请求正常结束时不会误升级",
      _rc21 == 0 and "NO_ESCALATION" in _out21 and "ESCALATED" not in _out21,
      f"rc={_rc21} {_out21.strip()[:60]}")

print("\n21 整个请求生命周期的期限 + 无条件的最终终止")
from http.server import HTTPServer as _HS21, BaseHTTPRequestHandler as _BH21


def _slow_header_case(mode, grace=0.15):
    """响应**头**分段慢送：urlopen 尚未返回，还没有 response 对象。"""
    gov = _gov18(grace_calls=2, grace_seconds=grace,
                 escalate_after=0.05, force_exit_after=None,
                 on_escalate=lambda x: None)
    seen = []

    class _H(_BH21):
        def log_message(self, *a): pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if mode == "stop_during_headers":
                gov.request_stop("stop_during_headers")
            body = json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": "0x1"}).encode()
            wire = (b"HTTP/1.0 200 OK\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\nX-Slow: abcdefghijklmnop\r\n\r\n")
            try:
                for i in range(0, len(wire), 4):
                    self.wfile.write(wire[i:i + 4])
                    self.wfile.flush()
                    seen.append(len(gov._inflight))
                    time.sleep(0.025)
                self.wfile.write(body)
                self.wfile.flush()
            except Exception:                                     # noqa: BLE001
                pass

    srv = _HS21(("127.0.0.1", 0), _H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    gt = E.SharedGate(100000, 10, 5)
    gt.governor = gov
    raw = A.REAL_RPC(f"http://127.0.0.1:{srv.server_port}", max_calls=10,
                     max_seconds=5, timeout=2, rps=100000)
    td = tmp()
    lg = E.EvidenceLog(td / (mode + ".jsonl"))
    tap = E.RpcTap(raw, lg, gate=gt, worker=0)
    E.install_http_gate(gt)
    t0 = time.monotonic()
    try:
        try:
            if mode == "stop_before_headers":
                gov.request_stop("stop_before_headers")
                with gov.winddown():
                    res = tap.request("eth_chainId", [])
            else:
                res = tap.request("eth_chainId", [])
        except E.Shutdown as e:
            res = "Shutdown:" + e.reason
        except Exception as e:                                    # noqa: BLE001
            res = type(e).__name__
        elapsed = time.monotonic() - t0
        rep = gov.report()
    finally:
        E.uninstall_http_gate()
        lg.close()
        gov.close()
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)
    return dict(result=res, elapsed=elapsed, report=rep,
                registered_during_headers=max(seen) if seen else 0,
                fragments=len(seen))


for _m in ("stop_before_headers", "stop_during_headers"):
    _h = _slow_header_case(_m)
    check(f"{_m}：收响应头期间就已登记在途（不是等 urlopen 返回才登记）",
          _h["registered_during_headers"] >= 1,
          f"登记数 {_h['registered_during_headers']}")
    check(f"{_m}：超期即中止", _h["result"] == "Shutdown:wall_deadline_exceeded",
          str(_h["result"]))
    check(f"{_m}：实际耗时被期限收住（≤ 0.15s + 0.15s 余量）",
          _h["elapsed"] <= 0.30, f"{_h['elapsed']:.3f}s（期限 0.15s）")

_hc = _slow_header_case("no_stop")
check("未停机时慢响应头正常完成（期限不误伤）", _hc["result"] == "0x1", str(_hc["result"]))

# --- 最终终止不得依赖阻塞日志 ---
_cap21 = {}
_orig_gov21 = E.ResourceGovernor


class _Spy21(_orig_gov21):
    def __init__(self, **kw):
        _cap21["cb"] = kw.get("on_escalate")
        super().__init__(**kw)


_d21 = tmp()
with patch.object(E, "ResourceGovernor", _Spy21):
    A.flow(_d21, "run")
_cb21 = _cap21.get("cb")
check("拿到 measure 建的真实升级回调", _cb21 is not None)

# 回调闭包里的 EvidenceLog —— 持有它的写锁，复刻审查方的场景
_log21 = None
for _c in (_cb21.__closure__ or ()):
    _v = _c.cell_contents
    if isinstance(_v, E.EvidenceLog):
        _log21 = _v
        break
check("能定位回调所用的 EvidenceLog", _log21 is not None)

_exits21 = []
if _cb21 is not None and _log21 is not None:
    # os._exit 的替身**装上就不摘**：若被测实现会阻塞，那个线程可能在
    # 上下文退出之后才走到 os._exit —— 用 with 的话它调到的就是真的，
    # 会把测试进程自己杀掉（旧版实测如此：跑到一半 exit 1、零失败项）。
    _real_exit21 = os._exit
    os._exit = lambda c: _exits21.append(c)
    _log21._lock.acquire()                    # 占住写锁，模拟 fsync 卡住
    try:
        # info 里**不放 reason**：旧版回调写的是
        # log.write("abort", reason=..., **info)，info 若含 reason
        # 会在参数绑定阶段就 TypeError，根本走不到锁 ——
        # 那样这条断言对旧版没有鉴别力（实测旧版也"通过"）。
        _info21 = {"stuck_inflight": 1, "grace_seconds": 0.1,
                   "escalate_after": 0.05}
        _t21 = threading.Thread(target=lambda: _cb21(_info21), daemon=True)
        _s21 = time.monotonic()
        _t21.start()
        _t21.join(timeout=2.0)
        _el21 = time.monotonic() - _s21
    finally:
        _log21._lock.release()
        time.sleep(0.2)        # 让可能被解锁唤醒的线程走完，别让它调到真 os._exit
    check("写锁被占用时回调仍然返回（不等锁）", not _t21.is_alive(),
          f"{_el21:.3f}s")
    check("写锁被占用时仍尝试退出（退出码 3）", _exits21 == [3], str(_exits21))
    check("回调耗时可忽略（不是等锁等出来的）", _el21 < 0.5, f"{_el21:.3f}s")
    _note21 = Path(str(_log21.path) + ".escalation")
    check("退出前的最后记录写到独立 fd（绕开日志锁）",
          _note21.is_file() and "stop_escalation_forced_exit" in _note21.read_text(),
          f"存在={_note21.is_file()}")
else:
    for _n in ("写锁被占用时回调仍然返回（不等锁）", "写锁被占用时仍尝试退出（退出码 3）",
               "回调耗时可忽略（不是等锁等出来的）", "退出前的最后记录写到独立 fd（绕开日志锁）"):
        check(_n, False, "拿不到真实回调或 EvidenceLog")

# 即便回调整个卡死，无条件定时器也必须把进程带走（子进程）
_rc21b, _out21b = _sub18(
    "import evidence as E, time, os, sys\n"
    "def hang(info):\n"
    "    print('CB_ENTERED'); sys.stdout.flush()\n"
    "    time.sleep(30)          # 回调彻底卡住\n"
    "g = E.ResourceGovernor(grace_seconds=0.05, escalate_after=0.05,\n"
    "                       force_exit_after=0.2, on_escalate=hang)\n"
    "g.register_inflight(lambda: None)\n"
    "g.request_stop('stuck')\n"
    "time.sleep(5)\n"
    "print('NO_EXIT'); sys.exit(9)\n", timeout=60)
check("回调卡死时无条件定时器仍强制退出",
      _rc21b == 3 and "CB_ENTERED" in _out21b and "NO_EXIT" not in _out21b,
      f"rc={_rc21b} {_out21b.strip()[:70]}")

print("\n22 请求登记的归属、兜底保留、以及真正无条件的退出")


def _pending(gov):
    """旧版没有 pending_inflight()，退回读内部表，让断言报 FAIL 而不是崩掉。"""
    fn = getattr(gov, "pending_inflight", None)
    if fn is not None:
        return fn()
    return len(getattr(gov, "_inflight", ()) or ())


def _loopback_slow_body(gov, frag=0.035):
    """起一个慢响应体的本机服务，返回 (tap, cleanup)。"""
    class _H(_BH21):
        def log_message(self, *a): pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            body = json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": "0x1"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for i in range(0, len(body), 4):
                    self.wfile.write(body[i:i + 4])
                    self.wfile.flush()
                    time.sleep(frag)
            except Exception:                                     # noqa: BLE001
                pass

    srv = _HS21(("127.0.0.1", 0), _H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    gt = E.SharedGate(100000, 10, 5)
    gt.governor = gov
    raw = A.REAL_RPC(f"http://127.0.0.1:{srv.server_port}", max_calls=10,
                     max_seconds=5, timeout=2, rps=100000)
    td = tmp()
    lg = E.EvidenceLog(td / "e.jsonl")
    tap = E.RpcTap(raw, lg, gate=gt, worker=0)
    E.install_http_gate(gt)

    def cleanup():
        E.uninstall_http_gate()
        lg.close()
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)
    return tap, cleanup


# --- 22.1 超期放弃之后：不留后台线程，也不留陈旧登记 ---
# **受控阻塞**：服务端一直不发完，直到我们采样完才释放。
# 否则慢响应自己就结束了，后台线程也随之消失 —— 那样这条断言
# 对旧实现毫无鉴别力（实测旧版也"通过"）。
_hold22 = threading.Event()
_names_before = {t.name for t in threading.enumerate()}
_g22 = _gov18(grace_calls=4, grace_seconds=0.12,
              escalate_after=30, force_exit_after=None)


class _HoldH22(_BH21):
    def log_message(self, *a): pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        body = json.dumps({"jsonrpc": "2.0", "id": req["id"],
                           "result": "0x1"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body[:4])
            self.wfile.flush()
            _hold22.wait(10)          # 卡住，直到测试放行
            self.wfile.write(body[4:])
            self.wfile.flush()
        except Exception:                                         # noqa: BLE001
            pass


_srv22 = _HS21(("127.0.0.1", 0), _HoldH22)
_sth22 = threading.Thread(target=_srv22.serve_forever, daemon=True)
_sth22.start()
_gt22 = E.SharedGate(100000, 10, 5)
_gt22.governor = _g22
_raw22 = A.REAL_RPC(f"http://127.0.0.1:{_srv22.server_port}", max_calls=10,
                    max_seconds=5, timeout=3, rps=100000)
_td22 = tmp()
_lg22 = E.EvidenceLog(_td22 / "e.jsonl")
_tap22 = E.RpcTap(_raw22, _lg22, gate=_gt22, worker=0)
E.install_http_gate(_gt22)
_g22.request_stop("stop")
try:
    with _g22.winddown():
        try:
            _r22 = _tap22.request("eth_chainId", [])
        except E.Shutdown as e:
            _r22 = "Shutdown:" + e.reason
        except Exception as e:                                    # noqa: BLE001
            _r22 = type(e).__name__
finally:
    E.uninstall_http_gate()
    _lg22.close()
# **此刻服务端仍卡着**：调用方已经放弃，若实现开了后台线程，它必然还活着
_threads22 = [t.name for t in threading.enumerate()
              if t.name not in _names_before and t.name != "resource-governor"]
_pending22 = _pending(_g22)
_hold22.set()                     # 采样完毕，放行
time.sleep(0.3)
_pending22_after = _pending(_g22)
_srv22.shutdown()
_srv22.server_close()
_sth22.join(timeout=5)
check("超期后请求被中止", _r22 == "Shutdown:wall_deadline_exceeded", str(_r22))
check("调用方放弃时不留后台工作线程",
      not [n for n in _threads22 if "supervised" in n or "http" in n.lower()],
      str(_threads22))
check("放弃当时登记项就已交还（不等后台结束）", _pending22 == 0, str(_pending22))
check("后台迟到完成之后也没有陈旧登记", _pending22_after == 0, str(_pending22_after))
_g22.close()

# --- 22.2 正常完成的请求同样交还登记 ---
_g23 = E.ResourceGovernor(grace_calls=4, grace_seconds=5.0, force_exit_after=None)
_tap23, _clean23 = _loopback_slow_body(_g23, frag=0.001)
try:
    _r23 = _tap23.request("eth_chainId", [])
finally:
    _clean23()
check("未停机时正常返回", _r23 == "0x1", str(_r23))
check("正常完成后登记项归零", _pending(_g23) == 0, str(_pending(_g23)))
_g23.close()

# --- 22.3 还有在途工作时，不得撤销升级链 ---
_g24 = _gov18(grace_seconds=0.05, escalate_after=5, force_exit_after=5)
_g24.register_inflight(lambda: None)
_g24.request_stop("x")
_g24.close()
check("有在途时保留升级定时器（兜底不被提前撤销）",
      getattr(_g24, "_escalate_timer", None) is not None,
      str(getattr(_g24, "_escalate_timer", "<缺字段>")))
check("报告暴露在途数量",
      acc(_g24.report(), "pending_inflight", -1) == 1,
      str(acc(_g24.report(), "pending_inflight", "<缺字段>")))
check("报告暴露兜底是否武装",
      "backstop_armed" in _g24.report(), str(sorted(_g24.report())[:6]))
try:
    _g24.cancel_timers(keep_backstop_if_pending=False)
except TypeError:
    pass
_g25 = _gov18(grace_seconds=0.05, escalate_after=5, force_exit_after=5)
_g25.request_stop("x")
_g25.close()
check("无在途时正常撤销升级定时器",
      getattr(_g25, "_escalate_timer", None) is None)

# --- 22.4 stderr 是写满的管道时，最终退出仍然发生 ---
_rc26, _out26 = _sub18(
    "import os, sys, time\n"
    "import evidence as E\n"
    "r, w = os.pipe()\n"
    "os.set_blocking(w, False)\n"
    "try:\n"
    "    while True: os.write(w, b'x' * 65536)\n"
    "except BlockingIOError: pass\n"
    "os.set_blocking(w, True)\n"
    "os.dup2(w, 2)                     # stderr 现在是写满的管道\n"
    "g = E.ResourceGovernor(grace_seconds=0.02, escalate_after=0.02,\n"
    "                       force_exit_after=0.02, on_escalate=lambda i: None)\n"
    "g.register_inflight(lambda: None)\n"
    "g.request_stop('stuck')\n"
    "time.sleep(0.6)\n"
    "os.write(1, b'SURVIVED_PAST_FORCED_EXIT\\n')\n"
    "sys.exit(9)\n", timeout=30)
check("stderr 写满时最终退出仍然发生（退出码 3）",
      _rc26 == 3 and "SURVIVED" not in _out26,
      f"rc={_rc26} {_out26.strip()[:60]}")

print("\n23 连接全过程（DNS / TCP / TLS）的停机监督")
# 真实 urllib HTTPS 客户端 + 本机 loopback；**证书校验保持开启**。
# 探针放在 runs/tls_20260911/，由子进程运行（隔离 socket/线程/环境变量），
# 通过 RT_CODE_ROOT 指向被测代码 —— 反向验证时指向旧快照。
import shutil as _sh23
import subprocess as _sp23

_HERE23 = Path(__file__).resolve().parent
_PROBE_DIR23 = Path("/home/ancillary/rightTail/baseline_work_20260910/runs/tls_20260911")
_cert_dir23 = tmp()
_cert23, _key23 = _cert_dir23 / "cert.pem", _cert_dir23 / "key.pem"
_have_openssl = _sh23.which("openssl") is not None
if _have_openssl:
    _sp23.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
               "-keyout", str(_key23), "-out", str(_cert23), "-days", "1",
               "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
              capture_output=True, timeout=60)
check("能生成本机测试证书（缺 openssl 则 HTTPS 场景无法验证，判失败而非跳过）",
      _cert23.is_file() and _key23.is_file(), f"openssl={_have_openssl}")


def _probe23(name, trust_cert):
    # RT_PROBE_OUT：探针只往这个每次新建的临时目录里写，绝不写回交付目录
    env = dict(os.environ, RT_CODE_ROOT=str(_HERE23), RT_PROBE_OUT=str(tmp()))
    env.pop("SSL_CERT_FILE", None)
    if trust_cert:
        env["SSL_CERT_FILE"] = str(_cert23)
    r = _sp23.run([sys.executable, str(_PROBE_DIR23 / name), str(_cert23), str(_key23)],
                  capture_output=True, text=True, timeout=180, env=env)
    rows = []
    for line in r.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return r.returncode, rows, r.stdout[-300:] + r.stderr[-300:]


_rc23, _rows23, _tail23 = _probe23("phase_probe.py", trust_cert=True)
_by23 = {r.get("阶段"): r for r in _rows23}


def _row(key):
    return next((v for k, v in _by23.items() if k and key in k), {})


_tls = _row("TLS 握手")
check("TLS 握手中停机：握手期间已登记在途", _tls.get("握手期间登记数", 0) >= 1,
      str(_tls.get("握手期间登记数", "<无>")))
check("TLS 握手中停机：被期限收住（≤ 0.30s）且归因到握手阶段",
      "wall_deadline_exceeded(tls_handshake)" in str(_tls.get("结果"))
      and (_tls.get("停机后耗时s") or 9) <= 0.30,
      f"{_tls.get('结果')} {_tls.get('停机后耗时s')}s")
_tcp = _row("TCP 建连")
check("TCP 建连中停机：被期限收住（socket timeout 3s 不再是上界）",
      "wall_deadline_exceeded(tcp_connect)" in str(_tcp.get("结果"))
      and (_tcp.get("停机后耗时s") or 9) <= 0.30,
      f"{_tcp.get('结果')} {_tcp.get('停机后耗时s')}s")
_body = _row("停机后发起")
check("真实 TLS 下的慢响应体被期限收住",
      "wall_deadline_exceeded" in str(_body.get("结果"))
      and (_body.get("停机后耗时s") or 9) <= 0.30,
      f"{_body.get('结果')} {_body.get('停机后耗时s')}s")
_ctl = _row("未停机对照")
check("未停机时 HTTPS（校验开启）正常返回", _ctl.get("结果") == "0x1", str(_ctl.get("结果")))
check("未停机完成后没有残留登记", _ctl.get("在途登记残留") == 0,
      str(_ctl.get("在途登记残留", "<无>")))

_rc24, _rows24, _tail24 = _probe23("verify_and_dns_probe.py", trust_cert=False)
_ver = next((r for r in _rows24 if r.get("项", "").startswith("不信任")), {})
check("不信任测试证书时校验照样失败（没有削弱正常 HTTPS 校验）",
      _ver.get("判定") == "REJECTED", f"{_ver.get('判定')} {str(_ver.get('细节'))[:60]}")
_dns = next((r for r in _rows24 if r.get("项", "").startswith("DNS")), {})
check("DNS 阶段已登记在途（升级机制看得见它）", str(_dns.get("DNS期间在途登记")) == "1",
      str(_dns.get("DNS期间在途登记", "<无>")))
check("DNS 卡死时由升级兜底强制退出（退出码 3）",
      _dns.get("退出码") == 3 and _dns.get("未被强制退出") is False,
      f"rc={_dns.get('退出码')} 未退出={_dns.get('未被强制退出')}")

print("\n25 启动阶段端点瞬时不可达：干净地拒绝，而不是崩溃")
# 真链对照（2026-09-11）实测：端点瞬时 TLS EOF，并行与续跑在第一个请求就抛出
# 未捕获异常 —— 没有 abort 证据，退出码也不在规格定义的 0/1/2/3 之内。


class _FlakyRpc:
    """在指定的启动步骤抛传输错误，其余交给受控假链。"""

    def __init__(self, fail_on, inner):
        self.fail_on, self.inner = fail_on, inner
        self.records = inner.records

    def request(self, method, params):
        if (self.fail_on == "chain_id" and method == "eth_chainId") or (
                self.fail_on == "snapshot" and method == "eth_getBlockByNumber"
                and params and params[0] == "finalized"):
            raise P.V.RpcFailure("transport",
                                 "<urlopen error TLS/SSL connection has been closed (EOF)>")
        return self.inner.request(method, params)

    def call(self, *a, **kw):
        return self.inner.call(*a, **kw)


for _stage in ("chain_id", "snapshot"):
    from fake_chain import FakeRpc as _FR25
    _cfg25 = dict(head=25900000, genesis_ts=0, entry_block=A.MINT + 1, pair=A.PAIR,
                  token=A.TOKEN, received=10 ** 18, cash=10 ** 15, slot=0, chain_id=1,
                  supply=lambda b: 0 if int(b, 16) < A.MINT else 10 ** 6)
    _d25 = tmp()
    _smp25 = _d25 / "sample.json"
    _smp25.write_text(json.dumps(dict(
        universe_sha256=E.sha256_file(P.UNIVERSE), n=1,
        sample=[dict(index=1, pair=A.PAIR, token=A.TOKEN, created_block=A.MINT - 10)])))
    _ns25 = _ap17.Namespace(sample=str(_smp25), out=str(_d25 / "o.json"),
                            evidence=str(_d25 / "o.jsonl"), slot_limit=2,
                            max_calls=99999, max_seconds=9999, rps=10000)
    _before_term25 = _sig18.getsignal(_sig18.SIGTERM)
    _err25 = None
    try:
        with patch.object(P.V, "RPC",
                          side_effect=lambda *a, _s=_stage, **k: _FlakyRpc(_s, _FR25(_cfg25))), \
             patch.dict(os.environ, ETH_RPC_URL="https://x.invalid/test/FAKE_ONLY_KEY",
                        ETHERSCAN_API_KEY="FAKE_ONLY_SCAN_KEY"), \
             contextlib.redirect_stdout(_io18()), contextlib.redirect_stderr(_io18()):
            _rc25 = P.measure(_ns25)
    except BaseException as e:                                    # noqa: BLE001
        _rc25, _err25 = None, f"{type(e).__name__}: {str(e)[:60]}"
    check(f"{_stage} 步端点不可达：不抛未捕获异常", _err25 is None, str(_err25))
    check(f"{_stage} 步端点不可达：返回 2（前置条件不成立）", _rc25 == 2, str(_rc25))
    _ev25 = [json.loads(l) for l in (_d25 / "o.jsonl").read_text().splitlines() if l.strip()] \
        if (_d25 / "o.jsonl").is_file() else []
    _ab25 = [r for r in _ev25 if r.get("kind") == "abort"]
    check(f"{_stage} 步端点不可达：留下 abort 证据且理由明确",
          any(r.get("reason") == "endpoint_unreachable" and r.get("stage") == _stage
              for r in _ab25), str([(r.get("reason"), r.get("stage")) for r in _ab25]))
    check(f"{_stage} 步端点不可达：证据里没有凭据明文",
          "FAKE_ONLY_KEY" not in (_d25 / "o.jsonl").read_text()
          if (_d25 / "o.jsonl").is_file() else False)
    check(f"{_stage} 步端点不可达：闸门与信号处理器已撤销",
          E.http_gate_installed() is False
          and _sig18.getsignal(_sig18.SIGTERM) is _before_term25)

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

print("\n24 测试不得改写交付与审核产物")
_ARTIFACTS_AFTER = _artifact_snapshot()
_changed24 = sorted(k for k in _ARTIFACTS_BEFORE
                    if k in _ARTIFACTS_AFTER and _ARTIFACTS_BEFORE[k] != _ARTIFACTS_AFTER[k])
_removed24 = sorted(k for k in _ARTIFACTS_BEFORE if k not in _ARTIFACTS_AFTER)
_added24 = sorted(k for k in _ARTIFACTS_AFTER if k not in _ARTIFACTS_BEFORE)
check("快照覆盖到了实际存在的产物（不是空目录）", len(_ARTIFACTS_BEFORE) > 50,
      f"{len(_ARTIFACTS_BEFORE)} 个文件")
check("整次运行前后没有任何产物被改写", not _changed24, str(_changed24[:5]))
check("整次运行没有删掉任何产物", not _removed24, str(_removed24[:5]))
check("整次运行没有往交付/审核目录里新增文件", not _added24, str(_added24[:5]))

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

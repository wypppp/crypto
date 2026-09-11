#!/usr/bin/env python3
"""针对 audit_followup_20260910/REVIEW.md 九个反例的回归测试。

断言的是【修复后】应有的行为。审查方的 reproduce_remaining.py /
reproduce_retry.py 断言的是 bug 存在，修好之后它们必然失败，
因此不能当回归守卫 —— 保留原件作为反例出处，这里是守卫。

全部离线：链、Etherscan、HTTP 传输都是受控实现，绝不触真实端点。
"""
import contextlib, json, sys, tempfile, threading, time
from io import StringIO as _io18
from pathlib import Path
from unittest.mock import patch
import urllib.error

import audit_flow as A
import evidence as E
import pilot_measure as P

ok = fail = 0


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
    """旧版没有这些参数 —— 退回不带参数构造，让断言报 FAIL 而不是整节崩掉。"""
    try:
        return E.ResourceGovernor(**kw)
    except TypeError:
        return E.ResourceGovernor(**{k: v for k, v in kw.items()
                                     if k in ("max_rss_kb", "max_cpu_s",
                                              "max_wall_s", "poll_s")})


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

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

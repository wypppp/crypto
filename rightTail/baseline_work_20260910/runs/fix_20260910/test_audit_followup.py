#!/usr/bin/env python3
"""针对 audit_followup_20260910/REVIEW.md 九个反例的回归测试。

断言的是【修复后】应有的行为。审查方的 reproduce_remaining.py /
reproduce_retry.py 断言的是 bug 存在，修好之后它们必然失败，
因此不能当回归守卫 —— 保留原件作为反例出处，这里是守卫。

全部离线：链、Etherscan、HTTP 传输都是受控实现，绝不触真实端点。
"""
import json, sys, tempfile, time
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
check("实际 HTTP 与逻辑请求分开报",
      "http_calls" in g6 and "logical_requests" in g6, str(sorted(g6)))
check("受控链下实际 HTTP 为 0（不拿预留冒充实际）",
      acc(g6, "http_calls") == 0 and acc(g6, "logical_requests", 0) > 0,
      f"http={acc(g6, 'http_calls', '<缺>')} logical={acc(g6, 'logical_requests', '<缺>')}")

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

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

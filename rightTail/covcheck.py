# -*- coding: utf-8 -*-
"""对 selftest 做行覆盖，检查关键分支是否真的被执行到。

注意：行覆盖只能证明"这行跑过"，不能证明"这个分支的输出对"。
凡是有条件产出的文字（比如回看窗口分叉告警），必须在 selftest 里断言字面量。
"""
import sys, io, contextlib
import rt_a_attribution as R
SRC = R.__file__
lines = open(SRC, encoding='utf-8').read().split('\n')

AMBIGUOUS = []

def find(sub):
    hits = [i + 1 for i, l in enumerate(lines) if sub in l]
    if len(hits) > 1:
        # 上一轮就被这个坑到：find 取首个匹配，锚点撞车会去检查另一个函数的同名行
        AMBIGUOUS.append((sub[:48], hits))
    return hits[0] if hits else None


def find_after(marker, sub):
    """在 marker 所在行之后找 sub —— 用于多处同形的返回语句。"""
    start = next((i for i, l in enumerate(lines) if marker in l), None)
    if start is None:
        return None
    for i in range(start, len(lines)):
        if sub in lines[i]:
            return i + 1
    return None

KEY = {
  "L2b 整条不可用 → api_failure": find_after("if L2B_USABLE is False:", 'return None, None, None, "api_failure", "unknown"'),
  "L2b 便宜路径2 getBlockReceipts": find('brs, err = rpc("eth_getBlockReceipts"'),
  "L2b 退化路径撞扫描上限": find('# 扫描上限，不是"没有"'),
  "L2b 工厂部署 → ambiguous": find('"ok" if direct else "ambiguous", "direct" if direct else "factory")'),
  "L4 分页打满 → history_truncated": find('return None, None, ("history_truncated" if len(r) >= page'),
  "历史部署 接口失败 → api_failure": find_after('def creator_prior_deploys',
                                                '        return None, None, "api_failure"'),
  "历史部署 分页打满 → 截断": find('return total, earliest, "history_truncated"      # 分页打满'),
  "历史部署 数到0 → 截断(结构盲区)": find('    return 0, None, "history_truncated"'),
  "失败创建交易被排除": find('if str(t.get("isError", "0")) == "1":'),
  "hist_status → api_failure(顺序)": find('hist_status = "api_failure"'),
  "hist_status 主体必须一致": find('if prior_s > 0 and creator and s_from and s_from == creator:'),
  "creator 未知不宣称 no_history": find('hist_status = creator_status'),
  "l2b_self_test 断言失败分支": find('L2B_USABLE, L2B_NOTE = False, ('),
  "as_rows 形状异常返回 None": find('        return r if all(isinstance(x, dict) for x in r) else None'),
  "l2a 形状异常 → api_failure": find('# 形状异常按接口失败记'),
  "两路先比 txHash → conflict_tx": find('l2_agreement = "conflict_tx"'),
  "冲突时不写确定归因": find('        creator = None'),
  "deploy_kind 用 contractFactory": find('kind = "factory" if a_fac else "direct"'),
  "L3 识别 MINIMUM_LIQUIDITY 锁定": find('locked += 1                   # MINIMUM_LIQUIDITY 锁定'),
  "L3 不越过链头": find('# 前向模式不得请求当时链头之后的区块'),
  "Etherscan 日志源": find('    r, e = etherscan("logs", "getLogs", address=cfg["factory"],'),
  "日志源自动选择": find('        PAIR_LOGS_SOURCE = "etherscan"'),
  "日志缺口持久化": find_after('def record_gaps', '    con.executemany('),
  "allPairsLength 对账": find('out["count_match"] = (out["n_expected"] == len(uniq))'),
  "对账不通过 → 母体不完整": find('out["note"] = "对账不通过：日志有遗漏，该区间不得标为完整母体"'),
  "getLogs 跨度实测命中": find('return span, f"实测可用跨度 {span}'),
  "getLogs 全跨度失败": find('return 0, f"全部跨度失败，最后错误: {last_err}"'),
  "7702 委托判定": find('return 1 if str(code).lower().startswith("0xef0100") else 0'),
  "7702 查候选块非 latest": find('    tag = hex(at_block) if at_block else "latest"'),
  "前向按字段判超时": find('            for k, lagk in (("l1_status", "lag_l1_seconds"),'),
  "前向缺口重试": find('        pending = con.execute('),
  "续跑按 spec_hash 判": find('    done = {r[0] for r in con.execute('),
  "spec 在能力探测后冻结": find('    blob = {"spec": SPEC, "spec_hash": spec_hash(), "frozen_at": now_iso(),'),
  "报告分层一致率": find('for kind in ("direct", "factory", "unknown"):'),
  "报告 l2_agreement 细分": find('L.append("\\n【3c】两路一致性的细分'),
  "来源选择用固定批量标准": find('    bar = SPEC["min_bulk_log_span"]'),
  "空区间对账通过": find('        out["contiguous"] = out["boundary_match"] = True'),
  "历史/候选分别对账": find('        record_integrity(con, mode, role, a_, b_, rec)'),
  "缺口带归属落库": find('        [(SPEC["chain"], cfg["factory"], role, ACTIVE_BATCH or "unowned",'),
  "前向只补本次范围缺口": find('        pending = con.execute('),
  "补回日志需过对账": find('            if not g2 and retry_rec["ok"]:'),
  "报告读取完整性状态": find('        intact, irows = integrity_of(con, mode)'),
  "不完整 → INCOMPLETE 横幅": find('                  "!!  母体不完整 —— 这份是 INCOMPLETE 调试报告，不是验收结果  !!",'),
  "不完整 → 删掉旧正式报告": find('            os.remove(normal)      # 避免上一次的正式报告被误当成本次结果'),
  "report 返回非零": find_after("def report():", '        return 1'),
  "reconcile 只核验不归因": find('        print("\\n[对账模式] 只做完整性核验，不继续归因。")'),
}
seen = set()
def tr(frame, ev, arg):
    if frame.f_code.co_filename == SRC:
        if ev == 'line':
            seen.add(frame.f_lineno)
        return tr
    return None
sys.settrace(tr)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        R.selftest()
finally:
    sys.settrace(None)

print(f"{'分支':<34} {'行':>5}  覆盖")
print("-" * 56)
miss = []
for k, ln in KEY.items():
    if ln is None:
        print(f"{k:<34} {'?':>5}  定位失败"); miss.append(k); continue
    ok = ln in seen
    print(f"{k:<34} {ln:>5}  {'✔ 执行到' if ok else '✘ 未执行'}")
    if not ok: miss.append(k)
print("-" * 56)
if AMBIGUOUS:
    print("\n⚠ 以下锚点在源码中出现多次，find 只取了第一个，可能在检查别处的同名行：")
    for sub, hits in AMBIGUOUS:
        print(f"    {sub!r} -> 行 {hits}")
print(f"{len(KEY)-len(miss)}/{len(KEY)} 覆盖" + (f"；未覆盖：{miss}" if miss else ""))

print(f"Imported source: {SRC}")
sys.exit(1 if miss or AMBIGUOUS else 0)

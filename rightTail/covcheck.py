# -*- coding: utf-8 -*-
"""对 selftest 做行覆盖，检查上一轮被指出"从未执行"的分支现在走到没有。"""
import sys, io, contextlib, linecache
import rt_a_attribution as R
SRC = R.__file__
lines = open(SRC, encoding='utf-8').read().split('\n')

def find(sub, occ=0):
    hits=[i+1 for i,l in enumerate(lines) if sub in l]
    return hits[occ] if len(hits)>occ else None

KEY = {
  "L2b 整条不可用 → api_failure":        find('return None, None, "api_failure", "unknown"',0),
  "L2b 便宜路径2 getBlockReceipts":      find('brs, err = rpc("eth_getBlockReceipts"'),
  "L2b 退化路径 + 扫描上限":              find('return None, None, "history_truncated", "unknown"   # 扫描上限'),
  "L4 分页打满 → history_truncated":     find('return None, None, ("history_truncated" if len(r) >= page'),
  "历史部署 → history_truncated":         find('return total, earliest, "history_truncated"'),
  "历史部署 → api_failure":               find('return None, None, "api_failure"\n',0) or find('    if not any_ok:')+1,
  "hist_status 回落自足通道(body)":       find('            hist_status = "ok"                     # 自足通道已确认有前科'),
  "hist_status → api_failure(顺序修复)":  find('            hist_status = "api_failure"'),
  "hist_status → 抽样底线截断":            find('        elif hist_sampled_floor is not None'),
  "l2b_self_test 断言失败分支":            find('        L2B_USABLE, L2B_NOTE = False, ('),
  "as_rows 形状异常返回 None":            find('    return None\n',0) or find('def as_rows')+7,
  "l2a 形状异常 → api_failure":           find('        return None, None, "api_failure"        # 形状异常按接口失败记'),
  "l2b 工厂部署 → ambiguous":             find('                    "ok" if direct else "ambiguous", "direct" if direct else "factory")'),
  "creator 只取 ok 值":                    find('    creator = (a_cr if l2a == "ok" else None)'),
  "forward late → timeout 改写":          find('                        row[k] = "timeout"'),
  "report 分层一致率":                     find('        for kind in ("direct", "factory", "unknown"):'),
  # ---- 本轮新增的修复 ----
  "旧库迁移 ALTER TABLE 补列":            find('        con.execute(f"ALTER TABLE attribution ADD COLUMN {c}")'),
  "creator_status 先判 ambiguous":       find('                      ("ambiguous" if ((a_cr or b_cr) or "ambiguous" in (l2a, l2b)) else'),
  "l4 主体标记":                          find('    l4_subject = "creator" if creator else ("pair_created_tx_sender" if s_from else None)'),
  "l2_source 看状态":                     find('        "l2_source": ("etherscan" if (a_cr and l2a == "ok")'),
  "fully 按库中实际量判":                  find('    fully = have_hs >= total_hist'),
  "forward 回看窗口取自 SPEC":            find('                            max(1, bn - SPEC["forward_lookback_blocks"]),'),
  # 分叉告警改用场景 14 的行为断言验证；这里只查真分支的赋值语句是否可达。
  # （原先指向多行条件表达式，Python 3.8 会把每一行都误标为已执行。）
  "报告回看窗口分叉告警(真分支)":            find('            lookback_warn = ('),
  "自足通道兜底需 creator 非空":           find('        if prior_s > 0 and creator:'),
  "creator 未知不宣称 no_history":        find('            hist_status = creator_status'),
}
seen=set()
def tr(frame, ev, arg):
    if frame.f_code.co_filename == SRC:
        if ev == 'line': seen.add(frame.f_lineno)
        return tr
    return None
sys.settrace(tr)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        R.selftest()
finally:
    sys.settrace(None)

print(f"{'分支':<38} {'行':>5}  覆盖")
print("-"*58)
miss=[]
for k,ln in KEY.items():
    if ln is None:
        print(f"{k:<38} {'?':>5}  定位失败"); miss.append(k); continue
    ok = ln in seen
    print(f"{k:<38} {ln:>5}  {'✔ 执行到' if ok else '✘ 未执行'}")
    if not ok: miss.append(k)
print("-"*58)
print(f"{len(KEY)-len(miss)}/{len(KEY)} 覆盖" + (f"；未覆盖：{miss}" if miss else ""))

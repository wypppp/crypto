# v1.7 独立离线复核

本轮审核范围：v1.6 的三项修复，以及审核期间发现、随后由实现者在 v1.7 修复的“绑定字段缺失绕过”。本轮未修改实现，未请求真链，未启动正式冻结或300样本。所有独立流程反例使用临时目录与 mock 网络；审计产物单独保存，没有运行会写回旧 retry_gated.json 的交付脚本。

## 独立验证结果

四项修复在本轮受控范围内均通过，未发现新的阻断反例：

| 项目 | 本次实际行为 |
|---|---|
| 无关运行的完整证据替换原证据 | 续跑退出1，证据链问题非空；累计结果仍保留 |
| 主卖出stage20后尺寸诊断异常 | 退出1、data_missing；已知卖出swap1/approve2保留，主场景gas为440000000000000wei |
| 排队后超时拒绝传输 | 实际传输1次；http_sent=1、http_reserved=2、http_rejected_after_wait=1 |
| 六项绑定分别删除 | 六次续跑均退出1，明确evidence_binding_field_missing；不再静默通过 |

六项为 script_sha256、evidence_module_sha256、spec_sha256、sample_sha256、universe_sha256_now、finalized_snapshot。缺失运行头字段不再作为“不比较”的理由。显式null也进入不等比较，不享受缺失绕过。

验证命令（从 /home/ancillary 执行）：

```bash
python3 rightTail/baseline_work_20260910/audit_v17_20260910/verify_three.py
python3 rightTail/baseline_work_20260910/audit_v17_20260910/verify_missing_binding.py
```

两脚本均退出0，表示修复后预期断言成立；被测失败流程自身退出1。输出见 observations.json、verify_three.log、missing_binding.json、missing_binding.log。

## 版本与证据

v1.6 的305项入口日志、原始源码快照和缺失字段反例保留在 ../audit_v16_20260910/，该目录已补 REVIEW.md。没有将修复后的结果覆写为旧版本“通过”。

本目录 hashes_start.json / hashes_end.json 记录 v1.7 全入口复跑前后顶层 Python 源码与规格 hash；两份必须完全一致才能将本次入口结果归于同一版本。pilot_measure.audited.py、evidence.audited.py 为本轮快照。

preservation.json 独立确认 v1.4/v1.5/v1.6 原始字节与 v1.6 审核时一致；冻结 v3 原语 sha256 仍为 bc9ea52ec51259d79cfe435d47dc0d846fadd56d866494e7dfcfaf3b92c15d52。未独立重跑交付方旧源码反向守卫，其旧版通过/失败计数不作为本轮执行结果。

## 验收边界与后续

此结论只关闭上述离线工程反例，不表示完整经济实验验收通过。现有资源采样不是硬RSS/CPU上限，也不是可靠峰值。真链串行/并行同快照对照尚未执行，--pin-finalized机制通过不等于真实对照通过。

后续先落实资源约束与停机策略，再做同一开发样本、同一固定状态块、独立检查点的少量真链串行/两路对照，复核逐候选状态/金额/分类/身份、原始证据、HTTP计数及恢复行为。本轮不代为启动。正式冻结与300样本继续关闭。

measurement_semantics_verified=false、economic_results_eligible=false 继续成立；工程反例关闭不证明跨期持仓状态充分，也不赋予经济统计资格。

非阻断文档小项：SharedGate 类说明仍残留“calls 是实际HTTP次数”，该别名已删除，应在下一次文档整理中改为 http_sent；本轮实际测试以新字段为准。

## 全入口独立复跑：311/0

9个入口按顺序运行，全部退出0；复跑前后源码与规格hash完全一致。每条命令为在baseline_work_20260910目录执行 `python3 test_<入口>.py`。

| 入口 | 退出码 | 通过/失败 |
|---|---:|---:|
| test_evidence | 0 | 29/0 |
| test_first_mint | 0 | 17/0 |
| test_step3 | 0 | 27/0 |
| test_step4 | 0 | 18/0 |
| test_e2e_blocking | 0 | 41/0 |
| test_resume | 0 | 23/0 |
| test_parallel | 0 | 23/0 |
| test_audit_fixes | 0 | 34/0 |
| test_audit_followup | 0 | 99/0 |

逐入口完整stdout/stderr见本目录test_*.log，退出码汇总见tests.json。

# v1.5 交付复核（2026-09-10）

结论：修复有实质进展，但仍有三个可复现缺口，暂不放行真链并行对照或正式 300 样本。只运行离线受控测试；未修改被测实现或冻结 v3 包。完整源码 hash 校验见 `hash_verification.json`，本次源码快照见 `*.audited.py`。

## 已确认

交付清单中所有可定位文件的完整 sha256 与当前文件一致，包括 v1.4、v1.5 和原语脚本。v1.4 与上一轮审计 hash 一致，原语仍为 bc9ea52ec51259d79cfe435d47dc0d846fadd56d866494e7dfcfaf3b92c15d52。

内联结果+hash、累计交付、中段损坏阻断、样本唯一性、实际规格标识、原买入成本反例、基本证据结构和 Mint 字段校验均有针对性修复。HTTP 闸门在启动前安装并进入 urlopen，底层重试经过它；原反例替换整个 urlopen 的测试方式会绕过该修复，不能据此判修复失败。

独立复跑交付方 `reproduce_retry_gated.py`：exit=0，要求 10 秒，实测间隔 10.005 秒，2 次 HTTP，限流反例的修复成立。资源硬上限和真链对照仍未完成；经济统计资格仍为 false。

## 尚未关闭

### 1. P0：续跑证据未绑定到被复用的运行和结果

位置：`pilot_measure.py:637`–`:656`；检查点已记 evidence_run_id，但检查代码没有使用它，也没有把 candidate_result 与检查点的 result_sha256 对上。

独立全流程反例：先完成两个候选；保持检查点不变，把其引用的证据文件换成**另一个 run_id 的完整 header/footer 文件**；然后续跑。

实测：exit=0，累计 n=2，skipped=[1,2]，evidence_chain_problems=[]，validation_passed=true。该文件完全没有原运行和原候选的证据，却通过了引用检查。

文件自身结构完整不代表它支持被复用的结果。需核对指定 run_id、绑定规格/样本/状态、candidate_result 及其结果 hash；缺失或不符阻断复用验收。正常恢复以及无关证据替换要分别测试。

### 2. P1：诊断失败把已到达的卖出阶段记成“未尝试”

位置：`pilot_measure.py:892`–`:925`、`:944`–`:959`。

全流程受控卖出返回 stage20，然后尺寸诊断抛 transport 异常。实测：state=data_missing、exit=1；rec.exit.stage=20 仍在，但 cost.exit_attempts={swap:0,approve:0}，basis 写“exit leg never attempted”。

这是因为卖出 attempts 在诊断之后才写；新统一收尾把缺失 attempts 默认为 0。该路径实际已经到达 swap，应保留 swap=1、approve=2。不是把诊断或 HTTP 重试算成交易尝试；应在收到主卖出返回值后立即保存已到达阶段，再执行诊断。

反例使用当前原 probe_call 执行受控链路径，将主卖出结果设为一致的 stage20（余额未清零、cash_in=0），仅在尺寸诊断注入异常；不依赖不可能的成功/失败混合结果。

### 3. P1：http_calls 名为实际次数，实际仍包含未发出的请求

位置：`evidence.py:425`–`:449`。

acquire_http 在等待前递增 calls/per_worker_http；等待后超时会拒绝传输，但不区分这份额度与真正发出的请求。

在闸门下替换传输：rps=10、max_seconds=0.02，第一个请求发出；第二个排队后被时间闸门拒绝。实测传输只执行 **1 次**，stats.http_calls 和 http_per_worker 却报告 **2 次**。

本例没有越过调用预算，门禁是保守的；问题在资源/成本的实际计量。应分开 reserved/admitted/sent/rejected，或在真正调用传输前登记实际次数，同时保持并发预算预留安全。不能再将当前字段当作可复算的实际网络调用量。

## 复现与验证

`python3 rightTail/baseline_work_20260910/audit_v15_20260910/reproduce.py`：exit=0，表示三个缺口全部按预期复现；输出 `observations.json` / `reproduce.log`。网络全部 mock，候选数据在独立临时目录，不覆盖正式数据。

9 个入口逐一 `python3 test_<name>.py`，命令工作目录为 baseline_work_20260910。逐入口日志和退出码见 `test_*.log`、`tests.json`；最终汇总另附。未重新执行旧源码反向守卫，该 14/51 结果只属于交付方记录，不冒充本次独立复跑。

复跑交付脚本有一个产物副作用：它固定写入 runs/fix_20260910/retry_gated.json，因此该文件现为本轮重测值（10.005 秒），并已复制到本审计目录；不能再把它当作交付方原先 10.01 秒测量的原始 JSON。本轮未改其余历史测量日志。

下一步：先把证据引用与具体结果闭合，再修诊断异常的阶段成本和 HTTP 实际计数；无需重开已经关闭的原反例，也不因测试数量增加改变经济语义边界。

## 本次独立全入口汇总

| 入口 | 退出码 | 通过/失败 |
|---|---:|---:|
| test_evidence | 0 | 29/0 |
| test_first_mint | 0 | 17/0 |
| test_step3 | 0 | 27/0 |
| test_step4 | 0 | 18/0 |
| test_e2e_blocking | 0 | 41/0 |
| test_resume | 0 | 23/0 |
| test_parallel | 0 | 23/0 |
| test_audit_fixes | 0 | 32/0 |
| test_audit_followup | 0 | 65/0 |

总计 275 项断言，9 个入口全部退出 0；上述三个独立反例并未被这些断言覆盖。

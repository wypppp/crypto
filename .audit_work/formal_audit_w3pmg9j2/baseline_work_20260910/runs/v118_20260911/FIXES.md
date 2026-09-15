# 已证不符的保留 + 比较器全量绑定 + 启动失败与结果证据链分开（规格 v1.18）

来源：`../../audit_v117_20260911/REVIEW.md` 两项 P1、一项 P2。本轮**没有请求任何真实端点**，
全部用既有真链证据与受控测试验收。正式冻结、300 样本、跨期持仓充分性与经济统计资格继续关闭，
`measurement_semantics_verified` / `economic_results_eligible` 仍为 `false`。`rt_a.sqlite` 未动。

| 项 | 结果 |
|---|---|
| 10 个入口 | **648 / 0，全部退出 0**（audit_followup 363，含新增 §27 50 项；realchain_tools 72） |
| §27 在 v1.17 审核快照 `d9dfb8f0…` 上反向 | 单节 17 通过 / **33 失败**；整份 `test_audit_followup.py` 330 / **33**，33 项全在 §27 |
| 同场景新旧工具对照（`reverse_tools_v117.*`） | 绑定三种篡改：v1.17 比较器 `0,0,0` → 当前 `1,1,1`（正对照都 0）；启动断连后续跑补齐：v1.17 驱动 1 → 当前 0 |
| 当前比较器对第二轮既有证据只读复核 | 58 项必需检查全部通过、退出 0；5 次历史运行都走**明确的旧版绑定规则** |
| 历史文件 | 审核记录的 74 个历史文件 hash 逐一一致；本轮在第二轮目录只**新增** `ERRATA_ADDENDUM_v118.md` |
| §24 | 覆盖 907 个交付/审核文件，零改写 / 删除 / 新增 |

---

## 一、P1：已证不符在后续中断中丢失（`pilot_measure.py`）

**根因**：校验、身份闭环、恢复核验都在**函数局部**累积结论，调用方只在函数正常返回后才拿到。
`validate_identity_closure` 算出两侧不符后，`getPair` 断连抛出，局部结论没交回；
预算（`RpcFailure kind=budget` 或闸门 `BudgetExhausted`）让校验函数直接上抛，局部 `failures` 随之丢失；
恢复阶段的异常收尾把 `restore_check` 整个换成一条 `failures=[]` 的新记录。

**改法**：
* 校验与恢复核验的记录**先挂到候选记录上**（`validation_placeholder`），函数就地写入，每得出一项当场落下；
  身份闭环的 `closure` / `failures` 由调用方持有。
* 非接口原因打断时（`mark_interrupted`）只把「未完成」占位换成具体原因（`budget` / `shutdown` / 异常类型），
  记 `interrupted_by`，并**先写证据摘要再上抛** —— 证据里的 `state_validation` / `wallet_restore_check` 也带着不符。
* **已证不符优先**：任一项 `failures` 非空，候选记 `state_validation_failed`；若原本被记成中断状态，
  另写 `data.interrupted_after_mismatch = {prior_state, mismatch_in}`，原有 `data`（`budget` 说明、`shutdown` 原因）不动。
* 没有不符时行为不变：仍按各自原因记（§26 全部照旧通过）。

**守卫 §27（50 项，完整 measure 流程，故障只作用于候选 1）**：

| 场景 | 候选 state | 该项 status | failures | unavailable | `interrupted_after_mismatch.prior_state` |
|---|---|---|---|---|---|
| 两侧不符后 getPair 断连（审核反例 1） | `state_validation_failed` | failed | pair sides … | identity_calls / transport | —（原本就是 failed 路径） |
| 两侧不符后 getPair 闸门预算耗尽 | `state_validation_failed` | failed | pair sides … | budget | `budget_exhausted` |
| 恢复复读代码已变后读余额 `RpcFailure budget`（审核反例 2） | `state_validation_failed` | failed | code persisted | budget | `budget_exhausted` |
| 同上，闸门 `BudgetExhausted` | `state_validation_failed` | failed | code persisted | budget | `budget_exhausted` |
| 入场钱包已有代码后读余额预算耗尽（审核反例 3） | `state_validation_failed` | failed | already has code | budget | `budget_exhausted` |
| 出场钱包已有代码后停机 | `state_validation_failed` | failed | already has code | shutdown | `aborted_by_shutdown` |
| 对照：恢复只预算耗尽、无不符 | `budget_exhausted` | unavailable | [] | budget | — |
| 对照：两侧正确、只 getPair 断连 | `data_missing` | unavailable | [] | transport | —（closure 保留已取到的两侧） |

每个故障场景另核：两条注入依次命中、验收 `validation_failed=[1]`、`validation_unavailable=[]`、退出 1、检查点不标完成、
证据完整、证据摘要带着不符、另一个候选 `measured_exit` / passed。

## 二、P1：比较器漏验 `primitives_sha256` / `runtime_params`（`realchain_tools/compare_runs.py`）

**根因**：检查点绑定只核对了手抄的 7 个键；运行证据里也根本没有这两项，没有可对照的对象。
「22 类检查都存在」没有保证每类覆盖了全部必需字段 —— v1.17 规格 §6.0 第 6 条「检查点绑定行一致」的说法因此不完整（v1.18 C12 更正）。

**改法**：
* 检查点绑定直接按测量程序的 `evidence.Checkpoint.BINDING_KEYS` **全部**核对，缺键即失败；
  新增必需参数 `--expect-primitives-sha`、`--expect-runtime-params`（非 JSON 对象退出 2）。
* `pilot_measure` 在运行头后写 **`run_binding`** 记录（检查点绑定的全部键）。`primitives_sha256()`、`runtime_params_of()`
  抽成函数，测量程序与驱动共用；驱动按将传给子进程的同一组参数推导期望值，写进 `driver.json`，续跑不接受改 `--extra`。
* 每次完整运行新增必需检查 **`run_binding_matches`**：有 `run_binding` 就逐键比对；
  没有时**只对 v1.16 / v1.17**（按运行头 `spec_sha256` 判定）走明确的旧版规则 ——
  原语对照结果文件里运行结束时独立计算的 `package_script_sha256`，runtime_params 逐键对照运行头 `params`；
  其它版本缺 `run_binding` 一律失败。报告里逐运行写明用了哪条规则。历史运行头未改写。

**受控测试**（`test_realchain_tools.py`）：第二轮副本上改/删串行检查点原语、改 slot_limit、同时删两键、翻转并行 diagnostics、
期望原语或期望参数不符 —— 全部退出 1；旧版规则下把检查点与期望**改成一致的假值**，仍被运行头 `params` 抓到；
检查点原语与结果文件 `package_script_sha256` 不符被抓到。新格式运行上篡改 `run_binding` 的参数 / 原语 / 删键、
以及把 `run_binding` 改名（v1.18 运行不得退回旧版规则），都点名 `run_binding_matches` 失败。

## 三、P2：启动失败后的续跑无法闭合验收

**根因**：驱动把一侧全部尝试声明为比较链，比较器要求链上每次运行都有完整结果与证据；
启动即断连的尝试天然没有运行头 / 结果文件 / footer，于是整组被拒 —— 尝试历史与结果依赖的证据链被混为一谈。

**改法（比较器 §6.0 第 8 条）**：满足**全部**条件的尝试记为 `startup_abort`，保留为诊断历史，只核对这些条件：
(abort 原因, 退出码) ∈ {(`endpoint_unreachable`, 2), (`budget_exhausted`, 2), (`shutdown_during_startup`, 3)} 且阶段为
`chain_id`/`snapshot`；证据只含该运行、结构无损；无运行头、`run_binding`、候选记录、`checkpoint_state`、Etherscan 记录；
RPC 全在启动阶段且不属于候选；检查点里没有尝试引用它的 `run_id`；不是该侧最后一次运行。
其余一切运行照旧逐项要求完整，最终结果只能回溯到完整运行。驱动无需改动。

**受控测试**：真实 `measure()` 在 `eth_chainId` 注入传输错误 → `serial` 2、`serial_resume1` 0、`parallel` 0，
比较器通过、驱动退出 0，该尝试角色为 `startup_abort`、abort 证据原样保留。六个负对照都退出 1：
伪装的启动失败其实开工过候选；检查点有尝试引用它；abort 原因改成 `chain_id_mismatch`；清单退出码改成 0；
证据文件缺失；整条链只剩那次启动失败。审核的对照也保留：首遍有候选完成并被带出时，
用 `--ignore-tag` 排除首遍仍退出 1（`final_results_traced`）。

## 四、审核的反例脚本（副本输出，未改动其字节）

* `reproduce_remaining.py`：现在**退出 1**，停在 `sides_then_transport` 的断言（不再是 `data_missing`）。
* `reproduce_tools.py`：现在**退出 1**，但原因是新比较器要求两个新参数、脚本用旧参数调用时比较器以 2 退出、没有报告文件 ——
  这只说明命令行变了，**不单独证明修复**。修复的对照证据是本目录 `reverse_tools_v117.*`（用正确参数跑同样场景）。

## 五、本轮我自己的一处越界

分析审核反例时我用 `importlib` 载入了 `audit_v117_20260911/reproduce_remaining.py`，Python 在审核目录的
`__pycache__/` 里生成了 `reproduce_remaining.cpython-38.pyc`（14:59，晚于审核最终 hash 快照 14:53；
审核的 hash 清单不含该目录的 `__pycache__`）。发现后已删除，审核目录恢复到交付状态。
§24 只在每次测试运行内核对前后，捕捉不到测试之外的写入；此后从审核目录载入代码一律加 `PYTHONDONTWRITEBYTECODE=1`。

## 六、规格 v1.18

`MEASUREMENT_SPEC.v1.18.md`（sha256 `19cc63391cc0dbc28f2fbf4fa3ab7ac838c9097f9800891a94d83a348045bf34`），
v1.17 原字节保留（`7cf15793…`）。新增 K7–K10、C12；§3「已证不符 + 后续中断」；§6.0 第 6 条原位更正并补 `run_binding` 与旧版规则、
第 7 条补期望绑定、新增第 8 条；§5 状态行。判据未变。运行证据格式有增补（`run_binding`；结果 `data.interrupted_after_mismatch`）。

## 七、未做 / 仍需注意

* 允许作为惰性历史的启动失败只有三种原因；`chain_id_mismatch`、`pinned_snapshot_mismatch`、`hard_limit_install_failed`
  等前置失败仍会让整组被拒 —— 这些情形应另建比较组，而不是在原组里续跑补齐。
* 旧版绑定规则只覆盖 v1.16 / v1.17；它依赖结果文件里的 `package_script_sha256` 与运行头 `params`，
  强度弱于 v1.18 的 `run_binding` 逐键比对。
* 校验仍在第一处中断处停止，其后步骤记为未做；「已证」只看已落进 `failures` 的结论。
* 新驱动仍只在受控链上运行过，未对真实端点运行。

## 文件

| 文件 | 内容 |
|---|---|
| `test_*.log`、`tests.json` | 10 个入口完整输出与退出码（先写临时目录再复制） |
| `reverse_s27_on_v117.log` | §27 单节在 v1.17 快照上：17 / 33 |
| `reverse_followup_full_on_v117.log` | 整份 followup 在 v1.17 快照上：330 / 33（全在 §27） |
| `s27_isolated.py`、`run_section_isolated.py` | 单独跑 §27 的副本与驱动 |
| `reverse_tools_v117.py/.json/.log` | v1.17 与当前比较器 / 驱动的同场景对照；第二轮目录前后一致 |
| `recheck_realchain2_v118.json` | 当前比较器对第二轮既有证据的只读复核（58/58，旧版规则） |
| `auditor_reproduce_remaining_now.log`、`auditor_reproduce_tools_now.log` | 审核反例脚本在当前代码上的输出（见第四节） |
| `source_hashes.json` | 本轮相关源码、规格、审核快照与冻结原语的完整 sha256 |

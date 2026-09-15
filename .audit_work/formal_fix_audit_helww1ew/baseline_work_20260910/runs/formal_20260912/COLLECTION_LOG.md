# 正式 300 样本采集日志（进行中）

口径决策（2026-09-12）：样本取 308 后排除 8 个开发候选；采集方案 **A**（全量并行一侧测一遍 + 30 个子集串并行对照）。
依据见 `../freeze_plan_20260912/FREEZE_CRITERIA.md`、`BUDGET_300.md`。

## 固定参数（全程不变）

| 项 | 值 |
|---|---|
| 正式样本 | `pilot/formal_20260912/formal_sample_300.json`，sha256 `38d685ed…`（300 个，排除开发 8 个） |
| 快照 pin | `25957718:0x2ff001c72249fe7a64b8fe7e8f9a5963b59585831c328b998f5b93c7c10bf6d1` |
| 代码 / 规格 | `pilot_measure.py 85eb8a60…`、`evidence.py fc6126be…`、`MEASUREMENT_SPEC.v1.19.md 4912eb66…` |
| 批次 | 主采集 15 批 × 20 个；对照子集 30 个分 2 批 × 15 个 |
| 测量参数 | 默认（rps 3、max_calls 4000、max_seconds 3000、slot_limit 32、diagnostics on） |

每批 20 个：预计 2100 次 RPC（上限 4000）、串行约 2532 s、并行两路约 1266 s（上限 3000）。
原按 23 个切分时串行约 2912 s、距上限仅 88 s，端点稍慢即预算耗尽，故改为 20 个（300 整除成 15 批）。

## 进度

用 `python3 update_state.py` 随时重新扫描，机器可读状态在 `collection_state.json`。

| 批 | 样本 | 尝试（标签/退出） | RPC（错误） | 墙钟 | 比较器 |
|---|---|---|---|---|---|
| 对照子集 01 | `subset_pair_01.json`（15） | serial 1 → serial_resume1 0；parallel 1 → parallel_resume1 0 | 2669（3） | 2284.3 s | **51 项全过，退出 0** |

对照子集 01 的两侧最终结果**状态分布完全一致**：`no_mint_by_cutoff` 2、`measured_exit` 11、
`entry_unknown` 1、`execution_reverted_unknown` 1；两侧 `set_complete=true`、`validation_passed=true`、
`economic_results_eligible=false`。

### 对预算模型的第一次实测校准

| 项 | 模型 | 实测（对照子集 01） |
|---|---|---|
| 每完整候选 RPC | 中位 105（102–107） | 中位 **104** |
| 每完整候选墙钟 | 109.2–126.6 s | 中位 **110.2 s**（落在低时延端） |
| RPC 错误率 | 区间 0.249%–0.582% | **3/2669 = 0.112%**（低于区间下界） |
| `no_mint_by_cutoff` 占比 | 开发样本 1/8 = 12.5% | 本批 **2/15 = 13.3%** |

错误率低于模型下界，但只有 3 次错误，**样本太小，不据此收窄区间**；`no_mint` 占比与开发样本接近，
若 300 个中确有约 13% 的廉价候选，总消耗会低于 `BUDGET_300.md` 的上界情景。
本批出现开发样本里从未出现的 `entry_unknown` 状态（买入 stage20 未知），说明正式样本会触发更多状态分支。

## 工具改动（采集期间唯一一处，按 F7 第 1 条）

方案 A 的主采集只测并行一侧，而原驱动全新执行固定跑两侧、比较器也要求两侧。为此：

* `realchain_tools/run_compare.py` 新增 `--sides`（默认 `serial,parallel`，顺序即执行顺序），
  声明的侧记入 `driver.json`；续跑只接受已声明的侧。
* `realchain_tools/compare_runs.py` 新增**单侧模式**：只给一侧时跳过四项对照检查
  （`same_snapshot`、`same_candidate_set`、`results_identical_except_allowed`、`rpc_plus_cache_equal`），
  并以 `snapshot_matches_pin` 取代 —— 单侧同样必须钉在声明的快照上。报告记 `mode`。
  给了 `--parallel ""`（声明空链）与不给这一侧是两种不同情形，前者判不通过。

**为什么这不影响正式采集的一致性**：改动只在这两个工具，二者的 hash 既不进检查点绑定
（绑定只含 `pilot_measure.py`、`evidence.py`、规格、样本、台账、原语、快照），也不在比较器的
`--expect-*` 期望值里。测量实现与规格**字节未动**，因此对照子集 01（改动前跑）与后续批次仍属同一组测量。
`test_realchain_tools.py` 重跑 **83/0**（原 75 项 + 8 项单侧检查，含三个负对照：缺 footer、
`run_binding` 不符、退出码非 0 在单侧模式下仍各自被点名拦住）。

**待补（登记在案，避免规格与实现脱节）**：规格 §6.0 第 6 条列举的必需检查集合尚未写入单侧模式。
按 F7 第 1 条，正式采集进行期间不动规格；应在冻结时或下一版规格中补写。

---

## 2026-09-12 修复四项审核缺口（`audit_formal_20260912/REVIEW.md`）

本轮未请求真实端点，未改测量实现与规格（`85eb8a60…` / `fc6126be…` / `4912eb66…` 字节未动）。
十一个测试入口 **705/0** 全部退出 0（新增 `test_ledger.py` 11 项；`test_realchain_tools.py` 89 项）。

### P1-1 单侧模式漏掉本侧 RPC 计数核验

原 `rpc_plus_cache_equal` 其实做两件事：**本侧**自报 `rpc_calls` 与原始记录数一致、**跨侧**总和相等。
整项被当作对照专用而在单侧跳过，于是"自报 112 次、实际 105 次"能过。
现拆成 `candidate_usage_matches_evidence:<side>`（**两种模式都必需**，同时核 `etherscan_calls` 与
worker 的候选起止区间）与只剩跨侧相等的 `rpc_plus_cache_equal`。

用审核留下的反例副本复核：篡改件**单侧与双侧都退出 1** 并点名新检查；未改动的首批正对照两模式都退出 0。
历史两轮真链重算 58 → **60 项**全过，说明真实数据里自报与记录本就一致、新检查不误报。

### P1-2 预算模型假设错误 + 自动重启放大治理缺口

模型的三处错误与更正见 `../freeze_plan_20260912/ERRATA.md`，新口径见 `BUDGET_300_v2.md`：
错误数 ≠ 续跑进程数（实测比 0.6–0.67）；额外成本是**失败前缀**（中位 43、最大 104）而非整候选；
Etherscan 至少 **360** 次；批次 **15×20**；撤回"硬结论/上界"表述，一律称条件情景。

驱动侧改为按退出原因分流，不再一律重启：退出 1 自动续跑；退出 2 仅 `endpoint_unreachable` 视为瞬时；
**退出 3 不自动重启**（重启会重新获得一份 `max_calls`/`max_seconds`）。每次决定写 `retry_decision`。
新增跨尝试闸门 `--budget-rpc/--budget-etherscan/--budget-wall-s`，按运行目录累计（含中断尝试），
达到上限两侧都不再启动新子运行并记 `budget_stop`。

### P1-3 总账漏掉未收尾子进程已经发生的调用

`spent()` 改为枚举目录下**全部**证据文件（含无 footer、末尾半行、清单里还没有完成条目的），
并区分 `rpc` / `etherscan` / `unmatched_rpc_begin`（只有 begin、结果未知）。驱动也改为**启动子进程前**
先写 `run_start`，中断同样留痕。守卫：造一份 698 条记录且末尾半行的未收尾证据，成本必须计入且不报错。

### P1-4 跨批完成判定没有绑定冻结样本

新增冻结的 `campaign.json`（17 个批次声明：15×20 主批 + 2×15 对照，含 pin、样本 hash、成员、要求的侧、
验收模式、**验收工具 hash**）。总账改为：按 `driver.json` 的样本文件名 + 样本 sha256 + pin **按内容**绑定批次
（改目录名无效）；同一批次的多个目录**累加**成本；完成判定要求该目录最后一次 invocation 的验收报告
`verdict.passed`、`mode` 与声明一致、**报告出自登记的验收工具版本**、且最终结果候选集合恰为声明成员。
比较器报告现在自带 `tool_sha256` 与 `required_checks`。

首批 `formal_sub01` 因此需用当前工具重新验收（`verify_batch.py`）：**53 项通过、退出 0**、`mode=pair`，
报告 `recompare_20260912T083633Z.json`。旧报告出自改动前的比较器，不再作为完成依据。

## 当前真实进度（`collection_state.json`）

| 项 | 值 |
|---|---|
| 对照子集 | 声明 2 批，**完成 1 批**（sub01） |
| 主采集 | 声明 15 批，**完成 0 批**，300 个候选覆盖 0 |
| 已发生成本 | RPC **5,133**、Etherscan **62**、子运行墙钟 **4,588 s**、只有 begin 未知结果 **1** |

**第二批对照 `formal_sub02` 未完成**：串行侧已完成（serial 1 → serial_resume1 0），
**并行侧在上一会话结束时被中断** —— 已有 2,266 行证据、无 footer、清单里没有完成条目。
这 698 次 RPC 与 10 次 Etherscan 现已计入上表（旧总账漏计），该批判定为未完成并列出未收尾尝试。
原始证据原样保留，未删除、未重启。

## 下一步（待审核复核本轮修复后执行）

1. 续跑 `formal_sub02` 的并行侧：`--continue-dir … --resume parallel`，带预算闸门；
   驱动的 `_free_tag` 会分配新标签，不覆盖被中断的 `parallel.*`。
2. 两批对照齐备后，按 `BUDGET_300_v2.md` 第六节的参数逐批跑主采集（`--sides parallel`，单侧验收）。
3. 规格仍待补：§6.0 第 6 条的必需检查集合应写入单侧模式与本侧计数核验；按 F7 采集期间不动规格。

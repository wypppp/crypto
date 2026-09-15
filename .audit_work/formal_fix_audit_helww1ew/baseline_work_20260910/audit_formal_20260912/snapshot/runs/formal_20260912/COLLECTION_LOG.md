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

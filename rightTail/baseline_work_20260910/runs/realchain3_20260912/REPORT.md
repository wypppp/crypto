# 第三轮真链同快照对照（v1.19 新驱动首次真实端点运行）

**结论：新工具链在真实端点上跑通。两侧各 8/8 完成、比较器 58 项必需检查全过、驱动退出 0。**
本轮是 `realchain_tools/` 驱动与比较器第一次对真实端点运行，也是四态校验第一次在**真实传输错误**上被触发。
正式冻结、300 样本、跨期持仓充分性与经济统计资格**继续关闭**；两侧结果的 `economic_results_eligible`、
`measurement_semantics_verified` 仍为 `false`。

## 本次运行

| 项 | 值 |
|---|---|
| 运行目录 | `../v119_20260911T233131Z-546793/`（驱动新建；注意与上一轮交付目录 `../v119_20260911/` 只差后缀） |
| 钉住快照 | `25957369:0xf1589d1a…`（第一、二轮钉的都是 `25950799`，本轮**第一次换快照**） |
| 代码 / 规格 | `pilot_measure.py 85eb8a60…`、`evidence.py fc6126be…`、`MEASUREMENT_SPEC.v1.19.md 4912eb66…` |
| 样本 | `pilot/dev_sample.json`，8 个开发候选（与第二轮同一份） |
| 测量参数 | 与第二轮逐项相同：rps 3、max_calls 4000、max_seconds 3000、slot_limit 32、diagnostics on |
| 凭据 | 只经 `runs/realchain_20260911/launch.py` 以环境变量传入子进程；产物扫描 0 命中 |

尝试序列（清单只追加，日志从不覆盖）：

| 标签 | 并行 | 退出 | 墙钟 |
|---|---:|---:|---:|
| serial | 1 | 1 | 642.9 s |
| serial_resume1 | 1 | 1 | 221.0 s |
| serial_resume2 | 1 | **0** | 112.4 s |
| parallel | 2 | 1 | 370.5 s |
| parallel_resume1 | 2 | **0** | 118.3 s |

驱动按 `--max-resumes 2` 自动续跑，两侧最终都以 0 结束后才调用比较器；`driver_exit=0`。

## 验收（`../v119_20260911T233131Z-546793/compare_67fa5fd3.json`）

**58 项必需检查全过、退出 0。** 五次运行角色均为 `run`，绑定规则均为 **`run_binding`** ——
这是 v1.18 起写入运行证据的完整绑定记录第一次在真链上被使用（第二轮的历史证据只能走旧版规则）。
两侧检查点绑定按全部 `BINDING_KEYS` 核对通过；每条最终结果都回溯到本链检查点与某次运行的 `candidate_result`；
两侧同快照、同候选集、逐字段一致（除耗时/计数/带出标记），每候选「RPC + 缓存命中」两侧相等。

## 四态校验第一次被真实传输错误触发

5 次传输错误全部是 `transport`、全部发生在 `eth_getBlockByNumber`（4 次在 `exit_locate`、1 次在 `restore_check`）。
冻结包 RPC 不重试传输错误，因此每次都让当次运行以 1 结束、由驱动续跑补齐：

| 运行 | 候选 | 状态 | `validation_status` | 记录 |
|---|---:|---|---|---|
| serial（首遍） | 488019、491410 | `data_missing` | `passed` | 校验本身已做完，缺的是测量数据：`data.rpc_failure` + `error_kind=transport` |
| serial_resume1 | 491410 | `data_missing` | **`unavailable`**、`validation_passed=null` | 恢复复读遇传输错误：`restore_check.unavailable[transport]`、`data.restore_unavailable`，验收 `validation_unavailable=[491410]` |
| parallel（首遍） | 480842、491410 | `data_missing` | `passed` | 同第一行 |

第二行正是 v1.17 引入、此前只有受控证据的分类：**校验开始了但没做完 ⇒ `unavailable` / `null`，不是 `true`**，
并且阻断该候选完成、续跑重测而不跳过。续跑后这些候选全部重新测得，最终两侧 8/8 `validation_passed=true`。

## 数字（只报本次观察，不外推）

* 逐条 RPC 执行记录 **5 / 1755 = 0.285%** 报错（第二轮 **8 / 2292 = 0.349%**）。分母只含 RPC 执行记录；
  本轮另有 **21 条 Etherscan 记录**，不并入该分母。两轮都只是各自一次观察，**不能当作 300 样本的失败率预测**。
* 墙钟：串行侧合计 **976.3 s**、并行侧合计 **488.8 s**，并行约为串行的 **50.1%**（两侧都含续跑）。
  仅首遍为 642.9 s vs 370.5 s = 57.6%，但两侧首遍的**完成集合不同**（各有候选因传输错误未完成），
  该比值不能当加速比。第二轮对应数字为 902.2 / 715.0 = 79.3%（含续跑）。本轮与第二轮的墙钟不可直接相比：
  候选集合虽同，但传输错误次数、续跑次数与端点当时状态都不同。

## 跨轮跨快照复现（`cross_round_report.json`，观察项）

第二轮最终串行 vs 本轮最终串行：**8/8 状态一致**；把 v1.17 的结果格式增补
（`status` / `unavailable` / `failures` 等 v1.16 结果里不存在的键）单列后，**8/8 逐字段一致**，没有任何字段取值变化。

这是两轮**第一次钉在不同 finalized 快照**上的比较（第一、二轮同快照）。逐候选测量只读候选自己的历史块，
快照主要约束 cutoff 与新鲜度检查，本次观察与该预期一致。**但这不是保证**：第一轮→第二轮里候选 491473 就因传输错误
在两轮落到不同状态（`state_validation_failed` vs `data_missing`）。跨轮一致性取决于当次传输是否顺利，不是本轮建立的性质。

## 本轮没有建立什么

* 不开放正式冻结、300 样本、跨期持仓充分性（H1）或经济统计资格。
* 0.285% 与 50.1% 都是单次观察，不是预算依据，也不是吞吐结论。
* 惰性启动失败（`startup_abort`）路径本轮**未被触发**（五次运行都越过了启动阶段），仍只有受控证据。
* 硬兜底（RLIMIT）本轮同样未越线，越线后的真链表现仍只有离线证据。

## 文件

| 文件 | 内容 |
|---|---|
| `../v119_20260911T233131Z-546793/` | 原始运行目录：清单、两侧结果与证据、检查点、各运行 stdout/stderr、比较器报告、`driver.json` |
| `cross_round.py`、`cross_round_report.json` | 跨轮跨快照逐字段比较（把 v1.17 格式增补单列） |
| `summarize.py`、`rpc_error_inventory.json` | 只读汇总：错误清点（错误在 `rpc.record.error` 里）、墙钟 |
| `artifact_hashes.json` | 运行目录与本目录全部产物的 sha256（29 项） |

# 校验分类 + 对照验收入口 + 报告数字（规格 v1.17）

来源：`../../audit_v116_20260911/REVIEW.md` 三项 P1。本轮**没有请求任何真实端点**，
全部用既有真链证据与受控测试验收。旧真链记录保留原字节：两轮目录 74 个文件与审核记录的
`delivery_artifact_hashes.json` 逐一比对一致，只**新增**了两份勘误。
正式冻结、300 样本、跨期持仓充分性与经济统计资格继续关闭，`measurement_semantics_verified` 与 `economic_results_eligible` 仍为 `false`。
`rt_a.sqlite` 未动。

| 项 | 结果 |
|---|---|
| 10 个入口 | **572 / 0，全部退出 0**（新增 `test_realchain_tools.py` 46 项；§26 73 项） |
| §26 在审核快照 `5cb58ed8…` 上反向 | 单节 33 通过 / **40 失败**；整份 `test_audit_followup.py` 273 / **40**，40 项全在 §26，§1–§25 行为不变 |
| 审核的分类反例脚本（副本） | 现在退出 1，停在第 2 个场景（入场身份调用不再被写成 `state_validation_failed`） |
| 新旧入口同场景对照 | 旧比较器 `0,1,1,0,0,0` → 新 `0,1,1,1,1,1`；子运行全失败时旧驱动退出 0 且丢历史 → 新驱动退出 1、历史原字节 |
| 新比较器对第二轮既有证据只读复核 | 53 项必需检查全部通过、退出 0（`recheck_realchain2.json`） |
| §24 | 覆盖 562 个交付/审核文件，零改写 / 删除 / 新增 |

---

## 一、校验分类（`pilot_measure.py`）

### 根因（先在审核同字节源码上复现，再改）

| # | 现象 | 根因 |
|---|---|---|
| K1 | 入场取代码断连 ⇒ `data_missing` 却 `validation_passed=true` | 校验函数中途抛出，`rec["state_validation"]` 从未写入；汇总时缺席被当成「不适用 ⇒ 通过」 |
| K2 | 身份调用 / 恢复复读断连 ⇒ `state_validation_failed` | 身份调用的异常被塞进 `failures`；恢复阶段所有 `RpcFailure` 一律改写成状态校验失败 |
| K3 | 出场取代码断连后报 4 条凭空的 `persisted` | 出场快照块在校验**之前**已写进 `rec["blocks"]`，恢复检查照样复读它；原值缺失时 `before.get(key,{})` 得到空，再拿真实 `0x`/`0x0` 与 `None` 比 |
| K4 | 真实不符与随后的接口故障并存时，不符被丢 | 代码与余额取完两项才比较；代码已显示「有代码」、取余额断连 ⇒ 整项只剩 unavailable。**这条是 §26 的并存对照抓到的，审核未列** |
| K5 | 恢复阶段预算耗尽让 worker 崩溃；预算/解码/停机被写成状态不符 | 恢复块只接 `RpcFailure/StopIteration/KeyError` 且一律写 `state_validation_failed`；`BudgetExhausted` 不是 `RpcFailure`，直接冲出 worker |

### 改法（不是只换最终状态字符串）

* **四态**：`fold_validation()` 把每项校验折成 `failed / unavailable / passed`；未开始的不产生记录，汇总为 `not_applicable`。
  `validation_passed` 对应 `false / null / true`（not_applicable 也是 `true`）。
* **开始前占位**：`validation_placeholder()` 在调用校验函数之前写入「未完成」—— 函数中途抛出也不会留下「缺席 ⇒ 通过」。
* **接口故障判定** `interface_failure()`：`kind ∈ {transport, http, protocol, response_limit, missing_result}`，
  或 `kind=rpc` 且消息不含 `revert`。回滚是链的答案（证据）；`budget / forbidden_method / abi` 交上层按各自原因记。
* **校验内**：接口故障 ⇒ `unavailable`（写明 `step` 与 `error_kind`），已取到的部分证据保留；每取到一项**当场判定**（K4）。
* **阻断**：`failed` ⇒ `state_validation_failed`；`unavailable` ⇒ `data_missing` + `data.validation_unavailable{stage, items}`。
* **恢复核验**只复读**实际注入过**的块（`injected_at`，在 `probe_call` 之前登记）；代码/余额逐项比较，缺原值记 `baseline_missing`、不比较；
  复读断连记 unavailable；预算 ⇒ `budget_exhausted`、解码 ⇒ `decode_error`、停机 ⇒ `aborted_by_shutdown`，都不再改写成状态不符（K5）。
  已有更具体原因的状态不被 `data_missing` 覆盖。
* **验收**：新增 `validation_unavailable`；`acceptance.validation_passed` 要求 failed 与 unavailable 都为空。
  检查点「完成」仍要求 `validation_passed is True`，所以 unavailable 的候选**续跑时重测**。
* 已发生的买入 / 卖出阶段与成本照常保留（v1.5 起的收尾逻辑不变）。

### 受控验收（`test_audit_followup.py` §26，完整 measure 流程，受控链）

| 场景 | state | validation | 退出 | 检查点完成 | 证据完整 | 成本 | 其它 |
|---|---|---|---:|---|---|---|---|
| 入场取代码断连 | `data_missing` | unavailable / null | 1 | 否 | 是 | 无（未买入） | 不做恢复核验；证据里校验记录 status=unavailable、无 failures |
| 入场身份调用断连 | `data_missing` | unavailable / null | 1 | 否 | 是 | 无 | 同上 |
| 出场取代码断连 | `data_missing` | unavailable / null | 1 | 否 | 是 | 买入 stage0、swap=1，回款未知 | 恢复只复读入场块，有原值 ⇒ passed，`persisted=[]` |
| 出场身份调用断连 | `data_missing` | unavailable / null | 1 | 否 | 是 | 同上 | 同上 |
| 恢复复读断连 | `data_missing` | unavailable / null | 1 | 否 | 是 | 完整（含回款） | `data.restore_unavailable` 写明缺哪一步 |
| **对照**：真实身份不符（`bad_sides`） | `state_validation_failed` | failed / false | 1 | 否 | 是 | — | failures 非空、无 unavailable；验收列入 `validation_failed` |
| **对照**：注入后钱包出现代码 | `state_validation_failed` | failed / false | 1 | 否 | 是 | 完整 | `persisted` 非空 |
| **对照**：不符 + 随后断连（恢复） | `state_validation_failed` | failed / false | — | — | — | — | persisted 与 unavailable **都保留** |
| **对照**：钱包已有代码 + 随后断连（入场） | `state_validation_failed` | failed | — | — | — | — | failures 与 unavailable 都保留 |
| **对照**：no_mint | `no_mint_by_cutoff` | not_applicable / true | **0** | **是** | 是 | — | 不产生校验记录 |
| 校验中预算耗尽（`kind=budget`） | `budget_exhausted` | unavailable | — | — | — | 买入保留 | 不再是 `data_missing` |
| 校验中停机 | `aborted_by_shutdown` | unavailable / null | — | — | — | — | |
| 恢复复读拿到畸形区块 | `decode_error` | unavailable / null | — | — | — | — | 不再是 `state_validation_failed` |
| 续跑 | — | — | 0 | — | — | — | 未完成的候选 1 **重测**、不跳过；候选 2 从检查点带出 |
| 单元 | — | — | — | — | — | — | 缺原值 ⇒ 4 条 `baseline_missing`、0 条 persisted；只有代码原值 ⇒ 代码照比、余额只记缺；接口故障判定规则 |

每个故障场景都断言注入**确实命中**、另一个候选不受影响（`measured_exit`、passed）。

**改动了一条旧断言**：`test_audit_fixes.py` §2「缺失候选被列出」。它依赖的是 K5 的副作用 ——
旧版预算耗尽让 worker 崩溃，候选没有结果才落进 `missing_candidates`。现在候选有结果、状态 `budget_exhausted`。
本意（阻断）不变，改为更严的判定：两个候选都列为未完成、状态都是 `budget_exhausted`、没有 worker 崩溃。改动处有注释说明。

## 二、验收入口（`realchain_tools/`，新增；旧脚本原字节保留）

**比较器 `compare_runs.py`**：退出 0 当且仅当 `REQUIRED` 里的 22 类必需检查**都存在且都为 True**；
检查求值异常记失败、不中途崩溃；空集合与缺席的必需项都判失败；只读输入，报告路径已存在即退出 2。
条件对应审核所列：最终运行记录存在 / 唯一 / 无来历不明条目、两侧检查点独立；最终运行退出 0；
每次运行证据 complete、恰一个 footer、无 abort、只含本运行、footer 的验收与结果文件一致、并行路数相符；
脚本/证据模块/规格/样本/台账/快照/参数全部一致且等于显式期望值，检查点绑定一致；样本自洽；
最终结果一候选一条且与样本逐项一致、验收清单全空、每条 `validation_passed` 恰为 true、经济资格仍 false；
每条最终结果回溯到本链检查点与本链某次运行的 `candidate_result`（hash / run_id / 绑定 / 带出标记与来源）；
两侧同快照、同候选集、逐字段一致、每候选「RPC + 缓存命中」相等。

**驱动 `run_compare.py`**：每次全新执行新建 `runs/<name>_<attempt_id>/`（已存在即拒绝）；
续跑必须显式 `--continue-dir … --resume serial|parallel`，沿用该目录清单里的检查点、换新标签、
清单只追加并逐行 fsync、所有输出以 `x` 模式独占创建；两侧**最后一次运行**都退出 0
（给 `--compare` 时比较器也退出 0）才返回 0。期望 hash 取自创建目录时写下的 `driver.json`。不读凭据。

**受控测试 `test_realchain_tools.py`（46 项）**：A 节在第二轮既有证据的副本上正对照 + 20 种破坏
（含审核的 5 个反例：后 3 个旧比较器都放行）；B 节用 `fake_launch.py`（不读 .env、不联网，
可跑真的 `pilot_measure` CLI 于受控链，也可按标签返回指定退出码）驱动：子运行全返回 2 ⇒ 驱动 1；
1 / 3 同样 1；再次执行新建目录、旧目录原字节；续跑只追加、跳过已有同名文件的标签、沿用本目录检查点；
用法错误 2；受控链两侧完成 + 比较器通过 ⇒ 0；一侧首跑断连、自动续跑一次补齐 ⇒ 0（首跑候选记 unavailable、续跑重测）；
不给续跑额度 ⇒ 1 且不跑比较器；子运行都报 0 但没有证据 ⇒ 比较器 1、驱动 1；产物里无 .env 凭据值。
C 节：`runs/realchain2_20260911` 整个目录前后一致。

**限制**：新驱动只在受控链上跑过，本轮没有对真实端点运行。比较器要求一侧整条链在同一目录内（按文件名定位）；
`rpc_plus_cache_equal` 是严格条件，若以后缓存路径不再确定需要重新论证。

## 三、报告数字与退出码更正

勘误写在 `../realchain2_20260911/ERRATA_20260911.md`（首轮目录另有指向它的短勘误），REPORT 原字节不动。
数字由 `recount_numbers.py` 从两轮逐条证据重新计数（`recount_numbers.json`），与审核一致：

* 全部逐条 RPC 执行证据 **8 / 2292 ≈ 0.349%**（6/2290 只是六次完整运行）；
* 24% 只保留为**独立同分布假设下的预算压力情景**，撤回「300 样本约 70 个失败」；直接事实是第二轮首遍串行 1/8、并行 2/8 未完成，续跑又失败 1 次，首轮 4 次 TLS 错误集中在约 7 秒内；
* 首遍墙钟比 56.8%（完成集合不同）；计入补齐续跑 **902.2 s vs 715.0 s，约 79.3%**；
* 首轮崩溃的真实退出码是 **1**，不是「不在 0/1/2/3 之内」（规格 v1.17 C11 原位更正，§7.5 补说明）；
* REPORT 的复跑命令会清空清单、覆盖日志、全失败仍退出 0 —— 标为**不要执行**，给出新入口的替代命令。

另查到**真链上确有 K1 的实例**：第二轮 `serial.json` 491473 入场校验取代码断连，记 `data_missing` 却 `validation_passed=true`。
它和首轮 491473（K2）都是被续跑取代的首遍尝试，不在 16 条最终结果里；最终结果的全部校验都完整通过，v1.17 不改变它们。

## 四、规格 v1.17

`MEASUREMENT_SPEC.v1.17.md`（sha256 `7cf15793c7626ce725c133ce748920998083bb46b32ef6913f17604a1ada3542`）。
v1.16 原字节保留（`2a6c5dcf…` 未变）。§3 判据本身未变 —— 「接口失败不得冒充链上失败」自 v1.1 起就在 §3，是实现没做到；
本版新增 §3「校验的四态」、编排层逐项原因、§5 状态行、§6.0 第 6/7 条（验收入口）、§7.5 退出码 1 说明、C11 更正。
**结果文件格式有增补**（`validation_status`、`validation_passed` 可为 null、`validation_unavailable`），默认规格指向 v1.17。

## 五、未做 / 仍需注意

* 校验在第一处接口故障处停止，其后步骤记为未做（未知），不推断、不继续取证。
* 故障不在校验内时（如 `exit_locate` 断连），`validation_status` 只汇总**已做**的校验，可能为 passed；候选仍是 `data_missing`、未完成。
* 端点故障率与归因仍无结论；300 样本的分档预算与超预算规则留到正式规模设计时定。
* 正式冻结、300 样本、跨期持仓充分性、经济统计资格继续关闭。

## 文件

| 文件 | 内容 |
|---|---|
| `test_*.log`、`tests.json` | 10 个入口的完整输出与退出码（先写临时目录、跑完才复制进来） |
| `reverse_s26_on_audited.log` | §26 单节在审核快照上：33 / 40 |
| `reverse_followup_full_on_audited.log` | 整份 `test_audit_followup.py` 在审核快照上：273 / 40（全在 §26） |
| `s26_isolated.py`、`run26_isolated.py` | 单独跑 §26 的原样副本与驱动（反向验证用） |
| `auditor_reproduce_classification_now.log` | 审核分类反例脚本（副本）在修复后代码上的输出：退出 1 |
| `reverse_entrypoints.py/.json/.log` | 新旧比较器与驱动的同场景对照；交付目录前后一致 |
| `recheck_realchain2.json` | 新比较器对第二轮既有证据的只读复核（53/53） |
| `recount_numbers.py/.json/.log` | 勘误数字的重新计数 |
| `source_hashes.json` | 本轮相关源码、规格、历史脚本与勘误的完整 sha256 |

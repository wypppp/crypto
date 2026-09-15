# 完整绑定核验下沉为续跑与比较器共用的证据守卫（规格 v1.19）

来源：`../../audit_v118_20260911/REVIEW.md` 一项 P1。本轮**没有请求任何真实端点**，只用受控测试与既有证据验收。
正式冻结、300 样本、跨期持仓充分性与经济统计资格继续关闭，`measurement_semantics_verified` / `economic_results_eligible` 仍为 `false`。
`rt_a.sqlite` 未动。

| 项 | 结果 |
|---|---|
| 10 个入口 | **680 / 0，全部退出 0**（audit_followup 392，含新增 §28 29 项；realchain_tools 75，含新增 B14 3 项） |
| §28 在 v1.18 审核快照上反向（pilot_measure `2832734d…`、evidence `1fe5c43c…`、比较器 `dd4cfadd…`） | 单节 8 通过 / **18 失败**；整份 `test_audit_followup.py` 371 / **18**，18 项全在 §28 |
| 当前比较器对第二轮既有证据只读复核 | 58 项全过、退出 0；v1.16 真链运行经共用守卫的旧版分支通过 |
| 历史文件 | 审核记录的 74 个历史文件 hash 逐一一致；本轮未在任何历史 / 审核目录写入 |
| §24 | 覆盖 1204 个交付/审核文件，零改写 / 删除 / 新增 |

## 根因

完整绑定规则（`Checkpoint.BINDING_KEYS` 全部键、`run_binding`、旧版规则）上一轮只写在比较器的私有函数里。
续跑复用证据时调用的是 `evidence.verify_evidence_supports()`，它只核对运行头的 7 个字段和 `candidate_result` ——
两个入口对同一份证据用的是两套规则，于是给出相反结论。

## 改法

* **规则只保留一份**：新增 `evidence.verify_run_binding(recs, run_id, binding, result_doc=, result_file=)`，
  返回 (问题清单, 采用的规则)。`verify_evidence_supports()` 在给了检查点绑定时调用它 —— 续跑（`binding=prior`）自动执行；
  比较器的 `run_binding_matches` 与结果回溯（`final_results_traced`）也都改为调用它，删掉了比较器里的私有副本。
* **旧版规则收紧为精确对**：只有运行头 (脚本 sha256, 规格 sha256) 恰为 v1.16 真链那一对（`5cb58ed8…`, `2a6c5dcf…`）
  或 v1.17 那一对（`d9dfb8f0…`, `7cf15793…`）时开放；此前按规格单独判定，v1.18 起的脚本被指向旧规格文件时会被错放进去。
  旧版规则要结果文件（原语对照 `package_script_sha256`），拿不到即问题。§28 另核对这两对常量**等于真实文件的 hash**。
* **续跑处置写明**（沿用 v1.6 起的做法）：结果与尝试历史照常保留、候选以带出结果出现在交付里、验收不通过（退出 1）、
  **不在本检查点内重测**；`acceptance.evidence_chain_action` 写明 `carried_but_blocked … start a new checkpoint to re-measure`，
  无问题时为 `none`。续跑把检查点尝试里记的 `result_file` 交给守卫，供旧版分支使用。

## 受控验收（§28，真实 `measure()` 完整流程）

与审核相同的做法：受控链测两个候选 → 只改原运行证据里的 `run_binding`（seq 不变，证据结构仍完整）→ 同一检查点续跑 →
再独立测一侧并行，把同一份交付交给比较器 CLI。

| 原运行证据的变化 | 续跑退出（v1.18 → 现在） | 续跑的证据链问题 | 处置 | 比较器退出 | 两处原因 |
|---|---|---|---|---:|---|
| 无改动正对照 | 0 → **0**，跳过 [1,2] | [] | `none` | 0 | — |
| `runtime_params.slot_limit` 2→999 | 0 → **1** | 候选 1、2：`evidence_run_binding_mismatch` | 带出但阻断 | 1 | 相同 |
| `primitives_sha256` 改成全 0 | 0 → **1** | 候选 1、2：`evidence_run_binding_mismatch` | 带出但阻断 | 1 | 相同 |
| `run_binding` 缺席（kind 改名） | 0 → **1** | 候选 1、2：`evidence_run_binding_missing` | 带出但阻断 | 1 | 相同 |

另核：验收 `validation_passed=false`；两条带出结果照常交付；检查点原有记录一行不少；比较器点名 `run_binding_matches:first`
与 `final_results_traced:serial`；比较器报出的绑定问题原因与续跑的逐项相同。
旧版分支单元：真链 v1.16 证据（只读原件）通过；拿不到结果文件 ⇒ `legacy_rule_needs_result_document`；
(脚本, 规格) 不是登记的一对 ⇒ `evidence_run_binding_missing`；检查点 runtime_params 与运行头 params 不符被抓到。

驱动路径（`test_realchain_tools.py` B14）：完成的受控目录里改串行原证据的 `run_binding`，`--continue-dir --resume serial` ⇒
续跑退出 1、驱动退出 1、比较器不运行、续跑交付点名 `evidence_run_binding_mismatch`；同一条链直接交给比较器同样退出 1。

## 审核探针（副本在新临时目录运行，未改其字节）

`probe.py` 现在退出 1，但**不是**停在它断言缺口存在的那一行：它直接调用比较器私有函数 `_run_binding_ok` 的旧五参数签名，
而本轮把规则移进 `evidence.py` 后该私有函数只剩四个参数，于是 `TypeError`。这只说明私有接口变了，**不单独证明修复**；
修复的证据是 §28 及其在 v1.18 快照上的反向。输出见 `auditor_probe_now.log`。

## 规格 v1.19

`MEASUREMENT_SPEC.v1.19.md`（sha256 `4912eb662141fb26686d23828d1b35a93b869a393e1f76e9348832df8e98b15f`），
v1.18 原字节保留（`19cc6339…`）。新增 K11–K13、C13（§6.0 第 6 条原位更正旧版规则的判定依据），§5 状态行。判据未变。
`evidence.py` 自 v1.14 以来首次改动（`1fe5c43c…` → `fc6126be…`），只动证据核验，停机与连接实现未动；
因此新运行的 `evidence_module_sha256` 绑定随之改变，旧检查点按设计拒绝复用。

## 未做 / 仍需注意

* 证据链有问题的候选不在原检查点内重测，需要操作者另起新检查点 —— 这是有意的保守处置，不是自动恢复。
* 旧版规则仍弱于 `run_binding` 逐键比对，只覆盖两对精确版本。
* 新驱动仍只在受控链上运行过，未对真实端点运行。

## 文件

| 文件 | 内容 |
|---|---|
| `test_*.log`、`tests.json` | 10 个入口完整输出与退出码（先写临时目录再复制） |
| `reverse_s28_on_v118.log` | §28 单节在 v1.18 快照上：8 / 18 |
| `reverse_followup_full_on_v118.log` | 整份 followup 在 v1.18 快照上：371 / 18（全在 §28） |
| `s28_isolated.py`、`run_section_isolated.py` | 单独跑 §28 的副本与驱动 |
| `recheck_realchain2_v119.json` | 当前比较器对第二轮既有证据的只读复核（58/58） |
| `auditor_probe_now.log` | 审核 `probe.py` 副本在当前代码上的输出（见上） |
| `source_hashes.json` | 本轮相关源码、规格、v1.18 审核快照与冻结原语的完整 sha256 |

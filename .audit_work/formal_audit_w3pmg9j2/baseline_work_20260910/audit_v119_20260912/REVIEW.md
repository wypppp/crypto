# v1.19 独立审核：共享绑定核验闭合

**本轮 P1 可以关闭。独立顺序复跑十个入口 680/0、全部退出 0；完整续跑和比较器对同一份绑定异常证据均拒绝，无修改正对照均通过。本次审查范围内没有发现新的阻断项。**

本轮只用受控链及既有证据，没有请求真实端点，未修改被审核实现、已发布规格、冻结包、原始真链记录或 `rt_a.sqlite`。只新增本审核目录并追加交接/索引。这个关闭结论不开放正式冻结、300 样本、跨期持仓充分性或经济资格。

## 独立端到端验证

使用上轮相同的故障注入方式，先在当前版本测量两个候选，再只改原运行证据中的 `run_binding`，保持检查点、运行头、候选结果与结果 hash 不动。随后调用真实 `measure()` 续跑，再将同一份交付交给真实比较器 CLI。

| 原运行证据变化 | 续跑退出 | 比较器退出 | 共同问题原因 |
|---|---:|---:|---|
| 无修改 | 0 | 0 | 无；比较器 44 项通过 |
| slot_limit：2 → 999 | **1** | **1** | evidence_run_binding_mismatch |
| 原语 hash 改成全零 | **1** | **1** | evidence_run_binding_mismatch |
| 记录 kind 改名，使 run_binding 缺席，seq 仍连续 | **1** | **1** | evidence_run_binding_missing |

三种异常的证据结构仍完整；拒绝来自绑定核验，不是 JSON 损坏、参数缺失或调用旧私有函数造成的异常。续跑逐候选的问题对象与比较器 `final_results_traced:serial` 的问题对象**逐项完全相同**，包括原因、差异、候选及原运行归属。

同时独立断言了拒绝后的交付策略：

- 两条原结果保留，去掉带出标记后与首次交付逐字段相同；经济和测量语义资格仍为 false。
- 检查点仍保留原来的两次候选尝试，来源 run_id 不变；续跑没有任何 candidate_start，不重新测量。
- `evidence_chain_problems` 非空，`evidence_chain_action` 明确说明另建检查点；退出 1。正常对照该字段为 none、退出 0。

因此，“仍然跳过原候选”是本版明确的**保留但阻断验收**策略，不再是上轮“跳过且声称证据链无问题”的误放行。

证据：`probes/resume_observations.json`、`probes/full_resume_compare.json`、`preservation_verification.json`，以及每个 `probes/resume_*/` 下的原始结果、证据、检查点、比较器报告和命令。

## 共享规则与旧版边界

源码核对确认：完整规则只有 `evidence.py:1459` 的 `verify_run_binding`；续跑经 `verify_evidence_supports` 调用，比较器的运行绑定检查和结果追溯也进入同一规则。比较器保留了委托用的薄包装函数，没有保留另一份完整规则实现。

`evidence.py` 与 v1.18 的全部差异落在证据核验区域；HTTP、限流和停机治理区域没有变化。源码快照、三个实现文件的差异及变更区域已归档。

旧版规则独立验证：

- 两对兼容常量均与真实 v1.16/v1.17 审核源码快照、规格文件的完整 hash 相同。
- 真实 v1.16 证据通过共享旧版规则。
- 当前脚本配旧规格、旧脚本/旧规格交叉配对，均拒绝缺失 run_binding 的证据。
- 旧版规则缺结果文档或文档原语 hash 不符，均明确拒绝。

第二轮既有真实证据用完整新 CLI 只读复核，**58 项通过、退出 0**；独立副本中删改检查点原语/runtime_params 的三种负对照仍全部退出 1。启动失败后续跑补齐的受控驱动对照也保持 `[2,0,0]`、驱动退出 0。上轮三条“已证不符 + 后续中断”独立对照未回退。

证据：`legacy_verification.json`、`probes/compare_observations.json`、`probes/driver_observation.json`、`probes/closed_classification.json`。

## 实际执行与完整性

工作目录为 `/home/ancillary/rightTail/baseline_work_20260910`。以下十个命令在本轮重新完整、顺序执行一次，逐入口日志与退出码已落盘：

| 命令 | 通过/失败 | 退出 |
|---|---:|---:|
| python3 test_evidence.py | 29/0 | 0 |
| python3 test_first_mint.py | 17/0 | 0 |
| python3 test_step3.py | 27/0 | 0 |
| python3 test_step4.py | 18/0 | 0 |
| python3 test_e2e_blocking.py | 41/0 | 0 |
| python3 test_resume.py | 23/0 | 0 |
| python3 test_parallel.py | 23/0 | 0 |
| python3 test_audit_fixes.py | 35/0 | 0 |
| python3 test_audit_followup.py | 392/0 | 0 |
| python3 test_realchain_tools.py | 75/0 | 0 |

见 `run_suite.py`、`tests.json` 和十份 `test_*.log`。前一次会话的进程句柄及 `/tmp/rta-audit-v119-q47r0aek` 不再可用，不能证明那轮完整结束，因此没有拼接其部分结果。本轮改在工作区 `.audit_work/v119_20260912_sbae1js7/` 保存中间产物，全部测试结束后才复制到本审核目录，避免干扰 §24。

另外执行以下独立验证，均退出 0：

```
PYTHONDONTWRITEBYTECODE=1 python3 /home/ancillary/.audit_work/v119_20260912_sbae1js7/verify_fix.py
PYTHONDONTWRITEBYTECODE=1 python3 /home/ancillary/.audit_work/v119_20260912_sbae1js7/verify_fix_compare.py
PYTHONDONTWRITEBYTECODE=1 python3 /home/ancillary/.audit_work/v119_20260912_sbae1js7/verify_legacy.py
python3 /home/ancillary/.audit_work/v119_20260912_sbae1js7/verify_preservation.py
python3 ../baseline_20260909/verify_package.py
```

前两份脚本从上轮审核探针复制，改为调用共享 API，并断言**修复后**的退出码和问题清单；比较器的运行清单记入实际续跑退出码 1。修改差异保存在 `verify_fix.diff`、`verify_fix_compare.diff`。没有用旧签名的 TypeError 或缺 CLI 参数作为修复依据。旧审核代码通过读取/compile/exec 载入，禁止生成字节码缓存。

脚本与对应日志、`verification_exits.json`、`verify_package.log` 已归档。归档的受控记录保留原执行路径；复跑应将验证脚本放在新的工作目录，先运行 verify_fix，再运行 verify_fix_compare，不覆盖现存 probes。

交付清单 **19 项完整 hash 一致**，历史清单 **74 项全部保持**；测试前后源码/规格/工具 hash 相同。冻结 v3 包为 **PACKAGE VERIFIED: 11 files**。本次 v1.19 规格完整 hash：

```
4912eb662141fb26686d23828d1b35a93b869a393e1f76e9348832df8e98b15f
```

v1.18 规格仍为 `19cc63391cc0dbc28f2fbf4fa3ab7ac838c9097f9800891a94d83a348045bf34`。详见 `delivery_hash_verification.json` 和 `hashes_start/end/final.json`。

## 关闭与保留项

关闭 v1.18 审核中“measure 续跑与比较器完整绑定核验不一致”的 P1，本次范围内无需继续修补该问题。

以下边界保留，不当作本轮已完成：有问题的检查点需人工另建；旧版证据走较弱但明确限制的兼容规则；新驱动尚未对真实端点运行；故障归因、正式规模预算及跨期持仓语义未由本轮验证建立。正式冻结、300 样本和经济资格继续关闭。本轮无须新增真实取数。

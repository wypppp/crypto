# v1.18 独立审核

**上轮三处具体反例已经修复；十个入口独立复跑 648/0、全部退出 0。但完整绑定核验只接入了比较器，没有接入 `measure` 的续跑证据守卫，仍有一处 P1。正式冻结、300 样本和经济资格继续关闭。**

本轮没有请求真实端点。只读取已有证据、执行受控测试，未修改被审核实现、发布规格、旧运行记录、冻结包或 `rt_a.sqlite`。新增本审核目录，另追加 HANDOFF 与 INDEX。

## 已独立关闭的具体项

1. **已证不符 + 后续中断。** 原审核的同一故障注入：pair 两侧不符后 getPair 断连、恢复代码不符后预算耗尽、入场代码不符后预算耗尽，现均 `state_validation_failed / failed / false`、退出 1；已有不符保留，无故障对照退出 0。§27 的预算和停机变体亦在全量测试中通过。没有仅凭旧反例脚本退出 1 判断修复：本轮复用了故障注入函数，改为明确断言正确行为。
2. **比较器的检查点全量绑定。** 用正确的新 CLI 参数复核第二轮原始证据，**58 项通过、退出 0**。独立副本中仅改原语 hash、改 slot_limit、删除这两个检查点绑定键，现均退出 1，点名 `checkpoint_binding:serial` / `run_binding_matches`。不是靠缺 CLI 参数导致的退出 2。
3. **启动失败后补齐。** 真驱动 + 真 measure、FakeRpc/Fake Etherscan：`serial=2`（启动断连）、`serial_resume1=0`、`parallel=0`，比较器和驱动均退出 0；启动 abort 原样保留。六种伪装启动失败的负对照及已有结果被继承时不得排除首遍的守卫在全量入口中通过。这里只确认规定的三种启动原因，不扩大到 chain_id_mismatch 等。

证据：`probes/closed_classification.json`、`compare_observations.json`、`driver_observation.json` 及各目录的原始结果、证据、命令、日志。

## P1：同一份矛盾证据，续跑接受而比较器拒绝

位置：`pilot_measure.py:1047` 调用 `EV.verify_evidence_supports()`；`evidence.py:1447–1537` 仍只校验运行头的七个字段与 candidate_result，**没有读取 `run_binding`**。新完整核验位于 `realchain_tools/compare_runs.py` 的 `_run_binding_ok()`。

独立完整流程：

1. 用当前 v1.18 在受控链测量两个候选，退出 0，生成完整检查点和证据。
2. 只改这份原运行证据中的 `run_binding`；检查点绑定、run_header、candidate_result、结果 hash 及测量参数均不动。证据结构仍完整。
3. 调用真实 `measure()` 复用同一检查点。
4. 再独立运行一侧并行测量，把同一份续跑交付提交给真实比较器 CLI。

| 原运行证据的变化 | measure 续跑退出 | 跳过候选 | evidence_chain_problems | 比较器退出 |
|---|---:|---|---|---:|
| 无变化正对照 | 0 | [1,2] | [] | 0，44 项全过 |
| `run_binding.runtime_params.slot_limit`：2 → 999 | **0** | **[1,2]** | **[]** | **1** |
| `run_binding.primitives_sha256` 改成 64 个 0 | **0** | **[1,2]** | **[]** | **1** |
| 将该记录 kind 改名，使 `run_binding` 缺席，seq 保持连续 | **0** | **[1,2]** | **[]** | **1** |

三条反例中，续跑均 `process_completed=true`、`validation_passed=true`，两个候选从检查点带出；比较器唯一失败项均为 **`run_binding_matches:first`**。这说明新比较器确实有效，也说明底层续跑守卫没有采用同一套规则。

**影响边界：** 不是经济资格误放行；经济及测量语义资格仍为 false。使用新比较器的完整对照链会挡住这些产物。但独立 `measure`/续跑已经给矛盾或缺失绑定的证据发出“证据链无问题”的完成交付，其自动验收口径与比较器不一致。新结果依赖的原语和运行参数没有在复用入口得到完整证明。

建议把完整绑定及明确的旧版兼容规则下沉到共用证据核验，再让续跑和比较器复用。不要只在比较器中另加断言，也不要只改变最终退出码。存在绑定问题时，必须阻断验收、列出具体问题；结果与失败历史照常保留，不得继续报告 `evidence_chain_problems=[]`。是否重新测量或要求新检查点应明确，不可静默跳过后声称证据有效。

验收使用上表三条完整续跑反例和无变化正对照，检查退出码、复用决定、问题清单、累计结果和比较器结论一致性。若增加旧版分支，继续保留精确版本限制；不改写旧运行头。

原始证据：`probes/resume_observations.json`、`probes/full_resume_compare.json`，以及 `probes/resume_*/first.jsonl`、`resume.json`、`shared.ck`、`full_comparator_report.json`。反例修改只发生于新建临时受控数据，不触碰真实交付。

## 验证、版本与执行记录

十个入口在 `/home/ancillary/rightTail/baseline_work_20260910` 顺序作为独立子进程执行：

| 命令 | 通过/失败 | 退出 |
|---|---:|---:|
| `python3 test_evidence.py` | 29/0 | 0 |
| `python3 test_first_mint.py` | 17/0 | 0 |
| `python3 test_step3.py` | 27/0 | 0 |
| `python3 test_step4.py` | 18/0 | 0 |
| `python3 test_e2e_blocking.py` | 41/0 | 0 |
| `python3 test_resume.py` | 23/0 | 0 |
| `python3 test_parallel.py` | 23/0 | 0 |
| `python3 test_audit_fixes.py` | 35/0 | 0 |
| `python3 test_audit_followup.py` | 363/0 | 0 |
| `python3 test_realchain_tools.py` | 72/0 | 0 |

完整输出见十份 `test_*.log`、`tests.json`。测试期间全部输出放在 `/tmp/rta-audit-v118-ysy28ini`，全部结束后才创建本审核目录，未干扰 §24 的目录保护。

额外实际执行：

```
PYTHONDONTWRITEBYTECODE=1 python3 /tmp/rta-audit-v118-ysy28ini/probe.py
# exit 0：原反例正确行为、比较器正负对照、启动恢复通过；同时断言续跑绑定缺口存在。

PYTHONDONTWRITEBYTECODE=1 python3 /tmp/rta-audit-v118-ysy28ini/probe_resume_compare.py
# exit 0：同一份反例续跑交付，比较器正对照 0、三个反例 1；唯一失败为 run_binding_matches:first。
```

日志分别为 `probe.log`、`probe_resume_compare.log`。**探针退出 0 包含“缺口被复现”的断言，不是实现验收通过。** 两份脚本复制到本目录供检查；复跑时将它们复制到一个全新临时目录，依次执行，避免覆盖归档的 `probes/`。脚本内部亦禁止字节码缓存；旧审核函数通过读取/compile/exec 载入，没有在旧审核目录生成 pyc。

交付 `source_hashes.json` 的 **19 项完整 hash 一致**；上轮历史清单 **74 项全部保持**。v1.18 完整 hash：

```
19cc63391cc0dbc28f2fbf4fa3ab7ac838c9097f9800891a94d83a348045bf34
```

v1.17 仍为 `7cf15793c7626ce725c133ce748920998083bb46b32ef6913f17604a1ada3542`。测试前后源码、规格和工具 hash 相同，见 `hashes_start.json` / `hashes_end.json`；历史与交付比对见 `delivery_hash_verification.json`。源码快照与 `pilot_measure_v117_to_v118.diff` 已保存。

本轮没有把新驱动的受控验证说成真实端点验证，也没有重写旧版证据。既有八个开发候选的最终一致性结论保留；故障率归因、正式规模预算和经济语义不在本次关闭范围。下一步只需补齐上述共用守卫并验证两个入口一致，无需为这个修复新增真实采集。

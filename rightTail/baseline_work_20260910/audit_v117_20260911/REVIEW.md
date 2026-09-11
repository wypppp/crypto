# v1.17 独立审核

**独立复跑确认 10 个测试入口 572/0、全部退出 0；普通接口故障的四态分类、原比较器的已知误放行、驱动覆盖历史文件的问题，以及报告数字更正，均有验证。仍有两处 P1 缺口和一处 P2 恢复流程缺口，不能把本轮标成全部关闭。**

本轮只用受控链和已保存的真链证据，没有请求真实端点。未修改测量实现、已发布规格、冻结 v3 包、原始运行记录或 `rt_a.sqlite`。新增本审计目录，另追加 HANDOFF、INDEX 的审核索引。正式冻结、300 样本、持仓充分性与经济统计资格继续关闭。

## 已确认的范围

- 全部入口实际顺序执行一次：evidence **29/0**、first_mint **17/0**、step3 **27/0**、step4 **18/0**、e2e_blocking **41/0**、resume **23/0**、parallel **23/0**、audit_fixes **35/0**、audit_followup **313/0**、realchain_tools **46/0**。总计 **572/0**；详见 `tests.json` 及十份 `test_*.log`。测试期间输出放在独立 `/tmp` 目录，全部结束后才归档，避免干扰 §24 的交付目录保护检查。
- 本次被审源码与交付 `runs/classify_20260911/source_hashes.json` 的 **21 项完整 hash 全部一致**；测试前后源码和规格 hash 相同。v1.17 完整 hash 为 `7cf15793c7626ce725c133ce748920998083bb46b32ef6913f17604a1ada3542`。
- §26 的五种单独接口故障、原值缺失、no_mint、真实不符、已发生成本、完成标记与续跑测试均通过。旧问题的这些具体路径可以关闭；下面第一项是其未覆盖的并存路径。
- 新比较器对第二轮既有证据复核 **53 项通过，退出 0**。原来的缺 footer、最终退出非零、最终运行缺失等守卫通过；修改已纳入检查的 `script_sha256` 也确实会拒绝。本次新驱动的受控候选失败后补齐路径 `[1,0,0]` 通过比较，驱动退出 0。
- 另独立重读既有真链记录，未以新比较器代替底层复核：**16 条最终结果的来源核验、28 次主买卖原始响应解码、8/8 候选的 RPC+缓存计数核对均通过**。本轮还检查了两侧真实检查点的原语 hash 和 runtime_params，原件均正确。八个候选最终结果一致这一既有工程观察不受下述反例影响。
- 勘误数字重新计数：逐条 RPC 执行记录 **8/2292 ≈ 0.349%**；另有 **28 条 Etherscan 记录**，不混入这个 RPC 错误率分母。第二轮补齐到 8/8 的子运行墙钟合计 **902.2 s / 715.0 s，比例 79.25%**；首轮两次启动崩溃确为退出 1。16 条最终结果的校验均完整通过、经济资格均为 false。24% 的说法只保留为附带独立性等假设的情景，不能预测 300 样本失败数。
- 上轮审核清单的 **74 个历史文件 hash 全部保持**。精确范围包括两轮真链目录的 63 项及 closeout 的 11 项，并非全部来自两轮目录。冻结 v3 包独立校验退出 0：`PACKAGE VERIFIED: 11 files`。

以上见 `delivery_verification.json`、`realchain_verification.json`、`source_hashes.json`。底层真链复核脚本从上轮复制到本目录，明确改为核对历史 v1.16 源码快照，并补 runtime_params 对照；差异保存在 `verify_existing_realchain.diff`，没有修改旧脚本或降低断言。

## P1：已取得的不符仍会在后续异常中丢出分类结果

位置：`pilot_measure.py:371–386` 的 `validate_identity_closure`；`:389–459` 的校验累积；`:462–496` 的恢复检查；`:1373–1402` 的异常收尾。

完整 `measure()` 受控运行结果如下。每例均有两个候选，故障只作用于候选 1；所有证据结构完整，失败候选仍退出 1、未获经济资格。

| 场景 | state | validation_status / passed | 已知不符在结果中 |
|---|---|---|---|
| 无故障对照 | measured_exit | passed / true | 不适用，退出 0 |
| pair 两侧不符，无后续异常 | state_validation_failed | failed / false | 保留 |
| 同样两侧不符，接着 getPair 断连 | **data_missing** | **unavailable / null** | **failures=[]，identity_closure 缺席** |
| 恢复复读发现钱包代码变化，无后续异常 | state_validation_failed | failed / false | 保留 |
| 同样代码变化，接着读余额预算耗尽 | **budget_exhausted** | **unavailable / null** | **failures=[]，persisted 未保留** |
| 入场发现虚拟钱包已有代码，接着读余额预算耗尽 | **budget_exhausted** | **unavailable / null** | **failures=[]，只剩未完成占位** |

第一条反例中，token0 已返回错误地址，token1 也已返回，helper 已算出 `fails['error']`，随后 `getPair` 抛异常，helper 没有返回，其局部不符从未并入外层结果。预算场景则让函数局部累积的 failures/bad 随异常丢失，收尾重新写入空 failures。**原始 RPC 证据仍在；丢失的是候选分类和校验摘要里的已知不符，不能描述成原始证据文件丢失。**

影响：本应保留的“已证不符 + 后续未完成”被折成只有未知。当前仍阻断，不是误放行成功，但会改变失败分类及续跑解释，违反 v1.17 §3 的并存要求。现有 §26 只测了钱包代码不符之后的 transport，没有覆盖身份 helper 的后续异常和不符之后的预算中断。

修复应让已取得事实进入持久的候选累积器，异常路径也保留它，再统一折叠四态。预算/停机原因与已经证实的不符分别保留，不用空占位替换部分结果。验收至少覆盖上表三条并存反例及其无异常对照，检查 failures、unavailable、全局验收清单、检查点及退出码。

证据：`mismatch_artifacts/summary.json`、各场景的结果 JSON / JSONL / 检查点；探针 `reproduce_remaining.py`。

## P1：新比较器漏验检查点的原语和运行参数绑定

位置：`realchain_tools/compare_runs.py:275–289`，以及其调用的 `evidence.py:1447` 起 `verify_evidence_supports`。测量程序真正的绑定键在 `evidence.Checkpoint.BINDING_KEYS`，其中包含 `primitives_sha256` 和 `runtime_params`；比较器仅取七个键，缺这两个，后续证据核验也没有补齐。

在第二轮证据的独立副本中，**仅修改串行检查点 binding 行**，其余记录、结果和原始证据不变：

| 修改 | 比较器检查 | 退出 |
|---|---|---:|
| 无修改正对照 | 53 项全过 | 0 |
| `primitives_sha256` 换成 64 个 0 | **53 项全过** | **0** |
| `runtime_params.slot_limit` 从 32 改成 0 | **53 项全过** | **0** |
| 删除上述两个绑定字段 | **53 项全过** | **0** |
| 修改 `script_sha256` 的负对照 | checkpoint_binding、final_results_traced 失败 | 1 |

这不等于原件绑定有错；原件本轮独立核对通过。问题是自动验收会给绑定缺失或相矛盾的交付发出通过结论。“22 类检查存在”不能证明每一类包含了全部必需字段。

应统一必需绑定字段，校验检查点之间、检查点与对应运行证据，以及显式期望的原语版本和测量参数。字段缺失须有明确失败；历史版本缺少某处记录时应采用明确的旧版验证规则或独立依据，不能直接跳过，也不要改写历史运行头。新增删除/修改每个漏验字段的负对照，同时保留真实原件通过的正对照。

证据：`tools_artifacts/{baseline,primitives_changed,runtime_changed,bindings_deleted,known_field_control}/report.json` 及 `binding_before_after.json`；探针 `reproduce_tools.py`。

## P2：启动失败后的自动续跑不能闭合验收

位置：`realchain_tools/run_compare.py:196–241` 将该侧全部尝试加入比较链；`compare_runs.py:159–220` 要求每次声明的运行均有结果文件、完整运行头/footer、无 abort。

用真实驱动和真实 `measure()`，仅以 FakeRpc/Fake Etherscan 替代网络：第一次串行在 `eth_chainId` 注入 transport，走实际启动异常处理、留 `endpoint_unreachable` abort、退出 2。随后自动续跑成功，并行也成功：

```
serial          2   endpoint_unreachable，0 个候选开工
serial_resume1  0   两候选完成
parallel        0   两候选完成
last_exit_per_side = {serial: 0, parallel: 0}
compare_exit = 1
driver_exit = 1
```

失败项仅来自第一次启动的无结果文件、无完整运行头/footer、abort 等。后面再追加成功续跑也不会改变这些历史事实。这是当前规格“每次声明的运行都须完整”和驱动“把全部尝试都声明为结果证据链”的恢复设计冲突；它保守拒绝，不是错误放行。

补做两个有区分力的对照：

- 在同一份启动失败历史上，手动只声明 `serial_resume1` / `parallel` 为比较链，并 `--ignore-tag serial`，**35 项全过、退出 0**，旧 abort 原样保留。没有任何最终候选依赖被排除的启动尝试。
- 对“首遍有一个候选失败、另一个已完成且被续跑带出”的历史做同样排除，比较器因 `final_results_traced:serial` 与 `rpc_plus_cache_equal` **退出 1**。因此不能简单忽略所有失败尝试。

建议显式区分完整尝试历史与最终结果所依赖的证据链。无候选开工、无结果被复用的前置 abort 可以保留为诊断历史，不必成为结果祖先；任何被复用的候选证据仍须完整且归属正确。或者启动失败后明确新建比较组并关联旧尝试，不让驱动宣称原组可继续补齐。实现前不靠删除清单/abort 绕过验收。

证据：`tools_artifacts/startup_failure_recovery/`、`candidate_failure_recovery/` 及 `exclude_initial_controls.json`。全是受控运行，新驱动仍未用真实端点运行。

## 执行与复跑

所有 Python 测试在工作目录 `/home/ancillary/rightTail/baseline_work_20260910` 下作为独立子进程顺序执行，标准输出/错误输出逐入口保存。真实命令为 `python3 test_<入口名>.py`，十个入口及退出码见 `tests.json`；没有把中途测试结果拼成一次全量通过。

本轮另执行：

| 命令 | 退出 | 关键结果 |
|---|---:|---|
| `python3 audit_v117_20260911/reproduce_remaining.py --out-root /tmp/rta-v117-mismatch-audit` | 0 | 正对照及三条“已知不符丢出分类”反例复现 |
| `python3 audit_v117_20260911/reproduce_tools.py --out-root /tmp/rta-v117-tools-audit` | 0 | 绑定漏验三种变化、启动失败恢复冲突复现 |
| `compare_without_initial()` 对上述两份受控历史的补充调用 | 0（外层） | 启动失败排除对照 0；有继承结果的排除负对照 1 |
| `python3 audit_v117_20260911/verify_existing_realchain.py` | 0 | 16 条来源、28 次原始解码、8/8 缓存核对 |
| `python3 audit_v117_20260911/verify_delivery.py` | 0 | 21 项交付 hash、74 项历史 hash、勘误计数通过 |
| `python3 ../baseline_20260909/verify_package.py` | 0 | PACKAGE VERIFIED: 11 files |

**两个 reproduce 探针的退出 0 表示已断言反例存在，不表示被测实现验收通过。** 未来修复后应编写断言正确行为的守卫；不能把这些探针当前的退出 0 当回归通过。

复跑反例时使用新的、尚不存在的 `--out-root`。归档目录 `mismatch_artifacts/` 和 `tools_artifacts/` 保留本轮原始内容；记录内的 `/tmp` 路径保留当时执行位置，未重写记录。工具反例的输入使用指向只读历史文件的链接，只有被改变的检查点解除链接后写入副本。

审核脚本自身有一次语法错误：`reproduce_remaining.py` 首次缺右括号，退出 1，未执行任何候选；修正该脚本后才得到上表的完整结果。没有将此错误归到被测程序，也没有改变反例断言。额外的“排除首遍”正负对照是在主探针完成后独立执行，现已纳入脚本便于一次复跑，原观测另存而未覆盖。

## 下一步

关闭普通接口故障、旧入口的既知反例、历史保护与勘误数字这几个具体项。修复上述两项 P1，给启动前置失败确定可恢复的组/证据链规则并补 P2 守卫，再复跑全量。无需为本轮这些结论新增真实请求；不扩大样本，不改写旧真链证据，也不据此开放经济统计。

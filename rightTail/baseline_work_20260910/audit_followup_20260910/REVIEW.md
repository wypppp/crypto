# 2026-09-10 修复后独立复核

结论：**8 个原测试入口均退出 0，200 项断言成立；工程验收仍未通过。** 本轮仅离线审核，未改被测实现、未请求真实端点、未修改冻结 v3 包、未启动正式样本。测试和反例在临时目录产生候选数据。源码快照与完整 hash 见本目录 `*.audited.py`、`source_hashes.json`。

## 已确认进展

线程异常与初始化失败已纳入主流程失败判定；blk 显式使用传入 RPC；各 tap RPC 计数汇总；pending_id 全局分配；runtime_params 与 primitives hash 绑定；尾部半行隔离；candidate_result 先持久化再标完成；最终 JSON 脱敏；无 Mint 分支和零尝试成本已修。原回归入口的 Namespace.parallel 问题消失。economic_results_eligible / measurement_semantics_verified 仍为 false。

预留两次 HTTP 的额度是有意义的保守上界，不应将预留数当实际调用数；它仍未覆盖下述全局边界。

## 未关闭的阻断与复现

### 1. P0：检查点完成标志仍不保证结果可交付

位置：`evidence.py:220`、`:286`；`pilot_measure.py:524`、`:914`。

完整跑完两个假链候选，删除本次临时目录中的原结果 JSON 和原证据 JSONL，只保留检查点，再续跑：**exit=0、results=[]、skipped=[1,2]、set_complete=true、validation_passed=true**。没有验证旧结果的路径、hash 或完整性，也没有重建累计结果。正常使用同一输出路径续跑亦会用本次 results 覆盖旧汇总。

另外，在检查点 binding 后插入完整的一行 `BROKEN`，仍被静默跳过，续跑 exit=0。尾部隔离修复没有解决中段损坏。

要求：检查点引用可验证的完整结果与证据；缺失/损坏拒绝复用或显式重新测量；累计交付包含每个已完成候选；中段损坏必须阻断。验证中断恢复时同时检查最终交付，不仅检查 skipped。

### 2. P0：共享预算与实际 HTTP 限流仍不闭合

位置：`pilot_measure.py:474`、`:848`；`evidence.py:154`、`:318`。

受控全流程设 parallel=2、max_calls=2，实际 FakeRpc 记录 **3 次调用**，最终虽 exit=1，调用上限已经越过。chainId / finalized 在创建共享 gate 之前执行。串行分支也未使用该共享 gate，Etherscan 因而不受同一总预算约束。

单独使用**原包真实 RPC 类 + 当前 RpcTap/SharedGate**、只 mock urlopen：全局 rps=0.1 应有 10 秒发车间隔；第一个 HTTP 返回 503，底层约 1 秒后重试并成功。两次 HTTP 没有都经过全局限流。两次额度预留解决 gated 范围内的数量上界，不能替代每次 HTTP 的速率/截止控制。

要求：启动、串行、并行、Etherscan、重试使用一致的全运行预算；明确区分实际次数与预留额度。在实际 HTTP 边界验证速率与截止，不靠逻辑请求的门禁推断。

### 3. P1：买入后异常仍遗漏已知成本

位置：`pilot_measure.py:650`、`:693`、`:755` 及统一异常收尾。

注入 find_slot 抛 transport 异常：输出 data_missing、exit=1；entry 保留 stage=0、swap=1、approve=0 和已知 base_fee，**cost 字段仍不存在**。本次修复覆盖了正常返回“槽位不支持”，没有覆盖查询抛异常。不能因为后续数据失败而不生成已知买入腿的成本记录；未知退出腿应独立保留未知。

### 4. P1：完整性检查仍可接受不完整证据

位置：`evidence.py:read_evidence`。

空文件被判 complete=true；仅含 rpc_end 与 run_footer、没有 run_header 也没有对应 begin，同样 complete=true。当前只检查 begins−ends，没有验证相反方向、唯一配对及合法运行结构。不得凭该 complete 字段验收完整证据包。

### 5. P1：样本唯一性没有约束

位置：`pilot_measure.py:914`。

声明两个候选但 index=[1,1]，全流程 exit=0，results 两行均 index=1，set_complete=true。集合差检查不能证明“一候选恰好一条结果”。需验证样本自身的数量、唯一性，以及累计结果与冻结样本逐项一致。

### 6. P1：Mint 元数据规范性只部分修复

位置：`pilot_measure.py:85`。

规范 data/topic 配上 transactionHash='0x'、blockHash='WRONG'、logIndex='garbage'，`_validate_log` 仍返回 None。这是**校验函数级**反例；后续 int(logIndex) 可能抛异常，不将它误报成整个流程成功。transactionHash 的长度/十六进制、logIndex 的非负合法量、日志块身份仍需校验。sender topic 的非十六进制也应返回明确拒收原因，而不是裸 int 抛错。

## 仍需保留的并行验收条件（源码观察，未冒充新真链实测）

- `pilot_measure.py:569,813` 的候选 Etherscan 次数用共享总计差计算；并行重叠会把其他候选的调用算入。应按 candidate/worker 从实际请求记录归集。
- `:540` 的区块缓存仍为共享字典；显式 RPC 参数修复了发请求的归属，但缓存命中没有独立的消费/来源证据。串行/并行证据比较需要定义并验证缓存口径。
- 资源记录在启动、候选开始/结束、关闭采样，并非硬 RSS/CPU 上限或可靠峰值测量。不能把已有采样说成资源上限已验收。
- 独立串行与并行运行需显式固定同一状态快照。新检查点重新取 finalized、共用检查点则跳过候选，均不能直接替代同快照对照入口。
- 汇总仍写 `MEASUREMENT_SPEC.md v1 (draft)`（`:902`），不应与运行头的实际版本混用；规格中的历史“待实现”表述需与状态表统一。

## 执行命令与证据

从 `/home/ancillary/rightTail/baseline_work_20260910`，依次执行 `python3 <入口>.py`，各日志在本目录，汇总 `tests.json`：

| 入口 | 退出码 | 通过/失败 |
|---|---:|---:|
| test_evidence | 0 | 29/0 |
| test_first_mint | 0 | 17/0 |
| test_step3 | 0 | 27/0 |
| test_step4 | 0 | 18/0 |
| test_e2e_blocking | 0 | 41/0 |
| test_resume | 0 | 23/0 |
| test_parallel | 0 | 20/0 |
| test_audit_fixes | 0 | 25/0 |

独立反例命令（均退出 0，表示成功复现当前缺陷，不是通过验收）：

```bash
python3 rightTail/baseline_work_20260910/audit_followup_20260910/reproduce_remaining.py
python3 rightTail/baseline_work_20260910/audit_followup_20260910/reproduce_retry.py
```

输出：`remaining.json`/`.log`（8 条观测）、`retry.json`/`.log`（原 RPC HTTP 重试限流反例）。所有网络均由 mock 替代；反例代码与预期断言完整保留。未运行上一轮断言旧 bug 存在的 reproduce.py，也未改变现有测试断言。

下一步：先关闭恢复交付和共享预算两个 P0，再补成本、证据结构、样本与日志校验；统一复跑入口后复核。不放行真链并行对照或正式 300 样本。工程验收即便通过，也不自动赋予跨期持仓充分性或经济统计资格。

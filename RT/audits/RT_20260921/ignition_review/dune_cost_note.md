# Dune SQL 成本/中止核验

核验日期：2026-09-21。来源仅为 Dune 官方文档；未运行查询、未访问 API key 或 `.env`。

## 明确结论

1. **SQL 内没有查到可限制“实际 credits”的 DuneSQL 语法或查询参数。** Dune 官方说明 credits 按实际 compute 计费，且不公开单次查询的固定公式；文档提到的是全局的 per-execution “global query cost cap”，属于平台/账户控制项，不能据此声称 SQL 内可自我止损。[How Credits Work](https://docs.dune.com/resources/credits-billing/how-credits-work#credit-pricing)；[Execute SQL](https://docs.dune.com/api-reference/executions/endpoint/execute-sql#pricing)

2. **取消不保证零计费，也没有官方退款保证。** Cancel API 只说明按 execution ID 取消并返回成功布尔值；Billing 明确写明：用户取消但已经使用 compute 的 execution，可能仍消耗已使用资源对应的 credits；运行到 Dune 超时也可能计费。因此不能把取消理解为退费或撤销既有扣费。[Cancel Execution](https://docs.dune.com/api-reference/executions/endpoint/cancel-execution)；[Billing](https://docs.dune.com/api-reference/overview/billing#executions)

3. **可预估但不是硬上限。** 官方没有单次查询的统一 cost 公式；可在执行前查看界面中的估算/提示，执行后从 status 的 `execution_cost_credits` 核对实际成本。SQL 执行本身按实际资源使用计费。[How Credits Work](https://docs.dune.com/resources/credits-billing/how-credits-work#credit-pricing)；[Billing](https://docs.dune.com/api-reference/overview/billing#billing)

4. **存在执行超时，但超时不是免费止损。** Small engine 默认约 2 分钟后超时；Medium/Large 有更大资源/超时能力，但官方该页没有给出统一的 Medium/Large 时间上限。Billing 同时说明执行到 Dune timeout 可能按已用资源计费。[Query Executions](https://docs.dune.com/query-engine/query-executions#small-engine)；[Billing](https://docs.dune.com/api-reference/overview/billing#executions)

5. **扫描约束可降低风险，不能证明 credits 上限。** 官方建议按 `block_date`/`block_time` 做分区裁剪，并在跨链表增加 `blockchain` 过滤，以减少扫描量；只选需要的列、对大结果使用 `LIMIT` 也属于效率建议。文档没有把这些 SQL 写法定义为 credits 硬上限或保证取消前不扣费。[Writing Efficient Queries](https://docs.dune.com/query-engine/writing-efficient-queries#leverage-time-based-partitioning)

## 保证与风险降低的区分

| 项目 | 官方文档能支持的结论 | 性质 |
|---|---|---|
| SQL 内 credits 硬上限 | 未见 SQL 语法/参数；文档仅提 global per-execution cost cap | **不能由 SQL 保证** |
| 账户/平台 cost cap | 官方说明存在 per-execution ceiling；达到用户定义 cap 的失败执行可能仍按已用资源计费 | 平台控制；**不是零计费保证** |
| Cancel API | 可请求取消，返回是否成功 | **中止控制；不保证退款/零扣费** |
| 查询超时 | Small 明确 2 分钟；timeout 可能按已用资源计费 | **时间边界；非费用边界** |
| 时间/链过滤、少列、LIMIT | 减少扫描与资源使用的官方优化方法 | **降低风险；非硬上限** |

### 对“取消仍扣 320 credits”的直接判定

官方文档支持“取消时已消耗的 compute 仍可能计入 credits”，所以该现象与官方计费规则一致；官方文档没有承诺取消会自动退回已计 credits，也没有提供 SQL 内按 credits 实时中止的保证。具体一次 execution 的金额应以 status 返回的 `execution_cost_credits` 为准。

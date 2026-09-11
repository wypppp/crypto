# 试跑结论勘误 · 2026-09-10

> 依据 [AUDIT_PILOT_20260910.md](AUDIT_PILOT_20260910.md)。审查的每一条我都独立复现，**全部成立**。
> `pilot/pilot_results.json`（原始试跑记录）**字节不动**；本文件是它与 `PILOT_RESULTS.md`
> 的勘误。带 `[已复现]` 的条目附了复现方式。

## 一、立即撤销的结论

### E1 · `adequate_proven_by_execution` 撤销

**原结论**：`stage==0 且 token_before==amount 且 token_after==0` ⇒ 跨期持仓状态适配充分。

**为什么不成立**：它只证明「在本次注入的状态里，该调用完成且余额归零」，
不证明注入状态等价于真实买入后的退出状态。

反例（源码语义，未声称已在 EVM 部署复现）：代币在买入时设 `unlockAt[buyer]=buyTime+90天`，
卖出要求 `timestamp >= unlockAt[buyer]`。真实持有 30 天应被拒；
而只注入余额、`unlockAt` 保留默认 0 时，卖出会**成功并清零**，完全满足原判据。
反射/重基导致 30 天后应卖数量不同，同样不能被该判据排除。

**改为**：`simulated_completion_under_injection`。

**连带撤销**：`pilot_results.json` 里 5 个 `measured_exit`
**不再支持**「持仓充分」或「M/Z 可判定」。它们只是**注入状态下模拟完成**。
不是只换标签——这些样本的经济统计可用标志一并撤销，
升级需要另有可审查的状态语义依据。

### E2 · 规格 v1 的相应条目失效 —— **已发 v1.1**

H1 判据作废，D1「扫描成本 = 2×limit」也错（见 E5）。
**已于 2026-09-10 发布 [v1.1](MEASUREMENT_SPEC.v1.1.md)**：v1 原始字节保留在
`MEASUREMENT_SPEC.v1.md`（sha256 `04e673214d49…`）不追改；
被取代条目列在 v1.1 §0，各条实现状态列在 v1.1 §5。
本文件涉及的旧运行继续关联 **v1 ＋ 本勘误**。

## 二、我的报告中不成立的陈述

| # | 原陈述 | 实际 | 依据 |
|---|---|---|---|
| **E3** | 「包内自带的一次重试没救回来」 | `RPC.request` **只对 HTTP 429/502/503/504 重试一次**；`URLError/TimeoutError/OSError` 走 `raise RpcFailure(...) from None`，**不重试**。`RemoteDisconnected` 继承 `ConnectionResetError`（属 OSError） | [已复现] 读 `verify_capabilities.py:320-366` |
| **E4** | 8 例「含重试加权 86.9 秒」 | **无法从交付记录复算**。实测逐候选耗时合计 600.33s，**均值 75.04125s** | [已复现] 由 `pilot_results.json` 重算 |
| **E5** | 槽位扫描 34 次 | **35 次**。计数器漏了扫描前的原值读取：1(原值)+32(第一哨兵)+1(第二哨兵)+1(恢复核验) | [已复现] 计数 `find_slot` 中 4 处 `rpc.call` 对 3 处 `calls += 1` |
| **E6** | `identity_probe` 作为试跑证据 | **它不在 `pilot_measure.py` 里**。我在另一个临时脚本中执行，却写进了试跑结果，等于把非本次记录的证据混入 | [已复现] `'identity_probe' not in 源码` |
| **E7** | `no_mint_by_cutoff` 候选 `rpc=0` | 该候选**确实发出了 1 次 Etherscan 请求**。8 次 Etherscan 调用全部未计入 `rpc_calls`，不能称零网络成本 | [已复现] `first_mint` 无条件调用 etherscan |
| **E8** | 「6 例离散度低 ⇒ 成本可预测」 | 6 例接近**不能**证明没有长尾 | 审查 §6 |
| **E9** | 「1/8 失败 ⇒ 300 例约 30–40 个失败」 | 单次观察不能预测总体失败率 | 审查 §6 |
| **E10** | 「3→15 rps 变化说明是节点计算耗时」 | 该对比**不能**分解出节点计算与网络时间 | 审查 §6 |
| **E11** | 「7.24 小时 ⇒ 超 8 小时预算」 | 8 小时是**主动工时**上位约束，墙钟/人工/额度分别记账，不能混算 | 审查 §7 |
| **E12** | 最小单位仍 revert ⇒ 排除规模相关机制 | **不能排除**：最低输出取整为零或其他限制可能并存 | 审查 §6 |

## 三、已复现的功能缺陷（待修，不在本文件修）

`first_mint` 离线 mock 复现：

```
status=1 空数组                  → (None,'no_mint_by_cutoff')   无链上状态交叉核验
日志缺 address/topic 且块号越界    → (24136000,'ok')             请求起点为 24136053
恰好 1000 条（分页打满）           → (24200000,'ok')             未判截断
```

编排层九项逐条核对全部属实：`right_censored` 漏写 `elapsed_s/rpc_calls`、
全部失败仍 `return 0`、`started_at` 结束时才填、未校验 universe hash、
买入 stage20 直接升级 `entry_failed_verified`（与规格 §3 自相矛盾）、
`baseFeePerGas` 缺失默认零、`gas_table` 固定次数、`rpc.records` 未落盘。

## 四、仍然成立的部分

- `no_mint_by_cutoff`（idx 477926）**独立复核过**：该池到 finalized 快照为止从未有 Mint 事件
- `execution_reverted_unknown`（idx 488019）的 revert 字符串
  `TransferHelper: TRANSFER_FROM_FAILED` 是实测所得；**分类维持未知**，未被标为蜜罐或不可卖
- 只读白名单缺陷（`eth_blockNumber` 不在 `ALLOWED`）确为真缺陷，已修为 finalized 快照

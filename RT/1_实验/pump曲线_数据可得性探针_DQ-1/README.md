# pump 曲线阶段：生命周期与数据可得性探针（DQ-1）

> **状态：已完成，if_A（限定切片）**｜2026-09-15｜3 条探针 SQL 由用户在 Dune 网页运行｜现状以 [总入口](../../00_总入口.md) §2.1 为准

## 问了什么

pump.fun 曲线阶段的全发行分母（含无成交的币）、储备、迁移、迁移后池子，能否用现有资源（Dune）测量。

## 结论

- 限定切片可测：SOL 计价、经 PumpSwap 迁移的发行，分母、曲线储备、迁移后的池地址和池储备都有 Dune 表。
- 不覆盖：2025-03-20 前迁往 Raydium 的分支、USDC 计价、2024 年初。
- 顺带确认了 Dune 账户的可用流程：账户为只读，由用户在网页运行 SQL，执行方按 query 编号读取结果。
- 证据：F49–F51。抽样只有 6 天，只能发现缺口，不能证明其他日期完整。

## 先读哪个文件

| 文件 | 是什么 |
|---|---|
| **[DQ1_结果.md](DQ1_结果.md)** | 结论，**先读这个** |
| [DQ1_卡.md](DQ1_卡.md) | 规格 |
| `sql/` | 3 条冻结探针 SQL：`A_trade_fields`、`B1_denominator`、`B2_migration` |
| `raw/` | SQL 结果 CSV、pump 程序各版本 IDL、Dune API/MCP 探测记录 |
| `raw/dune_datasets_pumpdotfun.json` | **Dune 的 pump 表目录**。DQ-1M、DQ-1F 生成 SQL 时读取它 |

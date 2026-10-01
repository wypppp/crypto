# 探针：tokens_solana.transfers 中原生 SOL 的表示（10-01）

- query 8875236，execution `01M3V73ZD2N0K1XTK75GNVA3RX`，0.576 credits；SQL：`sql/PROBE_NATIVE_SOL_20260803.sql`（只读 2026-08-03、一个签名者）。
- 结果（经 MCP 读取，前几行按笔数排序）：
  - 原生 SOL：`token_version='native'`、`token_mint_address='So11111111111111111111111111111111111111111'`、`symbol='SOL'`；`action` 有 `transfer` 与 `create_account`（建代币账户的租金）。
  - 经 pump 程序（`6EF8…`）的内部 SOL 转账 4,896 笔共 16.32 SOL（成交付款）；顶层 System Program 转账 2,040 笔共 0.0102 SOL；建账户租金 1,640 笔共 3.34 SOL。
  - `inner_instruction_index` 对所有行都非空，所以“顶层”只能用 `outer_executing_account` 判断。
  - 2026-08 的 pump 币是 `spl_token_2022`；WSOL 为 `So11111111111111111111111111111111111111112`（PumpSwap 成交中出现）。

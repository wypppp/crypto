# H1 S0：单日事件枚举草稿

> **2026-09-21 执行方更新：请运行 v1，不运行 v0。**先运行 [V_failed_evt_check_20260601.sql](V_failed_evt_check_20260601.sql)，结果为"失败组 0 笔、对照组 10 笔"才运行 `H1_S0_v1_<day>.sql`。绑定证据、v1 的 5 处改动、本地 DuckDB 逻辑核验和运行顺序见 [S0_v1_核验.md](S0_v1_核验.md)。下文是 v0 原说明，保留作为记录；其中"表列待核实"已由核验文档回答。

[H1_S0_2026-06-01.sql](H1_S0_2026-06-01.sql) 只枚举 6 月 1 日创建队列中的首个合格事件，不计算收益。规格见[H1 执行规格](../../audits/RT_20260921/ignition_review/H1_执行规格_v0.md)。

**状态：本地 Trino 方言语法检查通过，未在 Dune 执行，未验证实际 schema/执行计划。**需要核实 DepositEvent、WithdrawEvent 两张 decoded 表，以及 BuyEvent 的 `quote_amount_in_with_lp_fee` 列。其名称来自本地 IDL 和项目已有命名，不能把本地 IDL 当成 Dune 表已存在的证据；Dune 编辑器绑定检查未通过时不启动扫描。既有四张主要表的字段沿用 F2/F3，但本查询没有复用其收益输出。

## 查询做什么

- 从创建队列开始，统一连到 `solana.transactions.success=true` 后确定实际成功创建时间与 SOL 计价范围。它没有继承 F2 在创建后 30 分钟的活跃度筛选。
- 事件来源限定 pump 曲线与由 pump 创建的 index=0 PumpSwap 池。监测币龄 `[30min,24.5h)`；满足净买入 ≥4 SOL 且此前 30 分钟净买入合计 <4 SOL，按交易链上顺序取首个合格事件。
- 一笔交易内先聚合，含卖出、迁移/LP 事件或多个场所的交易不作入场触发。历史前窗仍统计其已解码买入腿；没有把未来整秒的买入算到当前信号里。非单调区块时间采用前缀时钟并标为数据异常。
- 输出 `candidate`、`candidate_needs_data_review`、`data_quality` 与一条 `__SUMMARY__`。不要把 summary 当成币。数据异常行须先解释，不能直接丢掉后计算收益。
- 汇总中的 `n_created` 是有成功创建事件的币数；`n_sol_without_decoded_events` 是未见解码买卖的 SOL 币数，不能直接解释成链上没有交易。`n_large_mixed_txs` 是监测期内被排除的大额混合交易数。

## 金额校准

曲线用 `TradeEvent.sol_amount`；AMM 用 `BuyEvent.quote_amount_in_with_lp_fee`，均为 lamports。三笔本地原件中的机械触发应为：

| mint | UTC | 买入 lamports | 前窗买入 SOL（交易余额差示例） |
|---|---|---:|---:|
| `B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump` | 06-02 01:10:13 | 26113797485 | 0 |
| `5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump` | 06-03 06:21:28 | 4889866666 | 0 |
| `BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump` | 06-06 22:55:54 | 4406666666 | 2.190296023 |

单日 6 月 1 日草稿应覆盖 B1C2 和其对照。其余两行属于不同创建日，不要求它们出现在这条结果中。旧 `quote_amount_in − protocol_fee − coin_creator_fee` 在 B1C2 首单与实际池余额不符，不能用作本查询默认净流入。更广的本地金额对账仍有少量差额/缺失，见[解码记录](../../audits/RT_20260921/ignition_review/EVENT_DECODE_RESULTS.md)；上述对账不是声称所有交易都已正确解码。

## 执行顺序与费用

1. 核实 Dune 编辑器的表/列绑定和账户**单次查询 cost cap**。SQL 不含 credits 中止逻辑；用户取消也可能收取已消耗计算。
2. 首次只运行 6 月 1 日创建队列，记录 query/execution ID、engine、cap、实耗、汇总行与 B1C2 的触发。没有指定一个未经验证的 credits 估计。
3. schema、金额、边界和成本量级通过后，再按创建日扩展 A 周。通过与否不由这三个已知赢家的收益决定。
4. S1 持仓路径查询另做；不要给 S0 顺带接上全池 30 天路径或收益标签。

因为最后一刻创建的币还需监测 24.5 小时，6 月 1 日队列实际扫描 **6 月 1–3 日**事件分区。交易成功性半连接也访问这三天的交易表；小队列不保证只扫很少数据。池映射和创建 CTE 仍可能被 Trino 重算，实际费用要靠执行计划/冒烟核对。

生成其他已打开 A 周日期（只生成文件，不联网、不执行）：

```bash
.venv/bin/python RT/case_timing/build_h1_s0.py --day 2026-06-03
```

生成器拒绝 A 周之外的日期，避免误把确认队列写入查询。修改金额、前窗、延迟、事件单位或人群时须留下版本差异，不覆盖原定义后继续称作同一次检验。

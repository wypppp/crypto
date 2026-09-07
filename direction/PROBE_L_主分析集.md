**日粒度联合候选表 + 主分析集｜config v1.8.27→v1.8.29｜2026-09-06**

config v1.8.29 `755091fc…`、`L_11_join.py` `a248bfbf…`、产物 `L_u_master.json` `8ea8526d…`。归档于 [archive/v1.8.29/](archive/v1.8.29/)（45 个文件 + SHA256SUMS.txt）。四阶段断言 **129 / 68 / 12 / 54** 全绿，无归档反例通过。

**1. 盘前改为按交易阶段处理，不再永久剔除交易对**

原实现把最早归档日早于正式开盘日的交易对**整体删除**，REDUSDT / USUALUSDT / SCRUSDT 在正式现货阶段的成交也被排除在 T0 选择之外。现改为保留并标注阶段边界：

```
RED / REDUSDT: archive_earliest_day=2025-02-28  phase=PREMARKET_THEN_SPOT
               spot_window_start=2025-03-06     qualifying_earliest_day=null
               why: 正式现货区间内的首笔成交日需逐日数据,日粒度未定
```

T0_day 取自合格对并记录来源：RED 2025-03-06（来自 REDBTC/REDFDUSD/REDTRY/REDUSDC）、USUAL 2024-12-18、SCR 2024-10-22。全部 746 行标 `T0_precision = DAY_GRANULARITY_ONLY`——**本阶段只声明 T0_day，不宣称精确 T0 已验收**。精确 T0 须在合格交易对的正式现货区间内取最早成交、保留所用交易对与成交证据，并继续遵守留出隔离。

**2. join_class 口径冲突已消除**

`SCHEDULE_UPDATED_OR_CANCELLED` 改为 MATCHED 行上的**附加标签**。守恒只对互斥类别成立：`MATCHED 269 + TRADE_ONLY 477 = 746`；标签 10 单独统计，并断言标签名不与类别名重叠。

**3. TRADE_ONLY 477 条互斥归因**

| 类别 | 条数 | 依据 |
|---|---:|---|
| T1 窗口前 | 379 | T0_day < 2021-09-01，公告窗口不覆盖——**不是漏抓** |
| T2 报价资产作为 base | 1 | USDP |
| T3 有公告但裁定非上市类 | 20 | 公告已进对账，判为新增报价对或待裁定（含 BDOT、WBETH、T） |
| T4 bStocks 代币化证券 | 56 | 被提及公告**全部**匹配 `bStocks｜Tokenized Securities` |
| T5 仅有服务新增公告 | 19 | 只有 `Will Add … on Earn/Margin/Futures`，无现货上市公告；多为改名换代号 |
| T6 公告目录完全无提及 | 2 | NBT、PDA——**未解释的证据缺口** |

T4 有一处需要记下来：我最初用"T0≥2026-06-01 且代号以 B 结尾"的**形态启发式**，而且把这个判断排在"是否被公告提及"之前，因而掩盖了这 56 个资产其实有 bStocks 专项公告（276672、279255、283323，均落在 OTHER 桶）。形态判据已废弃——这与 `FUSDT→Ford` 是同类错误。现按公告证据识别，归因结果不变。

T5 的 19 个资产（RENDER、POL、S、A、MANTRA、FRAX…）多为代码迁移或改名，现货对在旧代号下早已存在。按 `b_leg.linkage_rule` **禁止猜测映射**，单列。

**4. 主分析集 = 261**

定义：`join_class == MATCHED` 且 `UTC-date(T_scheduled)` 落在 2021-09-01 ~ 2026-08-31。

- 构成：258 `FIRST_SPOT_LISTING` + 3 `PREMARKET_TO_SPOT`
- 按年：2021 37、2022 26、2023 28、2024 56、2025 92、2026 22
- 其中 10 条经历过计划时间变更
- 排除 8 条回看缓冲期条目（ALPACA、FARM、GNO、MBOX、MINA、RAY、TRIBE、WAXP），用于时间链与去重，不计入主窗口统计

**261 是来源清楚的研究样本量，不是上市频率。** 2026 年只到 08-31；首发上市计数仍不完整、净偏差未定；T4 与 T6 未解决。不得据此计频率或收益。

**5. 未决项**

- 精确 T0 未测：日粒度只到 `T0_day`，盘前对的合格最早成交日记为未定。
- T6 的 NBT、PDA 仍无解释。
- `ANNOUNCEMENT_ONLY`、`RELISTING_OR_AMBIGUOUS`、`AMBIGUOUS`、`PENDING_NO_ARCHIVE_EVIDENCE` 四分支与多次时间串联均无真实实例，只有反例行为。
- 剩余 285 篇 OTHER 未逐篇证明正确（bStocks 公告即在其中）。
- 未对全部 `assertions` 做代理式排查；隔离机制只验证了 T0 文件读取一条路径。
- `repro_L` 仍在 v1.8.10；C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`。

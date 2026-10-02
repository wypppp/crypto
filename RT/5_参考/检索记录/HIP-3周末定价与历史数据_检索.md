> 10-02 子 agent（sonnet）检索整理稿，服务 DQ-34 写卡前三问之①与③（总控第六轮）。执行模型的核对：xyz 规则与 HIP-3 的 websocket `trades` 带地址（本机实测 40 秒 4,817 笔全部带双方地址，见第 3 节“未实测”一句，已由执行模型补测）；Dune `hyperliquid.perp_trades`、`rwa_hyperliquid.perp_trades` 本账户执行失败（“does not exist or it is private”，0 credits，查询 8883255、8883257）。其余未逐条核实，引用前回原页。

# HIP-3 周末定价与历史数据检索（检索日期 2026-10-02）

说明：以下引用来自 2026-10-02 当天直接抓取的原页（docs.trade.xyz 的 .md 版本、docs.hydromancer.xyz、Hyperliquid 官方文档、GitHub README）。抓取工具对部分页面做了摘要，凡标“原文”的都是从 .md 原始文本读到的句子。第三方博客/新闻只作旁证，已标注。

## 1. 各部署方在休市时的 oracle / mark 规则

当前存活（据协调者自有数据）：xyz、para、io、mkts；其余 flx、vntl、hyna、km、abcd、cash 已全部 isDelisted。

### 1.1 xyz（trade.xyz）— 官方文档齐全

文档入口：https://docs.trade.xyz/llms.txt（全站索引）；机制页在 /perpetuals/mechanics/{oracle-price,mark-price,external-price,discovery-bounds}.md。注意：旧路径 /perp-mechanics/... 已 404，现路径是 /perpetuals/...。

**市场类别**（规格表 https://docs.trade.xyz/perpetuals/specifications-and-schedules/specification-index.md 共 109 行）：
- 股指：SP500、XYZ100（US）；JP225、KR200（日、韩）
- 个股/ETF：TSLA、NVDA、AAPL 等美股；韩股 SKHYNIX、SAMSUNG、HYUNDAI；日股 KIOXIA、SOFTBANK；港/中股 MINIMAX、ZHIPU、GIGADEV、UNITREE 等；ETF 如 EWY、EWJ、EWT、XLE、SMH、TLT、SOXL、URNM
- 商品：BRENTOIL、WTIOIL、NATGAS、GOLD、SILVER、PLATINUM、PALLADIUM、COPPER、DIESEL
- 外汇：JPY、EUR、GBP
- Pre-IPO / 私募：另有 Pre-IPO 规格表（https://docs.trade.xyz/perpetuals/specifications-and-schedules/pre-ipo-specification-index.md，未逐条读）

**美股个股的外部价源与时段**（原文，https://docs.trade.xyz/perpetuals/markets/stocks/us.md）：
> "The Relayer derives external prices for stocks 24/5, from Sunday 8:00 PM ET to Friday 8:00 PM ET." 分四段聚合：Pre-Market 4:00–9:30 ET；Market 9:30–16:00 ET；Post-Market 16:00–20:00 ET；Overnight 20:00–4:00 ET，"The overnight trading session is provided by Blue Ocean ATS (BOATS)."

规格表中个股（如 NVDA）：External Session "24/5, from Sunday 8:00 PM ET to Friday 8:00 PM ET"；Internal Session "Friday 8:00 PM to Sunday 8:00 PM ET, and follows equities holidays & trading hours"。

**对旧笔记的核实**：“xyz 个股 oracle 在周日 20:00–周五 20:00 ET 取自外部价源（含 BOATS 隔夜）”——**仍然成立**（上面原文）。周末（周五 20:00 ET 至周日 20:00 ET）及美股休市日：**内部定价**，见下。精确到时区：全部用 ET（美东，随夏令时变化），没有给 UTC。

**内部定价（休市时）**（原文，oracle-price.md）：
> "When external inputs are unavailable, the oracle advances via a continuous-time exponentially weighted moving average that incrementally adjusts the previous oracle price by a fraction of the impact price difference." IPD = max(P_impactBid − S, 0) − max(S − P_impactAsk, 0)；时间常数 τ = 30 分钟，单步 Δt 上限 c·τ（c = 0.1，即每步最多更新约 9.5%）；"When external data becomes unavailable, the internal mechanism initializes from the last available external price. When external inputs resume, the oracle reverts to the externally derived price on the next tick."
- 概述：休市期间 oracle 起点 = 最后外部价（周五收盘），之后随 HL 自身订单簿的冲击价差漂移。impact notional 为各市场配置值（页面未给数值）。
- External Price（external-price.md 原文）：休市时 "the external price remains fixed at the external close price while the oracle advances via its internal pricing mechanism"。

**Mark 价**（mark-price.md 原文）：三者中位数：(1) oracle；(2) oracle + 150 秒 EWMA 的（永续中间价 − oracle）；(3) 买一、卖一、最新成交的中位数。Relayer 每次更新对 mark 和 oracle 都夹在当前值 ±50 bps。

**价格带（Discovery Bounds）**（原文，discovery-bounds.md）：
- mark 被限制在参考价 ±(1/最大杠杆) 内；内部时段参考价初始为最后外部价（如周五收盘）。例：WTIOIL 20x → ±5%。
- “再锚定”：oracle 触及触发阈值（例 90%）时，参考价移到该边界，建立新带；每个市场、每个方向有配置的次数（resets），用完变硬上限，外部价恢复后清零。规格表例：SP500 ±2% / 1 次；XYZ100 ±3.5% / 1 次；NVDA ±5% / 2 次；URNM、EWT、JP225、KR200 的 resets 为 0（静态带）；GOLD ±4% / 2 次；NATGAS ±10% / 1 次。
- 带外强平被暂停："If a trader's liquidation price lies outside the active price bounds, their position cannot be liquidated while those bounds are in effect."
- v1→v2 变更：2026-03-13 "Discovery Bounds v2"（https://docs.trade.xyz/perpetuals/changelog/discovery-bounds-v2.md），v1 为固定 ±1/杠杆围绕最后外部 oracle，v2 增加再锚定。

**休市期间仍可交易**：是，24/7（文档 discovery-bounds：“XYZ is the primary venue for price discovery over weekends, holidays…”）。无“市场关闭”模式，但股指/商品/外汇有每日 17:00–18:00 ET 维护窗口（“Daily maintenance window applies from 5PM ET to 6PM ET, Monday to Thursday”，规格表）。

**资金费**：2025-12-19 起 HL 资金费公式乘 0.5（"Funding Rate XYZ (F) = 0.5 [Average Premium Index (P) + clamp (interest rate - Premium Index (P), -0.0005, 0.0005)]"，https://docs.trade.xyz/perpetuals/changelog/funding-rate-formula-updates.md）；规格表所有市场“Funding Rate Multiplier 0.5”。oracle 是资金费参考价（oracle-price.md：“as the reference price for funding”）。

**股指/商品的外部价源**：
- 股指（原文 equity-indices/us.md）：现货指数仅在 9:30–16:00 ET 周一至周五；“Traditional futures quotes … available 23/5 (Sunday 6:00 PM ET through Friday 5:00 PM ET, with daily gaps from 5:00–6:00 PM ET)”；用期货按持有成本换算成现货：S = F·e^(−(r−q)T)。v1 页（2026-02-19 归档，changelog/equity-indices-v1.md）注明折现率 4%、主数据源 Pyth NMH6 期货喂价；2026-02-19 起升级为 v2（v2 的具体公式未读到，需看 https://docs.trade.xyz/perpetuals/markets/equity-indices.md）。
- 滚动表（原文）：H6 至 2026-03-16 14:00 UTC 活跃；M6 至 06-15 14:00Z；U6 至 09-14 14:00Z；Z6 至 2026-12-14 15:00Z（到期 12-18 14:30Z）。
- 商品/外汇：规格表外部时段为周日 18:00 ET–周五 17:00 ET（BRENTOIL 到 18:00），JPY 周日 17:00–周五 17:00 ET。
- 假日表（https://docs.trade.xyz/perpetuals/specifications-and-schedules/holiday-closures.md）分期货、基本金属、能源、股票、“Overnight Equities”、韩/日/港/上海科创板。例（2026）：股票 9/7 劳动节全天 CLOSED；11/26 感恩节 CLOSED，11/27 与 12/24 提早收盘（04:00–13:00）；Overnight Equities 另有休市日，如 9/6（周日，劳动节前）、11/25（周三，感恩节前）。该页未写明时区，按上下文应为 ET（未核实）。

**规则近期变更（日期均来自 changelog）**：
- 2025-11-21：个股内部 oracle 时间常数 8 小时 → 1 小时
- 2025-12-19：资金费乘 0.5
- 2026-02-19：股指 oracle 方法 v2
- 2026-03-13：Discovery Bounds v2（再锚定）
- 2026-04-30：个股内部 oracle 时间常数 1 小时 → 30 分钟（当前 τ=30 分钟）
- 另有 market-parameters 条目（6/12、6/24、7/28）与 2026-09-28 Kioxia 拆股公告，未读。
- 重要含义：2025-11-21 之前的周末数据与现在的 oracle 行为不同（τ 8h/1h/30min）；2026-03-13 前后的价格带也不同。分析周末定价时要按这些日期分段。

### 1.2 io（Entropy）
- 文档 https://docs.entropy.io/ ：“Oracle feeds are implemented and maintained by RedStone.” 页面未写休市规则。
- 旁证（搜索摘要，非官方原页，未核实）：Entropy 发布约每 3 秒的流动性加权 oracle，混合内部价与外部聚合价，内部权重上限 0.95。出处线索：https://github.com/alexbabits/entropy-oracle 、https://entropyguides.com/guides/trading/anthropic-pre-ipo-perp 。休市规则：未找到官方文档。

### 1.3 para（Paragon）
- 加密市值指数永续（BTC.D、TOTAL2、OTHERS 等），2026-04-02 上线（搜索摘要），官方文档 https://docs.paragon.trade/ （未读）。标的是加密指数，24/7 有外部价，无“美股休市”问题。休市规则：不适用（未核实）。

### 1.4 mkts / km（Markets by Kinetiq，同一部署者地址 0x71f0…2d7b，两个 dex 名）
- 旁证：使用 Kaiko 的 HIP-3 oracle（https://www.kaiko.com/news/how-kaikos-oracle-and-institutional-rates-power-kinetiqs-24-7-global-on-chain-perpetual-markets ），上线品种 US500、EUR、BABA、USTECH、SMALL2000、USBOND、USENERGY。休市规则：未找到官方文档（https://markets.xyz/docs 抓取超时，未读到）。

### 1.5 已下线的 dex（简记）
- flx（Felix）：官方下线指南 https://usefelix.gitbook.io/perps ：“Settlement is expected to occur on June 19 (Friday)”，自 6/19 17:30 ET 起依次结算（商品→股票→加密）。其休市锁价规则（原文摘要）：RedStone 负责；商品用周五 13:00 ET 收盘价，股票用周四正常收盘（16:00 ET）oracle 价，加密用周五 15:50–16:00 ET 的 10 分钟 EMA。（注意：文中“周四收盘”是下线结算期间的规则，是否同样适用于生前周末，未核实。）旁证：2025-11-13 以 TSLA 上线，用 RedStone。
- vntl（Ventuals）：旁证新闻称 2026-06-15 关闭（kucoin.com/news 摘要，未核实）；oracle 一半来自私募二级成交，一半来自合约自身移动平均（搜索摘要）；文档 https://docs.ventuals.com/perp-specifications/private-companies （未读）。
- cash（Dreamcash）：旁证 Bitget 新闻称 6/30–7/2 分三阶段按 oracle 价结算关闭，原因是 USDC 原生化后 USDT 部署者体验差。
- hyna（HyENA）：USDe 保证金加密永续；旧文档页 docs.hyena.trade/trading/oracle-price-and-mark-price 已不存在；搜索摘要称 Chaos Labs 为 oracle 更新者、加密 CEX 加权中位数、约每 3 秒更新。关闭原因：未找到。
- km、abcd：关闭原因：未找到。

### 1.6 Hyperliquid 官方 HIP-3 文档
- 页面 https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals 与 /for-developers/api/hip-3-deployer-actions 。本次未读其正文，故“HL 协议层如何限制部署者 oracle/mark”未核实。已知：官方 node README 有 `--write-hip3-oracle-updates` 参数，把每次 HIP-3 部署者 oracle 更新动作写到 `~/hl/data/hip3_oracle_updates/hourly/{date}/{hour}`（https://raw.githubusercontent.com/hyperliquid-dex/node/main/README.md）。这对复盘周末 oracle 轨迹很关键，但官方桶里是否上传了该目录：未核实。
- `perpDexs` 实测（2026-10-02 POST https://api.hyperliquid.xyz/info）：xyz、flx、vntl、hyna、km、abcd、cash、para、mkts、io，与协调者一致；km 与 mkts 部署者地址相同。

## 2. Hyperliquid 历史数据存档

官方文档 https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data.md （原文）：
- `hyperliquid-archive`：“uploaded to the bucket … approximately once a month. There is no guarantee of timely updates and data may be missing.” 前缀仅两类：`s3://hyperliquid-archive/market_data/[date]/[hour]/[datatype]/[coin].lz4`（L2 快照，示例 market_data/20230916/9/l2Book/SOL.lz4）和 `s3://hyperliquid-archive/asset_ctxs/[date].csv.lz4`。“No other historical data sets are provided via S3 (e.g. candles or spot asset data).” 付费方式：`--request-payer requester`，“the requester of the data must pay for transfer costs.”
- `hl-mainnet-node-data`：`node_fills_by_block`（`--write-fills --batch-by-block` 产出，当前格式）、旧的 `node_fills`（与 API 格式一致）与 `node_trades`（格式不同）、`explorer_blocks`、`replica_cmds`、`misc_events_by_block`（转账、质押、资金费等非成交事件）。
- 官方文档**没有提到 HIP-3**。
- 覆盖日期（第三方文档，非官方）：
  - alpenmilch411/hyperliquid-archive-notes（https://github.com/alpenmilch411/hyperliquid-archive-notes）：asset_ctxs 起自 2023-05-20，约 1,137 天，首日不全，三个整小时缺失（2023-07-02T20:00Z、2023-08-23T20:00Z、2024-08-15T13:00Z），日文件约 7 MB（lz4 CSV）。
  - bond-labs-dev/hyperliquid-data README（https://github.com/bond-labs-dev/hyperliquid-data）：`node_fills/hourly` 覆盖 2025-05-25 至 2025-07-27，之后用 `node_fills_by_block/hourly/<YYYYMMDD>/<H>.lz4`；`node_trades` 前缀存在但“returns empty files”；每行 `{"events": [[address, fill], …]}`，**含用户地址**，每笔成交 taker（crossed=true）和 maker（crossed=false）各一行、共享 tid；L2 快照按事件驱动，约 550 ms 一次，活跃币约 1.8 条/秒。
- 是否含 HIP-3 币（带 dex 前缀）：Hydromancer 称官方档“Validator perps only”、“HIP-3 trade data was not uploaded at all”（https://hydromancer.xyz/resources/hyperliquid-historical-s3-archive ，竞争对手的说法，未独立核实）。node README 说 `--write-fills` 输出含 HIP-3 的 `deployerFee` 字段，说明节点程序产出的 fills 含 HIP-3，但官方桶是否包含：**未核实**。要确认只能用 `aws s3 ls --request-payer requester` 列目录并读一小时的文件（需 AWS 账号，本次未做）。
- 更新规律：官方称约每月一次，无保证。
- 费用：按 AWS 标准，bond-labs 的估算工具按 **$0.09/GB** 出口流量费计价（README 示例：2026-06 一个月 fills 约 0.64–0.96 GiB/天，合计约 $2.21；日期范围为 2026-06-01 至 06-30 的示例输出）。请求费（每千次 GET 约 $0.0004）量级可忽略，此处为 AWS 公开价格的一般知识，本次未抓取 AWS 价格页核实。L2 单币一个月的大小：未找到官方或社区数字。bucket 区域和跨区流量未核实。

**更好的来源（见第 3 节）**：Hydromancer 的 Reservoir 免费 S3（`s3://hydromancer-reservoir`，requester pays，区域 ap-northeast-1），含 HIP-3 全部成交（带地址）、1 秒 K 线、每日持仓快照、1 分钟 20 档 L2。

## 3. 带买卖双方地址的 HIP-3 历史成交来源

**官方 info API**（POST https://api.hyperliquid.xyz/info）：
- `recentTrades`：官方文档页（/for-developers/api/info-endpoint）没写这个类型，但实测可用：`{"type":"recentTrades","coin":"xyz:TSLA"}` 在 2026-10-02 返回 10 条（本次实测，非恒定），字段 `coin, side, px, sz, time, hash, tid, users`，其中 `users` 为 [买方, 卖方] 两个地址（本次实测）。只含最近几条，不能回溯。部分 `hash` 为全零。
- `userFills`：官方文档原文 “returns at most 2000 most recent fills”；`userFillsByTime`：“at most 2000 fills per response and only the 10000 most recent fills are available”。按用户查，需先知道地址。HIP-3 是否默认包含：文档未写（userFills 订阅无 dex 参数，其他用户订阅有）。
- WebSocket `trades` 频道（https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions 原文）：`WsTrade: coin, side, px, sz, hash, time, tid, users: [string, string]`，`users` 为 [buyer, seller]，**含地址**。只能前向记录。HIP-3 币用 `xyz:TSLA` 订阅，实测方式（recentTrades 已验证）；ws 对 HIP-3 的行为本次未实测。

**Dune**（通过 mcp__dune__searchDocs 读到官方文档）：
- `hyperliquid.perp_trades`：“fill table for Hyperliquid perpetual futures, venue-wide: first-party markets (coin = BTC) and HIP-3 builder-deployed markets (coin = xyz:TSLA) alike. Grain: one row per fill leg — both sides of every match — keyed on (block_date, coin, trader, oid, tid)”，含 trader 地址；“History starts 2025-07-27”。概览页：fills 起自 2025-07-27，持仓量与资金费起自 2025-09-27，每小时刷新。**标注为 Gated dataset（需要企业权限）**，https://docs.dune.com/data-catalog/curated/perpetuals/hyperliquid/perp-trades 。
- `rwa_hyperliquid.perp_trades`：HIP-3 RWA 永续，每行一个 taker leg；同样是 Gated。https://docs.dune.com/data-catalog/curated/rwa/activity/perp-trades
- `hyperliquid.perp_orderbook_1m`：含 HIP-3，最多 100 档，历史起自 2026-06-29；Gated。
- 社区表（https://docs.dune.com/data-catalog/community/hyperliquid/overview ）：涵盖订单、成交、取消、TWAP、资金费、HIP-3 等；是否含地址、表名细节、价格档：未读到，需另查。
- 我方 Dune 账户是否有 Gated 权限：未核实（请用 searchTables 或试跑）。

**Hydromancer Reservoir（免费，S3 requester-pays）**（https://docs.hydromancer.xyz/reservoir.md 及子页，原文）：
- Fills：路径 `by_dex/{dex}/fills/perp/all/date=YYYY-MM-DD/fills.parquet`；可用 dex：`hyperliquid, xyz, cash, hyna, flx, km, vntl, para, io`（文档此处未列 mkts、abcd）；27 列，含 `address`（用户钱包）、`crossed`、`order_id`、`trade_id`、`start_position`、`fee`、`builder`、`deployer_fee`（2026-03-21 起）、`priority_gas`（2026-04-13 起）、`liquidation_*`。每笔成交应有 taker 和 maker 两条（该页未明说，按 `crossed` 字段与 bond-labs 对官方流的描述推断，未核实）。
- 起始：xyz 为 2025-10-13（“complete history since launch”）；flx 2025-11-13。每日更新。
- 1 秒 K 线：`by_dex/xyz/candles/1s/date=…/candles.parquet`。
- 订单簿：`by_dex/{dex}/orderbook/1m/perps/date=…/{coin}.parquet`，20 档，1 分钟，每周更新；HIP-3 币名用不带前缀的 `NVDA`（dex 在路径里）。
- 每日持仓快照：`by_dex/xyz/snapshots/perp/date=…/*.parquet`。
- 文档里“The data cutoff is August 2025. Candlesticks are backfilled before the cutoff date.”，含义不清（xyz 2025-10 才上线），按字面理解可能指 K 线对更早时段回填；未核实。
- 费用：数据免费，只付 AWS requester-pays 流量；Hydromancer 付费 API 套餐 Starter $300/月、Growth $1,200/月、Scale $2,500/月（https://hydromancer.xyz/pricing ），REST 端点 `userFills`/`userFillsByTime`（无 2000/10000 限制，称 “no fills limit”）、`builderFillsByTime`、`fundingHistory` 等。
- 第三方说法，须独立抽样核对（数据完整性与官方 node_fills_by_block 对账）。

**其他第三方**（Allium、HypurrScan、Artemis、ASXN、Goldsky）：本次未检索到各自的 HIP-3 成交带地址产品与价格，**未核实**。SonarX 提供 HIP-3 L2 快照免费 S3（`sonarx-hyperliquid-public`，requester-pays，gzipped JSON，https://docs.sonarx.com/datasets/HYPERLIQUID/public-l2-snapshots ），未读详情。

## 4. CME 股指期货与美股延长交易

**CME ES/NQ 周日开盘**：Globex 周日 18:00 ET 开盘（= 17:00 CT），周五 17:00 ET 收盘，周一至周四每天 17:00–18:00 ET 维护（旁证：多个第三方页，CME 官方页 https://www.cmegroup.com/trading-hours.html 抓取超时，未直接读到；与 trade.xyz 文档“Sunday 6:00 PM ET through Friday 5:00 PM ET, with daily gaps from 5:00–6:00 PM ET”一致）。
- 夏令时（EDT, UTC−4）：周日 **22:00 UTC** 开盘。
- 冬令时（EST, UTC−5）：周日 **23:00 UTC** 开盘。
- （注意：检索工具返回的摘要把这两个写反了，已按偏移量更正；trade.xyz v1 滚动表里的 “Active Until” 3 月 22:00Z、12 月 22:00Z 的写法也只是它们自己的内部时刻，不是开盘时刻。）
- 2026 年美国夏令时：3 月 8 日开始；**11 月 1 日（周日）02:00 EDT 结束**（美国现行规则：11 月第一个周日，此为一般知识，未抓取官方页核实）。因此 2026-10-25 的周日开盘是 22:00 UTC，2026-11-01 的周日开盘是 23:00 UTC。
- 2026 年 CME 假日（旁证，第三方日历）：全天休市 1/1、4/3（耶稣受难日）、12/25；其余提前收盘。trade.xyz 假日表“Futures Holiday closures”与此一致（如 4/3 仅开 00:00–09:15，12/25 CLOSED）。

**纳斯达克 23 小时交易**（已证实，有冲突点）：
- SEC 于 **2026-04-10** 批准纳斯达克把美股交易从每天 16 小时扩到 23 小时、每周 5 天（Arnold & Porter：https://www.arnoldporter.com/en/perspectives/advisories/2026/04/sec-approves-nasdaq-proposal-to-expand-trading-hours ；SEC 备案 SR-NASDAQ-2025-109 Federal Register 2026-01-13：https://www.federalregister.gov/documents/2026/01/13/2026-00416/self-regulatory-organizations-the-nasdaq-stock-market-llc-notice-of-filing-of-proposed-rule-change ）。
- 时段：Day Session 4:00–20:00 ET；维护 20:00–21:00 ET；Night Session 21:00–次日 4:00 ET；周一周期始于周日 21:00 ET，止于周五 20:00 ET；夜盘仅限价单；SEC 条件含“temporary static 20% Overnight Price Bands”（Jones Day 摘要：https://www.jonesday.com/en/insights/2026/09/nyse-and-nasdaq-move-to-23hour-trading-day-overnight-session-is-an-evolution-but-not-yet-a-revolution ）。
- 上线日：**2026-12-06（周日）**，Nasdaq 与 NYSE Arca 均计划（Jones Day 称“subject to regulatory approval”）。公告日期有出入：Euronews 文章日期为 2026-08-18（https://www.euronews.com/business/2026/08/18/nasdaq-confirms-23-hour-trading-from-december-with-new-overnight-session ）；GuruFocus/bitcoin.com 摘要称 2026-08-25。纳斯达克官方页（nasdaq.com/articles/nasdaq-global-trading-hours-future-trading）抓取超时，未读到，官方公告确切日期未核实。
- 纽交所：NYSE Arca 已获批 22 小时/日（Arca 2025-02 获批，据搜索摘要），2026-05-12 提交修订备案（SR-NYSEARCA-2026-53，https://www.sec.gov/files/rules/sro/nysearca/2026/34-105532.pdf ，未读），同样计划 2026-12-06 起覆盖 21:00–20:00 ET 的 23 小时框架（Jones Day）。Euronews 另称“NYSE 22 小时日（1:30am–11:30pm ET）”，与 Jones Day 冲突，未核实。**主板 NYSE 是否跟进：未找到官方文档**，目前只确认 NYSE Arca。
- 对本研究的含义：2026-12-06 起美股夜盘延长到周五 20:00 ET 前后无变化，但周日开盘从 20:00 ET（BOATS）变为 21:00 ET 的主流交易所夜盘；trade.xyz 的外部价源文档若改，会有 changelog，需持续关注。Blue Ocean 是否继续作为 xyz 的夜盘源：未找到官方文档。

## 5. 未能核实的事项
1. Hyperliquid 官方 HIP-3 文档中关于部署者 oracle 与 mark 的协议层约束（页面未读正文）。
2. `hyperliquid-archive`/`hl-mainnet-node-data` 是否真包含 HIP-3 币、`hip3_oracle_updates` 目录是否上传、从哪天起（需 AWS 账号列目录）。
3. 官方 L2 快照每币每月大小（GB），官方 S3 区域与具体请求费。
4. 纳斯达克官方公告原文与确切日期（8/18 与 8/25 冲突）；主板 NYSE 是否跟进；SEC 备案的最终上线批准状态。
5. CME 官方交易时间页原文；2026 夏令时结束日期用的是通用规则，未抓官方页。
6. io、mkts/km、para、hyna 的休市 oracle/mark 官方规则；vntl、km、abcd、hyna 的关闭原因与日期（vntl 2026-06-15、cash 6/30–7/2 为新闻摘要）。
7. xyz 股指 v2 oracle 公式、market-parameters 三条变更内容、Pre-IPO 市场规则、各市场“impact notional”数值。
8. xyz 假日表时区未标注；假日表中的 “Overnight Equities” 与 BOATS 实际休市日的对应关系。
9. Dune 社区 Hyperliquid 表的名称/地址字段/是否免费；Gated 表我方是否有权限。
10. Allium、HypurrScan、Artemis、ASXN、Goldsky 的 HIP-3 成交（含地址）产品与价格。
11. Hydromancer Reservoir 数据完整性与“cutoff August 2025”含义、mkts/abcd 是否覆盖、每笔成交是否双边都有行、流量费总量估计。
12. WebSocket `trades` 对 HIP-3 币是否稳定带 `users`（只验证了 REST `recentTrades`）。

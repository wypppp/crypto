> 10-02 子 agent（sonnet）检索整理稿：币安 U 本位自动减仓（ADL）规则、资金费结算与上限、COAIUSDT 2025-09～11 的公开记录（服务 DQ-23 前向卡登记前的案头核查）。WebFetch 为摘要，非逐字原文，引用前回原页。

# COAIUSDT / 币安 ADL、资金费检索（检索日期 2026-10-02）

说明：WebFetch 返回的是小模型对页面的摘要，不是逐字原文；标“摘要”处引文可能有转述误差，进入结论前应人工打开原页核对。工具只能访问部分页面，未登录。

## 1. ADL 规则

官方来源：https://www.binance.com/en/support/faq/what-is-auto-deleveraging-adl-and-how-does-it-work-360033525471?hl=en （2026-10-02 取，摘要）

- 触发：ADL 是强平流程的最后一步，“occurs only if the Futures Insurance Funds are unable to accept a bankrupt futures position”。即保险基金接不住破产仓位时才触发。
- 排序公式（摘要所引）：
  - PNL Percentage = Unrealized Profit / abs(Position Notional)
  - Effective Leverage = abs(Position Notional) / (Account Balance + Unrealized Profit)
  - PNL% >= 0：ranking = PNL% × Effective Leverage；PNL% < 0：ranking = PNL% ÷ Effective Leverage
  - 原文：盈利越多、杠杆越高的仓位越先被 ADL。
- 成交价：盈利仓位“将按被强平订单的破产价（Bankruptcy Price）平仓”；破产价为交易者亏损等于所存保证金/初始保证金的价格。
- 推算（非官方原文）：1 倍逐仓多头，账户余额（逐仓保证金）= 名义额 N，价格涨 30 倍时未实现盈利约 29N，有效杠杆 = N' /(N + 29N)，其中 N' = 30N，故约 1.0；PNL% 约 29N/30N ≈ 0.97；排序值 ≈ 0.97 × 1.0 ≈ 0.97。对比 10 倍杠杆同方向多头，盈利 % 相同时有效杠杆在大涨后同样趋近 1，所以大涨后高杠杆的排序优势被压缩；但排序值与别人比的是相对位置，1 倍仓位的有效杠杆不会高于别人，故在“队列分位”上通常靠后于同盈利的高杠杆仓位，不是靠前。此推算依赖“有效杠杆用逐仓保证金+浮盈”这一读法，逐仓下“Account Balance”究竟取钱包余额还是该仓位保证金，官方页面摘要未说明，**未核实**。
- 保险基金分组：https://www.binance.com/en/support/faq/introduction-to-futures-insurance-funds-360033525371 （摘要）：BTC/ETH/BNB 共用一个；DOT、LINK、XMR、ADA、BCH、EOS、ETC、LTC、TRX、XLM、XRP 共用一个；“其他 USDT 本位合约各有自己的资金池”（摘要措辞，原文是否指每个合约独立，需核对）；USDC 本位共用一个。页面未出现“isolated insurance fund”这个词，也没提 COAIUSDT。
- 结论：未找到官方文字说明“新上线合约使用独立保险基金”，也未找到 COAIUSDT 的保险基金余额公告。可查 Binance “Insurance Fund History” 数据页（未取）。

## 2. 资金费

- 官方 FAQ：https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031 （摘要）
  - 公式：资金费 = 仓位名义价值（标记价格×数量）× 资金费率。
  - “Funding Payments are transferred directly between traders holding opposing positions”，平台不收费；即交易者之间划转，不是平台支付。（注：此为 FAQ 通用说法；平台不垫付，意味着收款依赖对手方被扣款成功。极端行情下是否有差额由保险基金处理，**未找到官方说明**。）
  - “You are only liable for funding payments ... if you have open positions at the pre-specified funding times”，只有结算时刻持仓才收付。
  - 上限：官方公式 0.75 × 维持保证金率相关（摘要所述“0.75 × Maintenance Margin Ratio”，具体形式需核对）；BTCUSDT 为 ±0.3%。
  - 极端波动时平台可把间隔从 8 小时改为更短；FAQ 摘要提到“触及上下限时改为 1 小时，稳定后回到 4 小时”。
- 规则公告（旁证，PANews 转述币安公告）：
  - https://www.panewslab.com/en/articles/13be25f4-ae90-4812-b940-840838c27305 （同 panews.io 同 ID；2026-01-02 公告）：若小时结算合约资金费连续 16 期绝对值 <= 0.025%，第 17 期起改回 4 小时。这是 2026 年的新规则，不适用于 2025-09/10。
  - Lookonchain 转述（搜索摘要，未打开）：自 2025-05-02 08:00 UTC 起，当上一期资金费达到上限/下限，结算频率改为每 1 小时。https://lookonchain.com/feeds/42319 。**币安官方 2025-05 公告原页未取到。**
- COAIUSDT 上限：
  - 搜索摘要（腾讯类中文站/百科聚合页，来源不明，旁证）称：最大杠杆 50 倍，结算 4 小时一次，资金费率上限 +2.00%/-2.00%。出处是 WebSearch 摘要，未能打开原页。
  - 币安官方公告“Important Updates on Funding Rates of USDⓈ-M Perpetual Contracts”（https://www.binance.com/en/support/announcement/important-updates-on-funding-rates-of-usd%E2%93%A2-m-perpetual-contracts-98d6b24d3e5c4f84a8ed04087997d8d0 ）为 2023 年，只列 15 个合约，不含 COAIUSDT；其中提到最大杠杆 <=25x 的合约上限为 ±3%。
  - 可通过 API fundingInfo 端点查 adjustedFundingRateCap/Floor/fundingIntervalHours（https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History 摘要），但只返回当前状态，不含历史。未调用（任务限公开网页检索）。
- COAIUSDT 何时 4 小时改 1 小时的官方公告：**未找到**。
- data.binance.vision fundingRate 是否等于实际结算费率：**未找到官方说明**。API 文档摘要只说 Get Funding Rate History 返回历史资金费率记录及对应标记价格，未明言“即实际结算费率”。

## 3. COAIUSDT 2025-09-25～11 期间事件

- 上线：PANews 转述币安公告：2025-09-25 15:30 UTC 起 COAIUSDT 永续上线，最高 50x。https://panews.io/articles/0e79afed-f170-4e68-84dd-9f468e58574c （旁证，2026-10-02 取）。
- 空头被轧案例（旁证）：blockchain.news 转述分析师 @ai_9684xtpa：币安聪明钱账户 Hanmancheol 空 COAI，均价约 10.79 美元，约 3 天内支付资金费约 77.4 万美元（按小时收），约 18.97 美元被强平，价差亏损约 60.4 万美元，合计约 137.8 万美元。https://blockchain.news/flashnews/coai-short-squeeze-on-binance-futures-smart-money-trader-hanmancheol-loses-1-378m-as-funding-fees-hit-774k-in-3-days-coai 。注意：该页自身把原因写成“positive funding”，与空头付费的事实矛盾，质量低；数字未经币安证实。该账户为空头强平，不是 ADL。
- 腾讯新闻 https://news.qq.com/rain/a/20251102A0432I00 ：只有前十大持有者占流通 96.5%-97%、10-15 涨 81%、10-25 跌 58% 等，**没有**期货参数、ADL、保险基金内容。
- ADL 发生、保险基金耗尽、调杠杆/持仓上限、调资金费上限、暂停交易、下架/结算：搜索中**均未找到**任何针对 COAIUSDT 的公告或报道（并非证明没有发生）。搜到的 10-10 全市场大面积 ADL 报道（arxiv 论文 https://arxiv.org/html/2512.01112v2 与 beincrypto 等综述）为全市场，未特指 COAI，未打开核对。

## 4. 单账户持仓/名义额限制

- 官方风控页 https://www.binance.com/en/support/faq/binance-futures-trading-risk-control-f1afe9cbcd7a438492a0676e024f1897 （摘要）：当 (a) 持仓名义额超过阈值、(b) 占该合约总持仓量比例超过触发百分比（子账户聚合默认 20%）、(c) 强平价与标记价的距离低于风险参数同时满足时，账户被限制为 Reduce Only（只能减仓、不能加仓），不是被强制平掉；当持仓降 30% 以上或强平价离标记价 40% 以上时 10 分钟内自动解除。具体参数页面未给出。这与 ADL 不同。
- 杠杆分档：https://www.binance.com/en/support/faq/leverage-and-margin-of-usd%E2%93%A2-m-futures-360033162192 （摘要）：名义额涨入更高档不会自动降低杠杆或强制减仓，只是维持保证金率按分档提高；保证金不足则强平。
- 另有币安“持仓上限”（max position by leverage）规则：杠杆越高，允许的最大名义额越低（https://www.binance.com/en/futures/trading-rules 搜索摘要）。价格涨 30 倍后名义额超档时的具体处理（是否禁止加仓、是否强降杠杆）：**未找到明确官方文字**。对 3,000 元 1 倍仓位，名义额涨到约 9 万元，远低于各档上限，推算影响很小（推算）。

## 未能核实的事项

1. ADL 排序公式中，逐仓账户的“Account Balance”取值口径（仓位保证金还是钱包余额），因此对 1 倍逐仓大盈利多头的排序位置只给出了推算，未核实。
2. 官方是否有“独立保险基金（isolated insurance fund）”用于新上线合约，COAIUSDT 的保险基金归属与余额。
3. COAIUSDT 资金费上限 ±2% 只有聚合页旁证，未见币安官方公告；上限随时间是否被调整未知。
4. COAIUSDT 由 4 小时改 1 小时的具体官方公告和生效时间；2025-05-02 规则原公告未取到，仅有 Lookonchain 转述。
5. data.binance.vision 的 fundingRate 与实际结算费率是否一致，无官方说明。
6. 资金费是否在对手方不足时由平台/保险基金补足，无官方说明。
7. COAIUSDT 在 2025-09～11 是否发生 ADL、保险基金耗尽、调杠杆或持仓上限、暂停交易、下架/结算：未找到相关公告或报道。
8. 该交易者 77.4 万美元资金费等数字仅来自二手转述。
9. 币安官方“公告”页（binance.com/support/announcement）未能直接检索列表，COAIUSDT 的全部公告可能漏查。

# 阶段1-A 事实提取清单（T1）

**范围说明**：原始任务字段写的是"为T1提取"，未指定具体对象。按 AI协作规则.md 中"1-A 市场结构"行对 T1 的定义（术语 / 英文文档摘要 / 规格页整理成表），本清单覆盖阶段1-A 五个必学机制中可核查、有来源支持的条目：①永续合约与资金费率 ②清算机制 ③CEX托管结构/Gas费 ④稳定币储备 ⑤真实交易成本。以 Binance 作为主要参照交易所（你的文档中引用最多）。如果这个范围理解错了，告诉我重做。

**不含**：稳定币监管条款（已在补充信息汇总.md）、小市值币实时滑点（原因见文末）。

---

## 1. 永续合约与资金费率（Binance USDⓈ-M）

| 事实陈述 | 数值 | 来源 | as-of日期 | 类型 |
|---|---|---|---|---|
| 资金费率默认结算频率 | 每8小时一次，00:00 / 08:00 / 16:00 (UTC) | [1] | 页面更新于2026-03-06 | 事实 |
| 资金费率方向规则 | 费率为正→多头付给空头；费率为负→空头付给多头 | [1] | 同上 | 事实 |
| 资金费用计算公式 | Funding Amount = 名义仓位价值 × 资金费率 | [1] | 同上 | 事实 |
| 资金费率公式 | F = [平均溢价指数P + clamp(利率−P, 0.05%, −0.05%)] / (8/N)，N为结算间隔小时数 | [1] | 同上 | 事实 |
| 默认利率分量 | 多数币种0.03%/天（每8小时结算0.01%）；ETHBTC等个别合约为0% | [1] | 同上 | 事实 |
| 资金费率封顶（BTCUSDT等被列名的合约） | 上限/下限 = ±0.75×维持保证金率；文档示例中给出BTCUSDT当前上限/下限为 +0.3% / −0.3% | [1] | 同上 | 事实 |
| 资金费率封顶（未被列名的其他USDⓈ-M永续） | ±2% | [1] | 同上 | 事实 |
| 极端行情下结算频率调整规则 | 若费率触及上/下限，下一周期改为每小时结算；连续16期绝对值≤0.025%后于第17期恢复为4小时结算 | [1][2] | 规则生效于2026-01-02 | 事实 |
| 资金费用入账时间容差 | 与预定结算时刻允许15秒偏差 | [1] | 页面更新于2026-03-06 | 事实 |
| 结算频率不是行业统一标准（跨所对照） | Hyperliquid按1小时结算资金费；Binance默认按8小时结算 | [3][4] | 说明性文档，无快照日期 | 事实 |

**来源**
[1] https://www.binance.com/en/support/faq/detail/360033525031
[2] https://www.binance.com/en/support/announcement/detail/e4445d0389ce4defa6009021fcf6ee46
[3] https://docs.pendle.finance/boros-academy/the-basics/chapter-0-understanding-funding-rates
[4] https://medium.com/@joaotx/inside-the-perpetual-the-mechanics-of-funding-rates-3896384695c7

---

## 2. 清算机制（Binance USDⓈ-M）

| 事实陈述 | 数值 | 来源 | as-of日期 | 类型 |
|---|---|---|---|---|
| 初始保证金公式 | Initial Margin = 仓位价值 / 杠杆倍数 | [1] | 公式为静态文案，数值表为动态加载 | 事实 |
| 维持保证金公式 | Maintenance Margin = 仓位价值 × 维持保证金率 − 速算扣除数 | [1] | 同上 | 事实 |
| 标记价格公式 | Mark Price = Median(Price1, Price2, 最新成交价)；Price1 = 指数价格×(1+最近资金费率×(距下次结算时间/结算周期))；Price2 = 指数价格 + 30秒移动均值 | [2] | 页面更新于2026-07-09 | 事实 |
| 指数价格构成交易所 | 加权平均现货价，含Binance、KuCoin、OKX、Coinbase、Kraken、Bitget、Bitfinex、Bybit等，及部分DEX（2025-02-10起对该日后上线合约生效） | [2] | 同上 | 事实 |
| 单一价源偏离保护 | 若单一来源报价偏离全部来源中位数超3%，该数据点被限制在中位数的1.03/0.97倍 | [2] | 同上 | 事实 |
| ADL（自动减仓）触发条件 | 保险基金无法覆盖破产仓位时触发，是清算流程最后一步 | [3] | 页面标注最后更新2024-12-18 | 事实 |
| ADL优先级排序公式 | 盈利仓位：排序值 = 盈亏% × 有效杠杆；亏损仓位：排序值 = 盈亏% / 有效杠杆 | [3] | 同上 | 事实 |
| ADL成交价与费用 | 按被减仓方的破产价格成交，不收取手续费 | [3] | 同上 | 事实 |
| 逐仓/全仓定义 | 逐仓：保证金仅分配给单一仓位；全仓：账户余额被该模式下所有仓位共享 | [4] | 无独立标注更新日期 | 事实 |
| BTCUSDT永续最高杠杆 | 125倍 | [5] | 文章标注2026-05-04 | 事实（二手，官方页面见下） |
| BTCUSDT/ETHUSDT当前完整维持保证金分层表（各档名义价值区间/最高杠杆/保证金率/速算扣除数） | 未获取 | 官方页面：https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin | — | 未获取 |

**口径差异说明（非Binance数据，仅作对照）**：MEXC 官方公告显示其自身 BTCUSDT 分层保证金表在2025年内被多次调整（2025-01-24、2025-03-13、2025-04-04 三版数值均不同），来源 https://mexc.com/en-IN/support/articles/17827791522470 、 https://www.mexc.com/sv-SE/support/articles/17827791521341 。这是MEXC而非Binance的数值，不能相互替代，仅用于说明"分层杠杆表是交易所自定义参数、会被频繁调整"这一点本身。

**来源**
[1] https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin ；公式另见 https://www.binance.com/en/support/faq/detail/360033162192
[2] https://www.binance.com/en/support/faq/detail/360033525071
[3] https://www.binance.com/en/support/faq/what-is-auto-deleveraging-adl-and-how-does-it-work-360033525471
[4] https://www.binance.com/en/support/faq/differences-between-isolated-margin-and-cross-margin-b4e9e6ad70934bd082e8e09e33e69513
[5] https://www.datawallet.com/crypto/binance-futures-review

---

## 3. CEX 托管结构 / Gas 费

| 事实陈述 | 数值 | 来源 | as-of日期 | 类型 |
|---|---|---|---|---|
| Binance用户协议对资产托管权的表述 | 条款载明Binance对平台内数字资产、资金及用户数据拥有完全托管权 | [1] | 当前生效版本 | 事实 |
| Binance（澳大利亚主体ADGM实体）用户协议关于存款保护 | 条款明确平台内数字资产不受澳大利亚APRA金融权益保障计划（Financial Claims Scheme）覆盖 | [2] | 检索到的版本标注约2026年7月 | 事实 |
| 美国SIPC/FDIC对加密交易所账户的覆盖范围 | 律所分析指出：加密交易所账户不同于受SIPC保护的传统券商账户，也不受FDIC存款保险覆盖；美国目前没有专门针对加密交易所的客户资产保护基金 | [3] | 文章发布于2022-05-18 | 事实 |
| 交易所破产情形下用户资产的法律定性（以Coinbase 10-K为例） | 媒体转述Coinbase 10-K风险披露：若发生破产，平台持有的加密资产可能被视为破产财产的一部分，用户可能被认定为普通无担保债权人 | [4] | 披露见于2022年5月的10-K | 事实（二手转述，未直接取得SEC原文链接） |
| 以太坊主网Gas价格快照（说明其高波动、非稳定值，不同时点会有数量级差异） | 2026-02-05：18.006 gwei；2026-06-05：8.774 gwei；2026-07-29：0.116 gwei；2026-08-05：0.146 gwei | [5][6][7][8] | 各行分别标注 | 事实 |

**来源**
[1] https://www.binance.com/us-to/terms
[2] https://bin.bnbstatic.com/static/cms/cg08ou2ak0tn7mcplvfg/file/726b56c4be2cd37669996d366e827c3f7861eab81157b48b78fc3890985833dc.pdf
[3] https://www.nixonpeabody.com/insights/alerts/2022/05/18/hold-on-for-dear-life-how-a-bankruptcy-of-a-cryptocurrency-exchange-may-affect-holders
[4] https://www.benzinga.com/news/22/05/27131315/coinbase-ceo-armstrong-says-new-disclosure-does-not-mean-bankruptcy-risk
[5] https://goto.etherscan.com/gastracker（2026-02-05快照）
[6] https://etherscan.io/gastracker?v=1649187329（2026-06-05快照）
[7] https://etherscan.io/gastracker?gasperiodsort=24（2026-07-29快照）
[8] https://etherscan.io/gastracker（2026-08-05快照）

---

## 4. 稳定币：USDT vs USDC 储备结构

| 事实陈述 | 数值 | 来源 | as-of日期 | 类型 |
|---|---|---|---|---|
| USDC 流通量与储备总额（Circle官方鉴证报告原文数字） | 2026-03-31：流通量77,049,290,538枚；储备资产公允价值$77,125,330,954 | [1] | 报告日2026-03-31，签署日2026-04-29 | 事实（一手） |
| USDC 储备构成明细（同一份报告） | Circle Reserve Fund合计$66,467,038,905（美国国债$24,913,211,699 + 隔夜逆回购$40,756,000,000 + 基金内现金$1,003,770,592，经时点调整净额后）；另有独立托管现金类资产（Other USDC Reserve Assets）$10,658,292,049 | [1] | 同上 | 事实（一手） |
| USDC 储备审验机构与频率 | Deloitte & Touche LLP，按月出具AICPA准则下的鉴证报告（非完整审计） | [2] | 页面标注约3周前更新 | 事实 |
| USDT（Tether）Q1 2026 储备总览 | 总资产约$191.7B，对应负债（流通USDT）约$183.5B，超额储备约$8.23B；单季净利润$1.04B | [3][4] | 报告覆盖2026年Q1，转述文章发布于2026-05-01 | 事实（二手转述BDO Italia鉴证报告，本工具未能取得tether.to上的原始PDF） |
| 【口径冲突】Tether"现金及等价物" vs "美国国债"两种表述指向相近但不完全一致的数字 | 来源A标签为"cash and cash equivalents"：环比从$147.2B降至$141.2B；来源B标签为"US Treasuries (direct+indirect)"：约占储备80%即约$141B | [3][5] | 均为2026年Q1数据 | 事实（两个标签不同，是否为同一资产分类未能确认，需以Tether官方PDF消歧） |
| 【口径冲突】Tether 黄金持仓 | 来源A："约$8B黄金"；来源B："$20B黄金"，两者相差约2.5倍 | [5][6] | 均标注为2026年Q1数据 | 事实（未消歧的冲突，未采信任一方） |
| USDC 2023年3月脱锚——起因 | Circle确认约$33亿美元储备资金存于已被接管的Silicon Valley Bank | [7] | 2023-03-11 | 事实 |
| USDC 2023年3月脱锚——最低价（不同来源口径不同） | CoinDesk数据博客（CCCAGG口径）：$0.8726；Decrypt/Chainalysis：$0.87；CoinMarketCap学院文章：$0.88；CoinDesk主站文章：$0.89 | [8][9][10][11] | 均报道2023-03-11当天 | 事实（价格发现在挤兑期间高度碎片化，不同数据源/交易所口径本就不同） |
| USDC 2023年3月脱锚——回到$1附近的时间 | 多来源报道于2023-03-13回升至约$0.99以上 | [12] | 2023-03-13 | 事实 |
| USDT 2022年5月脱锚——最低价（不同来源口径不同） | Medium/SimplePro：$0.94（2022-05-12）；Arcane Research转引：FTX交易所上$0.945；Crypto.com周报：$0.95（"周四"，即2022-05-12当周）；FXStreet：Coinbase上$0.96；Chainalysis转述文章：$0.97 | [13][14][15][16] | 事件发生于2022-05-12前后 | 事实（不同交易所/数据源口径不同） |
| USDT 2022年5月脱锚——恢复 | 多来源称次日（2022-05-13）已回到$1附近；另有CoinDesk文章称直至2022-07-20才首次进入此后两个多月未见明显波动的"稳定"状态 | [15][17] | 前者2022-05发布，后者2022-07-26发布 | 事实（两篇文章对"恢复"的定义不同：短期回到$1附近 vs 此后不再出现明显波动） |

**来源**
[1] https://6778953.fs1.hubspotusercontent-na1.net/hubfs/6778953/USDCAttestationReports/2026/2026%20USDC_Examination%20Report%20March%2026.pdf
[2] https://www.circle.com/usdc
[3] https://finance.yahoo.com/markets/crypto/articles/tether-publishes-attestation-q1-2026-172503645.html
[4] https://www.bankless.com/read/news/tether-publishes-reserve-attestation-for-q1-2026
[5] https://www.spark.money/tools/stablecoin-reserve-composition-comparison
[6] https://eco.com/support/en/articles/15182154-tether-usdt-reserves-attestations-and-risk-mechanics-in-2026
[7] https://www.cnbc.com/2023/03/11/stablecoin-usdc-breaks-dollar-peg-after-firm-reveals-it-has-3point3-billion-in-svb-exposure.html
[8] https://data.coindesk.com/blogs/market-analysis-silicon-valley-bank-circle-usdc
[9] https://decrypt.co/123211/usdc-stablecoin-depegs-90-cents-circle-exposure-silicon-valley-bank
[10] https://coinmarketcap.com/academy/article/explaining-the-silicon-valley-bank-fallout-and-usdc-de-peg
[11] https://www.coindesk.com/markets/2023/03/11/usdc-stablecoin-and-crypto-market-go-haywire-after-silicon-valley-bank-collapses
[12] https://www.coindesk.com/business/2023/03/13/usdc-stablecoin-regains-dollar-peg-after-silicon-valley-bank-induced-chaos
[13] https://medium.com/@SimplePro/stablecoin-depeg-how-1-usdt-stops-being-worth-1-878a9ff1ef0c
[14] https://capital.com/en-int/analysis/tether-price-prediction-will-usdt-go-up
[15] https://cryptocomdefi.substack.com/p/weekly-defi-update-2022-week19
[16] https://www.thearmchairtrader.com/luna-ust-stablecoin-analysis-bequant/
[17] https://www.coindesk.com/markets/2022/07/26/tether-finds-stable-dollar-peg-after-terras-collapse

---

## 5. 真实交易成本（Binance）

| 事实陈述 | 数值 | 来源 | as-of日期 | 类型 |
|---|---|---|---|---|
| 现货 Regular User 档 maker/taker 费率 | 0.100% / 0.100% | [1] | 本工具实时抓取官方费率页 | 事实（一手） |
| 现货 Regular User 档 + BNB抵扣25% | 0.07500% / 0.07500% | [1] | 同上 | 事实（一手） |
| 现货 USDC计价交易对 taker费率（未抵扣） | 0.095%（maker与非USDC对相同，标注为Standard） | [1] | 同上 | 事实（一手） |
| 现货 VIP1门槛 | 30日交易量 ≥ $1,000,000 且 持有 ≥ 5 BNB | [1] | 同上 | 事实（一手） |
| 现货 VIP9（最高档）maker/taker（未抵扣） | 0.011% / 0.023% | [1] | 同上 | 事实（一手） |
| USDⓈ-M合约 Regular User 档 maker/taker | 0.02% / 0.05% | [2][3][4] | 官方页面本工具抓取时表格为动态加载未取得数值；[3]标注2026-06-12，[4]标注2026-07-08，二者相互印证 | 事实（二手，多个独立来源一致） |
| USDⓈ-M合约 BNB抵扣幅度 | 10% | [3][4] | 同上 | 事实（二手） |

**来源**
[1] https://www.binance.com/en/fee/schedule
[2] https://www.binance.com/en/fee/futureFee（官方页面，本工具未能取得表格数值）
[3] https://trade-reclaim.com/en/blog/binance-fees
[4] https://comparedge.com/tools/binance/pricing

---

## 查不到 / 对判断重要但本次未获取的信息

1. **Binance BTCUSDT/ETHUSDT 当前完整维持保证金分层表**（各档名义价值区间、对应最高杠杆、维持保证金率、速算扣除数）。官方页面 https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin 表格为前端动态渲染，本工具的网页抓取拿不到JS加载后的数据；需要登录页面查看，或调用需要API Key鉴权的 `/fapi/v1/leverageBracket` 端点。这正是出口问题2要求你"自己查"的内容,本清单只能给到公式和入口,给不了具体数值。
2. **Binance USDⓈ-M合约完整VIP分层费率表**（VIP1–VIP9各档maker/taker）。同样因官方页面动态渲染,本工具只取得Regular档的二手印证数据,VIP分层数值未获取。
3. **Tether Q1 2026 BDO Italia鉴证报告原始PDF**。tether.to/en/transparency 页面为前端动态渲染,本工具未能取得可直接下载的原始文件链接,只能引用多家二手转述,且转述之间存在两处口径冲突(见上表)。
4. **一万元人民币等值资金分别买卖一次BTC和一个具体小市值币的实际来回总成本**。这个数字取决于下单时刻的实时盘口深度、滑点、当时费率档位,不是可以固定引用的静态事实——任何我现在给出的数字到你实际查的时候都可能已经过期,应在决策当下用交易所的预估滑点/深度工具现查。
5. **一家具体交易所现货与永续来回交易的综合成本量级对比**。同第4条,属需要实时计算的衍生值,未纳入本清单。
6. **USDT 2018年、2019年历史脱锚的具体最低价与确切日期**。仅在一篇二手文章([16])中见到"$0.94(2018)、$0.93(2019)"的转述,未找到可独立核实的一手价格数据源,未采信为独立条目。
7. **OKX/Bybit 与 Binance 资金费率结算频率、保证金分层的逐项对照表**。本次仅取得Hyperliquid的1小时结算频率作为单点跨所对照;搜索中见到OKX有自己的分层保证金调整公告,但未逐项核实其当前具体数值,未纳入表格。

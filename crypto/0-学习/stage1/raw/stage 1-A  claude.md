# 阶段1-A · T1材料包

> 角色：材料提供者（T1，全权委托）
> 主题：加密市场结构（与 A 股默认假设的差异）
> 编制日期：2026-08-06
> 范围：术语解释、英文官方文档的定位与摘要、合约规格/费率字段整理。
> 边界：不回答出口题，不核验路线图的差异表，不做候选、策略或 go/no-go 判断。

## 0. 证据状态

本次运行无法建立外部网络连接。下面的官方 URL 是供人工打开和留存页面的定位器；没有在页面上逐项看到的动态数值均写作 `未获取`。URL 本身不等于已核验的证据。

类型只使用三类：

- **事实**：术语/公式或材料状态的直接陈述；动态字段必须回到来源页面核对后才能进入个人笔记。
- **推断**：由已列规则进行的条件推导，不能当作来源原文。
- **假设**：为后续计算暂时设定的输入；本包不预设任何行情、费率、滑点或储备数值。

**假设（本包）**

- 无。未获取字段不以零、均值、历史常数或“约数”填充；后续计算若需要输入，须在独立表中注明来源、时点和假设。

## 1. 五个必学机制：术语材料

### 1.1 永续合约与资金费率

**事实（术语）**

- 永续合约没有预先约定的到期交割日。托管型衍生品平台通常按其规则在多空持仓者之间转移资金，并用指数价格/溢价相关规则形成合约价格靠近现货指数的约束。
- 资金支付额的基本字段是名义仓位价值和资金费率。符号、结算时刻、费率上下限、溢价指数的采样方法由具体交易所和具体合约规定。
- 在采用该记账口径的合约中，资金支付额可写为：`名义仓位价值 × 资金费率`；计费基数和正负号仍须以具体合约文档为准。
- “最新成交价”“指数价格”“标记价格”是不同字段。清算和未实现盈亏使用哪个字段，必须按交易所规则确认，不能用一条通用公式替代。
- 按多数永续合约规则，资金费率是多空持仓者之间的转移项；不能仅凭名称把它等同于交易所手续费收入，个别平台的结算处理仍需查条款。

**推断（仅由上面规则推导）**

- 只有在持仓、费率符号、结算时刻和名义价值都明确时，才能计算某一笔资金转移。
- 不同交易所、不同合约的结算频率或费率上限不同，不能把某个平台的费率周期移植到另一个平台。

**动态字段（未获取）**

| 字段 | 数值 | 官方定位 | as-of | 类型 |
|---|---|---|---|---|
| BTCUSDT 当前资金费率、下一次结算时刻 | 未获取 | [Binance Funding Rate History API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Get-Funding-Rate-History) | 未获取 | 事实 |
| BTCUSDT 当前资金费率周期、上下限、溢价指数窗口 | 未获取 | [Binance Futures Trading Rules](https://www.binance.com/en/futures/trading-rules/perpetual) | 未获取 | 事实 |
| OKX BTC-USDT-SWAP 当前周期、资金费率上下限 | 未获取 | [OKX Public Data API](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate) | 未获取 | 事实 |

### 1.2 清算机制

**事实（术语）**

- 初始保证金是开仓时为名义仓位提供的保证金；维持保证金是继续保留仓位所需的最低保证金。两者的定义、扣除项和计算单位由交易所规则决定。
- 常见分档记账形式是：`初始保证金 = 名义仓位价值 / 杠杆`；`维持保证金 = 名义仓位价值 × 维持保证金率 - 速算扣除额`。这是字段关系的整理，不是任何平台当前参数的代入结果。
- 标记价格通常由合约市场价格和一个或多个现货指数/基差字段构成；其用途包括未实现盈亏和清算触发。精确构成必须按合约文档核对。
- 逐仓模式把指定保证金隔离在单个仓位；全仓模式在账户或指定保证金资产范围内共享余额。共享范围、可否自动追加、清算顺序均属平台规则。
- 仓位档位（bracket/tier）可能改变允许的最大杠杆、维持保证金率和速算扣除额。清算价因此依赖仓位、保证金模式、账户余额、持仓方向、费用和平台当前档位。
- ADL（auto-deleveraging）是保险基金或清算流程不足时的风险分配机制。触发条件、排序字段、成交价和手续费处理以平台公告为准。

**推断（仅用于准备出口题，不是答案）**

- “10 倍杠杆跌多少清算”至少缺少交易所、合约、仓位档位、保证金余额、持仓模式、其他仓位、费用和标记价格定义等输入；缺一项就不能得到可复算的单一值。

**参数表（未获取）**

| 字段 | Binance BTCUSDT 永续 | OKX BTC-USDT-SWAP | Bybit BTCUSDT 永续 | 类型 |
|---|---|---|---|---|
| 最大杠杆 | 未获取 | 未获取 | 未获取 | 事实 |
| 维持保证金档位、费率、速算扣除额 | 未获取 | 未获取 | 未获取 | 事实 |
| 标记价格公式 | 未获取 | 未获取 | 未获取 | 事实 |
| 逐仓/全仓清算规则 | 未获取 | 未获取 | 未获取 | 事实 |
| ADL 触发与排序 | 未获取 | 未获取 | 未获取 | 事实 |

官方定位：[Binance leverage and margin](https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin)；[Binance USDⓈ-M Exchange Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information)；[OKX instruments](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments)；[Bybit instruments](https://bybit-exchange.github.io/docs/v5/market/instrument)。

### 1.3 CEX、DEX 与自托管钱包

**事实（术语）**

- 托管型 CEX 由平台维护撮合和账本。用户通常在平台账户中拥有余额记录以及按条款提出提现请求的权利，私钥由平台控制；资产隔离、客户财产权和破产清偿顺位不能由“放在交易所”四个字推出。
- 自托管钱包让用户控制签名密钥；链上余额和交易可公开验证，但密钥丢失、泄露、错误地址和恶意授权通常没有平台撤销路径。
- 多数链上 DEX 通过智能合约和链上交易执行交换，用户通常在签名时直接授权合约；除了价格和流动性风险，还要考虑合约、预言机、桥和密钥风险。
- Gas 是链上执行资源的计费单位；费用去向（例如验证者、区块构建者或链上协议）由具体链的规则决定。具体费用至少取决于链、交易所需的 gas、当时 gas price 和结算资产价格；不存在跨链通用的固定金额。

**动态字段（未获取）**

| 字段 | 数值 | 官方/公开定位 | as-of | 类型 |
|---|---|---|---|---|
| Ethereum 当前 gas price | 未获取 | [Etherscan Gas Tracker](https://etherscan.io/gastracker)；[Ethereum gas docs](https://ethereum.org/en/developers/docs/gas/) | 未获取 | 事实 |
| 某一笔 ETH 转账的 gas used、交易费 | 未获取 | 交易哈希对应的区块浏览器页面 | 未获取 | 事实 |
| CEX 客户资产隔离与破产处理 | 未获取 | 目标平台条款、托管协议和适用法律原文 | 未获取 | 事实 |

### 1.4 稳定币

**事实（术语）**

- 在本包讨论的 USDT/USDC 语境中，稳定币是以目标计价单位表示的链上代币；“锚定”是发行、赎回、做市和套利等机制共同形成的市场目标，不是保证任何时刻都等于目标价格的承诺。
- 储备报告、鉴证（attestation）和完整审计是不同文件类型。报告覆盖的时点、资产估值、负债口径、赎回资格和法律权利必须分别读取。
- 脱锚可能通过发行方赎回/暂停、储备资产流动性、银行或托管机构、交易所订单簿、链上池子和跨平台结算渠道传导。具体历史事件的原因要按事件时点的原始公告和市场数据逐项核对。
- USDT 与 USDC 的储备构成、发行/赎回资格、司法辖区和披露频率可能不同；不能只凭名称把二者视为同一种现金等价物。

**推断（不是历史事实）**

- 若市场参与者无法按预期速度赎回或转移代币，订单簿和链上池子的价格可能同时偏离目标；偏离幅度和持续时间需要事件数据，不能由储备比例单独推出。

**储备/事件字段（未获取）**

| 字段 | USDT | USDC | 官方定位 | as-of | 类型 |
|---|---|---|---|---|---|
| 流通量、总负债、储备资产逐项金额 | 未获取 | 未获取 | [Tether Transparency](https://tether.io/transparency/)（旧入口可能为 [tether.to](https://tether.to/en/transparency/)）；[Circle USDC Transparency](https://www.circle.com/en/transparency) | 未获取 | 事实 |
| 报告类型、报告日、鉴证机构 | 未获取 | 未获取 | 同上报告原文 | 未获取 | 事实 |
| 赎回资格、门槛、费用、暂停条款 | 未获取 | 未获取 | 发行方条款/客户协议 | 未获取 | 事实 |
| 历史脱锚最低价、时间、恢复路径 | 未获取 | 未获取 | 事件原始公告 + [CoinGecko](https://www.coingecko.com/) 或交易所历史行情 | 未获取 | 事实 |

### 1.5 真实交易成本

**事实（字段与计算关系）**

- 现货往返成本至少由开仓手续费、平仓手续费、买卖价差、成交滑点、充值/提现费用和可能的换汇成本组成。
- 永续往返成本还要加入资金费；若使用借贷或保证金，还要加入借款利息和清算相关费用。
- Maker/Taker 是订单与流动性的分类，不是账户等级；实际费率还可能受产品、VIP 等级、平台币抵扣、地区和活动条款影响。
- 费率表中的百分比必须先确认计费基数（成交名义金额、结算币种、是否按每腿计费），再做往返计算。

**推断（算术模板，不代入数值）**

```text
现货往返显性成本
= 买入成交额 × 买入费率
 + 卖出成交额 × 卖出费率
 + 买卖价差/滑点
 + 充值、提现及换汇费用

永续持仓期间成本
= 开仓手续费 + 平仓手续费
 + 各结算时点的名义仓位价值 × 当期资金费率
 + 借贷/保证金费用
 + 滑点及其他平台费用
```

**费率字段（未获取）**

| 字段 | Binance | OKX | Bybit | 官方定位 | as-of | 类型 |
|---|---|---|---|---|---|---|
| 现货 VIP0 maker/taker | 未获取 | 未获取 | 未获取 | [Binance fee](https://www.binance.com/en/fee/schedule)；[OKX fee](https://www.okx.com/fees)；[Bybit fee](https://www.bybit.com/en/help-center/article/Trading-Fee-Structure/) | 未获取 | 事实 |
| BTCUSDT 永续 maker/taker | 未获取 | 未获取 | 未获取 | 各平台官方费率页 | 未获取 | 事实 |
| 资金费率当前值/结算次数 | 未获取 | 未获取 | 未获取 | 各平台公开资金费率 API | 未获取 | 事实 |
| 提现、充值、借贷费用 | 未获取 | 未获取 | 未获取 | 各平台费用与产品条款 | 未获取 | 事实 |
| 某时刻 BTC 与小市值币的盘口深度/成交滑点 | 未获取 | 未获取 | 未获取 | 公开 order-book API；需记录时间、数量、方向 | 未获取 | 事实 |

## 2. 英文官方文档摘要定位

下表只给出需要阅读的原文和摘要字段。由于本次未能打开网页，`原文摘录` 均为 `未获取`；不能把标题或 URL 当成已核验内容。

| 主题 | 英文官方文档 | 应提取的原文字段 | 原文摘录 | 类型 |
|---|---|---|---|---|
| Funding rate | [Binance funding FAQ](https://www.binance.com/en/support/faq/what-is-funding-rate-in-binance-futures-360033525031) | funding formula、payment direction、settlement time、cap/floor | 未获取 | 事实 |
| Mark price / liquidation | [Binance perpetual trading rules](https://www.binance.com/en/futures/trading-rules/perpetual) | mark price inputs、maintenance margin、liquidation trigger | 未获取 | 事实 |
| ADL | [Binance ADL FAQ](https://www.binance.com/en/support/faq/what-is-auto-deleveraging-adl-and-how-does-it-work-360033525471) | ADL trigger、ranking、execution price | 未获取 | 事实 |
| Contract instrument fields | [Binance USDⓈ-M API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information) | tickSize、stepSize、contract status、brackets link | 未获取 | 事实 |
| OKX swap funding | [OKX funding rate API](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate) | fundingRate、nextFundingTime、method | 未获取 | 事实 |
| Bybit instrument/funding | [Bybit V5 market docs](https://bybit-exchange.github.io/docs/v5/market/instrument) | price/quantity precision、leverage filter、funding interval | 未获取 | 事实 |
| Gas | [Ethereum gas documentation](https://ethereum.org/en/developers/docs/gas/) | gas limit、gas used、base fee、priority fee | 未获取 | 事实 |
| USDT reserves | [Tether reports](https://tether.io/transparency/) | report date、asset categories、liabilities、attestation scope | 未获取 | 事实 |
| USDC reserves | [Circle transparency](https://www.circle.com/en/transparency) | reserve fund, cash, circulation, attestation scope | 未获取 | 事实 |

## 3. 待人工核对的事实提取表

格式：`事实陈述 | 数值 | 一手来源URL | as-of日期 | 类型`。这里的 `未获取` 是有意保留，不是估算值。

| 事实陈述 | 数值 | 一手来源 URL | as-of 日期 | 类型 |
|---|---|---|---|---|
| Binance BTCUSDT 永续的当前最大杠杆 | 未获取 | https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin | 未获取 | 事实 |
| Binance BTCUSDT 永续各仓位档位的维持保证金率与速算扣除额 | 未获取 | https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin | 未获取 | 事实 |
| Binance BTCUSDT 永续标记价格公式 | 未获取 | https://www.binance.com/en/futures/trading-rules/perpetual | 未获取 | 事实 |
| Binance/OKX/Bybit BTC 永续结算间隔与资金费率上限 | 未获取 | 各平台官方合约规则页 | 未获取 | 事实 |
| Binance、OKX、Bybit 现货与永续 VIP0 maker/taker 费率 | 未获取 | 各平台官方费率页 | 未获取 | 事实 |
| Tether 最近一期储备报告的资产、负债、流通量 | 未获取 | https://tether.io/transparency/ 或 https://tether.to/en/transparency/ | 未获取 | 事实 |
| Circle 最近一期 USDC 储备/流通量鉴证 | 未获取 | https://www.circle.com/en/transparency | 未获取 | 事实 |
| 指定时间的 Ethereum gas price 与一笔转账 gas used | 未获取 | https://etherscan.io/gastracker 与交易哈希页面 | 未获取 | 事实 |
| 指定时间、指定名义金额的 BTC 与小市值币 order-book 滑点 | 未获取 | 目标平台公开行情 API | 未获取 | 事实 |

## 4. 重要但本次查不到的信息

- 动态保证金档位、速算扣除额、最大杠杆和标记价格公式的当前版本。
- 各平台当前账户等级、地区、平台币抵扣和产品活动对应的实际费率。
- 资金费率的历史序列、结算时刻，以及某次持仓是否跨过结算时点。
- Tether/ Circle 最近一期报告的原始 PDF、报告范围、资产估值口径、赎回资格和法律权利。
- 历史脱锚事件的逐笔价格、交易场所、流动性、赎回/做市动作和时间线。
- 某一时刻不同资产订单簿的深度、成交量和实际滑点。
- CEX 客户资产隔离、再质押、托管实体和破产清偿顺位；这些不能由一般性术语推断。

## 5. 反驳材料：常见表述的失效条件

下表不是研究结论，也不是方向建议；它把需要区分的命题、反例入口和所缺字段分开列出。

| 常见表述 | 反驳材料/失效条件 | 类型 | 需要核对的证据 |
|---|---|---|---|
| “永续没有到期，所以没有持有成本。” | 没有到期日不等于没有资金费、手续费、借贷费、滑点或清算成本；缺少持仓时长、费率序列和成交记录时，成本仍未定。 | 推断 | 具体合约资金费率历史、费率表、订单簿快照 |
| “正资金费率就是看多，随后一定下跌。” | 费率符号描述某个结算规则下的转移方向；它本身不提供未来价格方向或反转时间。把符号直接翻译成预测，需要额外检验。 | 推断 | 费率公式、溢价指数、同时间价格与持仓数据 |
| “没有涨跌停就没有价格限制。” | 价格保护、风险限额、维护停机、提现暂停和 ADL 都是可能独立存在的控制项；是否存在、阈值和适用产品必须逐平台查原文。 | 事实/未核验 | 目标平台交易规则、风险控制和公告页面 |
| “链上账本公开，所以交易所负债和客户权利也透明。” | 链上转账不能直接证明 CEX 内部账本、客户资产隔离、再质押、托管实体或破产清偿顺位。 | 事实 | 平台条款、托管协议、破产文件和链上地址归属证据 |
| “稳定币就是现金。” | 代币目标价格、发行方赎回资格、储备资产、银行/托管渠道和暂停条款可能不同；缺少这些字段时不能把它当作同一法律或经济权利。 | 推断 | 发行方报告、条款、赎回记录和市场价格序列 |
| “费率表就是往返成本。” | 费率表只覆盖特定手续费字段；价差、滑点、资金费、提现/换汇和借贷费可能在表外。 | 事实 | 费率页、逐笔成交、盘口快照和资金费历史 |
| “BTC 深度好、小币滑点固定。” | 滑点随时间、订单方向、订单量、盘口状态和交易场所变化；没有同一时刻同一数量的 order-book 快照，不能比较或固定化。 | 推断 | 公开 order-book API 的原始响应和时间戳 |
| “10 倍杠杆的清算跌幅是一个通用百分比。” | 清算价还取决于标记价格、维持保证金档位、保证金模式、账户余额、其他仓位、费用和平台规则；输入不全时没有单一答案。 | 推断 | 指定交易所当前规则和完整账户/仓位输入 |

## 6. 对工作区原有草稿的证据标记

以下不是市场结论，只是材料状态标记：

| 原草稿内容 | 标记 | 原因 |
|---|---|---|
| 2026 年某季度 Tether 资产、负债、黄金、比特币等精确数值 | 暂不作为事实 | 本地没有对应官方报告快照；外部页面本次未获取。 |
| 由第三方费率站提供的 Binance/OKX 数字 | 暂不作为一手事实 | T1 模板要求官方来源；第三方页面只能作为待查线索。 |
| “历史上唯一一次脱锚”等全称断言 | 暂不作为事实 | 需要完整、可复核的历史价格数据和判定阈值；现有材料没有证明。 |
| 实时 gas、滑点、资金费率和年化换算 | 暂不作为事实 | 这些是时点数据或带输入假设的计算；原稿没有可复算快照。 |
| 把“建议登录/截图/选择某平台”等句子放进材料正文 | 移到流程层 | T1 材料只提供字段和来源，不替研究者决定工具或方向。 |

## 7. T1 交接边界

- **T2**：研究者逐条打开官方页面，记录访问时间，复制原文数值和页内位置；若与本表不同，以页面当时内容为准，并保留旧值及口径差异。
- **T3**：研究者本人脱稿回答阶段 1-A 的六道出口题。本包只提供术语和待填字段，不代答、不做结论。
- 本包没有预设任何费率、价格、滑点、储备或清算阈值假设；后续若要计算，假设必须在单独的计算表中显式登记。

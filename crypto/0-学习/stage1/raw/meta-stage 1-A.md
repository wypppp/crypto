# 阶段1-A T1 可审计事实清单

## 2. 永续合约与资金费率

- [事实] 资金费不是交易所收费，是交易者之间支付
- [事实] 方向：如果资金费率为正，多头向空头支付费用；如果为负，空头向多头支付费用。
- [事实] 结算时间：币安每日三次（UTC 时间）结算资金费率: 00:00 — 08:00 — 16:00
- [事实] 计算式：资金费 = 持仓规模 × 资金费率，示例 $5,000 × 0.0002 = $1.00 USDT
- [事实] 另一口径：资金费 = 头寸名义价值 × 资金费率，名义价值与 标记价格 × 仓位规模 挂钩
- [事实] 公式更新后：资金费率 (F) = [平均溢价指数 (P) + clamp(利率 - 溢价指数 (P), 0.05%, -0.05%)] / (8/N)
- [事实] OKX口径交叉验证：8 hours | 00:00, 08:00, 16:00

## 3. 清算与风控 - 维持保证金档位

- [事实] 清算触发价为标记价格
- [事实] 通用公式：维持保证金 = 名义持仓价值 × 维持保证金率 - 维持金
- [事实] BTCUSD_PERP（币本位永续）Tier1：maintMarginRatio 0.004 即 0.40%
- [事实] BTCUSD Quarterly示例：Position ≤10 BTC, 50x, Maintenance Margin 0.40%
- [事实] BTCUSDT（USDT本位）API示例档位：bracket 1 notionalCap 5000, notionalFloor 0, maintMarginRatio 0.01 即1%，initialLeverage 50
- [事实] 价格保护：当止损/止盈订单触达触发价格时，若最新成交价与标记价格之间的价差超过设定阈值，订单将会失效。
- [事实] ADL机制：币安采用队列方式，且对BTCUSDT/ETHUSDT有保证：持仓总量不超过100亿USDT则不发生自动减仓事件
- [推断] 10倍杠杆全仓做多BTC的清算跌幅无通用答案，取决于上述档位表、开仓价、账户余额、是否全仓有其他仓位盈亏。

## 4. 费用 - 口径冲突已定位

- [事实] 现货基准：Spot Trading Fee: 0.10% for both makers and takers
- [事实] 期货口径A：USDT-Margined 0.02% Maker 0.04% Taker
- [事实] 期货口径B：Regular User maker fee is 0.02% and taker fee is 0.05%，示例10,104 USDT市价单付5.052 USDT和
- [事实] 口径差异原因：口径A为Square汇总页未标注等级，口径B为官网FAQ明确Regular User等级，且VIP和BNB折扣会改变费率。
- [事实] 以太坊Gas：average gas fee has fallen from 72 gwei in 2024 to just 2.7 gwei as of March 12, 2025

## 5. 稳定币 - 最新可审计储备

- [事实] Tether Q4 2024：total assets $157.6 Billion, total liabilities $137.6 Billion, Reserves $143,704,755,547, liabilities $136,617,485,006, excess $7,087,270,541
- [事实] Q1 2025：total assets at least $149,274,515,988, total liabilities $143,682,673,588, tokens issued $143,678,070,758
- [事实] Q3 2025：reserves $181.2 billion, liabilities $174.4 billion, reserves include $135 billion Treasuries, $12.9 billion gold and $9.9 billion bitcoin，Other $14.6B secured loans, $3.9B other investments
- [事实] USDC：backed 100% by highly liquid cash and cash-equivalent assets，majority in Circle Reserve Fund (USDXX), an SEC-registered 2a-7 government money market fund，可含cash, short-dated US Treasuries and overnight US Treasury repurchase agreements
- [事实] USDC脱锚：sank to 87 cents from $1，约$3.3 billion tied up at SVB
- [事实] USDT脱锚：May 12 2022 traded at $0.92 per USD on Kraken, $0.95 on Binance.US；2023年6月15日低至 $0.996

## 6. 托管回收 - 口径差异

- [事实] FTX回收法币口径A：secured and customer claims 100% to 142%, overall 123% to 138%
- [事实] 口径B：recover between 118% and 142% of Petition claims
- [事实] 加密计价口径C：real crypto recovery 9% to 46%
- [事实] 差异说明：A/B分母为破产申请日法币索赔额，C分母为当时持有币数量按当前币价折算。

## 7. 仍未获取、但对判断重要的信息

1. 具体清算价计算中 Maintenance Amount 的数值表 - 需对应档位表一起读取。
3. 价格保护带具体阈值百分比（不同币种不同）- 官方仅描述为 set threshold，未给出统一数值。
4. ADL队列评分公式中的盈亏/杠杆权重 - 官方描述为queue-based methodology，但具体分数未公开。
5. 1万元小市值币的真实滑点分布 - 需盘口历史快照，非费率表可得。

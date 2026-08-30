# Robinhood CCA ≤10m：真实获配与24小时退出容量

> 主结果使用真实 bid 的 submitted/refund/tokensFilled；24小时容量 witness 使用真实整笔 Swap 的平均执行价，并扣100 bps与该笔交易的全部真实 gas。

## 覆盖

- 短拍卖：29；投标 492；已退出 455；正获配且普通公开 444。
- 未退出、保持未知：37。
- accepted cost >= $100 的普通公开 allocation：213。

## 全部普通公开 allocation

- accepted cost USD P10/P50/P90：$4.29 / $93.92 / $572.44。
- accepted/submitted P10/P50/P90：2.60% / 46.91% / 100.00%。
- accepted >= $100 且有24h 5x容量 witness 的不同 auction：8；其中洪水后：1。
- 选定 witness 中 tx.from 与 bidder 相同且单笔覆盖该 owner 总获配的诊断案例：2 笔 / 2 个 auction（非穷尽钱包历史）。
- leave-one-auction-out：28/29 仍通过；唯一失败是删掉洪水后单例 `0xa0266f6b55e610a6e5ff563fbc00a63d9b9626d0`。

## 最后25%时间的真实邻近资金档

| submitted目标 | 有匹配auction | accepted P50 | acceptance P50 | 24h 5x witness | 洪水后匹配/命中 |
|---:|---:|---:|---:|---:|---:|
| $100 | 9 | $87.58 | 80.69% | 7 | 0/0 |
| $300 | 10 | $286.55 | 82.82% | 3 | 1/1 |
| $500 | 5 | $485.00 | 88.33% | 1 | 0/0 |

## 分层审计

| 分层 | auctions | observed 5x | accepted >=$100 witness auctions |
|---|---:|---:|---:|
| 周: 2026-W29 | 14 | 8 | 3 |
| 周: 2026-W30 | 3 | 3 | 1 |
| 周: 2026-W31 | 6 | 5 | 3 |
| 周: 2026-W32 | 1 | 0 | 0 |
| 周: 2026-W33 | 3 | 2 | 1 |
| 周: 2026-W34 | 1 | 0 | 0 |
| 周: 2026-W35 | 1 | 0 | 0 |
| 募资: [1,2) ETH | 16 | 6 | 1 |
| 募资: [2,5) ETH | 13 | 12 | 7 |
| 时长: 121-300s | 5 | 2 | 1 |
| 时长: 301-600s | 10 | 6 | 4 |
| 时长: <=120s | 14 | 10 | 3 |
| 结局: False | 11 | 0 | 0 |
| 结局: True | 18 | 18 | 8 |

## 当前裁决

- gas前历史物理门：True。
- gas审计完整：True；gas后历史物理门：True。
- 市场容量 witness 是同规模真实成交下界，不等于我们的额外 bid 能以同样结果成交。

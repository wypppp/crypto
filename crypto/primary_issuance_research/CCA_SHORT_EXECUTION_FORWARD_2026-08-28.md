# Robinhood CCA ≤10m：历史执行审计与前向观察协议

> 状态：在新增 allocation、24h swap 和前向结果返回前冻结。  
> 性质：公开只读研究，不提交投标、不发送交易、不授权投入本金。  
> 机制版本：以每个 auction 的实际 factory/version 为准；v2.0/v2.1 的连续时间加权清算不得简化为期末单价拍卖。

## 1. 决策问题

本阶段只回答两个问题：

1. 普通公开钱包在 ≤10 分钟的物质性 CCA 中，是否真实取得过 $100/$300/$500 量级的可用分配？
2. 该分配是否在迁移后 24 小时内存在整仓、扣执行损耗后达到 5x 的退出证据？

即使物理执行通过，也不等于发行前判断能力成立。判断增量只允许由冻结后的前向评分回答。

## 2. 历史母体

从既有 104 个 Robinhood 原生币、成功迁移且 `currencyRaised >= 1 ETH` 的实质性 CCA 中，机械选择：

- `auction_duration_seconds <= 600`；
- 保留所有价格结局，包括未触及 5x；
- 预期冻结母体为 29 个，若重跑数量不同必须先解释新增链上事件或数据错误。

不得按赢家、峰值持久性、当前流动性或钱包结果缩小母体。

## 3. 真实投标与获配

逐 auction 收集完整 `BidSubmitted`、`BidExited`、`TokensClaimed` 事件，并按 bid id 连接：

- submitted native amount；
- refund；
- actual accepted cost = submitted - refund；
- tokens filled/claimed；
- 提交时点相对拍卖进度；
- max price 与最终 clearing price（可得时）；
- owner 是否为 tokens/funds recipient；
- validation hook；
- owner 在最新块是否 EOA-like；
- 事件和交易 gas payer。

只有已经出现 `BidExited` 且 tokens filled > 0 的 bid 可进入获配结果。尚未 exit 的 bid 保留为 unknown，不记零。

“普通公开”主层要求：零 validation hook、owner 不是项目 tokens/funds recipient、EOA-like。其他 bid 保留并单列。

### 3.1 固定资金档

用提交时 ETH/USD 标记临时占用本金，报告全部分布，并冻结三个邻近档：

- $100 档：submitted USD ∈ [$75, $175]；
- $300 档：submitted USD ∈ [$200, $400]；
- $500 档：submitted USD ∈ [$425, $650]。

每个 auction/资金档的“近结束自然实验”取拍卖最后 25% 时间内、最接近目标美元额的一个普通公开 bid；并列时取更晚者。没有符合 bid 时保持缺失，不放宽区间。

这是真实参与者自然实验，已经包含其自身对实际清算路径的影响；它不是“我们额外插入同一笔 bid”的精确反事实。

## 4. 24 小时退出证据

对29个池收集 `[migration, migration+24h]` 全部 Uniswap v4 `Swap` 日志。

每个真实获配 bid 报告两层证据：

1. **市场容量 witness**：存在一笔真实 token→native swap，其 token 数不少于该 allocation，且整笔平均 native out 在扣 100 bps 后不少于 `5 × actual accepted cost`；
2. **同钱包直接退出**：swap 交易 sender 与 bid owner 相同，累计卖出量与 allocation 一致（容许最小单位舍入），并按真实 proceeds、gas 和额外 100 bps 计算净倍数。

市场容量 witness 只证明当时市场吞吐过同等规模，不宣称该 bidder 必然能得到相同报价。同钱包完整退出是更强证据。

所有未命中、无 swap、未退出和缺失 RPC 结果必须分别保留，不能合并为零或从分母删除。

## 5. 历史结果输出

至少输出：

- 29个 auction 的 bid/exit/claim 覆盖率；
- 普通公开实际 accepted cost 与 submitted/accepted 比率分布；
- 三个资金档的 auction 覆盖数、accepted cost、token allocation；
- 每档24h市场容量 witness 数和同钱包完整退出数；
- 按周、募资额和拍卖时长分层；
- 赢家与非赢家均报告；
- 当前可复现的直接案例与 leave-one-out 集中度。

历史审计的物理通过门：至少两个不同 auction 存在普通公开、accepted cost >= $100、24h 内同钱包或严格市场容量 witness 的净 5x；且至少一个证据来自 W31 供给洪水之后。否则历史可执行性仍为“单例/旧 regime”，不得进入资金讨论。

## 6. 前向观察

观察器从冻结后的链上高度开始，追加而不覆盖地记录每个新 CCA：

- 创建块、创建时间、factory/version、token、auction 参数；
- 创建至开拍、拍卖时长、validation hook；
- 截止当时可见的项目资料 URL/哈希；
- 募资要求、token 供应、floor/tick、公开竞价状态；
- 所有 bids、最终获配、迁移和24小时 swap 结局。

### 6.1 前向评分

在知道 auction 结局前冻结0–2分的五项快速评分：

1. 身份与团队可验证性；
2. 已有产品/代码/使用证据；
3. 发行估值相对可核验资产或收入；
4. token 权利、团队锁仓与稀释；
5. 初始募资/流动性结构。

缺资料记0，不允许在结局后补回当时不可见的信息。总分只比较全参加基线与事前 top 1/3；不训练高维模型。

### 6.2 前向解封

累计20个新的 ≤10m、成功迁移、`currencyRaised >= 1 ETH` auction，或运行12周，以较晚者为准。主纸面仓位为$300档自然实验；没有邻近真实 bid 时记“无法估计”，不得用 auction VWAP替代。

前向通过至少需要：

- 不少于10个可估计的$300档自然实验；
- 至少两个不同 auction 出现 accepted cost >= $100 的24h净5x容量 witness；
- W31后/冻结后账户顺序回放总净利润为正；
- top 1/3评分的账户收益高于全参加基线，且不是由单一 auction 独占全部正利润。

前向不通过则关闭CCA ≤10m的“综合判断型公开参与”版本；通过后才允许请求使用者决定是否进行极小额真实投标验证。

## 7. 禁止事项

- 不用日线 high、当前池深或 auction-wide VWAP替代 bidder-specific执行；
- 不把 `$投标额 / 总募资` 当作清算价冲击；
- 不按事后赢家选择钱包或价格上限；
- 不把未成熟非赢家记为永久失败；本协议的独立终点是固定24小时；
- 不在历史结果后改变美元档、最后25%窗口、5x、24小时或100 bps；
- 不使用真实资金，直到前向门通过并单独取得使用者授权。


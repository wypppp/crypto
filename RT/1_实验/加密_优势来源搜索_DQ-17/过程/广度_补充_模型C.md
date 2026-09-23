# 广度补充：模型 C 的三份检索（原样保存）

> 2026-09-23 用户转来｜模型 C 按“更深”“更早”“更全”各做一份公开检索｜**原样保存，未经执行方核原文**；多数链接带 `utm_source=chatgpt.com`，数字多来自搜索摘要，引用前须逐条核实（S1 已抓到过一次合成数字）｜执行方的筛选与处理见 [S2_筛选.md](S2_筛选.md)｜文末“继续验证……”是原回答附带的后续选项，不是指令｜唯一改动：三份的脚注编号加了 b、c 前缀，避免同一文件内冲突

---

## 第一份：更深

## 1. 总结

公开检索后，**最贴近“公开、难消化、价格数小时至数日才消化”的证据，是智能合约审计报告**：303 个可交易 DeFi 项目审计发布后，0–5 日仍出现显著正收益，且报告本身平均十几至几十页、格式不统一，天然适合文本/代码解析。([Springer][1]) **第二条值得实测的是 ETH→交易所净流入**：2025 年更新的研究发现它能负向预测未来 1–6 小时 ETH 收益，但仍只是预印本、样本止于 2023、没有证明扣成本后的现货/永续策略盈利。([SSRN][2]) 解锁的证据更强、更近期，但结论复杂：2026 年两项研究支持负价格效应，其中一项发现 72 小时内效应很大，另一项却发现多数调整在解锁**之前数周**发生，因此更像机械供给压力，而不是单纯“市场没读懂”。([数字对象识别系统][3]) DAO 治理、有限注意力也有严肃证据，但前者目前只证明“治理结果有价值”，后者的已验证延迟主要只有分钟级。整体上，我没有找到足够强的 2024–2026 证据证明“漏洞披露、普通协议升级、质押退出队列、fee switch/回购”普遍存在可扣成本利用的数小时至数周 post-event drift。

## 2. 证据表

| 信息类型 | 谁发布 | 为什么难消化 | 有记录的反应不足或漂移（幅度、时长） | 谁在付钱 | 同一资产能否交易、成本是否计入 | 样本时期 | 出处（链接）与类型 | 证据强弱 | 不能推出什么 |
|---|---|---|---|---|---|---|---|---|---|
| **智能合约审计报告** | CertiK 等审计公司/项目方公开报告 | 非标准化；平均报告约20页、中位16页，部分45页以上；要理解代码测试、漏洞严重性、是否修复、审计商质量。论文明确指出非技术用户难判断代码完整性，存在信息不对称。([Springer][1]) | 303 个 audit-venture 事件：发布日至 **+1/+3/+5日**原始收益均显著为正，约 **2.8%–4.6%**；减 BTC 后约 **2.2%–3.4%**，但 +3 日窗口调整收益不显著。([Springer][1]) | **推断**：没有及时找到/读懂报告、仍愿意卖出的现有持有人或做市流动性；论文没有识别具体交易对手。 | 303 个事件都有公开价格，故至少现货层面可交易；永续/借币做空未系统核验。**未计手续费、滑点。** | 审计2017–2023H1；论文2024 | [Bourveau et al., Review of Accounting Studies 2024](https://link.springer.com/article/10.1007/s11142-024-09834-8?utm_source=chatgpt.com)；同行评审论文 | **较强**：直接以“报告发布日期”为事件；但价格子样本偏向大项目 | 不能证明2024–26仍存在同样幅度；不能证明收益来自“读懂具体漏洞”而非审计本身的认证/信号效应；不能直接得到可交易分类器 |
| **代币解锁：解锁后** | 项目 vesting 文档/合约；研究者整理 | 日期本身简单，真正复杂的是**解锁额/流通盘、token age、流动性、recipient、实际卖出与否** | 2026 预印本：52 个 Binance 上市币解锁（2023–25），**46/52 在72小时内下跌，均值 −16.97%**；同样88.5%跑输BTC。([数字对象识别系统][3]) | 最直接是解锁后新供应的边际买家及未对冲老持有人；作者解释为供给冲击，但仍属相关性 | Binance-listed ⇒ 现货可交易；并非全部确认有永续/借币。**未见完整交易成本模型。** | 2023–2025 | [Kim 2026, SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6632838&utm_source=chatgpt.com)；预印本，公开 replication data/code | **中**：非常近期、72h明确，但仅52例、未同行评审 | 不能断言这是“信息复杂度导致的延迟”；不能把 −16.97% 当可实现策略收益 |
| **代币解锁：提前定价** | 同上 | 同上 | Tokenomist 236 次事件：+1月 matched-peer 中位 **−4.85%**；但早期币约 −16%，成熟币无显著效应。最关键的是**解锁前1个月已经 −14.7%、前2周 −9.1%**；其自己的“提前做空BTC对冲”测试未过关。([Tokenomist Research][4]) | 机械性新增供应面对薄流动性；不是必须有人“没读懂” | underlying schedules公开，但研究使用Tokenomist整理数据；交易成本、借币成本、衍生品可得性**未建模**。([Tokenomist Research][4]) | 解锁 2024-06～2026-03 | [Tokenomist 2026研究](https://insights.unlocks.app/do-token-unlocks-crash-prices/?utm_source=chatgpt.com)；公开方法的行业研究 | **中**；近期且有matched-peer/age-match，但单一市场周期、约22个子组检验 | **尤其不能推出“等到解锁当天再做空”**；实际上这是对简单 post-event-drift 假说的反证 |
| **ETH→交易所净流入** | 公链实时产生；交易所地址标签由数据商/研究者识别 | 必须识别交易所地址、净掉内部转账、聚合时间窗；“进交易所≠卖出” | ETH exchange net inflow 对未来 **1、2、3、4、6小时 ETH 收益均为负向预测**；论文还做OOS检验。公开摘要没有给出一个可安全解释为“每次事件收益”的统一幅度。([IDEAS/RePEc][5]) | **推断**：链上供给已向交易场所移动，但价格尚未完全调整时仍持多头/接买盘的参与者 | **ETH本身**可交易，现货和永续均高度可得；研究还测试ETH期权策略。但没有找到现货/永续扣手续费、滑点、funding后的净策略结果 | 2017-12～2023-01；论文2024/25更新 | [Chi, Chu & Hao, SSRN/arXiv](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4630115&utm_source=chatgpt.com)；预印本 | **中**：与“小时级公开链上信息”高度吻合；但样本旧、未同行评审 | 不能推出2026仍有效；不能把 USDT→交易所预测 BTC/ETH 当成“同一资产信号”；BTC自身流入大多没有收益预测力 |
| **DAO治理提案结果/复杂条款** | Aragon/DAOHaus/项目治理论坛及链上投票 | 提案可长且技术化；需要判断资金、参数、治理权、实施方式，投票结果又可能临界 | 26,363项提案、457个DAO；利用接近50%门槛的 close-call RDD，**通过提案令投票当日 DAO token 日收益约增加4.7%**。([Aisberg][6]) | 未识别；可能是没有实时评价提案价值的边际持币者/交易者 | 有价格数据的DAO token可现货交易；衍生品可得性未系统报告；**成本未计** | 2020-08～2024-03 | [Lo Monaco, Momtaz & Vismara, Economics Letters 2025](https://www.sciencedirect.com/science/article/pii/S0165176525000709?utm_source=chatgpt.com)；同行评审/RDD | **对“治理信息有价值”强；对“漂移”弱** | 它证明的是**当日**反应，不证明通过后几小时/几天继续漂移；也没有把 fee switch、参数变更等提案单独拆出来 |
| **有限注意力：币间信息扩散** | 市场价格本身反映共同冲击 | 投资者不能同时跟踪全部币；共同信息先进入BTC等注意力高的币，再向其他币扩散 | Binance前30高成交币：其他币滞后收益能预测目标币，作用延续**最多约10分钟**；工作论文版本报告OOS long-short **日收益2.16%，已计交易成本**。([科学直接][7]) | 注意力较低、反应较慢的小币交易者 | Binance现货；论文建立long-short组合并称已计交易成本 | 2019-03～2021-04；正式发表2024 | [Guo et al., JEDC 2024](https://www.sciencedirect.com/science/article/abs/pii/S0165188924000551?utm_source=chatgpt.com)；同行评审 | **机制证据强，与你目标匹配度中低** | 不是长文本/代码信息；延迟只有分钟级；2019–21结果不能假定在2026仍存在 |
| **空投/硬分叉后的机械分配** | 项目/链公开规则 | 要估算snapshot、分配价值、接受者抛售及替代效应 | 较老研究的67次事件：公告本身无显著效果；**实际分发日 parent coin立即约 −4.65%**，另一版本报告5日CAAR约 −12.29%。([SSRN][8]) | 获得免费新币后重新配置资产的领取者及承接parent coin的买方；更接近机械替代效应 | parent coin有价格数据；空/永续可得性和成本未处理 | 主要早期加密样本，论文2021 | [Liebi, Raining Cryptos, SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3918432&utm_source=chatgpt.com)；工作论文 | **弱—中**：效应清楚但过旧、非近期独立复现 | 不能证明现代复杂airdrop规则存在同类优势；也不能证明announcement后慢消化 |

## 3. 查了但没找到足够证据的方向

* **Fee switch / 回购 / 销毁 / tokenomics 改革**：找到大量单案例，没有找到满足你标准的近期、大样本 post-event-drift 研究。例如 Uniswap 2025-11-10 的 UNIfication 明确包含 protocol fee→UNI burn 和一次性100M UNI burn；当天 UNI 已约涨30%，更像快速反应而非慢消化。官方条款在此：([Uniswap Labs][9])；30%只是新闻线索，不作为学术证据。([The Block][10])
* **协议升级 / hard fork / 普通代码变更**：2026 年同行评审研究反而发现 fork **没有显著平均收益效应**，只是波动率提高并持续约3天。([科学直接][11])
* **漏洞披露本身**：找到大量 hack 后价格研究和审计研究，但没找到近期大样本证明“漏洞/patch公开 → 尚未被利用 → 几小时后才持续跌”的可交易漂移。2026 JAE 的4000+ DeFi协议研究也主要研究 audit/breach，而非发布日期后的交易策略。([科学直接][12])
* **ETH 质押/解押队列**：退出队列确实把潜在供应分散到未来数日至数周，但“退出≠卖出”；检索到的研究主要做供应预测，没有可靠论文证明 queue 长度单独预测未来 ETH 收益。([GSR][13])
* **巨鲸单笔转账**：较可靠论文只支持分钟级反应，而且结论偏向“市场能辨认转账性质并迅速定价”；2,132笔≥500 BTC样本主要在事件后15分钟内反应，不是你要的小时—周慢消化。([科学直接][14])
* **稳定币供应总量变化**：找到稳定币流入交易所→BTC/ETH收益的证据，但这是**跨资产信号**；没有找到足够新的、同一资产、扣成本后的“稳定币供应扩张→未来收益”结果。

## 4. 用过的检索词

`crypto post-event drift public information`；`cryptocurrency underreaction investor attention`；`smart contract audit report release token returns event study`；`DeFi audit market reaction`；`token unlock event study abnormal returns 2024 2025 2026`；`token unlock 72 hour Binance`；`vesting schedule price drift crypto`；`DAO governance proposal token returns regression discontinuity`；`fee switch governance proposal token returns`；`token buyback burn event study crypto`；`protocol upgrade hard fork return event study`；`vulnerability disclosure crypto token price`；`exchange inflows predict cryptocurrency returns`；`ETH net inflows 1 hour returns`；`stablecoin exchange inflow future BTC ETH return`；`large Bitcoin transfers event study`；`staking withdrawal queue ETH returns predictability`；`Shapella withdrawal sell pressure event study`；`crypto airdrop abnormal returns event study`；`limited attention cryptocurrency slow information diffusion`；`cross-cryptocurrency return predictability transaction costs`。

**从“下一步最值得花很少成本做证伪”的角度，这轮检索把候选明显压缩到了两个：①审计报告/安全报告的文本与代码语义；②ETH交易所流入中比简单净流入更难处理的“来源/目的/实体类型”。** 解锁可以保留，但应测试“复杂解锁条款＋实际可卖供给”，而不是再测一个朴素的“解锁日做空”。

继续验证：细化 ETH 交易所流入信号；把审计报告做成事件研究方案。

[1]: https://link.springer.com/article/10.1007/s11142-024-09834-8
[2]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4630115&utm_source=chatgpt.com
[3]: https://doi.org/10.2139/ssrn.6632838?utm_source=chatgpt.com
[4]: https://insights.unlocks.app/do-token-unlocks-crash-prices/
[5]: https://ideas.repec.org/p/arx/papers/2411.06327.html?utm_source=chatgpt.com
[6]: https://aisberg.unibg.it/retrieve/10a7b3a5-9af2-4539-80e5-97088c0961d5/Lo%20Monaco%20Momtaz%20Vismara%20ECONLET25%20Distributed%20governance%20and%20value%20creation%20in%20decentralized%20autonomous%20organizations%20Evidence%20from%20a%20regression%20discontinuity%20design.pdf
[7]: https://www.sciencedirect.com/science/article/abs/pii/S0165188924000551?utm_source=chatgpt.com
[8]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3918432&utm_source=chatgpt.com
[9]: https://blog.uniswap.org/unification?utm_source=chatgpt.com
[10]: https://www.theblock.co/news/defi/2025-11-10-uni-token-soars-26-uniswap-labs-foundation-propose-fee-switch-activation-378257?utm_source=chatgpt.com
[11]: https://www.sciencedirect.com/science/article/pii/S1062976925001310?utm_source=chatgpt.com
[12]: https://www.sciencedirect.com/science/article/pii/S0165410126000546?utm_source=chatgpt.com
[13]: https://www.gsr.io/insights/enabling-staked-eth-withdrawals-shapella?utm_source=chatgpt.com
[14]: https://www.sciencedirect.com/science/article/abs/pii/S1544612320304438?utm_source=chatgpt.com

---

## 第二份：更早

## 1. 总结

检索后的结论是：**我没有找到一条同时满足“2024–2026、独立/高质量证据、公开合法信号、秒级个人可执行、并明确测出 1/10/60 秒剩余收益”的已证优势。** 最值得继续做原始数据验证的是 **Bithumb 首次 KRW 上币公告 → 已在其他场所交易的同币**：2026 年公开项目出现很大的分钟级效应，但样本仅 8 个、未扣成本，而且完全缺失秒级价格路径。([GitHub][b1]) 第二个值得调查的是 **Robinhood“实际开放交易”状态早于正式公告**：2026 年司法部案件文件称通常可早至约 1 小时，但合法公众如何实时捕获这一状态、价格还剩多少反应，尚无研究。([司法部][b2]) 相反，纯 CEX/DEX 跨场所领先在 2026 年已进入 **100–800 ms** 量级，基本不符合你的秒级约束。([Binance][b3])

## 2. 证据表

| 信息类型 | 谁发布 | 观察渠道 | 有记录的反应时滞与剩余幅度 | 排他性 | 能否在同一资产交易、成本是否计入 | 样本时期 | 出处（链接）与类型 | 证据强弱 | 不能推出什么 |
|---|---|---|---|---|---|---|---|---|---|
| **Bithumb 首次 KRW 上币** | Bithumb | 官方韩文公告有秒级时间戳；研究项目用官方 Telegram → Bybit | n=8：公告所在 **1分钟K** 收盘已 +3.94%～+18.75%；≤10m peak均值 +13.81%，+10m close均值 +8.61%。**1s/10s/60s均未测**。([GitHub][b1]) | 高度速度敏感，但不能证明第一名全吃；+10m仍高于“公告分钟开盘”不等于10m后仍可赚钱 | 同币 Bybit spot；**未计手续费/滑点** | 2026，Bithumb 90日，21公告中仅8个已在Bybit可交易 | GitHub公开方法/数据来源说明，**线索** ([GitHub][b1]) | 不能证明秒级个人能获得这些收益；入场价是公告分钟 open，是明显上界；n=8且无独立复现 | |
| **Upbit KRW 上币** | Upbit | 官方公告；自 **2026-08-31** 新增实时 Announcement WebSocket，需认证，官方明确不同渠道到达时间可能不同。([업비트 개발자 센터][b4]) | 同一上述项目 n=28：≤10m peak均值 +1.19%；+10m仅 +0.13%，13/28为正；未发现公告分钟 spike。([GitHub][b1]) | 即使存在速度竞争，该样本已几乎无经济余量 | 同币 Bybit；未扣成本 | 2026，180日 | 官方文档 + GitHub线索 | **渠道证据强；alpha证据反而偏负** | 新 WebSocket 发布后是否改变捕获速度、2026-08以后是否有新效应，尚无样本研究 |
| **“第一家韩国大所”而非重复上币** | Bithumb/Upbit | 韩文原始公告 | 同一项目4个重合币：先发生的 Bithumb peak +4.85%～+19.91%，之后 Upbit peak仅 +0.16%～+2.09%。([GitHub][b1]) | 信息新颖性可被第一事件消耗；不是永久可共享 | 同币其他CEX | 2026 | GitHub，线索 | **中低；但机制很值得验证** | n=4，不能推出“Bithumb天然优于Upbit”；也可能只是“首次重大韩国上市” |
| **Robinhood：实际可交易状态早于正式公告** | Robinhood；事实见美国司法部投诉书 | Robinhood Crypto交易可用状态；自动化公开观察方式**未核实** | DOJ投诉书称，资产通常可能在正式公告前**最多约1小时**已经可交易，并称价格压力常在公告前出现。无1/10/60s幅度。([司法部][b2]) | 若“可交易状态”公开给所有普通用户，则不是第一名全吃；但反应可能逐渐消耗 | 同币可在 Hyperliquid perp 等交易；成本未研究 | 2025–2026 | DOJ投诉书/官方 ([司法部][b5]) | **时间结构：中强；可交易edge：弱/待核实** | 案件中的获利来自**非公开内幕信息，不能复制**；只能据此提出“公开可交易状态是否比公告早”的合法测试 |
| **USDT 大额增发** | Tether链上事件；Whale Alert传播 | 公链/公开提醒 | 同行评审论文：每增发 $1B，OLS BTC累计反应约 **5m +0.24%、10m +0.38%、15m +0.51%、30m +0.68%、60m +0.57%**；说明5→30m反应仍在累积。([科学直接][b6]) | **非明显 winner-take-all**；历史上是分钟级扩散 | BTC可直接交易；未扣交易成本 | 2014–2021 | *Finance Research Letters*，论文 | **历史中强；当前弱** | 不能证明2024–2026仍存在；没有1/10/60秒数据；关系并非无条件稳定 |
| **Binance → Hyperliquid/Lighter 永续价格发现** | 市场成交本身 | 三所逐笔公开成交 | 29资产、截至2026-02-26的16天：Binance领先HL约 **600–800ms**；Binance与Lighter约 **100ms**；29/29 Binance领先HL。([Binance][b3]) | **高度排他**；陈旧报价被IOC套利者/做市商在1–2个block内吃掉 | 同币perp可交易；未给净手续费后收益 | 2026 | PANews/公开方法行业研究 | **中强，且是反证** | 不能认为“有700ms lag=个人能赚钱”；你的秒级系统大概率已经晚 |
| **CME BTC期货 → 加密永续** | 市场价格 | CME与Binance/Bybit等 | 官方申报中的TSLL：CME领先 Binance **3.07s**、Bybit **5.13s**、BitMEX **7.23s**、Huobi **2.34s**、OKEx **3.47s**。([thefederalregister.org][b7]) | 高度排他、典型速度竞争 | BTC对应perp可交易；未测交易净收益 | 2017–2021 | Federal Register/SEC材料，官方 | **历史强；当前弱** | 不能外推到2026；没有“第1秒之后还剩多少bp” |
| **美国BTC ETF价格 → BTC spot** | ETF市场 | ETF与Bitstamp 5分钟价格 | 2024-01-11～10-11；同行评审研究的ILS称 IBIT/FBTC/GBTC 等流动ETF对BTC spot约 **85%时间占价格发现优势**；只有5分钟粒度，无剩余bp。([数字对象识别系统][b8]) | 连续价格发现，不是离散公告；会受套利竞争 | 可以只交易BTC；研究未做策略成本 | 2024 | *Computational Economics*，论文 | **中** | 不能推出看到ETF上涨后买BTC有正EV；5分钟采样远不足以确定秒级延迟 |
| **代币解锁** | 项目/合约预定计划 | 公告、链上、unlock日历 | 2026预印本：52个Binance资产解锁，46/52在72h内为负，平均 **−16.97%**。([数字对象识别系统][b9]) | 非排他；事件日期通常提前已知 | 同币可交易；未计策略成本 | 2023–2025 | SSRN预印本，公开数据 | **事件效应中；“更早edge”弱** | 没有分钟/秒级反应；更重要的是信号预知，不能证明“解锁发生这一刻”产生新信息 |
| **一般大所listing效应** | Binance/Coinbase/OKX/Bybit/韩所等 | 公告+价格 | The Tie 2026覆盖1,844事件，发现价格效应越来越**前置于正式上线**；但它只有日频且**没有公告日期字段**。([The Tie][b10]) | 无法判断秒级排他性 | 同币可交易；非交易策略研究 | 2023–2026-06 | The Tie，公开方法行业研究 | **背景证据中；秒级证据弱** | 不能用于估算公告后1/10/60s收益；也不能区分公开公告与泄露/内幕提前交易 |

## 3. 查了但没找到合格证据的方向

* **Binance/OKX/Bybit/Hyperliquid 新现货或新永续公告**：找到大量个案和营销型“几秒涨20%”材料，但没找到 2024–2026 年公开方法、足够样本、同时报告公告后 **1s/10s/60s** 横截面的可信研究；不把它们当证据。
* **下币公告**：2026 年同行评审研究确认 Binance 下币具有明显风险并研究了104次公告，但重点是提前预测下币，不是公告后的秒级价格路径。([Wiley Online Library][b11])
* **韩语先于英语**：确认 Bithumb 韩文公告自带秒级发布时间，Upbit已有官方实时公告流；但没找到成体系比较“韩文原稿 → 英文渠道”的时间差并同时测量价格剩余反应的研究。
* **法院/监管文件、SEC公告**：找到事件研究和大量个案，未找到可复现的“文件首次公开时间 → 同币1/10/60秒价格路径”样本研究。
* **ETF资金流披露**：2026预印本发现每$100m净流入与当日BTC约+53bp相关且能预测次日，但它是**日频流量关系**，没有证明“公众看到每日流量数字以后”还有收益，且存在双向因果。([SSRN][b12])
* **稳定币增发的现代复现**：找到的最好论文仍以2014–2021为样本，没有找到2024–2026独立复现，因此不能假设旧的5–30分钟窗口仍在。

## 4. 用过的检索词

`crypto exchange listing announcement seconds price reaction 2024 2025 2026`；`Binance listing announcement minute price reaction`；`Upbit listing announcement price reaction seconds`；`Bithumb listing Telegram timestamp Bybit`；`빗썸 상장 공지 가격 반응 분 초 연구`；`업비트 상장 공지 가격 반응`；`cryptocurrency delisting announcement price reaction seconds`；`Robinhood crypto listing one hour before public announcement`；`Tether minting Bitcoin 5 10 30 minutes`；`token unlock 72-hour shock Binance`；`Bitcoin CME Binance lead lag seconds`；`Hyperliquid Binance lead lag milliseconds`；`Bitcoin ETF price discovery 5-minute`；`Bitcoin ETF flows price impact 2026`；`crypto regulatory announcement intraday reaction`。

**就“下一轮值得花数据预算验证什么”而言，这次检索只留下两个真正的 P0：`Bithumb 首次重大韩国 KRW listing → 其他场所`，以及 `Robinhood tradable-state → 正式公告之间的公开可观察窗口`。** 前者缺的正好是你最关心的 **0–1s / 1–3s / 3–10s / 10–60s 成交级路径与真实可买价**；如果补完后发现主要跳升在前1–3秒已经完成，这整个分支就可以很快杀掉。

继续验证：把 Bithumb 方案细化成秒级回测设计；把 Robinhood 窗口拆成公开可观测信号。

[b1]: https://github.com/sueun-dev/exchange-listing-sniper?utm_source=chatgpt.com
[b2]: https://www.justice.gov/usao-sdny/media/1461271/dl?utm_source=chatgpt.com
[b3]: https://www.binance.com/en/square/post/331117488687537
[b4]: https://docs.upbit.com/kr/changelog/websocket-announcement?utm_source=chatgpt.com
[b5]: https://www.justice.gov/usao-sdny/pr/two-robinhood-employees-charged-fraud?utm_source=chatgpt.com
[b6]: https://www.sciencedirect.com/science/article/pii/S154461232200321X?utm_source=chatgpt.com
[b7]: https://thefederalregister.org/documents/2023-15127/self-regulatory-organizations-nyse-arca-inc-notice-of-filing-of-a-proposed-rule-change-to-list-and-trade-shares-of-the-b?utm_source=chatgpt.com
[b8]: https://doi.org/10.1007/s10614-025-10998-x?utm_source=chatgpt.com
[b9]: https://doi.org/10.2139/ssrn.6632838?utm_source=chatgpt.com
[b10]: https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026
[b11]: https://onlinelibrary.wiley.com/doi/10.1111/ajfs.70045?utm_source=chatgpt.com
[b12]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6592830&utm_source=chatgpt.com

---

## 第三份：更全

## 1. 总结

本轮最像你要找的“**公开信息分散、市场整合较慢**”证据有三类：**韩国本地信息→全球市场（日级）**、**境外价格+韩国社区→Upbit 新币（日级）**、以及**BTC→低流动性山寨币（分钟级）**。其中只有最后一类真正做到分钟级、样本外并显式计入手续费；但它不是跨语言信号，而且只验证了少量低流动性币。跨平台“新闻+社交+链上+搜索”确实能提高预测，但 2024–2026 的论文多数仍停留在日/周频，净交易成本证据明显弱于预测准确率证据。**本轮没有找到**可靠的“中文/日文叙事先于英文”“同叙事跨链依次启动”或“亚洲时段→美国时段”且同时满足历史回放、明确领先窗口、净成本和独立复现的证据。

## 2. 证据表

| 信息组合 | 来源渠道与语言 | 有记录的领先时长与预测力 | 扣成本后是否仍在 | 同一资产能否交易 | 历史数据能否回放（免费/付费、价格） | 样本时期 | 出处（链接）与类型 | 证据强弱 | 不能推出什么 |
|---|---|---|---|---|---|---|---|---|---|
| **韩国新闻情绪 + 韩国/全球价格与成交量** | 韩国新闻（韩语）+135家全球媒体+KRW/USD加密市场 | **只有韩国新闻情绪**预测韩国及全球组合收益，并领先全球新闻情绪，效应最长约**2天**；韩国组合两日后超额收益约16bp，基于情绪符号持有2–3日的毛超额约16–26bp；当 KRW 成交量超过 USD 时关系消失。([Taylor & Francis Online][c1]) | **未证明**；论文交易结果是毛收益 | **是，但主要是市场组合**；BTC/ETH单币结果较弱/不显著 | 论文原始新闻库不公开。Naver 新闻搜索API公开、25k次/日，但单查询最多前1000条，历史穷举困难。([NAVER开发者][c2]) NewsAPI 免费档仅1个月；5年历史为 **$449/月或$1,749/月**。([News API][c3]) | 2017-12～2023-08 | Kang et al., *European Journal of Finance*, 2026，同行评审 ([Taylor & Francis Online][c4]) | **强** | 不能推出韩语新闻存在秒/分钟级套利；不能推出单币净成本后可赚；本轮未找到独立复现 |
| **上币前 Binance 价格 + 韩国市场 + 社区情绪** | Binance；Upbit；Bitcointalk/Altcoinstalk（主要英文国际社区，应用于韩国市场） | 对 Upbit 新上币，用上币前 Binance 数据及前期社区信号预测上币后1日急涨/泡菜溢价；社交增量**依模型而异**，如 LR 急涨 AUC约 .72→.80，MLP约 .83→.84。([韩国期刊中心][c5]) | **否**；分类研究，无净P&L | **是**：预测对象就是之后在 Upbit 可交易的币 | Binance 历史K线/成交文件免费公开，含1m/1s。([GitHub][c6]) Upbit 分钟K线可按`to`分页；秒线仅近3个月。([Upbit Developer Center][c7]) 论坛帖子有时间戳，但论文未公开完整清洗集/代码 | 2021–2025；107个具 Binance 数据的上币事件 | Park et al., 韩国 KCI 期刊，2026 ([韩国期刊中心][c8]) | **中** | 测试集仅约17个ticker、不是严格按时间切分；不能推出稳定alpha，也不同于单纯“上币后30分钟买” |
| **BTC一分钟价格冲击 + 山寨币自身价格/流动性** | Binance公开行情 | 低成交量ALT常比BTC慢**约1至数分钟**；BTC前一分钟收益对所测ALT均通过Granger检验；效应2–3分钟后大幅减弱。([Springer][c9]) | **部分成立**：回测显式扣**0.02%/次**手续费；最后一周样本外，低流动性小币组合优于买持，并有额外子样本。未计滑点/冲击。([Springer][c9]) | 可交易ALT；但严格说**信号资产BTC≠交易资产ALT** | **免费、很好回放**：Binance官方历史1m/交易数据，无API key。([GitHub][c6]) | 多个约1月窗口，2024–2025 | Kurihara & Matsumoto, *Asia-Pacific Financial Markets*, 2026，同行评审 ([link.springer.com][c10]) | **中强** | 只深入验证5个小市值ALT；币的选择和特殊事件窗口可能放大效果；无盘口容量 |
| **链上活跃度/算力 + Google搜索注意力** | 链上+Google Trends | 三个周度因子在**40种币**上有样本外预测力；按此前已实现预测力排序构建long-short也产生收益差。([科学直接][c11]) | **未核实**；可见摘要未说明交易成本 | 是，预测/排序的就是对应加密资产 | Coin Metrics Community 部分指标**免费无key**；Pro价格不公开。([GitHub][c12]) Google Trends API alpha 为滚动**5年**、日/周/月/年，当前仅有限测试者。([Google for Developers][c13]) | 具体起止在可见摘要中**未核实** | Guidolin & Ionta, *Journal of International Financial Markets, Institutions & Money*, 2026，同行评审 ([科学直接][c14]) | **中强** | 不能推出分钟级；“链上+搜索联合使用”不等于每个币都可实时低成本取得全部指标 |
| **新闻 + X/Twitter + Reddit + Google Trends + GitHub/链上/行情** | 多平台，主要英文 | BTC/ETH；滚动7折验证中，加入文本信息持续改善预测准确率、利润和Sharpe；目标包括次日方向及局部极值。([科学直接][c15]) | 主分析**不计成本**；论文仅做0.5%/交易敏感性，显示低频极值模型相对更有竞争力，并非证明净alpha。([Scribd][c16]) | 是，BTC/ETH | 代码公开；**原始数据因供应商/平台条款未公开**，因此无法免费完整逐时点复现 | BTC 2011–2023；ETH 2015–2023 | Gurgul et al., *International Journal of Forecasting*, 2025 ([科学直接][c15]) | **中强** | 不能推出“平台越多越好”；不能推出2026仍有效或净成本为正 |
| **BTC价格 + Twitter情绪 + 新闻情绪 + 美国宏观/社会经济变量** | X、新闻、行情、宏观；英文/美国 | 8种ALT，使用最长**1–4日滞后**；方向准确率约66.1%–71.0%；特征重要性依次包括BTC价格、社交、新闻。([IDEAS/RePEc][c17]) | 未做可执行成本验证 | 交易对象为ALT；部分重要信号来自BTC | 价格/宏观可重放；77M tweets/news 的原始集合未见公开，**完整免费复现不可行** | 2016–2022 | Gupta et al., *Computational Economics*, 2024，同行评审 ([IDEAS/RePEc][c17]) | **中** | 不能推出高频alpha；准确率不是收益率；Twitter历史数据构成严重复现障碍 |
| **交易所链上净流入 + 市场价格** | BTC/ETH/USDT链上+交易所地址标签 | **1–6小时**：ETH净流入负向预测ETH收益；USDT流入交易所正向预测BTC/ETH收益；BTC自身净流入除4h外通常不预测BTC收益。([SSRN][c18]) | 摘要有策略/P&L，但完整成本处理**未核实** | ETH流→ETH为同资产；USDT→BTC/ETH不是 | 原始链可免费回放；**交易所地址标签/论文精确数据集未核实**，这是主要 point-in-time 风险 | 2017–2023 | Chi et al., SSRN，2025修订，**工作论文** ([SSRN][c18]) | **中** | 不能假定任意“鲸鱼流入”都有方向预测力；BTC结果本身就是反例 |
| **单币Twitter异常注意力 + 单币收益** | X/Twitter，英文为主 | 当日ticker帖子异常注意力与**次日收益正相关**；项目官方账号帖子没有同样的收益预测力。([科学直接][c19]) | 未核实 | **是** | 论文所用历史X数据未见免费公开；当前无法靠免费官方历史API完整重放 | 2018–2022 | Maître et al., *Journal of Banking & Finance*, 2025 ([科学直接][c19]) | **中强（关系）/弱（可复现性）** | 不能推出任何热门推文都应追买，也没有证明扣成本后可交易 |

## 3. 查了但没找到证据的方向

* **“中文/日文社区先起叙事→英文社区及同一币价格随后补涨”**：本轮没有找到 2024–2026 年同行评审或方法公开研究，同时给出语言级时间戳、明确lead-lag、可交易价格和成本。搜到的中文/Baidu、日文社交研究要么较旧、要么只是相关/情绪预测，达不到你的证据标准。
* **“同一叙事先Solana，再Base/ETH/BSC”**：2025 的研究确实发现 launchpad/memecoin **跨链 contagion**，2026 USENIX 工作也有 34,988 币跨四链数据，但它们证明的是联动、操纵和风险传播，不是“链A出现后，链B存在稳定可交易延迟”。([科学直接][c20])
* **“亚洲时段的信息领先美国时段”**：大样本研究覆盖38家交易所、1,940交易对，反而发现小时模式在不同洲交易所高度相似，主要是全球共同日内周期，而非清晰 Asia→US 传导。([Springer][c21])
* **“Twitter+Reddit+Google Trends必然比单源强”**：2024 LASSO-VAR 只在较小市值币上明显改善方向准确率，并未改善RMSE；其因果检验还没有支持“社交情绪→收益”的Granger因果。([Taylor & Francis Online][c22])
* **秒级跨语言/社交信息优势**：没找到达到标准的公开证据。最接近可执行短延迟的是上表的 **BTC→低流动性ALT约1–数分钟**，但机制是价格发现，不是语言/文本优势。

## 4. 用过的检索词

`cross-border cryptocurrency Korean news sentiment global returns lead lag 2026`；`Korean crypto news sentiment global market KRW USD`; `Upbit Binance offshore prices social signals listing premium 2026`；`Korean community cryptocurrency prediction`; `Japanese social media cryptocurrency sentiment lead returns`; `Chinese Baidu cryptocurrency sentiment prediction`; `cryptocurrency cross language information diffusion`; `memecoin cross chain narrative spillover Solana Base Ethereum`; `launchpad contagion memecoin`; `Bitcoin altcoin price transmission high frequency 2026`; `Asia US session cryptocurrency lead lag`; `daytime overnight Bitcoin Ethereum`; `social media attention cryptocurrency returns 2025`; `Twitter Reddit Google Trends cryptocurrency forecast`; `blockchain fundamentals Google Trends crypto 2026`; `on-chain exchange flows BTC ETH USDT 1–6 hours`; `Naver News API history`; `Upbit historical candle API`; `Binance public historical data`; `Google Trends API 5 years`; `Coin Metrics Community Data`; `NewsAPI pricing history`.

继续验证：补查跨语言与跨链的空白证据；整理成可执行的历史回放清单。

[c1]: https://www.tandfonline.com/doi/full/10.1080/1351847X.2026.2652365?utm_source=chatgpt.com
[c2]: https://developers.naver.com/docs/serviceapi/search/news/news.md?utm_source=chatgpt.com
[c3]: https://newsapi.org/pricing?utm_source=chatgpt.com
[c4]: https://www.tandfonline.com/doi/abs/10.1080/1351847X.2026.2652365?utm_source=chatgpt.com
[c5]: https://journal.kci.go.kr/jksci/archive/articlePdf?artiId=ART003305943&utm_source=chatgpt.com
[c6]: https://github.com/binance/binance-public-data/?utm_source=chatgpt.com
[c7]: https://global-docs.upbit.com/reference/list-candles-minutes?utm_source=chatgpt.com
[c8]: https://journal.kci.go.kr/jksci/archive/articleView?artiId=ART003305943&utm_source=chatgpt.com
[c9]: https://link.springer.com/article/10.1007/s10690-026-09589-z
[c10]: https://link.springer.com/article/10.1007/s10690-026-09589-z?utm_source=chatgpt.com
[c11]: https://www.sciencedirect.com/science/article/pii/S1042443126000016?utm_source=chatgpt.com
[c12]: https://github.com/coinmetrics/docs-website/blob/master/api.md?utm_source=chatgpt.com
[c13]: https://developers.google.com/search/apis/trends?utm_source=chatgpt.com
[c14]: https://www.sciencedirect.com/author/6506142568/massimo-guidolin?utm_source=chatgpt.com
[c15]: https://www.sciencedirect.com/science/article/pii/S0169207025000147?utm_source=chatgpt.com
[c16]: https://www.scribd.com/document/1030038446/2311-14759v2?utm_source=chatgpt.com
[c17]: https://ideas.repec.org/a/kap/compec/v64y2024i5d10.1007_s10614-023-10538-5.html?utm_source=chatgpt.com
[c18]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4630115&utm_source=chatgpt.com
[c19]: https://www.sciencedirect.com/science/article/pii/S0378426625001384?utm_source=chatgpt.com
[c20]: https://www.sciencedirect.com/science/article/pii/S1544612325015181?utm_source=chatgpt.com
[c21]: https://link.springer.com/article/10.1007/s11156-024-01304-1?utm_source=chatgpt.com
[c22]: https://www.tandfonline.com/doi/full/10.1080/00036846.2023.2289930?utm_source=chatgpt.com

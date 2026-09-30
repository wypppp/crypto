
# Clean-room Architect 输出（2026-09-29）

**前置拆分**

- **目标**：3 年内只靠交易、扣掉全部可执行成本后，净利约 ¥100 万。
- **事实**：资本 ¥1 万–11 万；数据预算约 $100/月；每周约 40 小时；VS Code→WSL→Git 环境已经就绪。
- **核心假设（未验证）**：存在一类机会，能提前识别，扣成本后剩下的右尾仍然够大，而且容量足以承载目标。整个项目里，这是最大的未验证前提。
- **约束**：必须能做历史验证；研究环境与签名环境分离；人不审代码。

标注：〔证〕= 有外部证据；〔推〕= 模型的推断或建议，没有外部证据。

---

## A. Executive Answer

**上游有一个定义问题。** 现在的瓶颈不是"研究方式"，而是一个还没验证的前提：在可执行成本和容量约束下，机会集够不够大、能不能支撑目标。Path A 要涨约 101 倍，Path C 要约 10 倍。这个问题应该在第一周用数据回答，而不是靠流程设计回答。

**工具几乎都能直接用或配置：** Dune（链上全历史）、Binance/Hyperliquid 公开数据、arch/pypbo（多重检验），加一个编码代理和沙箱。

**真正需要自建的只有三样：**

- DEX/bonding curve 的可执行成交与容量模型；
- 由脚本自动记账的试验账本，加一次性的 holdout 门；
- 带 manifest 的本地数据快照。

**模型用法：** 默认只用一个模型。第二个模型只在"开 holdout"和"上真钱"两道门各用一次；独立性要靠非 LLM 的证据来保证。

**时间：** 研究"怎么研究"最多花 40 小时。

---

## B. Capability → Existing Solution


| Capability                                                             | Need?          | Existing solution                                                                                                                                                                                                             | Custom work still required                                                                             | Evidence                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 机会集上限与容量：假设完美预知，扣成本、按流动性限仓后，最多能赚多少 | 必需，最先做   | 没有现成工具。公开基准可以当先验：pump.fun 上已实现利润超过 $1 万的钱包只占 0.412%；毕业率约 0.2–2%                                                                                                                          | 一组 SQL 加一个容量函数                                                                                | 〔证〕[Cointelegraph/Dune](https://cointelegraph.com/news/pump-fun-crypto-traders-majority-do-not-realize-profits-dune-data)、[arXiv 2512.11850](https://arxiv.org/html/2512.11850v3)；方法本身〔推〕                                                                                                                                           |
| 2 链上时点正确的历史数据，含死币，无幸存者偏差                         | 必需           | Dune Analyst：约 $75/月、4000 credits（价格来自第三方页面）。免费版从 2026-09-10 起只能查看，没有 API。Helius Developer $49，含归档数据，用于抽检。**不要**用 CoinGecko 建样本宇宙：官方说明下架币的历史数据无法通过 API 获取 | 从"代币创建/建池事件"构建全样本；导出 Parquet 快照和 manifest                                          | 〔证〕[Dune FAQ](https://docs.dune.com/learning/how-tos/pricing-faqs)、[CryptoBriefing](https://cryptobriefing.com/dune-free-plan-view-only-access/)、[Helius](https://www.helius.dev/pricing)、[CoinGecko](https://support.coingecko.com/hc/en-us/articles/23190618031385)                                                                     |
| 3 CEX/永续历史：K 线、成交、funding、下架交易对                        | 视领域而定     | Binance data.binance.vision：免费，保留下架交易对。Hyperliquid S3 归档：下载费由请求方付。Tardis：每月首日的 tick 数据免费，可用来校准滑点                                                                                    | 数据加载器；处理已知陷阱，比如 funding 频率变更、缺失值记成 0                                          | 〔证〕[binance-public-data](https://github.com/binance/binance-public-data)、[HL 文档](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data)、[HL 陷阱](https://github.com/alpenmilch411/hyperliquid-archive-notes)、[Tardis](https://docs.tardis.dev/faq/billing-and-subscriptions)                                                 |
| 4 可执行成交模拟：手续费、滑点、失败交易、优先费/MEV、卖不出、容量     | **必需，核心** | CEX 永续：freqtrade（回测计入 funding，但按开盘价成交、没有滑点）或 nautilus。EVM AMM：degenbot 做精确的池子计算。Solana/pump.fun：没找到可信的开源实现                                                                       | **自建一个薄层**：bonding curve 和恒积池的成交计算，再用真实的后续成交回放来校准。大约几百行代码加测试 | 〔证〕[freqtrade](https://www.freqtrade.io/en/stable/leverage/)、[degenbot](https://github.com/BowTiedDevil/degenbot)；"没有 Solana 模拟器"只是检索没找到〔推〕                                                                                                                                                                                 |
| 5 多重检验与过拟合控制                                                 | 必需           | arch 8.0：SPA/StepM/MCS，块自助法。pypbo：PBO/CSCV 和 DSR。vectorbt 的 DSR 有人报告峰度计算有缺陷，不要直接用                                                                                                                 | 试验账本，自动统计所有尝试次数；把逐笔收益聚合成周度 P&L；同时报告中位数和"去掉最大 k 笔后"的结果      | 〔证〕[arch](https://bashtage.github.io/arch/multiple-comparison/multiple-comparison_examples.html)、[pypbo](https://github.com/esvhd/pypbo)、[vectorbt #872#872](https://github.com/polakowo/vectorbt/pull/872)                                                                                                                                |
| 6 泄漏自检                                                             | 必需           | 没有现成品                                                                                                                                                                                                                    | 三个固定测试：随机入场的 null 策略、信号延迟扰动、跨数据源对账                                         | 〔推〕                                                                                                                                                                                                                                                                                                                                          |
| 7 文献和工具发现                                                       | 偶尔用         | 现有的 Deep Research，品牌不限；数据集 SolRPDS、MemeTrans                                                                                                                                                                     | 不用自建；每个领域限时做一次                                                                           | 〔证〕[Claude Research](https://support.claude.com/en/articles/11088861-use-research-on-claude)、[SolRPDS](https://arxiv.org/abs/2504.07132)、[MemeTrans](https://arxiv.org/html/2602.13480v1)                                                                                                                                                  |
| 8 编码代理与权限                                                       | 必需           | Claude Code 或 Codex 二选一。两者都能原生读取 AGENTS.md：Claude Code 要求 ≥v2.1.277，且目录里没有 CLAUDE.md。两者都有 bubblewrap 沙箱，支持 WSL2                                                                             | 只做配置：一份 AGENTS.md；沙箱对`~/.ssh`、钱包路径、holdout 目录设 denyRead；关闭 bypass 模式          | 〔证〕[CC memory](https://code.claude.com/docs/en/memory)、[CC sandbox](https://code.claude.com/docs/en/sandboxing)、[Codex](https://developers.openai.com/codex/agent-approvals-security)                                                                                                                                                      |
| 9 数据连接器（MCP）                                                    | 可选           | Dune、Helius、CoinGecko 都有官方 MCP                                                                                                                                                                                          | 不建议当主路径：查询应存成仓库里的 SQL 文件，才方便复现                                                | 〔证〕[Dune MCP](https://docs.dune.com/api-reference/agents/mcp)；取舍〔推〕                                                                                                                                                                                                                                                                    |
| 10 复现                                                                | 必需           | git、uv.lock、Parquet/DuckDB；DVC 可选                                                                                                                                                                                        | 每张结果卡自动写入 commit hash 和数据 manifest hash                                                    | 〔证〕[uv](https://docs.astral.sh/uv/concepts/projects/layout/)、[DuckDB](https://duckdb.org/docs/current/data/parquet/overview)                                                                                                                                                                                                                |
| 11 前向影子测试                                                        | 上真钱前必需   | 没有合适的现成品                                                                                                                                                                                                              | 在 VPS 上用 cron 跑同一套代码，信号只追加写入并 push，借远端时间戳防止事后补写                         | 〔推〕                                                                                                                                                                                                                                                                                                                                          |
| 12 执行隔离与限额签名                                                  | 部署时必需     | CEX：API 只开交易权限、关闭提现、设 IP 白名单。链上：用独立的小额热钱包，人工签名；以后可以换成 Turnkey、Coinbase CDP 的策略限额，或 Safe 的 Allowance 模块                                                                   | 研究期不需要，也不建自动签名                                                                           | 〔证〕[Binance API](https://binance.com/en/support/faq/how-to-create-api-360002502072)、[Turnkey](https://docs.turnkey.com/features/policies/overview)、[CDP](https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/policies/evm-policies)、[Safe](https://docs.safe.global/home/ai-agent-quickstarts/agent-with-spending-limit) |
| 13 税基和出入金记录                                                    | 必需           | 没有合适的现成品                                                                                                                                                                                                              | 从第一笔交易起，记录每笔的 tx hash、成本和费用；评价时同时报告税前和税后（按 20% 情景）                | 〔证〕[税务总局境外所得自查 2026-01](https://m.gmw.cn/2026-01/16/content_1304306810.htm)；加密收益是否适用、税率是否为 20%，都没有明确的官方口径〔推〕                                                                                                                                                                                          |
| 14 资本路径模拟：A/B/C 三种路径、容量、破产概率                        | 必需           | 没有现成品                                                                                                                                                                                                                    | 一个小型 Monte Carlo，对逐笔结果做自助抽样，并加容量上限                                               | 〔推〕                                                                                                                                                                                                                                                                                                                                          |

---

## C. Minimal Workflow

1. **第 1 周：普查机会上限。** 挑一个数据最便宜的领域做"右尾普查"。在"已经涨了 2×/3×/5×"这类可观测时点上，统计四样东西：剩余可执行倍数的分布、当时的流动性、每月事件数，以及完美预知且扣成本后的利润上限（分别按 ¥1 万、¥10 万、¥100 万仓位计算）。经验法则〔推〕：如果容量约束下 3 年等效的利润上限不到目标的约 30 倍，就换领域。这个 30 倍来自一个假设，即现实规则只能拿到约 3%，要用第一批结果去校准。
2. **冻结数据切分。** 分成 discovery、validation、封存的 holdout 和前向四段。holdout 选在所用模型训练截止日之后的最近几个月。切分写进 STATE.md；holdout 快照放在代理沙箱设了 denyRead 的路径里。
3. **成本模型通过三项自检才能进入下一步。**

   - 随机入场的 null 策略，扣成本后收益应该约等于负的成本；
   - 信号延迟 +1 个区块或 +1 分钟后，收益不应该"变好"；
   - 跨数据源对账的误差在阈值以内；
   - 最后由人用区块浏览器抽查 5 笔交易。

   这一关没过，就不开始研究信号。
4. **Discovery 阶段，允许先看赢家再找规律。** 编码代理可以自由探索。但每次调用回测 runner，都会自动往 trials.csv 追加一行（配置 hash、数据 hash、指标），这一行不由模型手写。
5. **结果卡。** 每个候选规则一页以内，包括：规则本身、累计试验次数、周度 P&L、PBO/SPA、中位数和去掉最大 k 笔后的结果、容量曲线、A/B/C 路径模拟，以及 5 笔可点击的链上抽样。人只读结果卡，不读代码。
6. **门 1：开 holdout，由人决定。**

   - 前提：规则的 hash 已经提交；三项自检都通过；第二个模型做过一次审计，专门找泄漏和执行不了的地方。
   - holdout 只跑一次。失败就淘汰，不在 holdout 上调参。
7. **前向影子测试，4–12 周。** 同一套代码在 VPS 上定时运行，信号追加写入并 push。这一步主要验证执行是否可行、有没有泄漏。它证明不了右尾，因为样本太少。
8. **门 2：小额真钱，由人决定。** 在隔离的执行层操作（独立设备、独立钱包、限权 key），按事先定好的规模规则投入。实盘产生的真实成本回填到成本模型。

### 分工与控制（对应 Q3）

**人**

- 选领域和资本路径；批准付费；决定门 1 和门 2。
- 每周最多读 2 张结果卡，并抽查链上样本。

**Research AI**

- 每个领域开局用一次；遇到具体阻塞时再用一次。
- 每次限时 2 小时以内，输出不超过一页。

**编码代理**

- 默认只用一个。一家额度用完再换另一家，两家共用 AGENTS.md。
- 负责写 SQL、ETL、成交模拟器、测试和结果卡。

**第二个模型**

- 只在门 1 和门 2 各用一次。
- 它替代不了非 LLM 检验，因为模型之间的错误是相关的：在一个排行榜数据集上，两个模型同时答错时，约 60% 给出的是同一个错误答案。〔证〕[Kim et al., ICML 2025](https://arxiv.org/abs/2506.07962)

**必须来自非 LLM 证据的事实**

- 价格、成交和流动性；
- 交易是否真能执行；
- 试验次数；
- holdout 结果；
- 税基。

**项目状态全部放在 Git 里**

- AGENTS.md：规则，200 行以内；
- STATE.md：一页纸的当前状态；
- DECISIONS.md：只记人的决策；
- trials.csv；
- data/manifests/。

**不可逆动作**

- 付费、开 holdout、开始前向、投真钱，只能由人触发。
- 执行密钥永远不进研究机。

**覆盖检查**


| 维度       | 所在位置           |
| ------------ | -------------------- |
| 目标       | A、F1、F2          |
| 方法       | C                  |
| 信息发现   | B7                 |
| 工具       | B                  |
| 数据       | B2、B3             |
| 工程       | B4、B8             |
| 验证       | B5、B6、C3–C7     |
| 安全       | B12、E5            |
| 人的控制   | 上面的"分工与控制" |
| 运维与复现 | B10、B11           |

---

## D. Do NOT Build

1. 多模型编排，或自动化的 A→B→A 审阅流水线。
2. 实验追踪平台（MLflow 之类）或 Web 仪表盘。CSV 加 git 就够了。
3. 通用回测引擎。CEX 部分用现成的，只自建 DEX 成交层。
4. 自己的链上 ETL、节点或索引（比如自己跑 Old Faithful 或 cryo）。除非 Dune credits 连续两个月成为硬瓶颈。
5. 低延迟、狙击或 mempool 相关的基础设施。
6. 把实时社交/叙事抓取当主要证据。这类数据的历史恢复不了。
7. 大量 MCP、插件或第三方 skill。它们占上下文，也扩大供应链攻击面。
8. 让 LLM 给历史代币或叙事打分，再当回测特征。这会带来记忆型的前视泄漏，除非只在模型截止日之后评估。
9. 研究期的自动签名或自动交易代理。
10. 长篇周报。只要结果卡。

---

## E. Critical Risks

1. **目标和机会集对不上。** 基准数据极差：Solidus 报告称 98.6% 的 pump.fun 代币是 rug 或拉盘，平台对此有异议〔证〕[CoinDesk](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)。

   - 缓解：C1 的上限普查，加上领域淘汰规则。
2. **代理会放大研究过拟合。** 代理一小时能试上千个变体，而先看赢家再找规律又放宽了约束。

   - 缓解：试验次数自动统计；用 PBO/SPA；holdout 只用一次。
3. **两类前视泄漏。**

   - (a) 链上数据是公开的，代理随时能查 holdout 时段的数据，所以技术封存做不到完美。
   - (b) LLM 记得训练截止日之前的赢家。有研究发现，模型能回忆截止日前的市场数据，而且用提示遮蔽也没用〔证〕[2504.14765](https://arxiv.org/abs/2504.14765)；预测力集中在模型可能记住的样本上〔证〕[2512.23847](https://arxiv.org/abs/2512.23847)。泄漏程度有争议，另一项研究认为影响温和〔证〕[2502.21206](https://arxiv.org/abs/2502.21206)。
   - 缓解：holdout 放在模型截止日之后，最终以前向测试为准。
4. **模型误差相关。** 两个模型一致，不等于正确。

   - 缓解：C 部分列出的非 LLM 证据清单。
5. **供应链攻击和提示注入专门盯着加密开发者。**

   - Nx s1ngularity 事件利用 AI CLI 搜刮钱包〔证〕[Wiz](https://www.wiz.io/blog/s1ngularity-supply-chain-attack)；
   - 2026 年的 TrapDoor 往 CLAUDE.md 和 .cursorrules 里注入指令〔证〕[THN](https://thehackernews.com/2026/05/trapdoor-supply-chain-attack-spreads.html)；
   - 代币名称和元数据本身就是攻击者能控制的字符串。

   缓解：研究机上不放任何密钥；开沙箱和网络白名单；锁定依赖版本；不装第三方 skill 或 MCP；不开 bypass 模式。
6. **回测和真实执行之间有缺口。** 失败交易、优先费、夹子攻击、rug 时卖不出、流动性瞬间撤走，都会让回测假设了现实中不可能发生的退出。

   - 缓解：退出按真实的后续成交回放；专门建"卖不出"情景。

---

## F. Things We May Have Missed

1. **A 和 C 是两个不同的研究问题。**

   - Path A 要涨约 101 倍（年化约 4.7 倍），只有彩票型的右尾能承载。
   - Path C 要约 10 倍（年化约 2.2 倍），容量更大的策略也可以入选。

   建议让 C1 的普查结果来决定走哪条路径，而不是先定路径。〔推〕
3. **右尾策略天生统计功效很低。** 几个月的 holdout 里可能只有 0–3 个关键事件，统计意义上的"确认"也许根本做不到。设计上应该偏好横截面广的规则（大量独立的小注），或者明确接受"无法确认，只能小额前向"这种状态。〔推〕
4. **数据供应商按月变化，所以本地快照是必需品。**

   - Dune 免费版从 2026-09-10 起改为只读〔证〕；
   - Flipside 在 2026-05 出售了数据业务〔证〕[NatLawReview](https://natlawreview.com/press-releases/flipside-sells-blockchain-data-business-sonarx-commits-fully-edisyl)；
   - BigQuery 的公共 Solana 数据集在 2025-03-31 之后停更〔证〕[Google 论坛](https://discuss.google.dev/t/public-solana-bigquery-dataset-crypto-solana-mainnet-us-stopped-updating-on-march-31-2025/185629)。

---

## G. Stop Rule

**满足以下四条中的全部时，停止研究"怎么研究"**（预计不超过 40 小时）：

1. 一个领域的右尾普查从原始数据到结果卡端到端跑通，而且一条命令能重跑出相同的 hash；
2. null、延迟扰动、跨源对账三项自检通过，人工抽查的 5 笔交易也通过；
3. trials.csv 自动记账在运行，holdout 切分已经写进 STATE.md；
4. 安全基线到位：研究机上没有任何密钥，沙箱和网络白名单已开启。

**硬时限**

- 40 小时一到就停；没完成的项降级为"已知缺口"，记进 STATE.md。
- 之后花在工具和方法上的时间，不超过每周的 10%（约 4 小时）。

**重开条件**

- 只有两种情况可以重开：同一个具体阻塞连续卡住两个以上假设；或者供应商变更让管线失效。
- 重开时限时 4 小时，只回答那一个问题。

**搜索饱和**

- 连续两次检索都没能把任何"自建"项变成"直接用"，就停止。
- 按这次的检索结果，除了 Solana 成交模型和少量胶水脚本，其余都已经是直接用或配置。**所以现在就可以停止找工具。**

---

## H. Bottom Line

**这个项目今天最少只需要自建三样东西：DEX/bonding curve 的可执行成交与容量模型、由脚本自动记账的试验账本加一次性 holdout 门、带 manifest 的本地数据快照；其余全部用现成工具配置即可。**

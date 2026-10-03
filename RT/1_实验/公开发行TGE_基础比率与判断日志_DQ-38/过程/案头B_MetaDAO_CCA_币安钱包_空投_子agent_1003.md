# 案头检索 B：MetaDAO / Uniswap CCA / 币安钱包 TGE / 积分与空投型（2025-01-01 至 2026-09-30）

检索日期 2026-10-03。只用公开网页与免费公开接口（CoinGecko 免费 API、GeckoTerminal 免费 API、币安公开公告列表接口、Bitquery 公开 CSV），未注册、未登录、未用付费 API、未调 Dune、未跑链上查询。
逐场数据见同目录 `tge_desk_B_events.csv`（124 行，含无数据占位行）；Bitquery 原始 CSV 见 `bitquery_airdrops_2026.csv`（51 行，原样下载，6059 字节）。

通用约定（先读）
- “二手”＝新闻、聚合站、研究博客转述；“一手”＝项目/平台官方推文、官方博客、官方公告、链上池。多数数字是二手，已在表中标注来源 URL。
- 价格窗口限制：CoinGecko 免费接口只给近 365 天（本次 2025-10-04 起）；GeckoTerminal 免费接口只给近约 6 个月日线（更早返回 401）。所以 2025-10 以前上市的币、以及 2025-10～2026-03 的 MetaDAO 币，逐日 d1/d7/d30 常常缺。缺的留空，不外推。
- d1/d7/d30 定义：CoinGecko 行＝TGE 日 +0/+1/+7/+30 天 00:00 UTC 的快照价；GeckoTerminal 行＝对应日线 K 线开盘价。均不是严格“收盘价”，差半天内。
- 样本选择偏差：有公开发行价的场次才进入比值统计；发行价缺失的（多数币安编号 TGE）不进统计。这使统计偏向“有新闻的”场次，见各节。
- 价格“发行价”对 MetaDAO 是 ICO 价；对 CCA 是清算价（找不到时用地板价并注明）；对币安钱包是 Pre-TGE/Prime Sale 认购价。

---

## A. MetaDAO（metadao.fi，Solana）

### A1 事件率与名单
- 官方口径（Alea Research，2026-09-18，二手）：自 2025-04 首场起 23 场公开发行，报价需求 $624.7M，实收 $45.4M，22/23 成功完成（唯一未成功＝Hurupay，全额退款）。URL：https://alearesearch.substack.com/p/raise-in-public-spend-in-public ；同口径转述 https://www.kucoin.com/news/flash/metadao-raises-625m-in-23-sales-faces-challenge-of-filtering-quality-projects
- 2025 年：8 场（Alea 2026-01-21 称“8 ICO、实收 $25.6M、报价约 $390M、95% 退款”，https://alearesearch.substack.com/p/metadao）。Pine 季报：Q3 1 场 $1.1M，Q4 6 场 $18.7M（https://pineanalytics.substack.com/p/metadao-q4-2025-quarterly-report）；加上 2025-04 首场 $5.8M。
- 2026 年到 9 月中：23−8＝15 场（推算，二手）。
- 另有 futard.io（任何人可开的无筛选发行）：Alea 称已跑 90 场、仅 9 场过最低额，$44.0M 报价→$568K 实收（81/90 未达最低额＝全额退款）。这部分不在上面的 23 场内。
- 已识别名单（16/23）：
  - 2025：mtnCapital？（首场，2025-04，$5.8M，名字仅见 flow 推文，**未核实**）、Omnipair（07-21～28）、Umbra（10-06～10）、Avici（10-14～18）、Loyal（10-18～22）、ZKLSOL/Turbine Cash（10-20～24）、Paystream（10-24～27）、Solomon（11-14～18）。
  - 2026：Ranger（01-06～10）、Hurupay（02-03，失败）、P2P.me（03-26～04-01）、Laso（06-26 起）、Credible（07 中，07-17 上线）、Rip Cars（07，07-25 上线）、Kimia（08）、MycoRealms（约 $70K，单一来源）。
  - 其余约 7 场（2026 年）未能从公开页面枚举：metadao.fi/projects 被 Vercel 安全检查拦截，cryptorank/coinlaunch 被 Cloudflare 拦截。**这是 MetaDAO 最大缺口**。
- 名单可能不全：是。已识别 16 场里 mtnCapital 与 MycoRealms 证据弱。

### A2 额度分配机制
- 4 天内承诺 USDC；项目方有“自由裁量上限”（discretionary cap）：决定收多少，超出部分按比例退回。来源（官方文档）：https://docs.metadao.fi/how-launches-work/sale
- 分配＝累加器：每秒 accumulator += 承诺额×时间；份额＝个人累加器/总累加器；另有“填充提升”（池子稀疏时早进的人乘数更高）。所有人同价。早承诺且金额大者多得。（同上）
- 创始人/基金可事先谈“软承诺”和保证额度（同上）。Ranger 对积分持有者有优先（非积分持有者退款 92.9%，https://x.com/MetaDAOProject/status/2010037918572908629）。Rip Cars 起加入“Ownership Score”，一半额度按承诺的早晚与持有时长（Alea）。
- 典型规模：10M 枚代币出售（约占总量 40%），另 2.9M 枚＋募集 USDC 的 20% 入流动池；其余 USDC 进市场治理的金库；团队代币为绩效包（2x/4x/8x/16x/32x ICO 价，三个月 TWAP，至少 18 个月锁定）。
- 未达最低额：全额退款（Hurupay 例）。
- KYC/地域：本次未找到官方限制条款（INCRYPTED 称“no-KYC launchpad”，https://incrypted.com/en/metadao-review/ ，二手，**未核实**；docs 页未提及）。**项目资格问题（美国人等）本次没有查到官方说法，需另查法律条款。**
- 认购上下限：官方页未给统一的上下限；单场最低额由项目设（如 Loyal 最低 $500K，Laso 目标 $750K，Rip Cars 上限 $250K）。
- TGE 解锁：购买者代币在发行结束后直接可领（无锁仓，二手理解，docs 未专门写）；团队/投资人锁定按各场提案（P2P：投资人 12 个月后分 5 期，团队绩效包）。

### A3 逐场结果（节选，完整见 CSV）
| 项目 | 发行日 | ICO 价 | 上限/实收 | 承诺额 | 超募倍数 | 现价/ICO（2026-10-03）或终局 | 状态 |
|---|---|---|---|---|---|---|---|
| Omnipair | 2025-07 | 0.112（二手） | 0.3M–1.12M（二手冲突） | 1.12M | – | 2.35x | 已上市，ATH 约 16x（Alea） |
| Umbra | 2025-10 | 0.30 | $3.0M | ~$154M | ~51x | 0.80x | 已上市，周内 0.30→2.10，ATH 约 7–8x |
| Avici | 2025-10 | 0.35 | $3.5M | $34.2M | 9.8x | 0.73x | 已上市；TGE 日 1.57x、d7 3.47x、d30 11.6x |
| Loyal | 2025-10 | **冲突**（icodrops 0.05，step/Blocmates 暗示 0.22–0.25） | 最低 $0.5M | $75.9M | – | 现价 0.094 | 已上市；不进比值统计 |
| ZKLSOL/Turbine | 2025-10 | 0.0969 | $0.969M | $14.9M | 15.4x | 链上池陈旧，无可靠现价 | 后经投票转私有（Alea） |
| Paystream | 2025-10 | 0.075 | $0.75M | $6.15M | 8.2x | ~0.34x（陈旧池） | 2026-09-02 投票清算 |
| Solomon | 2025-11 | 0.80 | $8M | $102M | 12.8x | 0.95x | 已上市 |
| Ranger | 2026-01 | 0.80（FDV $20.5M） | $8M | $86.4M | 10.8x | 终局赎回约 0.78＝0.975x | 清盘并退回 $5.05M |
| Hurupay | 2026-02 | – | 最低 $3M | $2.00M | 0.67x | – | **退款（未成）** |
| P2P.me | 2026-03/04 | 0.60（FDV $15.5M） | $6M | 未找到 | – | 0.68x | 已上市 |
| Laso | 2026-06/07 | ~0.10 | $0.75M 目标 | 未找到 | – | 1.18x；TGE d1/d7/d30＝1.82/1.50/1.35x | 已上市 |
| Credible | 2026-07 | 0.40（FDV $9.07M） | $4M | $32.8M | 8.2x | 1.84x；d1/d7/d30＝1.46/1.31/1.46x | 已上市 |
| Rip Cars | 2026-07 | 0.025（FDV $0.645M） | $0.25M | $31.9M | 127x | 5.2x；d1/d7/d30＝2.10/2.06/2.35x | 已上市 |
| Kimia | 2026-08 | ~0.006（推算） | $0.06M | 未找到 | – | 0.71x；d1/d7/d30＝0.34/0.52/0.70x | 已上市；8 月持有人否决清算 |
主要来源：各场 MetaDAO 官方推文（https://x.com/MetaDAOProject/status/1979586735127568630 等，见 CSV）、Blocmates（https://www.blocmates.com/articles/metadao-projects-distilled）、Basis Point（https://basispointres.substack.com/p/metadao-ownership-coins）、Pine（https://pineanalytics.substack.com/p/p2p-metadao-ico-analysis）、GeckoTerminal 池价（链上池地址见 CSV）。除 MetaDAO 官方推文外多为二手。

### A4 小结（只用有发行价、已上市、能算比值的场次）
- 当前价/ICO 价（现价，不是 d30）：n=11（不含 Loyal 价格冲突、ZKFG 池陈旧、Hurupay 退款、mtnCapital/Myco 无数据）。中位 0.95x；>1 的 4/11（Laso、Credible、Omnipair、Rip Cars）；>3 的 1/11（Rip Cars 5.2x）；>10 的 0/11。与 Alea（2026-09-18）“10 个有公布发行价的 MetaDAO 币里 4 个高于发行价”一致。
- 历史峰值（二手）：Avici ATH 约 21x、Omnipair 16x、Umbra 8x。峰值高，但 2026-10 时 Avici/Umbra 已回到 ICO 价以下，说明“ATH 倍数”不等于可兑现。
- 上市首价/ICO 价：池子按 ICO 价播种，首日开盘价基本＝ICO 价（Laso 1.02、Credible 1.10、Kimia 1.14、Rip Cars 1.45、Avici 1.57），所以“首价/发行价>1”几乎是机制产物；有信息量的是 d1/d7/d30。
- d1/d7/d30（n=5：Avici、Laso、Credible、Rip Cars、Kimia）：d7/ICO 中位 1.50（>1：4/5，>3：1/5），d30/ICO 中位 1.46（>1：4/5，>3：1/5，>10：1/5）。**样本只有 5，且只含能取到日线的较新场次；2025-10～2026-03 的场次全缺 d1/d7/d30。**
- 退款/未成：curated 23 场中 1 场（Hurupay）；futard.io 90 场中 81 场未达最低额。清盘/清算/转私有：Ranger、Paystream、ZKFG（3 场，均已上市后事件）。
- 配置要点（影响“外部人能否吃到”）：超募倍数 8x–127x，意味着一个按比例的申购者只拿到约 1/10～1/127 的额度（退款的是其余），所以每美元承诺的收益被超募倍数稀释；Rip Cars 起额度部分按“早承诺+持有时长”加权。

### A5 来源与缺口
- 缺：7 场未枚举；多数场次承诺额；2025-10～2026-03 场次的 d1/d7/d30；KYC/地域官方条款；Umbra 等的真实首日收盘。
- 被拦截：metadao.fi（Vercel checkpoint）、cryptorank（Cloudflare）、coinlaunch（Cloudflare）、cryptobriefing（Cloudflare）。
- 公开 SQL 说明页 https://defi-kai.github.io/kai-site/notes/metadao-launchpad-query-notes/ （原链接重定向到该路径）已读：只给 launchpad_v7 等程序 ID 与指令判别码（initializeLaunch、fund、CompleteLaunch、claim、refund），**不含逐场结果表**。程序 ID：v0.7.0 moontUzsdepotRGe5xsfip7vLPTJnVuafqdUWexVnPM；v0.6.0 MooNyh4CBUYEKyXVnjGYQ8mEiJDpGvJMdvrZx1iGeHV；v0.5.0 mooNhciQJi1LqHDmse2JPic2NqG2PXCanbE3ZYzP3qA。这些是研究资料，未去链上查询。

---

## B. Uniswap CCA（连续清算拍卖）

### B1 事件率与名单
- 协议 2025-11-13 随 Aztec 首次公开；Uniswap Web App 的 Auctions 标签 2026-02-02 上线；2026-06-24 开放自助发起拍卖（https://blog.uniswap.org/launch-auctions-from-uniswap-web-app ）。
- 已知有结果的 CCA 发行（2025-11 至 2026-09，**已知名单很可能不全**，Uniswap 前端只列“Aztec、Cap 等”）：
  - 2025：Aztec（社区阶段 2025-11-13 起，公开阶段 12-02）— 1 场。
  - 2026：Rainbow RNBW（02-03～05，首个经 uniswap.org 的 CCA）、idOS（02-25～03-05，Arbitrum）、Cap Labs（约 06-09～18）、STRATO（Uniswap 史上第四大，细节未找到）、Igra（03-26～04-02，用 ZAP 协议，CCA 同类机制，是否 Uniswap 工厂**未证实**）— 至少 4–5 场。
  - flow.bid 等把 CCA 改成 9 分钟的 agent 微拍卖（https://x.com/Uniswap/status/2026774907904725048 ），未枚举。
- 工厂合约（只记录，未查链）：官方 README https://github.com/Uniswap/continuous-clearing-auction ，规范地址（跨 EVM 链同址，“select EVM chains”，Uniswap 称已上 Ethereum、Unichain、Arbitrum、Base）：
  - v2.1.0（推荐）0x000000001F26a0044BaA66024e7b6599c61963F8
  - v2.0.0 0x00cCa200BF124dBfA848937c553864f4B4CE0632
  - v1.1.0 0xCCccCcCAE7503Cac057829BF2811De42E16e0bD5
  - v1.0.0（候选）0x0000ccaDF55C911a2FbC0BB9d2942Aa77c6FAa1D
  - CCALens v2.0.0 0xc3C65F5453A3674aDb693cbdA3C842545cD30f53
  - Aztec 那场用的是 v1 系列还是自部署，README 未写，未核实。

### B2 额度分配机制
- 买家提交“总预算+最高价”；总量按区块匀速释放；每个区块以能卖光该区块配额的最高价清算，所有人成交价＝当期清算价，价格逐块延续。因此“比的是估值而不是速度”，无抢跑优势（https://blog.uniswap.org/aztec-cca ）。
- KYC/地域：可选“验证钩子”（validation hook）。Aztec 用 ZKPassport + Predicate 做身份验证，覆盖 191 国；idOS 阶段 2 无最低额，但不对英国人开放及“受限地域”（idOS 公告）。
- 认购上下限：由发行方设。Aztec 平均出资约 $4K，96% 出资人<$1 万，28% 的供给给了持仓<$10 万的钱包。
- 解锁：Aztec 社区代币首日 100% 解锁（Aztec 代表语，Cointelegraph），但另有 Aztec 治理解锁条款（icodrops：90 天后可发起解锁投票，12 个月后兜底解锁）；idOS 阶段 2 在 TDE（03-05）全额解锁，阶段 1 分 6 个月；Cap、Igra 无锁仓（Igra 称“无悬崖无归属”）。

### B3 逐场结果
| 项目 | 拍卖期 | 清算价/地板 | FDV | 募集 | 参与 | 上市/TGE | 价格/清算价（TGE日→d1→d7→d30→现） | 状态 |
|---|---|---|---|---|---|---|---|---|
| Aztec | 2025-11～12 | 0.047（0.00001551 ETH；高于地板 60%） | $486M（icodrops） | $59.1M | 约 17,000 | 2026-02-12 | 0.47→0.44→0.39→0.47→0.36 | 已上市，**破发**（-53%～-64%） |
| Rainbow | 2026-02-03～05 | 地板 0.10（清算价**未找到**，比值为上界） | $100M | ≤约 $0.5M（5M 枚=0.5%）；icodrops 列 $18M 疑指另一轮 | – | 2026-02-05 | 0.68→0.35→0.29→0.20→0.23 | 已上市，**破发** |
| idOS | 2026-02-25～03-05 | 约 0.04（地板 0.035） | $40M | 193.6 ETH（约 $0.3–0.4M） | 1,672 bids | 03-05（Arbitrum） | 0.86→0.96→0.72→0.32→0.21 | 已上市，**破发**；只卖出计划 10M 的 58%（欠额） |
| Cap Labs | 2026-06-09～18 | 0.011（地板 FDV $75M） | $106M | $16.4M | 1,002 bids，5.5x | 2026-06-26 | 2.23→2.68→2.04→1.90→约 6x（现价 0.07，**未核实 FDV 是否同口径**） | 已上市，高于清算价 |
| Igra | 2026-03-26～04-02 | 地板 0.006（清算价未找到） | – | 未找到 | – | CG 首价 2026-06-08 | 1.26→1.16→0.99→1.24→0.63（相对地板） | 已上市；不进统计 |
| STRATO | – | – | – | 未找到 | – | – | – | 未知 |
来源：https://blog.uniswap.org/aztec-cca ；https://icodrops.com/aztec/ ；https://www.idos.network/blog/public-sale-results ；https://www.kucoin.com/news/flash/cap-labs-completes-cap-token-auction-at-106m-fdv-5-5x-oversubscribed ；https://phemex.com/news/article/rainbow-wallet-launches-rnbw-token-auction-on-uniswap-57485 ；价格＝CoinGecko 日快照（ids：aztec、rainbow-3-2、idos、cap-4、igra）。

### B4 小结
- 有清算价且已上市：n=3（Aztec、Rainbow[上界]、Cap）。首价/清算价 中位 0.68（>1：1/3，>3：0/3，>10：0/3）；d30/清算价 中位 0.475（>1：1/3）。若加上 idOS（d30 0.32），n=4，d30 中位 0.40，>1：1/4。**样本极小，不外推。**
- 退款/未上市/延期：Aztec 从拍卖（2025-12）到 TGE（2026-02-12）隔约 2 个月；无退款场次；idOS 欠额（未卖满）。
- 机制含义：CCA 清算价由需求决定，没有“发行折扣”；4 场里 3 场上市后低于清算价。这与 MetaDAO（固定低价+超募退款）、币安钱包（固定超低价+超募）的结构不同：CCA 买家付的是市场价，上市即无“预设折价”。

### B5 缺口
- 完整 CCA 名单（Uniswap Auctions 页是 JS 渲染；cryptorank “Uniswap CCA” 页被拦）；STRATO、Igra 的结果；Rainbow 清算价；各场工厂版本。

---

## C. 币安钱包 TGE（Binance Wallet / BuildKey / Prime Sale）

### C1 形态与事件率
币安钱包有五种形态，**统计时必须分开**：
1. “独家 TGE”编号系列（PancakeSwap，Alpha 积分 15 分，BNB 认购，每人一般上限 ≤ 约 3 BNB）：到 2026-03-25 已到第 45 期（Perle，https://phemex.com/news/article/binance-wallet-to-list-perle-prl-in-45th-exclusive-tge-offering-68837）。已查到编号：#12 OKZOO 2025-04-25、#17 Alaya 05-16、#20 Reddio 05-29、#21 CUDIS 06-05、#22 MEET48 06-11、#24 Bombie 06-17、#26 LOT 06-20、#27 NodeOps 06-30、#28 Palio 07-07、#30 Velvet 07-10、#32 DeLabs 07-28、#35 Mitosis 08-28、#40 LAB 10-14、#43 Collect 12-27、#44 Zenchain 2026-01-07、#45 Perle 2026-03-25。#1–#11、其余编号未逐一查到。
   - 事件率：2025 年≥43 期（#43 在 12-27；约每 8 天一期，6–8 月最密）；2026 年 1–9 月只查到 #44（01-07）和 #45（03-25）。#45 之后**未找到**编号期，可能是系列变少/改形态（Prime Sale、Booster），**未核实**。
2. 联名 bonding-curve TGE（four.meme）：2025-07-16 第 1 期 RION（Hyperion）。
3. Pre-TGE + Booster（币安官方公告，Latest Activities 栏）：2025-06-23 Codatta、07-16 BAS、07-21 Treehouse、07-23 Bitlayer、08-13 Reveel、08-15 OpenEden、08-22 Hemi、08-28 OpenLedger、08-29 Pieverse、09-01 Holoworld、09-18 Astra Nova、09-23 ZEROBASE、09-30 Turtle、11-04 zkPass、12-19 Bitway、2026-01-09 Unitas、02-04 Opinion、02-25 Sentio。（来源：币安公开公告接口 `bapi/composite/v1/public/cms/article/list/query?catalogId=93`，已翻完 3164 条，仅标题；2025 年 17 场、2026 年 3 场，2026-03 后无新的 Pre-TGE 公告。**币安公告栏的 Pre-TGE 公告 2026-02-25 后断了**，而二手来源显示 Sentient（01-19）、Sentio（04-07 认购）仍有 Pre-TGE，说明公告栏不全。）
4. Prime Sale（2025-10 起）：YB（10-13，#1）、MMT（10-31，#2）、FOGO（2026-01-14，#3）、Sentient（01-19）等；2026 年后续期数**未查全**。
5. BuildKey TGE（Aspecta 联名，保证金式 bonding-curve 凭证）：2025-09-19 第一期 River，$100M、993x 超募；后续期**未查到**。
- 另：币安 Alpha 2025 年共 221 个代币经空投/TGE/Booster 上线，105 个进入合约、38 个进入现货（https://finance.yahoo.com/news/binance-alpha-2025-recap-token-184928086.html ，二手）。
- 名单可能不全：是；本节只是下限。

### C2 额度分配机制
- 门槛：Alpha 积分（常见门槛 190–256 分，认购扣 15 分；Prime Sale 门槛如 Sentio 243 分）。积分按滚动 15 天计，与交易量、持仓挂钩（二手）。
- 分配：超募制（oversubscription）—按用户存入 BNB 占总存入的比例分配，其余退回；每人上限 3 BNB（Pre-TGE 常见）、6 BNB（FOGO）、7 BNB（MMT）。独家 TGE 系列规则近似（PancakeSwap 固定价）。
- BuildKey：先存 BNB 得 Key（凭证，价格沿 bonding curve 上行），可在曲线池交易，TGE 日兑换代币；Phase1 需≥209 积分。
- KYC/地域：币安钱包为自托管入口，实际地域限制在币安/Alpha 协议条款，本次未找到单独条款；**需另查**。
- 解锁：Pre-TGE 样本多为 TGE 当日部分可交易（币安 Alpha 开启交易）；各项目另有 Booster 代币。具体 TGE 解锁比例本次未逐场采集。
- 关键结构：认购价通常是上市价的 1/2～1/50，但超募 40x～238x（见下），按比例分到的额度＝1/超募倍数。

### C3 逐场结果（有认购价的 9 场，其余见 CSV）
| 项目 | 形态 | 认购日 | 认购价 | 募集 | 超募 | 上市首价/认购价 | d1 | d7 | d30 | 现价/认购价（2026-10-03） |
|---|---|---|---|---|---|---|---|---|---|---|
| Yield Basis YB | Prime #1 | 2025-10-13 | 0.10（FDV $100M） | $2.5M 目标 | 238x（456,060 BNB，约 $6 亿） | 7.78 | 6.77 | 3.73 | 4.54 | 0.87 |
| Momentum MMT | Prime #2 | 2025-10-31 | 0.10 | 约 $1.5M 目标 | 376x（522,966 BNB） | 3.47 | 26.6（尖峰） | 5.40 | 2.55 | 1.9 |
| Fogo FOGO | Prime #3 | 2026-01-14 | 0.035（FDV $350M） | $7M | 40.8x（316,385 BNB） | 1.64 | 1.41 | 0.88 | 0.63 | 0.15 |
| Sentient SENT | Prime | 2026-01-19 | 0.01106 | $7.6M | – | 1.87 | 2.76 | 2.25 | 2.11 | 1.92 |
| Sentio ST | Pre-TGE | 2026-04-07 | 0.02 | $0.2M | – | 5.56 | 4.55 | 3.40 | 3.54 | 0.49 |
| Bitway BTW | Pre-TGE | 2025-12-22 | 0.008 | $1M | – | 1.23 | 1.31 | 3.47 | 2.50 | 180（现价 1.44） |
| Unitas UP | Booster+TGE | 2026-01 | 0.005 | – | – | 15.9 | 15.1 | 25.3 | 39.7 | 44.9 |
| ZEROBASE ZBT | Pre-TGE | 2025-09-24 | 0.02 | $0.2M | 超募 | 35.7 | 20.8 | 13.8 | 6.78 | 4.3（0.0865/0.02）；但相对上市价 -92% |
| Astra Nova RVV | Pre-TGE | 2025-10-16 | 0.0005 | $0.075M | 超募 | 41.7 | 17.2 | 26.5 | 10.6 | 0.06 |
另有认购价但无 d1/d7/d30（CoinGecko 窗口外）：Bitlayer 0.02（$0.4M，现价/认购价 2.5）、Hemi 0.0015（$0.15M，400x；单一来源；现价/认购价 4.0，但 2025-10-04 曾为 62）、Pieverse 0.01（$0.2M，现价/认购价 135）；River BuildKey 无认购价。
来源：币安钱包官方推文（https://x.com/BinanceWallet/status/1977694061080502273 、…/2011424778675200411 、…/1983839251713421755 、…/1968602237409837567）、icodrops（认购价，二手）、panewslab、CoinGecko 日快照。TGE 日期对 MMT、SENT、UP 取“CoinGecko 首个日期”，**为推定**。

### C4 小结（n=9，仅“有公开认购价”的 Pre-TGE/Prime 场次；独家 TGE 编号系列 43 期基本无价格数据）
- 上市首价/认购价：中位 5.56；>1：9/9；>3：6/9；>10：3/9。
- d30/认购价：中位 3.54；>1：8/9；>3：5/9；>10：2/9。d7 中位 3.73，>1：8/9。
- 但：(a) 选择偏差——有认购价的多是新闻多的头部场次，且 2025 年的 5 场（ZBT、RVV、BTR、HEMI、PIEVERSE）认购价取自单一二手来源，疑有口径问题（Hemi 0.0015 vs 上市 0.09，60 倍）；(b) 2026 年的 Prime Sale 倍数明显低于 2025 年（FOGO 1.64→0.63；SENT 约 2 倍），折价在收窄；(c) 超募 40x–376x：一个满额 3 BNB 的用户实际只被分到约 1/40～1/376 的额度，期望收益＝比值×份额，不是比值本身；(d) 币安官方称 2025 年 15 场 Alpha TGE “认购价平均比首日收盘低近 8 倍”（Yahoo/二手），与本表同量级。
- 退款/未上市/延期：Pre-TGE 全部已上市；Bitway 认购到上市间隔约 70 天（2025-12-22→2026-03-03，延期）；未发现退款场次。
- 现价/认购价（9 场）：中位 1.9；>1：5/9（YB 0.87、FOGO 0.15、Sentio 0.49、RVV 0.06 为 ≤1）。但相对上市首价，多数已回落（YB 0.087 对上市 0.78–1.14；ZBT -92%）。

### C5 缺口
- 编号 TGE #1–#11、#13–#16、#18–#19、#23、#25、#29、#31、#33–#34、#36–#39、#41–#42 的名单与全部价格；认购价；2026-03 之后是否仍有编号期；BAS（Pre-TGE 2025-07-16）、Reveel 等的结果；币安公告栏 CMS 接口只含公告标题；X 帖子无法抓取（只拿到搜索摘要）。
- 币安官方 TGE 帖大量在 X；币安公告页本身是 JS 渲染，已改用公开 CMS 列表接口。

---

## D. 积分/空投型 TGE

### D1 Bitquery 2026 空投统计（一手链上统计，Bitquery）
- 样本：2026-01 至 09 月，Ethereum/BNB Chain/Base/Arbitrum 上“≥5,000 钱包且≥$100 万（领取日价）”的空投共 51 场（BNB 24、Ethereum 14、Base 12、Arbitrum 1），202.4 万领取钱包，$8.09 亿（领取日价；CAT 一个占 $3.52 亿，为 DEX 价）。来源：https://bitquery.io/investigations/crypto-airdrops-2026 及 CSV（已原样存档）。
- 事件率：51 场/9 个月（只含上述门槛；**不含 2025 年**，也不含小于门槛的空投）。
- 结果（CSV `price_vs_first_week`＝代币现价相对“首周价格”的变动，不是相对发行价；空投免费，无发行价）：46 场已满月，其中 35 场低于首周价，中位 -48%（Bitquery 文）；CSV 全 51 行中位 -40.4%，36/51 为负，22/51 低于 -50%。
- 持有：第 24 小时内中位 73% 的领取者已转出；30 天后中位 23% 的领取者仍持有≥一半（CSV 中位 23.0%）；前 10% 领取者拿走中位 73% 的代币；7 场未上市（仅 DEX 价）。
- 与币安钱包的关联（https://www.bitquery.io/investigations/binance-wallet-airdrops ）：其中 10 场 BNB Chain 空投里，领取后 24 小时内 43% 的领取者经币安钱包路由器卖出，中位 70 秒；5% 的领取者在中位空投里 30 天后仍持有≥一半（其他空投 30%）。币安钱包直发的 4 场（CSV）：Unitas +157%、Bitway +9249%（首周价极低）、Arcium -11%、TermMax -93%（相对首周价）。
- 积分/Alpha 机制：币安钱包 Alpha 空投需积分；Bitquery 另有 Alpha 积分刷分调查（未读）。

### D2 BlockBase：Binance Alpha 项目表现（二手，样本小、期间短）
- 范围：2025-04-28～05-17 的 11 场 Alpha 空投（https://insights.blockbase.co/binance-alpha-projects-research/ ，2025-05-21 发表）。
- 结果：9/11 首日收盘低于首日开盘；从首日收盘起 3 日中位 -30%，7 日中位 -37%（仅 Haedal +13%、SXT +10% 为正）；仅 SIGN、HAEDAL 在首日之后创出 ATH。每个空投平均价值约 $80–$100，11 个合计约 $1,100–$1,600（单一用户案例）。
- 用途：作为“免费型发行”的基线，上市后价格走弱是常态。

### D3 小结
- 空投型（免费）无发行价，所以“首价/发行价”无定义。可比统计：上市后相对首周价，中位 -40%～-48%，约 70%～76% 的币低于首周价；CSV 51 场中 7 场未上市（14%）。
- 与有折价的发行（MetaDAO、币安 Prime Sale）不同：买方无成本基础，卖压集中在首小时/首日；钱包持有率极低。

---

## 交叉观察（仅供上游参考，不是结论）
1. 平台“发行价/上市价”关系分三类：MetaDAO（池按 ICO 价播种；上市后 d30 中位约 1.46x，2026-10 现价中位 0.95x）；币安 Prime/Pre-TGE（深折价+超募，上市价 3–40 倍认购价，但份额=1/超募倍数）；CCA（市场清算价，4 场里 3 场上市后破发）。
2. 母体构成：MetaDAO 的“失败”主要在 futard.io（81/90 未达最低额）而非 curated 场；curated 23 场 22 场成功，后续风险是 ICO 后的清盘/清算（至少 3 场）。
3. 大多数“ATH 倍数”在 2026-10 前已被回吐：Avici、Umbra、Yield Basis、Aztec 现价均低于其对应的发行/认购价或上市首价。
4. 所有数字的可复核性：一手＝币安/MetaDAO 官方推文、Uniswap 与 idOS 官方博客、Bitquery 链上统计、GeckoTerminal/CoinGecko 价格；其余二手。

## 文件
- /tmp/claude-1000/-home-ancillary/169f7497-1287-49b5-9fec-a864f119d993/scratchpad/tge_desk_B.md （本文件）
- /tmp/claude-1000/-home-ancillary/169f7497-1287-49b5-9fec-a864f119d993/scratchpad/tge_desk_B_events.csv
- /tmp/claude-1000/-home-ancillary/169f7497-1287-49b5-9fec-a864f119d993/scratchpad/bitquery_airdrops_2026.csv
- 中间文件：cg_*.json（CoinGecko 日线）、ohlc1/2/3.json（GeckoTerminal 日线）、bn93.json（币安公告标题 3164 条）、compile.py（生成 CSV 与比值统计的脚本）。

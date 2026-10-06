# D2 平台扫描 C 组（O1a 发行申购：优先资格机制）

检索日期：2026-10-06。**本文件只含机制，不含价格与收益。**

说明：多数官方页面当次抓取失败（socket 中断、404、403）；失败的部分写“未找到”。各场所“2025-10-06～2026-10-04 场次数”均**未能从官方来源核实**，只记录搜索结果中出现的零星日期（二手，且摘要未经原页核对）。标注：【原文】=官方页面摘录，【转述】=工具对官方页面的摘要，【二手】=非官方来源。

---

## 1. MetaDAO（futarchy 发行）

1. **是否仍在发行／场次**：仍在发行（二手）。场次数：未找到。搜索摘要中出现的日期：Ranger 4 天 ICO 始于 2026-01-07；Credible Finance 始于 2026-07-13；Rip Cars 于 07-25 截止（均二手，日期来自新闻摘要，未核对原页）。最近一场日期：未能确认（至少不早于 2026-07-25）。
   - https://blockworks.com/news/rangers-ico-metadao 【二手】
   - https://solanacompass.com/news/credible-finance-cred-raise-crosses-20m-and-10x-oversubscription-in-under-24-hours 【二手】
   - https://solanacompass.com/news/metadaos-rip-cars-ico-closes-127x-oversubscribed-with-319m-in-commitments 【二手】（URL 见搜索结果 solanacompass.com 同名文章）
2. **优先资格怎样取得**：官方文档称分配取决于"承诺金额与承诺早晚"。账户 USDC 每秒累积：accumulator += committed_amount × elapsed_seconds；份额 = 个人累积量 / 总累积量；另有"fill boost"，对池子尚稀疏时入场的资金加乘数。规则公开。
   - https://docs.metadao.fi/how-launches-work/sale 【转述（搜索摘要）；本次直接抓取失败】
   - 另有二手称：基金与天使有赛前谈定的保证额度，位于时间加权竞争之外；近期试验 "Ownership Score"，最多保留 50% 额度给持有此前 ownership token 的人，每持有 1 美元每日得 1 分。https://alearesearch.substack.com/p/metadao-a-new-allocation-formula 【二手，此点未在官方页核到】
3. **成本、周期、被超过**：资格即资金占用时间；募集期 4 天（官方转述）。时间加权下，他人更早或更多的承诺会稀释份额；总承诺越大份额越低。无独立“积累周期”。
4. **官方统计（优先 vs 普通中签率/数量差）**：未找到官方统计。（二手新闻称超募后各人只获约 5% 或更低的承诺额；此为结果性数字，按规则不记个案数值。）
5. **预缴、退款、锁定**：4 天内承诺 USDC（预缴）；超出创始人"discretionary cap"部分退回；未达最低额全部退款（官方转述）。解锁／TGE 日程：未找到。
   - https://docs.metadao.fi/how-launches-work/sale 【转述】
6. **资金时间线**：承诺（首次动用资金，第 0～4 天内，越早累积越多）→ 募集结束时按累积量定份额 → TGE 时代币发放与超额 USDC 退回（二手：自动于 TGE 退还）→ 资格失效（4 天窗口结束）。
7. **参与资格**：条款原文要点（转述）：年满 18 岁或有缔约能力；不得居住于或位于美国及受制裁地区（克里米亚、古巴、伊朗、朝鲜、叙利亚、俄罗斯等），"There are no exceptions"；禁止用 VPN 规避；不得为受限者代持。KYC 要求：未找到。
   - https://www.metadao.fi/terms-of-service 【转述（搜索摘要）；直接抓取失败】

---

## 2. Uniswap CCA（连续清算拍卖）

1. **是否仍在发行／场次**：协议上线（2025-11-14 发布，二手新闻称首场为 Aztec 社区阶段与 12-02 公开阶段；2026-06 Uniswap Labs 称可在 Web App 直接配置拍卖）。2025-10-06～2026-10-04 场次数：未找到；最近一场：未找到。
   - https://blog.uniswap.org/continuous-clearing-auctions（官方，直接抓取超时，仅见搜索标题）
   - https://www.theblock.co/post/378864/uniswap-continuous-clearing-auctions 【二手】
2. **优先资格**：协议本身无优先资格。技术文档称拍卖可选配"validation hooks"，用于限制可提交的出价，hook 必须 revert 表示无效（可据此做白名单，由发行方自定）。
   - https://github.com/Uniswap/continuous-clearing-auction/blob/main/docs/TechnicalDocumentation.md 【转述】
3. **成本、周期、被超过**：无资格积累；每笔出价按剩余区间拆分（官方搜索摘要："divided across all remaining auction intervals"），无时点抢先。
   - https://developers.uniswap.org/docs/liquidity/liquidity-launchpad/overview 【转述】
4. **官方统计**：未找到（机制上无优先层）。
5. **预缴、退款、锁定**：出价预缴货币。拍卖结束后，出价高于最终清算价的可 exit；未毕业（raised < required）时可经 exitBid 全额退款；领取代币须待 claim block 且先 exit；毕业前不能 exit 也不能 sweep。解锁日程由各发行方配置：未找到统一规则。
   - 同上技术文档 【转述】
6. **资金时间线**：出价（预缴）→ 逐区块按清算价成交（pro rata 于该区块超额时，二手）→ 拍卖结束后 exit → claim block 后领币 → 无“资格失效”概念。
7. **参与资格**：协议层无；由各发行方 hook 与前端决定。官方概念页未涉及地域或 KYC：未找到。

---

## 3. Fjord Foundry（LBP 与固定价销售）

1. **是否仍在发行／场次**：官方帮助中心仍在；2025-10～2026-10 场次数、最近一场日期：未找到（搜索只返回累计数字与旧文章）。
   - https://help.fjordfoundry.com/fjord-foundry-docs/welcome-info/welcome-to-fjord
2. **优先资格**：有“白名单销售”（创建者上传 CSV 地址，仅名单可参与；开售后名单锁定，不能新增；可与公开销售并行）。无按持仓／质押的优先层；文档未含白名单内的分配优先规则。
   - https://help.fjordfoundry.com/fjord-foundry-docs/for-sale-creators/fjord-features/whitelisted-sales 【转述，直接抓取成功】
   - 分档销售（Tiered Sale）：按价格档位依次售罄，“可从任一可用档购买”，文档未提用户优先；各档可设单钱包上限。https://help.fjordfoundry.com/fjord-foundry-docs/for-sale-participants/token-sale-types/tiered-sales 【转述】
3. **成本、周期、被超过**：白名单由创建者人工划定，资格取得方式由项目方决定：未找到统一规则。
4. **官方统计**：未找到。
5. **预缴、退款、锁定**：平台支持代币锁仓与归属（二手）；具体因销售而异：未找到。
6. **资金时间线**：未找到统一时间线（LBP 按权重随时间变动；固定价先到先得），不具体展开。
7. **参与资格**：分档销售页未提 KYC 或地域限制（转述）；其他：未找到。

---

## 4. 质押分级启动台

### 4a. Polkastarter
1. **是否仍在发行**：二手搜索称 2025 末～2026 初仍有项目（MultichainZ、PlusMore、Helios）及 2026-03 的 XO IDO 白名单开放公告；官方项目页抓取无内容。场次数与最近日期：未能核实。
   - https://polkastarter.com/blog/the-xo-ido-allowlist-on-polkastarter-is-now-open 【二手（官方域名，仅见标题）】
2. **优先资格**：POLS Power（钱包持有＋质押＋LP 汇总）。≥1,000 起可参加抽签，每 250 POLS Power 一张票；更高档票价值乘数 1.1/1.15/1.20/1.25；≥50,000 保证通过白名单、首阶段 4 小时分配窗口、更大额度。规则在官方知识库公开。
   - https://support.polkastarter.com/article/19-what-is-pols-power 与 https://support.polkastarter.com/article/49-how-our-tier-system-works 【本次直接抓取 404；以下内容来自搜索摘要转述，未核原页】
3. **成本、周期、被超过**：需持有／质押 POLS；30,000 以上免冷却期（转述）。保证档为固定门槛，不会被他人超过；抽签档按票数随申请人数稀释。冷却期细节：未找到。
4. **官方统计**：未找到。
5. **预缴、退款、锁定、解锁**：未找到。
6. **资金时间线**：持币／质押（先于快照）→ 白名单申请与抽签 → 销售 → 兑现：未找到日程。
7. **参与资格**：KYC、地域条款：未找到（抓取 404）。

### 4b. DAO Maker（SHO）
1. **是否仍在发行**：未找到 2026 年的官方公告；搜索无 2026 场次。判断：不确定。
2. **优先资格**：质押 DAO 代币于 DAO Vault（最低约 500 DAO）；五档（2,000/4,000/10,000/25,000/50,000 DAO）；按档位分抽签权重（1x、4.6x、9.76x、26x、69.5x、149x）；流动性质押 x3 乘数。规则公开，但这是旧版文章（日期未核）。
   - https://bkcrypto.medium.com/dao-maker-frequently-asked-questions-faq-112e6cb2ab58 【二手】
   - 官方：https://support.daomaker.com/support/solutions/articles/67000688027-what-are-the-shos-requirements- （抓取失败，未核）
3–7. 成本、统计、解锁、KYC：未找到。

### 4c. Seedify
1. **是否仍在发行**：二手称仍活跃（“2024～2025 约 75 场 IDO”）；2025-10～2026-10 场次与最近日期：未找到。
2. **优先资格**：九档 SFUND 持仓；Tier 1 抽签（每场 500 个钱包），Tier 2～9 保证额度；按档位池权重分配；快照确认档位；KYC 钱包自动白名单。
   - https://docs.seedify.fund/whitepaper/seedify.fund-launchpad 【直接抓取 403；内容来自搜索摘要转述】
   - https://blog.seedify.fund/seedify-blockchain-gaming-launchpad-the-new-tier-system-4e331e05b4c0 （官方博客，未打开，可能为旧版规则）
3～7. 门槛细节（二手：200 到 75,000 SFUND）、解锁、官方统计：未找到。

### 4d. ChainGPT Pad
1. **是否仍在发行**：官方路线图 2026 Q1-Q4 列有 Pad V4（标准化公开销售格式、动态 FCFS、保证金与退款自动化）；二手称 2026-04-20 有 AITECH 发行公告（日期待定）。2025-10～2026-10 场次：未找到；路线图页无具体 IDO 名称与日期。
   - https://docs.chaingpt.org/overview/road-map/2026-q1-q4 【转述】
2. **优先资格**：质押 $CGPT 得积分：积分 = 质押量 × 池乘数（示例 1.1×/1.4×/2×/3×，长期锁定乘数更高）；四档 Bronze/Silver/Gold/Diamond；二手称 Bronze 2,000 点仅 FCFS 轮、Silver 20,000 点起进保证轮。官方 tier-system 页不给门槛。标准 IDO 流程：钻石预购（可选）→ 保证轮 → FCFS 轮；先登记兴趣、快照后公布额度。
   - https://docs.chaingpt.org/our-ecosystem/chaingpt-pad/staking 【转述】
   - https://docs.chaingpt.org/our-ecosystem/chaingpt-pad/standard-ido-tiered 【转述】
   - https://docs.chaingpt.org/our-ecosystem/chaingpt-pad/tier-system 【转述：门槛未列出】
3. **成本、周期**：多数池锁定至周期结束；解质押后档位是否丢失：未找到。他人质押会通过总额度稀释份额（额度由档位、登记人数、销售容量共同决定）。
4. **官方统计**：未找到。
5. **预缴、退款、解锁**：“公开销售（认购制）”按承诺额（含质押加成）pro rata 分配，超额部分作为 Excess Refund 退回；可选 Full Refund（视活动而定）；不质押者领币手续费 3%，Diamond 0%；加成 1.00x～10.00x。领取按项目归属表（TGE 解锁加后续释放）。
   - https://docs.chaingpt.org/our-ecosystem/chaingpt-pad/public-sale-subscription 【转述】
6. **资金时间线**：质押（先于快照）→ 登记兴趣 → 快照与额度公布 → 保证轮／FCFS 或认购 → 领取与归属 → 质押到期解锁。
7. **参与资格**：须完成 KYC，领取也需 KYC；“部分司法辖区可能受限”，名单未录。

---

## 5. 其他活跃且有优先资格的平台（≤3）

### 5a. Legion（含 Kraken Launch 合作）
1. **是否仍在发行**：是。官方帮助页：Squid ($QUID) 销售 2026-06-30 13:00 UTC～2026-07-03 13:00 UTC。场次数：未找到。最近一场：至少为该场。
   - https://help.legion.cc/en/articles/15609626-how-to-participate-in-the-squid-quid-sale-on-legion 【转述（直接抓取）】
2. **优先资格**：Legion Score（0～1000；链上活动、开发、社交、过往投资行为）；二手称每场最多 20% 保留给 Legion Score 持有者，其余先到先得（Kraken 合作公告）。官方：由项目方审核申请并决定每人额度，Legion 不决定；高分不保证。
   - https://legion.cc/for-investors 【转述】；https://www.dlnews.com/external/kraken-brings-legions-crypto-native-fundraising-to-millions-of-global-users/ 【二手】
3. **成本、周期、被超过**：分数由多项历史行为累积，无单一资金门槛；分数动态，可被他人超过（项目内相对排序）。
4. **官方统计**：未找到。
5. **预缴、退款、锁定**：窗口内存入 USDC；结果后自动使用、取回超额或被拒后取回全部；官方称结束后 14 天内可申请退款；TGE 用同一钱包领取。
6. **资金时间线**：积累分数（长期）→ 窗口内存款（3 天）→ 项目方决定额度 → 退款窗口 14 天 → TGE 领取。
7. **参与资格**：不得为阿联酋、英国、美国、俄罗斯、伊朗、叙利亚、朝鲜、古巴居民及乌克兰受制裁地区；须 KYC 与 90 天内地址证明；需主网 USDC 与 ETH 手续费。

### 5b. Kaito Launchpad
仅有二手：按 Yap（社交影响力）分、链上历史、KAITO 持仓与质押、过往参与与地区额度决定优先（https://reports.tiger-research.com/p/public-launchpad-boom-eng 【二手】）。官方页未打开；其余六项：未找到。

### 5c. Buidlpad
官方优先规则：未找到（搜索只见 Lombard 销售用 KYC 与认购，二手）。其余：未找到。

---

## 最后一节：查不到的项

- 所有场所“2025-10-06～2026-10-04 场次数”：均未能核实（官方页面无场次列表或抓取失败）。
- 所有场所“优先 vs 普通中签概率与获配数量的官方统计”：均未找到。
- MetaDAO：官方 docs 与 terms 页本次直接抓取失败（内容来自搜索摘要）；KYC 要求、解锁日程未找到；"Ownership Score"和机构保证额度仅见二手。
- Uniswap CCA：官方 blog 抓取超时；各场的 hook、地域、KYC 条件未找到。
- Fjord Foundry：2025-10 后的场次、KYC 与地域条款、退款与解锁规则未找到。
- Polkastarter：知识库两页抓取 404，档位内容为搜索摘要；KYC、地域、退款、解锁未找到；官方项目页无内容。
- DAO Maker、Seedify：2026 年是否仍有发行未能确认；官方页抓取失败（Seedify 403）；规则多为旧版文章。
- ChainGPT Pad：tier-system 官方页无门槛数字；Bronze/Silver 门槛来自二手搜索摘要；受限司法辖区名单未录。
- Kaito、Buidlpad：官方规则未打开。
- 搜索摘要中出现的价格、倍数、超额认购倍数等结果性信息未记录。

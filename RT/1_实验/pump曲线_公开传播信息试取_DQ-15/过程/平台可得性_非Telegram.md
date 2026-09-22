# DQ-15 第一步：非 Telegram 平台可得性检查

> 2026-09-22。**只查"能不能取到"，不做任何收益分析**，检索方全程未接触任何价格/收益数据。窗口：A 周 = 2026-06-01T00:00Z ~ 2026-06-08T00:00Z（UTC）。合约地址正则：`[1-9A-HJ-NP-Za-km-z]{32,44}pump`。分母：A 周全部发行 191,192 个 mint（`raw/inputs/a_week_mints.txt`）、H1 的 308 个触发（`raw/inputs/h1_triggers_blind.csv`）。约束：≤1 req/s、每平台 ≤800 请求、不登录、不付费、不读 `.env`。原始返回见 `raw/platforms/<平台>/`；规范化产出见 `raw/normalized/`。

## 1. 总表

| 平台 | 访问方式 | 能否按时间窗全量取 | A 周帖子量 | 含合约帖子数 | 不同合约数 | 在 A 周清单内 | 编辑/删除可识别性 | 结论 |
|---|---|---|---|---|---|---|---|---|
| **Reddit**（5 个候选版块） | Arctic Shift 公开 API，`arctic-shift.photon-reddit.com/api/{posts,comments}/search`，按 `after`/`before` 游标翻页，无需密钥 | **能**，按 created_utc 游标翻页可取完整连续窗口（已验证） | posts 765、comments 1816（5 版块合计，逐日见 §2.1） | 47 条消息（去重后） | 36（跨版块并集） | **23** | 有：`edited`、`removed_by_category`、`selftext=[removed]/[deleted]` 字段完整；本窗口样本中未观察到任何编辑（36 小时后应与官方 dump 一致） | **可用** |
| **4chan /biz/（warosu.org）** | 网页 GET 表单 `?task=search2&search_text=...&search_datefrom=...&search_dateto=...`，无需密钥 | **不能**：空关键词/日期范围查询返回"No posts found"，必须给具体关键词才能出结果，无法枚举全量帖子；高频板块全量下载超出预算 | 未取得（无法枚举；测试的 12 个关键词/地址组合在 A 周内共命中约 4 条帖子，与 pump 合约均无关） | **0** | **0** | **0** | 有删帖标记（`search_del` 过滤器可选"仅看已删/仅看未删"），**无编辑**（4chan 协议本身不支持编辑帖子） | **部分可用**（平台机制支持增量式关键词检索+删帖识别，但 A 周内未检出任何 pump 合约提及） |
| **4chan /biz/（archived.moe / 4plebs）** | 同类网页/API | 不明（无法测试） | — | — | — | — | — | **不可用**：Cloudflare "Attention Required" 拦截所有请求（含 `/_/api/chan/search/` API 路径），无浏览器 JS 执行能力无法通过 |
| **4chan（desuarchive.org）** | — | — | — | — | — | — | — | **不适用**：该站不收录 `/biz/`（只收录 a/aco/an/c/cgl/co/d/fit/g/his/int/k/m/mlp/mu/q/qa/r9k/tg/trash/vr/wsg） |
| **Farcaster**（官方 Hub/Snapchain） | 官方文档只给出 `127.0.0.1:3381`（自建节点）或 Neynar（付费/需 key）两条路径；曾经免费的社区公开 Hub（`nemes/hoyt/lamia.farcaster.xyz`、`hub.farcaster.standardcrypto.vc:2281`）已下线（503 / TLS 连接被重置） | **不能**：协议原生 API 是按 FID 查询，没有全局关键词或全局时间窗端点；全量枚举需自建全节点同步整个网络，超出预算 | — | — | — | — | — | **不可用**（无免费公开端点） |
| **Farcaster**（Warpcast 客户端内部接口） | `client.warpcast.com/v2/search-casts?q=...`，未登录可访问（非官方文档接口） | **不能**：按相关性排序，非按时间可枚举；`limit=100` 单次拉到的 97 条结果跨度 2024-11~2026-09，**其中 0 条落在 A 周**；无更深翻页（`limit=100` 时不返回 cursor） | 0（无法覆盖 A 周） | 0 | 0 | 0 | 未测（无落在窗口内的样本） | **不可用**（关键词检索不保证覆盖任意历史时间窗） |
| **Bluesky** | 公开 AppView `public.api.bsky.app`；`getProfile`、`searchActors` 等端点可用（200），但 `app.bsky.feed.searchPosts`（含 `searchPostsSkeleton`）固定返回 **403**（BunnyCDN 边缘拦截，换 UA/Referer/Origin 头均无效） | 未验证（搜索端点本身即不可用；即使可用也只是关键词检索，非全窗口枚举）。历史全量只能靠订阅 firehose 实时抓取，事后无法回放 2026-06 | — | — | — | — | — | **不可用** |

## 2. 各平台细节

### 2.1 Reddit（Arctic Shift）

**访问方式**：`https://arctic-shift.photon-reddit.com/api/posts/search`、`.../comments/search`，参数 `subreddit`、`after`、`before`（ISO 时间）、`limit`（1–100，或 `auto`）、`sort`。无需密钥，文档动态限流（"普通用户每秒几个请求不用担心"），命中 429 时可看 `X-RateLimit-Reset` 头，本次全程未触发 429。另有 `/api/{posts,comments}/search/aggregate` 按天聚合计数，及 `/api/comments/tree`、`/api/subreddits/*`、`/api/users/*` 等端点未使用。

**取数方法**：先用 aggregate 端点按日出量摸底（10 次请求），确认 5 个候选版块（r/solana、r/SolanaMemeCoins、r/memecoins、r/CryptoMoonShots、r/pumpfun）量级在个位数到百位数/天，可全量下载；再用 `after=<上一页末条 created_utc+1>` 的游标翻页（`limit=100`），直到 `before=2026-06-08T00:00:00` 为止。**`limit=auto` 实测不可靠**（对 r/solana 评论只返回 174 条就在 2026-06-02 截断，未覆盖全周），改用固定 `limit=100` + 游标后稳定取全。共发出约 54 次请求（10 聚合 + 40 翻页 + 4 次前期探测），远低于 800 上限。

**逐日/逐版块量**（posts / comments，UTC 自然日，来自完整下载后按 `created_utc` 重新分桶，与 aggregate 端点的时区分桶不同、以此处为准）：

| 版块 | posts 合计 | comments 合计 | 含合约 posts | 含合约 comments | removed_by_category（posts） | edited（posts） |
|---|---|---|---|---|---|---|
| r/solana | 265 | 1088 | 1 | 1 | 145 | 0 |
| r/SolanaMemeCoins | 165 | 91 | 10 | 0 | 113 | 0 |
| r/memecoins | 136 | 286 | 6 | 3 | 100 | 0 |
| r/CryptoMoonShots | 110 | 239 | 4 | 1 | 81 | 0 |
| r/pumpfun | 89 | 112 | 19 | 2 | 36 | 0 |
| **合计** | **765** | **1816** | **40** | **7**（共 47 条消息，含合约） | — | **0** |

**合约映射**：47 条消息（去重后）里正则命中 36 个不同合约地址（跨版块并集），其中 **23 个**落在 A 周 191,192 个 mint 清单内，**2 个**落在 H1 的 308 个触发内（`GU527smM71ht8aCA8ouShfXhahVq6crz51FMbfZ8pump`、`DpPowzjETiU6421ReuwBB8XmDB7sMyB2JGzFLssYpump`）。不在 A 周清单内的地址，多半是 A 周之前创建、A 周内被继续讨论/拉盘的币（不是发现失败，是分母口径差异——发帖时间不等于铸造时间）。

**编辑/删除**：Reddit 原生字段 `edited`（false 或编辑时间戳）、`removed_by_category`（none/moderator/reddit/author/automod_filtered 等）、`selftext`/`body` 在删除后变为 `[removed]`/`[deleted]`。本窗口 765 条帖子中 **0 条**有编辑记录；**475 条**（62%）在快照时已带 `removed_by_category` 标记，说明这些小众加密版块的审核/垃圾过滤非常活跃，但**帖子本身连同元数据仍被完整保留和可取**（不是物理删除，是可识别的"已移除"状态），这正好满足"能看出删帖"的要求。Arctic Shift 文档说明其数据约 36 小时后与官方 `.zst` 转储一致，我们取数时间（09-22）距 A 周已过 3 个多月，数据应已稳定。

**样本作者判定**：47 条命中消息的作者用户名没有一个包含 `bot`/`auto` 字样或为 `AutoModerator`，按用户名启发式全部记为 `human`（见 `raw/normalized/reddit.csv`）。但需注意：多个作者名（如 `CapableOpportunity67`、`NeighborhoodFew877`）是 Reddit 未设置用户名时的默认随机生成格式，加上多条帖子使用完全相同的话术模板（例如 `#NewMemecoinAlert #GrandTheftTrencher #pumpfun #solanasummer #FeedTheGoons #Takebackthetrenches #memes #music` 这串标签在两条不同帖子里逐字重复），**更像是脚本化/规模化的自我推广而非官方机器人账号**——用户名启发式无法区分这种情况，是本轮的已知局限。

**20 条样本**（时间横跨 A 周全部 7 天，完整列表 47 条见 `raw/normalized/reddit.csv`）：

| # | 时间(UTC) | 来源 | 原文（截断 300 字） | 类型判断 |
|---|---|---|---|---|
| 1 | 06-01 00:07:31 | r/memecoins | Perfect entry boys! $TOPLESS🚀🚀 \| CA EuDGQRFvuDezFXsrPwA9XbeWj6PkgdVfKUuef7qBpump | 人写，短喊单 |
| 2 | 06-01 01:09:46 | r/pumpfun | Institutional-Grade Web3 Infrastructure: The $THREE ($339k MC) Multi-Cloud Strategy with AWS and IBM \| The conventional lifecycle of token launches on automated bonding curves typically mirrors a speculative pattern... | 人写，长文案自我推广 |
| 3 | 06-01 09:56:09 | r/pumpfun | $ICANTSLEEP – The ultimate meme coin for traders awake at 4 AM. ☕️🚀 [Website & X Live] \| Hey Reddit! Are you watching the charts 24/7?... We just launched $ICANTSLEEP on Pump.fun... | 人写，长文案自我推广 |
| 4 | 06-02 14:59:00 | r/SolanaMemeCoins | $PMV going viral \| DhaLZtprNqwpUYqhrTrtnCGSuxsdnk489UqSrZj3pump Pump Mind Virus is getting some motion today. Check them out. Active dev and team... | 人写，短喊单 |
| 5 | 06-02 16:26:59 | r/memecoins | From Memecoin to Real Impact: WWS just partnered with charity: water (Yes, the actual NGO) \| Hello everyone, Yousuf here again. When I first posted about World Water Supply (WWS)... | 人写，长文案，带人名 |
| 6 | 06-03 04:58:46 | r/pumpfun | PUMP UNTIL 4TH OF JULY LETS GET RICH \| # 7iqHbv2Y8oqKTDJ2AHBdEpiyUTpk1htrqNbfpLGjpump | 人写，短喊单 |
| 7 | 06-03 15:27:30 | r/pumpfun | AI the path to real filipino Democracy \| 🇵🇭 Help Build the Future of Filipino Democracy This token was created to help fund the development of BayanVoice... | 人写，长文案，叙事型 |
| 8 | 06-04 01:00:35 | r/SolanaMemeCoins | Major SALES \| Everyone running around with the chicken in his head cut off. Once upon a Time, we were all praying that we got in that lower deals... | 人写，杂谈+喊单 |
| 9 | 06-04 13:27:43 | r/pumpfun | 5h2FH6HtNcG9m9Zkus69Dm2rxhrqiyTaW1GaUY2Tpump Hunter The Gunner 🚀🚀🚀🚀🚀 #NewMemecoinAlert #GrandTheftTrencher #pumpfun #solanasummer #FeedTheGoons #Takebackthetrenches #memes #music | **模板化/疑似脚本批量发帖**（标签串与 #12 完全相同） |
| 10 | 06-04 16:12:40 | r/SolanaMemeCoins | Don't chase hype, lock in on conviction!! $Pissin \| Funniest meme in the space, doxxed team, 90+ days old... A4STU4JNW9euEWnsqnTFxAJnTKrPgcw4XNJqYMG1pump | 人写，短喊单 |
| 11 | 06-04 21:36:10 | r/pumpfun | I reveal you the biggest gem in the meme space🃏 \| Dex: https://dexscreener.com/solana/7om3hr4r... CA: Cz7LGKdZPpAxonXx23ZYPW3RtDQvjcf17ZDCZEzFpump | 人写，带外链 |
| 12 | 06-05 04:32:23 | r/pumpfun | GTA6 vs WW3 \| CA: 6f1d3Qyb1coViAR4VBm4Widqbu8pYAT1kkbLDJxFpump | 人写，极短喊单 |
| 13 | 06-05 13:10:25 | r/pumpfun | #NewMemecoinAlert #STARLINK 29 6tDgjeYkJV42N9BmiiXMu56pBoB4pN9dP61TWqRMpump #pumpfun #solanasummer #FeedTheGoons #Takebackthetrenches #memes #music https://starlink-elon-moons.lovable.app/ | **模板化/疑似脚本批量发帖**（标签串与 #9 完全相同） |
| 14 | 06-05 17:09:09 | r/pumpfun | https://pump.fun/coin/WX489YfGvZAvFyxnQMotm3AYpS3cmVqk2r566aHpump \| （无正文） | 人写但极简，近似自动播报 |
| 15 | 06-06 01:18:08 | r/SolanaMemeCoins | 🚀 New Solana Gem Just Dropped - CA: Fksmw79BNH8kzN2WWhaCFR4F2BPr5uhdji3Ekynipump \| Hey, Just spotted this fresh launch on pump.fun. Contract address: Fksmw79...  Early stage vibes — low MC, high potential... | 人写，模板化喊单 |
| 16 | 06-06 10:56:01 | r/pumpfun | $BPEPE - Blue Pepe on USDC \| 38m4k1TVYw5BY4AQjUwEFHZhyBNkuWynEtmgTsnrpump Deployed abt 7 hours ago off a fresh wallet, no sides and no insiders @ launch... | 人写，细节丰富 |
| 17 | 06-06 17:56:45 | r/SolanaMemeCoins | 📊 Ticker: $CJP Chain: Solana (SOL) Join the Colony: Contract Address (CA): 5mbEzkr8NMMynSx3aqhjEhHvk3MnGT1hQ42L76cPpump \|【正文已被移除，`removed_by_category` 非空】 | 人写（标题）+ 正文已删 |
| 18 | 06-07 02:21:17 | r/memecoins | 100% liquidity safe no rug pulls, my girlfriend wanted a community where everyone wins \| This is a coin my girlfriend has been working on... your money is 100% safe from a massive sell by my gf the dev... | 人写，叙事型 |
| 19 | 06-07 12:39:01 | r/memecoins（评论） | CA: 6yxLF2HpbzQehJZrpZS6MiAktSdc9NmDQ1sSWJyYpump BEST MEME GEM 1.5k MC | 人写，极短喊单 |
| 20 | 06-07 23:17:32 | r/pumpfun | Hey, Anyone can help me with this? \| Hey, it's me the Dev of GamerShit and This token is made for hardcore gamers... Hqes1FCBtFtkLchR29wjpuCHRubb2qm4zcTVhSCEpump So, i got one problem is that no one is buying... | 人写，求助型（非推广） |

### 2.2 4chan /biz/

**警索站点核实**：/biz/ 目前已知的第三方连续档案只有 warosu.org（自 2026-09-22 仍在收录当日帖，覆盖 2026-06 无问题）。archived.moe（4plebs）被 Cloudflare "Attention Required" 完全拦截，包括其 `/_/api/chan/search/` API 路径（同样 403，说明拦截在边缘层，不区分是否走"API"路径）。desuarchive.org 根本不收录 `/biz/`（它收录 a/aco/an/c/cgl/co/d/fit/g/his/int/k/m/mlp/mu/q/qa/r9k/tg/trash/vr/wsg，无 biz）。因此本轮只测了 warosu。

**访问方式**：GET `https://warosu.org/biz/?task=search2&search_text=...&search_datefrom=YYYY-MM-DD&search_dateto=YYYY-MM-DD&search_ord=old|new`（还有 `search_del`=仅看/排除已删帖、`search_op`=仅串主）。无需密钥、无需登录。

**能否全量取**：**不能**。空 `search_text`（含只传一个空格）在指定日期范围内直接返回"No posts found"，说明搜索引擎不支持"给定日期范围、任意内容"的全量枚举，必须提供实际关键词/短语/用户名等过滤条件之一。/biz/ 是高流量板块（数据表明主页当天帖子编号已到 6271万+，是数千万量级的历史帖子），要绕过这个限制做到"全量取 A 周"，只能靠已知串号区间暴力翻页，超出本轮预算，未做。

**关键词/地址检索结果**（全部在 A 周日期范围 `2026-06-01`~`2026-06-08` 内，`search_ord=old`）：

| 关键词 | 命中帖数 | 含 pump 合约地址 |
|---|---|---|
| `pump.fun`（无引号，可能被拆词） | 2 | 0（"Fun 3% pump"、"no volume pump...fun" 均为巧合分词，与 pump.fun 网站无关） |
| `pump.fun/coin/`（精确短语） | 0 | 0 |
| `pumpfun` | 2（同上，与"pump.fun"检索结果一致，最后一次覆盖文件） | 0 |
| `dexscreener` | 0 | 0 |
| `solscan` | 1 | 0（命中内容是某条无关交易哈希，非 pump 合约） |
| `bonding curve` | 0 | 0 |
| `CA:` | 14 | 0（人工核对：均与"California"等无关词汇相关，未见 pump 地址） |
| 5 个 H1 触发 mint 地址逐个精确检索（**不限日期**，全站历史） | 0/5 | 0/5（全站范围内这 5 个地址从未被提及） |

对照：不限日期检索精确短语 `"pump.fun"`（带引号短语匹配）在**全站历史**（非仅 A 周）能查到真实的、人写的、含合约地址的帖子，例如 2025-01-30 一条帖子里出现 `https://pump.fun/coin/ASCBDTWFWVCYv7Pq5d2zPzmk1U97UrwDGJM6gDmupump` 和另一个合约地址，证明 **warosu 的索引和数据本身没有问题、机制上能检索到合约地址**，只是 A 周这个具体窗口内、我们测试的这些检索词都没有命中。不能排除还有别的说法（如某个特定币的代称、图片里贴的地址、表情包里嵌的地址）没有被我们试到。

**编辑/删除**：4chan 协议本身**不支持编辑帖子**（发布后内容不可改）。warosu 的高级搜索表单提供 `search_del`（全部/仅已删/仅未删）过滤器，说明该站确实区分并保留了"帖子曾存在但已删除"的记录，理论上可以统计删帖率，但因为本窗口没有相关内容可看，未做统计。

**结论**：机制上"部分可用"（关键词检索+删帖识别可行，非全量枚举），但**实测在 A 周内检索不到任何 pump 合约地址提及**，产出为 0，不满足 DQ-15 §4.2 合格条件第 4 条（有新增内容）。

### 2.3 Farcaster

**官方协议层**：Snapchain（2025 年取代 Hubble 成为新的参考实现）官方文档（`snapchain.farcaster.xyz`）里所有示例 curl 命令都用 `127.0.0.1:3381`（本地自建节点），文档原话建议"如果目标是尽快上手，考虑用 Neynar 这类托管服务替代自己跑节点"。协议原生 HTTP API 是按 FID（用户 ID）查询（`castsByFid`、`castById` 等）和事件流（`/v1/events`，只能订阅实时新事件、不能按日期回放历史），**没有任何全局关键词搜索或全局时间窗查询端点**。要拿到"A 周全部 cast"，唯一免费路径是自己跑一个同步了全网历史的 Snapchain 全节点——这是重基础设施投入，超出本轮"只查可得性"的范围。

**曾经免费的社区 Hub**：`hub.farcaster.standardcrypto.vc:2281` TLS 握手阶段被重置（`SSL_ERROR_SYSCALL`，代理 CONNECT 隧道本身正常建立，说明是对端问题不是代理限制）；`nemes.farcaster.xyz:2281` 明文 HTTP 直接返回 `503 Service Unavailable`。两者均已下线，与 Snapchain 迁移后旧 Hub 停止维护的公开时间线吻合。

**Warpcast 客户端内部接口**（非官方文档化，但未登录即可访问）：`https://client.warpcast.com/v2/search-casts?q=pump.fun&limit=100`，200 OK。但这是**相关性排序搜索**，不是按时间可枚举的接口：单次请求返回的 97 条结果时间戳跨度从 2024-11-18 到 2026-09-20（跨近两年），**其中 0 条落在 A 周（2026-06-01~08）**；且 `limit=100` 时响应不带分页游标（`next` 字段为 `null`），无法继续翻页深入到更早的结果去覆盖 A 周。这说明即使勉强用它做关键词检索，也不能保证对任意历史窗口的召回率。

**结论**：**不可用**。协议层无免费全局检索能力；仅存的未登录客户端接口检索不到 A 周窗口的任何内容。

### 2.4 Bluesky

**访问方式**：官方公开 AppView `https://public.api.bsky.app/xrpc/...`。多数只读端点（`app.bsky.actor.getProfile`、`app.bsky.actor.searchActors`）都能在未登录状态下正常返回 200。**但 `app.bsky.feed.searchPosts`（帖子内容搜索，我们需要的端点）固定返回 403**，响应来自 BunnyCDN 边缘（`server: BunnyCDN-LA1-*`），不是应用层 401（区别于 `bsky.social`/xrpc PDS 端点那种明确的 `{"error":"AuthMissing"}`）。测试过：不同查询词（`pump.fun`/`bitcoin`/`solana`/空查询）、不同请求头（浏览器 UA、`Accept`、`Referer: https://bsky.app/`、`Origin: https://bsky.app`）均无法绕过，`app.bsky.unspecced.searchPostsSkeleton` 在这个 AppView 上直接 501（未实现，不是同类拦截）。这说明**专门是内容搜索这一个端点被边缘拦截**，可能是 2025 年前后 Bluesky 为遏制爬虫滥用对搜索端点加了额外限制（具体机制未证实，见 §4）。

**即使该端点可用，也不能满足"全量取时间窗"的要求**：`searchPosts` 本质是关键词相关性检索，Bluesky 没有公开的"按时间窗取全部帖子"REST 端点；唯一能拿到"全部"帖子流的方式是订阅 firehose（`com.atproto.sync.subscribeRepos`，WebSocket 实时流），且**只能拿到订阅开始之后的新事件，无法回放 2026-06 已经过去的历史**——除非当时就在录制。我们没有在 A 周实时录制过 Bluesky firehose。

**结论**：**不可用**。核心检索端点被拦截；即便解除拦截也只是关键词检索，无法满足"连续时间窗全量取"。

## 3. 检索范围清单（含失败）

### Reddit
- `https://arctic-shift.photon-reddit.com/api`（404，无此路径）
- `https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=solana&after=2026-06-01&before=2026-06-02&limit=10`（200，验证参数生效）
- `https://arctic-shift.photon-reddit.com/api/posts/search/aggregate` × 5 版块（`subreddit`+`after=2026-06-01`+`before=2026-06-08`+`aggregate=created_utc`+`frequency=day`）
- `https://arctic-shift.photon-reddit.com/api/comments/search/aggregate` × 5 版块（同上参数）
- `https://arctic-shift.photon-reddit.com/api/comments/search?subreddit=solana&after=2026-06-01T00:00:00&before=2026-06-08T00:00:00&limit=auto&sort=asc`（验证 `limit=auto` 不可靠，改用游标翻页）
- `https://arctic-shift.photon-reddit.com/api/{posts,comments}/search?subreddit=<5 个候选>&after=<游标>&before=2026-06-08T00:00:00&limit=100&sort=asc`（翻页，约 40 次）
- 文档：`https://github.com/ArthurHeitmann/arctic_shift`、`.../blob/master/api/README.md`（WebFetch）；`https://arctic-shift.photon-reddit.com/api/openapi.json`（404，不存在）
- 候选版块：r/solana、r/SolanaMemeCoins、r/memecoins、r/CryptoMoonShots、r/pumpfun（全部存在且有数据；未测 r/CryptoCurrency 等更大众版块，见"不确定之处"）

### 4chan /biz/
- `https://warosu.org/biz/`（200，可用）
- `https://archived.moe/biz/`（403，Cloudflare）
- `https://archived.moe/_/api/chan/search/?boards=biz&text=pump.fun&start=2026-06-01&end=2026-06-08`（403，Cloudflare，含 API 路径）
- `https://desuarchive.org/biz/`（404，该站不收录 biz）
- `https://warosu.org/biz/search`、`https://warosu.org/biz/search/text/pump.fun/`（404，路径猜测错误）
- `https://warosu.org/biz/?task=search2&search_text=pump.fun&search_datefrom=2026-06-01&search_dateto=2026-06-08&search_ord=old`（2 命中，均无关）
- `https://warosu.org/biz/?task=search2&search_text=pump.fun/coin/&search_datefrom=2026-06-01&search_dateto=2026-06-08`（0 命中）
- `https://warosu.org/biz/?task=search2&search_text=<pumpfun|dexscreener|solscan|bonding curve|CA:>&search_datefrom=2026-06-01&search_dateto=2026-06-08`（各 0~14 命中，均无 pump 地址）
- `https://warosu.org/biz/?task=search2&search_text= &search_datefrom=2026-06-01&search_dateto=2026-06-01`（空词，0 命中，证明不能全量枚举）
- `https://warosu.org/biz/?task=search2&search_text=<5 个 H1 触发 mint 地址>`（不限日期，全部 0 命中）
- `https://warosu.org/biz/?task=search2&search_text="pump.fun"&search_ord=new`（不限日期，命中多条，验证索引本身有效，含 2025-01 的真实合约地址样本）

### Farcaster
- `https://hub.farcaster.standardcrypto.vc:2281/v1/info`（连接失败，TLS 被重置）
- `https://nemes.farcaster.xyz:2281/v1/info`（HTTPS 连接失败）、`http://nemes.farcaster.xyz:2281/v1/info`（明文 503）
- `https://api.neynar.com/v2/farcaster/feed?...`（未继续测试，Neynar 明确需要付费 key，按规则直接记为不可用，不做进一步尝试）
- `https://snapchain.farcaster.xyz/v1/info`、`/llms.txt`、`/reference/httpapi/httpapi`（均为文档站页面，非真实 API；确认协议层无公开端点）
- `https://client.warpcast.com/v2/search-casts?q=pump.fun&limit=5`、`limit=100`、翻页 1 次（未登录可访问，但无法覆盖 A 周）

### Bluesky
- `https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=pump.fun&limit=5`（403）
- 同一端点换 UA / 浏览器头 / `q=bitcoin` / `q=solana` / 无参数（均 403）
- `https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=bsky.app`（200，验证该 AppView 本身可用）
- `https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?q=solana&limit=5`（200，验证不是全局搜索拦截）
- `https://public.api.bsky.app/xrpc/app.bsky.unspecced.searchPostsSkeleton?q=solana`（501，未实现，非拦截）
- `https://bsky.social/xrpc/app.bsky.feed.searchPosts?q=pump.fun&limit=5`（401 AuthMissing，PDS 端点本就需要会话，不是我们要用的路径）

## 4. 不确定之处

1. **Bluesky 403 的确切原因未证实**：可能是官方在搜索端点上加了鉴权/更严格的限流规则（2025 年前后有此类变更的传闻），也可能是这个 CDN pullzone 对特定路径做了地域或流量特征拦截。我们只能确认"当前用这个代理、这套请求头拿不到"，不能确认"任何未登录客户端都拿不到"（例如官方 App 内嵌 token 或不同的 AppView 域名可能仍然可用，未测）。
2. **4chan /biz/ 的 0 命中不是穷尽性证明**：我们只试了约 12 个关键词/地址组合，warosu 的分词方式（是否按非字母数字字符切词、大小写是否敏感）没有完全弄清楚；不能排除某些说法（图片里的地址、用简写代称讨论的币）真实存在但没被试到的关键词覆盖。
3. **Reddit 候选版块的选择未穷尽**：只测了卡片里列出的 5 个版块，像 r/CryptoCurrency、r/CryptoMarkets 这类更大众但可能更少提及具体 pump 合约地址的版块没有测；也没有测试跨版块全站关键词搜索（Arctic Shift 的 `posts/search` 不传 `subreddit` 时是否能全站检索未验证）。
4. **"A 周清单内 23 个"的口径**：这 23 个是"帖子提到的地址 ∩ A 周创建的 mint"，不代表这些帖子讨论的就是"A 周内发行"这件事本身——发帖时间和币的创建时间在窗口内独立满足，两者都可能滞后或提前于对方（例如老币在 A 周被重新提及）。不做因果或时序解读，仅是可得性口径下的交集计数。
5. **author_kind 的"human"判定很弱**：只基于用户名是否含 bot/auto 字样，样本里明显有模板化/规模化推广的迹象（见 #9、#13 相同标签串），这类账号是否为脚本控制无法仅凭这批数据判断，需要看账号历史发帖模式（未做，超出本轮范围）。
6. **Farcaster/Bluesky 结论建立在"不允许注册/登录/付费"的前提下**；如果放开这个约束（哪怓只是免费注册 Neynar 的 free tier、或用个人 Bluesky 账号走已登录的 `searchPosts`），两个平台的可得性结论可能改变，但这超出了 DQ-15 卡片 §2 的成本上限约定，本轮未做。

## 5. 规范化产出

`raw/normalized/reddit.csv`（47 行，列：`source,msg_id,ts_utc,url,text,author_kind,edited`）——本轮唯一有 A 周数据可规范化的平台。4chan/Farcaster/Bluesky 均为 0 命中，未生成对应 CSV。

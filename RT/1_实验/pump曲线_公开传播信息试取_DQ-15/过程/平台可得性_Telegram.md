# Telegram 公开频道可得性试取（第一步）

> 只查"能不能取到"，不做收益分析。窗口：A 周 = 2026-06-01T00:00Z ～ 2026-06-08T00:00Z。今天 2026-09-22。
> 已知不再使用：@SolanaPumpsignals、@gmgnsignals、@Pumpfun_alerts、@MemeCoinDaily、@usefillr、@crocc_sol（此前 F100 用过，均为便利样本）。本轮换用检索发现，未复用以上任何一个。

## 0. 结论摘要

检查 18 个候选（超出计划的 15 个，原因见 §3），其中 5 个在 t.me/s 上能取到 A 周连续历史。5 个里 **只有 1 个（@devcabal，"Dev's Calls"）是人工撰写且含 pump 合约地址**，其余要么是模板化机器人（@solana100xcall、@pfultimate），要么是人工写但 A 周内零 pump 合约提及（@memecoin_finder、@memecoin_daily）。

@devcabal：A 周 223 条消息，其中 6 条含完整 pump 合约地址（每天约 1 条，稳定出现在 20:01 UTC 附近），6 个不同 mint，3 个能在本地 `a_week_mints.txt`（191,192 个 A 周发行币）里核对到，另 3 个核对不到（见 §5 不确定之处）。这是唯一满足"人工＋A 周连续＋含合约地址"的来源，但样本量很小（6 次/7 天），不足以支撑量化比较，只回答"存不存在"。

## 1. 总表

| 频道 @handle | 标题 | 订阅数 | 最新消息时间 | A 周有历史 | A 周消息数 | ID 缺口率 | 含合约消息数 | 不同合约数 | 在 A 周清单内 | 人工/机器人 | 结论 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pump_calls | PUMP CALLS 🚀 | 20.9K | 2026-05-17 | 否（A 周前已停更） | – | – | – | – | – | 未判 | 排除：无 A 周历史 |
| pumpfunlistings | PUMP FUN RAYDIUM LISTINGS | – | – | 不可访问 | – | – | – | – | – | – | 排除：t.me/s 无频道内容标记（可能已改名/关闭/为机器人非频道） |
| SolanaMemeCoinss | SOLANA MEME COINS CALLS | 3.91K | 2025-11-18 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史 |
| **solana100xcall** | Solana100xCall \| Memecoin Calls 💯 | 22K | 今天 | **是** | 1174 | 4.0% | 754 | 375 | 355 | **机器人**（模板："$X REACHED N.NX AFTER VIP SIGNAL"） | 不合格：机器人 |
| memecoin_finder | Memecoin finder | 5.5K | 今天 | 是 | 8 | 0% | 0 | 0 | 0 | 人工（新闻/评论式） | 不合格：A 周零 pump 合约 |
| memecoin_daily | Memecoin daily | 811K | 今天 | 是 | 3 | 0% | 0 | 0 | 0 | 人工（加密新闻摘要） | 不合格：A 周零 pump 合约；**注意与被排除的 @MemeCoinDaily 是不同 handle**，本轮首次检查 |
| solana_mfers | SOLANA TRADE MFERS | – | – | 不可访问 | – | – | – | – | – | – | 排除：t.me/s 无频道内容标记 |
| sol_newpools | ⚡️Solana New Liquidity Pools | 555 | 2026-04-19 | 否 | – | – | – | – | – | 未判（ID 密度极高，疑似机器人） | 排除：无 A 周历史 |
| pumpfunalphacalls | Pump.Fun Alpha Calls By Web3 Wizard | – | – | 不可访问 | – | – | – | – | – | – | 排除：t.me/s 无频道内容标记 |
| **pfultimate** | Pumpfun Ultimate Alert | 11.1K | 今天 | **是** | 1525 | 0.0% | 0（文字层） | 0 | 0 | **机器人**（"pinned «🌙$X N.Nx (N.Nx from VIP)…»" 模板；正文 99.8% 为图片，t.me/s 显示 "message media not supported"） | 不合格：机器人＋正文不可读 |
| PumpEarlyAlert | Pump Early Alert | 211 | 2024-09-25 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史（停更近两年） |
| pumpfunkingofthehill | Pump.fun • King Of The Hill (KOTH) | 2.31K | 2026-02-02 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史 |
| pumpscamalerts | Pumpfun Scam Alerts | 706 | 2024-11-10 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史，且全站仅 11 条消息 |
| NewPairsSolana | New Pairs — Trojan on Solana | 2.82K | 今天 | 技术上未定位到 | – | – | – | – | – | 机器人（Trojan bot 新交易对播报，非人工） | 排除：二分查找在 id 中段反复返回空页（见 §5），且内容性质本身是机器人；未继续排查 |
| pump_sol_alert | Portal for Pump Alert Channel - GMGN | – | – | 不可访问 | – | – | – | – | – | – | 排除：t.me/s 无频道内容标记 |
| pumpfundetector | Pump.fun Detector | 2.33K | 2025-06-12 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史 |
| solana_millionaires | Solana Millionaires - Pump Signals | 506K | 2025-01-10 | 否 | – | – | – | – | – | 未判 | 排除：无 A 周历史 |
| **devcabal** | Dev's Calls | 24.2K | 今天 | **是** | 223 | 10.1% | 6 | 6 | 3 | **人工**（口语化喊单/喊单预告，非模板；简介自称 #Dev #Investor #GemHunter #DYOR） | **合格：唯一满足条件的来源** |

## 2. 有 A 周历史的频道详解

### 2.1 @devcabal — 合格

- **规模**：24.2K 订阅，全站累计约 12,807 条消息（2026-09-22 时点），持续活跃到今天。
- **A 周窗口**：id 6473–6720（span 248），实取 223 条，缺口 25 个 id（10.1%）。缺口分布不是均匀的：紧贴在 6 条合约消息之前几乎都各缺 1 个 id（如 6490、6520、6602-6603），另有一段连续缺口 6663–6672（10 个）。这与"先发后删/编辑重发"的使用习惯一致（见下），不能排除是频道自己删帖，也不能排除是 t.me/s 网页层的展示问题（§5）。
- **含合约消息**：6 条，6 个不同 mint，全部标了"已编辑"（edited）。发帖时间高度规律：每天一次，集中在 20:01–20:02 UTC 附近（06-01 20:01、06-02 20:01、06-03 20:01、06-05 20:01、06-06 20:01、06-07 20:02）。06-04 当天没有合约消息（可能当天没发或被删）。
- **与 A 周清单核对**：6 个 mint 中 3 个能在本地 `a_week_mints.txt`（191,192 个 A 周发行币）查到；另 3 个查不到，原因不明（见 §5）。
- **人工判据**：内容口语化、有输入错误/网络俚语（"fr fr"、"GOOOO"、"Who's online???"），会预告"今晚 9 点 UTC 有大项目"、描述"同一个 dev 昨天拉盘过 $SPCX"、动员"把提醒打开""不要错过"，属于喊单/自我造势文本，不是固定字段模板。频道简介自称"Based #Dev | #Investor | #GemHunter | #DYOR #NFA"，与自动播报机器人的品牌化命名（"XXX Alert""XXX Signals"）明显不同。
- **原文证据（照录，未删减 emoji）**：

  > EARLY ENTRY PLAY IS HERE!!
  > I think this sends hard fr fr
  > Ca
  > 5vAExw5RGMqsxUTUoX2UByh1vi4U4UoLL4fguaMEpump
  （msg 6489，2026-06-01T20:01:20Z，已编辑）

  > Yo who's got notifications on?
  > HUGE ALPHA FOR TODAY AT 9PM UTC
  > A serious $SOL runner is launching in about 6 hours from now and this setup is looking extremely strong.
  > Same dev who ran up yesterday's $SPCX launch, multiple KOLS onboarded and marketing wallet loaded.
  （msg 6474，2026-06-01T14:00:33Z，正文无合约，为当晚喊单预告）

  > LETS FREAKING GOOOO
  > Touched ATH of 9M market cap, making it a 160x 🚀from 10-50k entry i gave.
  > Pulled out the initial and now freeriding the moonbags.holy hell, we just printed so much freaking cash.💵
  （msg 6473，2026-06-01T08:12:21Z，复盘上一轮结果，无合约）

  > BHiVUHns5sR4JE9tYXagBLEeSZ9sEVsJ5Qmpyterpump
  （msg 6521，2026-06-02T20:01:41Z，已编辑；正文只有 CA，无说明文字）

- **原始记录**：`raw/telegram/devcabal/`（latest.html + before_*.html 共 15 个页面）；规范化后 `raw/normalized/tg_devcabal.csv`（223 行）。

### 2.2 @solana100xcall — 不合格（机器人）

- **规模**：22K 订阅，A 周窗口 id 31035–32257（span 1223），实取 1174 条，缺口率 4.0%。
- **含合约消息**：754/1174（64%），375 个不同 mint，355 个（94.7%）能在 A 周清单里查到——映射质量很好，但内容判定为机器人。
- **机器人判据**：全部消息严格复用固定模板："$TICKER REACHED 💰N.NX💰 AFTER VIP SIGNAL / 💰 N.Nx From Call! / 🏠 MCap: $X ➜ $Y (ATH) 😎 / CA: <mint> / 🧮 Position PnL / 💵 $100 → $Z (PnL +$W)"，末尾从几条固定文案里轮换（"Get VIP access""Promote your token here""Next signal fires soon"等）。0 条被标记"已编辑"，与自动生成、不做人工校对一致。
- **原文证据**：

  > $99N2 REACHED 💰6.0X💰 AFTER VIP SIGNAL
  > 💰 6.0x From Call!
  > 🏠 MCap: $24.9K ➜ $148.9K (ATH) 😎
  > CA: 99N2yocr2m9e2NxrBqAsUgxrHyDriFUknUq6tAPupump
  > 🧮 Position PnL
  > 💵 $100 → $598 (PnL +$498)
  > ⚡ Stop watching from the outside. Get VIP access now

- **原始记录**：`raw/telegram/solana100xcall/`（61 个页面）；规范化 `raw/normalized/tg_solana100xcall.csv`（1174 行）。

### 2.3 @pfultimate — 不合格（机器人，且正文层不可读）

- **规模**：11.1K 订阅，A 周窗口 id 135791–137315（span 1525），实取 1525 条，理论缺口率 0%（但这只是 id 连续性，见下）。
- **正文层几乎全空**：1525 条里 1522 条 `tgme_widget_message_text` 为空——t.me/s 对这个频道展示的是 `message_media_not_supported`（"Please open Telegram to view this post"），说明这些消息是图片/贴纸形式的告警卡片，告警数字（倍数、市值）画在图里，网页快照抓不到文字。只有 3 条可读文本，是频道自己"置顶"了历史播报的转述："Pumpfun Ultimate Alert pinned «🌙$BOUNTYWORK 24.5x(39.7x from VIP) | 💹From 28.0K ↗️ 684.3K within 1h:24m»"——同样是模板化数字播报，只是这次是纯文字。
- **机器人判据**：频道名"Ultimate Alert"、置顶文本的固定格式（倍数+VIP 标注+市值区间+耗时）与 @solana100xcall 同属一类工具生成的喊单播报，且 3 条可读样本里没有一条带独立评论或判断性文字。
- **合约地址**：文字层里没有一条含 pump 合约（图片里可能有，但抓不到，不计入统计，见 §5）。
- **原始记录**：`raw/telegram/pfultimate/`（79 个页面）；规范化 `raw/normalized/tg_pfultimate.csv`（1525 行，text 列多数为空）。

### 2.4 @memecoin_finder — 不合格（A 周零合约）

- **规模**：5.5K 订阅，全站仅约 2619 条消息（自 2025 年初起），发帖频率低（A 周仅 8 条）。
- **人工判据**：内容是对市场情绪的评论式短文（"Bought this #Gram on the #TON network, strong pump likely"、"World Cup 的时候我只关心 meme 币"），带有第一人称口吻、无固定字段结构，判定为人工撰写（或至少非模板机器人），但不能完全排除是 AI 辅助生成的营销文案。
- **合约地址**：A 周 8 条消息里出现的唯一"地址"是一个 TON 链地址（`EQBrDGesI9uyzGzVi3kjiRJt1k4Vf7iXVX7AQVQyEPvBYboQ`），不是 Solana/pump.fun 格式，也不以 `pump` 结尾。全周 0 个 pump 合约。
- **原始记录**：`raw/telegram/memecoin_finder/`（3 个页面）；规范化 `raw/normalized/tg_memecoin_finder.csv`（8 行）。

### 2.5 @memecoin_daily — 不合格（A 周零合约）

- **规模**：811K 订阅（远高于其余候选），但全站仅约 1252 条消息，发帖频率很低（A 周仅 3 条）。
- **人工判据**：内容是加密圈新闻摘要/锐评（"Claude AI 一个月被刷了 5 亿美元 token""Polymarket 一个有争议的裁决""一枚封装 25 BTC 的 Casascius 实体币被兑换"），叙事口吻明显，判定为人工（或人工编辑把关的编辑部风格），非模板机器人。
- **合约地址**：A 周 3 条消息里没有任何 Solana 地址或 pump 合约，内容与 meme 币无直接关系。
- **与排除清单的关系**：本轮候选 handle 是 `memecoin_daily`（小写+下划线），此前 F100 排除的是 `MemeCoinDaily`（无下划线、驼峰）——Telegram 用户名大小写不敏感但下划线不同即为不同频道，两者应为不同实体，本轮视为首次检查、未复用。
- **原始记录**：`raw/telegram/memecoin_daily/`（3 个页面）；规范化 `raw/normalized/tg_memecoin_daily.csv`（3 行）。

## 3. 检索范围

发现方法按 §1 的候选来源分组列出（每条查询都实际执行过）：

**WebSearch 查询**（均在 2026-09-22 执行）：
1. `Telegram channel pump.fun contract address alerts site:t.me` → pump_sol_alert、pumpfunnewlistingalerts、pfultimate、PumpEarlyAlert、pump_tech_updates、pumpscamalerts、pumpfunkingofthehill、pumpfunsupport、pumpfundetector
2. `"pump.fun" Telegram channel new token calls "CA:" list` → telemetr.io/tgstat 索引到 pump_calls、pumpfunlistings（handle 来自 tgstat 搜索结果标题）
3. `best Solana memecoin Telegram channels 2026 pump.fun gems` → 多为博客列表站（coinspot.io、tradersunion.com 等），命名式提及"MemeCoin Daily""FarmercistJournal""SuperX"等但未给出可验证 handle
4. `tgstat directory Solana memecoin channels` → SolanaMemeCoinss、solana100xcall、memecoin_finder、memecoin_daily、solana_mfers、sol_newpools（均来自 tgstat 搜索结果标题，未登录访问 tgstat 站点本身）
5. `reddit solana memecoin telegram channel recommendation pump.fun alpha` → 未找到可验证 handle 的 Reddit 讨论，命中的仍是同类博客列表站
6. `github awesome solana telegram channels list pump.fun signals` → 找到 GitHub 项目 `nikolan17/pumpfun-call-analyzer`（评分 Telegram "calls" 的工具），其 `scan_telegram.py` 配置 `CHANNELS = ["devcabal"]` → **devcabal 由此发现**
7. `"pump.fun" telegram "contract address" gem calls channel join site:reddit.com` → 无可用结果
8. `Solana meme coin sniper Telegram channel "new pair" "CA" -bot site:t.me` → NewPairsSolana
9. `pump.fun alpha caller telegram channel manual research not bot` → pumpfunalphacalls
10. `telegram channel solana memecoin research analysis "my take" OR "thoughts" pump.fun` → 无新增可用 handle
11. `tgscanx.com solana telegram channels trending list` → 未获得可用 handle（站点本身不可访问，见下）
12. `solana trader personal telegram channel journal "sending it" pump.fun public not vip` → solana_millionaires
13. `"pump.fun" telegram channel KOL personal notes degen public archive not paid signals` → 无新增可用 handle（多为同类博客软文）
14. `telegram channel solana memecoin "why I bought" OR "my thesis" OR "here's why" pump.fun` → 无新增可用 handle
15. `solana memecoin research telegram channel not bot manual curated 2026` → 无新增可用 handle（重复同类博客站）
16. `"t.me/s/" pump.fun "CA:" telegram channel screenshot reddit warning scam` → 无新增可用 handle

**WebFetch 尝试的目录站**（均为"看能否不登录访问"的测试）：
- `coinspot.io` 的"最佳 Solana meme 币 Telegram 群组"文章：可访问，但只给频道名不给 handle（DEXTOOLS PUMPS、VIP SOLANA PUMPS CHANNEL、Coins Capital 等），无法验证是否真实存在、无法定位到具体 t.me 地址，未纳入候选
- `telegramchannels.me/tag/solana`：403（Cloudflare 人机验证）
- `tgstat.com/channel/@...`：403（Cloudflare "Just a moment..." 人机验证）
- `telemetr.io/en/channels/...`：403（同上）
- `teleteg.com`：返回 200 但页面是"需要 JavaScript 和 Cookie"的跳转壳，curl 拿不到真实列表
- `tgscanx.com`：curl 连接失败（HTTP 000）
- GitHub `nikolan17/pumpfun-call-analyzer` 的 README 和 `scan_telegram.py`：可正常访问（raw.githubusercontent.com）

**结论**：所有专门做 Telegram 频道目录/统计的第三方站点（tgstat、telemetr、telegramchannels.me、teleteg、tgscanx）在不登录、不跑浏览器 JS 的条件下**全部不可访问**（Cloudflare 人机验证或需要 JS+Cookie）。本轮候选实际来自：（a）Google 搜索结果摘要里能直接解析出的 t.me 链接或 tgstat/telemetr 页面标题里带的 @handle；（b）一个 GitHub 频道评分工具的配置项（devcabal）。这是明显的选择偏差来源：搜索引擎索引到的多是营销力度大、SEO 存在感强的"品牌化"机器人频道（XXX Alert / XXX Signals / XXX Calls），真正的个人喊单频道除非被第三方工具引用，否则很难通过关键词搜索找到。

**候选入选/排除一览**（18 个，超出计划 15 个 3 个，因为前 15 个里只有 2 个进入"人工判定"阶段就被证伪为机器人或零合约，为了不让"至少找到一个合格来源"这一步落空又追加检查了 3 个，其中 devcabal 命中）：

| 顺序 | 候选 | 入选理由 | 结果 |
|---|---|---|---|
| 1 | pump_calls | WebSearch #2/#9，tgstat 标题含"CALLS" | 停更于 A 周前，排除 |
| 2 | pumpfunlistings | WebSearch #2，tgstat 标题 | t.me/s 不可访问，排除 |
| 3 | SolanaMemeCoinss | WebSearch #4，tgstat 标题"最好的 caller" | 停更于 A 周前，排除 |
| 4 | solana100xcall | WebSearch #4，tgstat 标题 | A 周有历史，机器人，排除 |
| 5 | memecoin_finder | WebSearch #4，tgstat 标题 | A 周有历史，人工但零合约，排除 |
| 6 | memecoin_daily | WebSearch #4，tgstat 标题 | A 周有历史，人工但零合约，排除 |
| 7 | solana_mfers | WebSearch #4，tgstat 标题 | t.me/s 不可访问，排除 |
| 8 | sol_newpools | WebSearch #4，tgstat 标题 | 停更于 A 周前，排除 |
| 9 | pumpfunalphacalls | WebSearch #9，标题含"manual research" | t.me/s 不可访问，排除 |
| 10 | pfultimate | WebSearch #1 | A 周有历史，机器人+正文不可读，排除 |
| 11 | PumpEarlyAlert | WebSearch #1 | 停更于 2024，排除 |
| 12 | pumpfunkingofthehill | WebSearch #1 | 停更于 A 周前，排除 |
| 13 | pumpscamalerts | WebSearch #1 | 几乎无历史（仅 11 条），排除 |
| 14 | NewPairsSolana | WebSearch #8 | 内容为机器人播报，且二分查找定位 A 周失败，排除 |
| 15 | pump_sol_alert | WebSearch #1 | t.me/s 不可访问，排除 |
| 16 | pumpfundetector | WebSearch #1 | 停更于 2025-06，排除 |
| 17 | solana_millionaires | WebSearch #12 | 停更于 2025-01，排除 |
| 18 | devcabal | WebSearch #6（GitHub 工具配置项） | **A 周有历史，人工，含合约，唯一合格** |

## 4. 不确定之处

1. **ID 缺口≠删帖的确证**：t.me/s 网页层看到的"消息 ID 不连续"，可能是频道主动删帖，也可能是发布了网页预览不支持的内容类型（投票、群组迁移通知、服务消息）后又被折叠，无法用网页快照区分这两种情况。@devcabal 的缺口集中在每条合约消息前后，与其"编辑/重发"的使用习惯吻合，但不能排除是其他原因。
2. **@pfultimate 的图片正文不可读**：99.8% 的消息在 t.me/s 上显示"message media not supported"，说明告警内容是图片/贴纸渲染的，网页快照拿不到文字。如果图片里真的嵌了合约地址，本次统计会把它算作"0 合约"，这是低估，不是真实的 0。要拿到这类内容需要 OCR 或登录客户端，超出本轮"只查可得性、不登录"的范围。
3. **NewPairsSolana 的分页异常**：这个频道 data-post 的消息 ID 编号空间达到约 1977 万，但对 id 中段（如 9,888,062、4,944,031 等）发起 `before=` 请求全部返回空页，只有非常接近当前最新 id 的请求才有内容。可能原因：该频道链接了一个讨论组，data-post 里的数字并非频道自身消息序号；也可能是该频道历史上做过大量删帖/清空。因为其内容性质本身就是机器人转发新交易对（不属于"人工撰写"），本轮没有进一步排查这个技术问题。
4. **devcabal 6 个合约里 3 个不在 `a_week_mints.txt`**：可能是发帖人打错/手抄错地址（懒人错字在喊单频道常见），可能是这些币不是在 A 周（06-01～06-07 UTC）创建而是更早创建、A 周内被重新提及，也可能是该地址对应的币从未成功创建（提前营销、最终没有真正部署）。本轮未做进一步核实（不涉及收益，只是可得性问题，留给第二步处理）。
5. **候选发现范围有偏差**：见 §3 结论段——搜索引擎能索引到的候选系统性偏向"品牌化机器人频道"，本次真正找到的人工频道（devcabal）来自一个第三方 GitHub 工具的配置项而非直接搜索，说明用关键词搜索本身对"个人喊单频道"的召回率很低。如果要扩大样本，需要换检索方式（例如从已知人工频道的转发/引用链条继续找，或找该 GitHub 工具作者是如何找到 devcabal 的），本轮未继续做。
6. **订阅数/标题解析可能不完整**：部分频道（如 solana100xcall、sol_newpools）的标题正则未命中（表中标为空），因为标题在 HTML 里被 emoji `<i>` 标签打断，不影响 A 周消息统计但表格里"标题"列有缺失，已用搜索结果里的名称补充。

## 5. 方法与产出文件

- 抓取工具：`curl`/`urllib`，UA 固定为 Chrome UA 字符串，节流 1.1 秀/请求（实际请求间隔 ≥1 秒），总请求数 **305 次**（预算 1500 次的约 20%），过程中未遇到限流（无 429）。
- 脚本已放在 `raw/telegram/` 下，可直接复跑：
  - `screen.py`：拉取频道最新页，判断能否访问、抓取最新消息 id/时间/订阅数
  - `bsearch.py`：对消息 id 做二分查找，定位 A 周起止对应的 id
  - `collect_week.py`：从 A 周末尾向前翻页直到跌出窗口，收集全部 A 周消息
  - `parse_full.py` / `normalize.py`：解析消息文本、编辑标记，规范化为 CSV
- 原始页面：`raw/telegram/<频道名>/`，文件名为 `latest.html` 或 `before_<消息ID>.html`
- 规范化输出（列：`source,msg_id,ts_utc,url,text,author_kind,edited`）：
  - `raw/normalized/tg_devcabal.csv`（223 行）
  - `raw/normalized/tg_solana100xcall.csv`（1174 行）
  - `raw/normalized/tg_pfultimate.csv`（1525 行，text 列多数为空）
  - `raw/normalized/tg_memecoin_finder.csv`（8 行）
  - `raw/normalized/tg_memecoin_daily.csv`（3 行）

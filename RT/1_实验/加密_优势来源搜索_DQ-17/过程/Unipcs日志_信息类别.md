# Unipcs 公开日志：信息类别编码

> 2026-09-24｜子任务执行，仅读免费公开网页（Telegram 预览页 `t.me/s/unipcsjournal`），不看价格、不算收益、不做链上查询｜对应 [胜者公开记录_可得性_外部补充.md](胜者公开记录_可得性_外部补充.md) 中"模型乙"对 `@theunipcs`（Unipcs Journal / Bonk Guy）的未核实说法｜原始逐帖 CSV：[raw/unipcs_posts.csv](../raw/unipcs_posts.csv)｜本页只做信息类别编码与核实，不做优势判断、不算命中率

## 方法说明

- 抓取方式：直接 `curl` 公开预览页 `https://t.me/s/unipcsjournal`，用 `?before=<msg_id>` 逐页向前翻，解析 HTML（`data-post`、`<time datetime>`、正文 `div.tgme_widget_message_text.js-message_text`、`edited` 标记、附带链接）。网页请求约 15 次（14 页翻页 + 少量结构核对），远低于 120 次上限。
- **口径提醒**：初版解析脚本曾把"引用回复"预览框（`js-message_reply_text`，属于被回复的那条旧消息）误当作本条消息正文，导致约 30 条消息内容与更早的消息重复。已修正脚本（改为只取 `js-message_text`），并对全部已抓取页面重新解析，本页与 CSV 使用的是修正后的结果。
- **覆盖范围**：抓取 2025-12-30～2026-09-23 共 252 条帖子；按任务要求只保留 2026-01-01 至今、且跳过封存期（2026-06-15～2026-07-12）的帖子，共 **209 条**写入 CSV。
- **封存期处理的一处失误（如实披露）**：在核实"fomo.family 返佣链接"这一说法时，我先对全部 252 条（未按日期过滤）做了关键词搜索，其中一次搜索意外把封存期内 msg 368（2026-07-09）的完整正文打印了出来（内容是一条 FOMO 返佣链接推广帖）。发现后已立即停止对该消息的任何使用：**msg 368 未被记入 CSV、未参与任何分类统计、本页不复述其内容**。除这一条外，封存期内其余 41 条消息未被读取正文，只在统计口径中出现过 `msg_id`/时间戳/`edited` 布尔值等元数据（用于计数，不构成"内容"）。此处如实记录，供审计追溯。
- **编码口径**：`stance` 的判定较严格——作者长期持有 USELESS 超过 3% 供给，日常绝大多数帖子是对已持仓头寸的叙事/图表强化，不构成"新的买入决定"，因此编码为 `other`；只有明确陈述"已经买入/加仓"的才记 `post`，明确陈述"等回调/等条件满足再买"的才记 `pre`。这比外部模型乙的"未来式语言即算 pre"的口径更严格（见 §1）。
- `info_categories` 未新增代码，11 个类别（含 `none`）全部沿用任务给定的表。

## §1 核实结果

| 说法（来自任务背景 / 外部模型乙） | 结果 | 依据 |
|---|---|---|
| 频道 `@unipcsjournal`（`https://t.me/s/unipcsjournal`）公开可翻页，作者 X 账号 `@theunipcs`，外号 "Bonk Guy" | **属实** | 频道预览页可用 `?before=` 稳定翻页（14 页，252 条）；频道显示名为 "Unipcs Journal (bonk guy)"；正文中反复出现 `x.com/theunipcs/status/...` 链接（如 [msg 251](https://t.me/unipcsjournal/251)、[msg 469](https://t.me/unipcsjournal/469)）；[msg 469](https://t.me/unipcsjournal/469)（2026-09-15）本人自述"i literally became known as 'Bonk Guy' due to my viral BONK trade" |
| 抽查 20 条：严格事前 9 / 事后 11 / 承认失败或放弃 3 / 带 edited 1 | **未核实，无法复现原抽样** | 外部模型乙未说明抽了哪 20 条、判据细节。本子任务改为对全部 209 条做同口径编码，结果是 `pre`=4、`post`=22、`other`=183，`failure=y`=4、`edited=y`=8（详见 §2）。差异主要来自口径更严：外部口径似乎把"等待/观望/看好"类通用行情帖也计入 pre/post，本子任务只把明确的"已下单"或"未来条件式加仓"计入，其余记为 `other` |
| 作者自认"17 笔 FOMO 交易里，在 X 或 TG 发过的不到 3 笔"，据称在 `?before=441` 附近 | **属实，但位置有出入** | 原文见 [msg 437](https://t.me/unipcsjournal/437)（2026-08-25T05:52:05Z）："i've taken 17 trades on FOMO since joining 3 months ago / 14 of them are currently in profit / that's an 82% win rate so far / i think i've posted less than 3 of these trades on X or TG"。位置在 msg 437，不在 441 附近（441 是 2026-09-02 的另一条 USELESS 帖，与此说法无关） |
| 作者使用 `fomo.family/r/unipcs` 返佣链接 | **属实** | 在覆盖范围内至少 10 条帖子出现该链接并附带"join through my ref"等措辞，例如 [msg 409](https://t.me/unipcsjournal/409)（2026-07-30）、[msg 437](https://t.me/unipcsjournal/437)（2026-08-25）、[msg 467](https://t.me/unipcsjournal/467)（2026-09-14）。另发现一条封存期内（2026-07-09, msg 368）也使用同一链接，仅记录"存在"这一事实，不引用其正文（见上文"失误披露"） |
| 作者称有"my public wallet"并宣布迁出 | **属实** | 原文见 [msg 252](https://t.me/unipcsjournal/252)（2026-03-04T12:34:32Z）："i moved all my $USELESS tokens away from my public wallet today / i'll gradually be moving every other token i have in the public wallet soon"。背景是 Arkham/Wublockchain 等公开指出其"从峰值回撤 $20m"，作者未否认该数字，但也未主动确认（表述为第三方说法，本人只回应"不太在意 Arkham 的关注"） |
| （补充，外部模型乙提到但任务未列入核对清单）另有 Nado 邀请/返佣链接 | **属实** | 原文见 [msg 235](https://t.me/unipcsjournal/235)（2026-01-05）：`https://app.nado.xyz?join=hKSmQI8`，并称"i've got you if you're interested in signing up"；[msg 236](https://t.me/unipcsjournal/236)（编辑过）后续说邀请名额用完 |

## §2 覆盖范围

- 翻到的最早帖子：[msg 224](https://t.me/unipcsjournal/224)，2026-01-01T01:18:16Z（纯视频，无文字）
- 翻到的最晚帖子：[msg 509](https://t.me/unipcsjournal/509)，2026-09-23T15:10:08Z（抓取时的频道最新帖）
- 跳过封存期（2026-06-15～2026-07-12）帖子：**42 条**（msg_id 328–378 区间内实际存在的 42 个 id，不含正文，只记元数据用于计数；封存期跨越 msg 327 → 379，中间即为跳过区间）
- 记入 CSV 总帖数：**209 条**
- `stance` 分布：`other` 183 条、`post` 22 条、`pre` 4 条
- `failure=y`：4 条（[msg 246](https://t.me/unipcsjournal/246) 后悔没在低点加仓 LIT、[msg 248](https://t.me/unipcsjournal/248) 承认此前"carried away"错判回调时点、[msg 384](https://t.me/unipcsjournal/384) Noxa 仓位因团队"关停自家 launchpad"腰斩逾九成、[msg 466](https://t.me/unipcsjournal/466) 后悔当初没把 PONS 仓位翻倍）
- `edited=y`：覆盖范围内 8 条（[236](https://t.me/unipcsjournal/236)、[305](https://t.me/unipcsjournal/305)、[381](https://t.me/unipcsjournal/381)、[414](https://t.me/unipcsjournal/414)、[436](https://t.me/unipcsjournal/436)、[446](https://t.me/unipcsjournal/446)、[484](https://t.me/unipcsjournal/484)、[490](https://t.me/unipcsjournal/490)）；另封存期内还有 3 条 edited（只计数，不引用内容）
- `promo=y`（含返佣/邀请/推广链接）：10 条（`fomo.family/r/unipcs` 8 条：[409](https://t.me/unipcsjournal/409)、[410](https://t.me/unipcsjournal/410)、[412](https://t.me/unipcsjournal/412)、[414](https://t.me/unipcsjournal/414)、[436](https://t.me/unipcsjournal/436)、[437](https://t.me/unipcsjournal/437)、[440](https://t.me/unipcsjournal/440)、[467](https://t.me/unipcsjournal/467)；`app.nado.xyz` 1 条：[235](https://t.me/unipcsjournal/235)；`app.arcus.xyz/ref` 1 条：[383](https://t.me/unipcsjournal/383)）

## §3 信息类别计数（`pre` 帖 vs `post` 帖）

`info_categories` 可多选，下表按"该类别在多少条 `pre`/`post` 帖中出现"计数（`other` 帖不计入本表，但 §附表给出全量参考）：

| 类别 | pre 中出现 | post 中出现 | pre 示例 | post 示例 |
|---|---|---|---|---|
| CHART（图表形态） | 3 | 11 | [246](https://t.me/unipcsjournal/246)、[247](https://t.me/unipcsjournal/247) | [226](https://t.me/unipcsjournal/226)、[229](https://t.me/unipcsjournal/229) |
| NARRATIVE（叙事/文化梗） | 1 | 5 | [247](https://t.me/unipcsjournal/247) | [226](https://t.me/unipcsjournal/226)、[241](https://t.me/unipcsjournal/241) |
| FUNDAMENTAL（产品/代币经济） | 1 | 4 | [246](https://t.me/unipcsjournal/246)（LIT 上市基本面） | [235](https://t.me/unipcsjournal/235)（LIT 空投）、[384](https://t.me/unipcsjournal/384)（PONS launchpad 背书） |
| VOLUME（成交量） | 1 | 2 | [247](https://t.me/unipcsjournal/247) | [260](https://t.me/unipcsjournal/260)、[266](https://t.me/unipcsjournal/266) |
| EXCHANGE_FIGURE（交易所/关联人物） | 1 | 1 | [247](https://t.me/unipcsjournal/247)（CZ "Binance Life"） | [226](https://t.me/unipcsjournal/226)（Binance 否认被黑） |
| CEX_LISTING（交易所上币） | 0 | 3 | — | [241](https://t.me/unipcsjournal/241)、[245](https://t.me/unipcsjournal/245) |
| KOL_SOCIAL（KOL/社群热度） | 0 | 1 | — | [467](https://t.me/unipcsjournal/467) |
| MACRO（大盘/BTC 行情） | 2 | 0 | [413](https://t.me/unipcsjournal/413)、[415](https://t.me/unipcsjournal/415) | — |
| FLOW_ONCHAIN（链上资金） | 0 | 0 | — | — |
| TEAM（团队行为） | 0 | 1 | — | [384](https://t.me/unipcsjournal/384)（Noxa 团队"关停自家 launchpad"） |

**全量参考**（不分 `pre`/`post`/`other`，209 条帖子中各类别出现的总条数，前五）：CHART 77、NARRATIVE 38、MACRO 18、FLOW_ONCHAIN 17、VOLUME 12（其后 CEX_LISTING 9、FUNDAMENTAL 8、KOL_SOCIAL 7、EXCHANGE_FIGURE 5、TEAM 1）。这组全量数字主要由大量 `other`（对已持仓 USELESS 头寸的持续图表/叙事喊单）贡献，不代表"买入前信息"，只用来说明频道整体的话题构成。

## §4 其他观察（只写事实，不做优势判断）

1. **"pre"极少，且窗口内没有一条完整的"先 pre 后 post"闭环**。209 条里只有 4 条严格 `pre`：[246](https://t.me/unipcsjournal/246)（LIT，"跌破入场价会再加"）、[247](https://t.me/unipcsjournal/247)（BIBI，"等回调再买"）、[413](https://t.me/unipcsjournal/413)、[415](https://t.me/unipcsjournal/415)（均为 USELESS，"等更低点加仓"）。在 2026-09-23 前的覆盖范围内，这 4 条都没有找到对应的后续"确认已加仓"的 `post` 帖——BIBI 此后再未被提及；USELESS 的 413/415（2026-08-17～19）之后频道继续大量看多 USELESS，但没有一条明确写"已按此计划加仓"。
2. **同一代币常见的模式是"post→post→…"（连续披露已完成的操作），而非"pre→post"**。例如 LIT：[235](https://t.me/unipcsjournal/235)（披露空投）→[245](https://t.me/unipcsjournal/245)（"今天开了新多"）→[246](https://t.me/unipcsjournal/246)（转为 pre，"跌破入场价再加"）；PONS/MARSCOIN 系列多条 FOMO 战报（[409](https://t.me/unipcsjournal/409)、[412](https://t.me/unipcsjournal/412)、[436](https://t.me/unipcsjournal/436)、[437](https://t.me/unipcsjournal/437)、[440](https://t.me/unipcsjournal/440)）也都是事后战报，互相之间不构成 pre-post 配对。
3. **FOMO 平台相关的战报几乎都不含具体买入理由**：[409](https://t.me/unipcsjournal/409)、[410](https://t.me/unipcsjournal/410)、[412](https://t.me/unipcsjournal/412)、[436](https://t.me/unipcsjournal/436)、[437](https://t.me/unipcsjournal/437)、[440](https://t.me/unipcsjournal/440) 六条 `info_categories` 均为 `none`——内容集中在战绩数字、跟随者数、返佣链接，不涉及为什么买。这与"17 笔仅不到 3 笔公开"的自述（[msg 437](https://t.me/unipcsjournal/437)）一致：公开渠道看到的多是结果展示，不是决策过程。
4. **少数几条明确承认失败/后悔的帖子都伴随着立刻转向下一个仓位**，没有"止损后观望"的空档：[384](https://t.me/unipcsjournal/384) Noxa 腰斩当场转投 PONS；[466](https://t.me/unipcsjournal/466) 为 PONS 仓位不够后悔的同一条里，已经在讲新买的 EMBER。
5. **`edited` 的 8 条里，内容改动幅度都不大**（补充说明、纠正误解、追加免责声明），没有发现"把已错的判断悄悄改成正确"的实例；但预览页只显示最终版本，改动前的原文本身无法核实，这点仍是"未核实"。
6. **代币代码提取口径**：CSV 的 `tokens` 列以正文中 `$TICKER` 形式为主，另人工补齐了 6 处正文未加 `$` 但明确指代代币/协议的提及（BIBI→msg 247；NOXA→msg 384、386；PONS→msg 388；NADO→msg 235、236）。这类无 `$` 前缀的提及可能还有遗漏，未做穷尽式专有名词扫描。

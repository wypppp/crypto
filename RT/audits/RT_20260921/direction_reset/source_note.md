# Telegram 官方资料核验（2026-09-21）

范围：仅核验 Telegram 官方 API/TDLib 文档；未使用账号凭据、未调用 API、未发消息。

## 结论

### 1) “消息 ID 连续，断档=删帖，可直接算删帖率”

- **部分确认**：Telegram 官方说明每个频道/超级群有独立、单调递增的消息 ID 序列；并说明在正常 `updates.getChannelDifference`/`getDifference` 同步中，消息 ID 缺口的成因“例如”是已删除消息，缺口不应填补。官方也定义了 `updateDeleteChannelMessages`。见：
  - https://core.telegram.org/api/updates （“Channel/supergroup message ID sequences”“Recovering gaps”）
  - https://core.telegram.org/constructor/messageService （服务消息本身也是带 `id` 的 `Message`；这不证明网页一定展示或过滤该类消息）
- **不能确认为严格等价**：官方同时区分正常同步缺口与非常旧的更新盒缺口；过旧状态可能需重取，频道很老的消息仍可能不可访问。`channels.getMessages` 返回的范围还可能用 `messageEmpty` 表示已删除或其他不可表示消息。因此 ID 断档只能列为待核实缺口，不能仅凭断档证明删帖，也不能据此直接得到删帖率。
- **媒体组不是一个单一消息**：官方说明一个 album/media group 由多个 `InputSingleMedia`/消息组成，消息有共同 `grouped_id`；逐 ID 计数时应按消息计数，不能把一个媒体组误当成一个 ID。见 https://core.telegram.org/constructor/message
- “预览过滤导致 ID 断档”在本次查到的官方文档中**未找到确认**；不应作为已证实解释。以上 `updates` 说明针对完整 API 消息流的 ID/更新缺口，不能自动套用于 `t.me/s` 网页解析得到的帖子 ID 缺口。已证实的其他边界是隐藏前史、过旧更新盒、已删除/不可表示占位消息。

### 2) “`t.me/s/channel?before=id` 可随机访问任意历史且完整”

- **官方 API 文档未确认这一 Web URL 的语义或完整性保证**；因此不能把它当作官方保证的随机历史访问接口。网页解析到的帖子 ID 缺口与完整 API 消息流的 ID 缺口属于不同观测层，不能直接套用 API 缺口解释。
- 官方资料反而明确存在历史可见性边界：`hidden_prehistory`/`updateChannelAvailableMessages` 表示新用户可能看不到频道/超级群旧历史；非常旧的频道消息也可能不可访问。见：
  - https://core.telegram.org/method/channels.togglePreHistoryHidden
  - https://core.telegram.org/constructor/updateChannelAvailableMessages
  - https://core.telegram.org/api/updates （“very old channel/supergroup messages may still be inaccessible”）
- 因此该说法应标为**未知/不可由官方资料确认**，不能承诺“任意历史且完整”。

### 3) “自己的 `api_id/api_hash` 账号通过全局搜索按任意 mint 找到所有公开频道历史提及，偏差最小”

- **方法范围需纠正**：`messages.searchGlobal` 是“全局搜索消息和 peers”，可设 `broadcasts_only` 只搜频道；官方没有承诺它返回所有公开频道历史，结果类型还明确有 `messagesSlice.inexact`（不精确）/分页。见 https://core.telegram.org/method/messages.searchGlobal
- **更直接的公开频道全局文本搜索**是 `channels.searchPosts(query)`：官方定义为在所有公开频道全局搜索完整文本帖子，包括未加入的公开频道；但每个用户有每日免费搜索额度，Premium 用户用完免费额度后每次搜索需 Stars，须先调用 `channels.checkSearchPostsFlood`，并可能等待 `wait_till`。见：
  - https://core.telegram.org/method/channels.searchPosts
  - https://core.telegram.org/api/search （“Posts tab”“Global hashtag search”）
  - https://core.telegram.org/method/channels.checkSearchPostsFlood
- **不确认“任意 mint/所有提及/偏差最小”**：官方只写 query 的全局公开频道帖子搜索及分页/不精确标记，没有给出召回率、历史保留、删除后可见性或“所有结果”的保证；账号登录也不消除这些服务端限制。Hashtag 搜索是另一分支（`hashtag` 与 `query` 二选一），不要把任意字符串自动等同于 hashtag。

## 对短时轮询“能否保证全量保留”

- **不能保证**。官方建议对正在查看的频道定期调用 `updates.getChannelDifference`；公开频道即使未加入，也可在持续轮询时向登录会话被动推送更新。但官方同时规定：超过更新盒大小的旧状态会被丢弃，频道更新盒大小是服务端实现细节（通常很大，约 100000），且过旧频道消息仍可能不可访问；客户端还应处理删除更新、同步缺口和不可表示消息。见 https://core.telegram.org/api/updates （“Subscribing to updates”“Recovering gaps for very old messages”）。
- 所以持续前向轮询可降低漏收窗口、可对已收到消息做留存，但不是 Telegram 官方的“短时删除全量保留”保证；轮询启动前已删除、未发出/未能同步、权限/历史边界内消息不能由此恢复。

## 未确认项

- Telegram 官方资料未给出 `t.me/s/...?...before=...` 的完整历史承诺。
- 未找到官方资料把“预览过滤”列为频道消息 ID 缺口的原因。
- 未找到官方资料保证 `messages.searchGlobal` 或 `channels.searchPosts` 对任意 token/mint 的全量召回、无删帖偏差或历史完整性。

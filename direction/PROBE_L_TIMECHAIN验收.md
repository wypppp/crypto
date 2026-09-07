**TIME_CHAIN 验收｜config v1.8.21｜2026-09-06**

config v1.8.21 `16bc2252…`、`L_10_time_chain.py` `e9f77b6d…`、产物 `L_time_chain.json` `637bbe79…`。归档于 [archive/v1.8.21/](archive/v1.8.21/)（37 个文件 + SHA256SUMS.txt）。L03 122 项、B_RESOLVE 49 项、TIME_CHAIN 12 项断言全绿，三阶段退出码均为 0。

**1. 时间链结果**

全语料 `UPDATE_ADVANCED` 命中 **9 篇**更新公告，展开为 10 个 `(baseAsset, old_time)` 键，**8 个成功链接并应用**，事件 1126 条守恒：

| 资产 | 原时间 | 最终时间 | 动作 | 源公告 | 更新公告 |
|---|---|---|---|---|---|
| FIDA | 2021-09-30 06:00 | 12:00 | postponed | 69161 | 69219 |
| ARB | 2023-03-23 17:00 | 15:00 | advanced | 153313 | 154260 |
| **SUI** | **2023-05-03 12:15** | **12:00** | **advanced** | **160049** | **160121** |
| FLOKI | 2023-05-05 16:00 | 18:00 | postponed | 160484 | 160544 |
| PEPE | 2023-05-05 16:00 | 18:00 | postponed | 160484 | 160544 |
| MOVE | 2024-12-09 13:00 | 12:00 | advanced | 219471 | 219510 |
| BABY | 2025-04-10 10:00 | 11:00 | postponed | 232630 | 232920 |
| XAUT | 2026-03-26 13:30 | 14:00 | postponed | 269505 | 269535 |

SUI 样本逐项通过：更新已应用、`old/new/action` 吻合、更新公告自身不产生事件、最终时间 12:00、**L03 阶段原始时间仍保持 12:15**、`time_versions` 完整链存在。反例（把 SUI 的 old 改为 11:15）令链接失败并触发 fail-closed 退出 1。

另 2 篇 OPERATIONAL_UPDATE 公告经原文核实**本就不是时间变更**：171585 是 FDUSD 停牌与复牌，235952 是 SXT 增加 Earn/Margin/Futures 服务。已断言它们未被误取。

**2. 两处 fallback 的原因与处理**

`UPDATE_ADVANCED.extract` 模板只容得下一个 `(sym)`，两篇走 fallback：160544 是 `FLOKI (FLOKI) and Pepe (PEPE)` **双资产**；269535 是 `originally set at 2026-03-26 13:30 (UTC)**.**,` 多出一个句点，卡住模板的 `\s*,?\s*will be`。

fallback 无 `sym` 组，我在 config 增设 `asset_scope`：在 `time for … originally set at` 之间的**有界子句**内复用已冻结的 `ASSET_PAREN` 取资产代号——复用既有规则、不新写正则、不做无界搜索。这不改变公告的语义分类，只确定一篇已判定为时间更新的公告指向哪个资产。**这是我做的判断，若你认为应改判 AMBIGUOUS 可以推翻。**

**3. TIME_CHAIN 暴露出一个更严重的问题：母表缺失 6 条首发上市**

NEXO 与 RED 的更新公告链接失败，原因不是链接逻辑，而是**这两个资产在母表里根本没有任何事件**。顺藤摸下去，OTHER 桶里有 5 篇真正的首发上市公告：

| 公告 | 资产 | 计划时间(UTC) | 原文 |
|---|---|---|---|
| 80831 | ACA | 2022-01-25 12:00 | `will list Acala (ACA) at … . Binance will open trading pairs for ACA/BTC, …` |
| 90387 | MOB, NEXO | 2022-04-29 10:00 | `will list MobileCoin (MOB) and Nexo (NEXO) at … . Trading will open for MOB/BTC, …` |
| 90740 | LDO | 2022-05-09 11:00 | `will list Lido DAO (LDO) at … . Trading will open for LDO/BTC, …` |
| 93602 | OP | 2022-06-01 04:00 | `will list Optimism (OP) at … . Trading will open for OP/BTC, …` |
| 228182 | RED | 2025-03-06 13:00 | `will end the RedStone (RED) Pre-Market at … and open spot trading for the following pairs at …` |

根因：①`A_LISTING_HEAD` 要求 `will list … and … open trading for … at TIME` 落在**同一跨度**内，而这批 2022 年公告写作 `will list X at TIME.` + **另起一句** `Trading will open for …`；②`GEN.A.require_all` 要求字面 `spot trading pair`，这些公告只写 `trading pairs`；③228182 是 Pre-Market 转现货，正文无 `will list`。

**影响：ACA、MOB、NEXO、LDO、OP、RED 六次首发上市不在母表内。** ACA/LDO/OP 母表中只有其后的新增报价对事件，MOB/NEXO/RED 完全没有事件。

范围已量化：OTHER 桶 292 篇中 `will list` + 有时间者 17 篇，其余 11 篇 Margin 加对、1 篇期权、1 篇服务新增（211457）均属正确归类，真正漏抓即上列 4 篇（+228182）。

记为 `a_gate_missed_listings: PENDING_RULE_DECISION`。**本轮未改判据**——这会改变分类语义与首发上市计数，须由你裁定。

**4. 剩余不确定项**

- 上述 6 条漏抓未修复，当前任何"首发上市次数"都偏低。
- `ANNOUNCEMENT_ONLY` 与 `PENDING_NO_ARCHIVE_EVIDENCE` 仍只有反例行为，无真实实例。
- 联合母表（`U_trade ∪ U_announcement`）未形成。
- 未对全部 `assertions` 做代理式排查；隔离机制只验证了 T0 文件读取一条路径。
- `repro_L` 仍在 v1.8.10；C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`。

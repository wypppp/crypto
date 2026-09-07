**标题首次上市声明 + ANNOUNCEMENT_ONLY 收口｜config v1.8.19→v1.8.20｜2026-09-06**

config v1.8.20 `18e7826b…`、`L_03_classify.py` `40907c38…`、`L_09_b_resolve.py` `6bb18a09…`、母表 `e798963f…`、B_RESOLVE 产物 `dd6bce58…`。归档于 [archive/v1.8.20/](archive/v1.8.20/)（33 个文件 + SHA256SUMS.txt）。L03 **122 项**、B_RESOLVE **49 项**断言全绿，退出码均为 0。

**1. 结果与预期完全一致**

裁定分布 **848 新增报价对 / 51 首发 / 3 待裁定**，B 候选 902 条守恒。对比 v1.8.18 母表：事件 1126 → 1126，**新增 0、删除 0，资产与时间完全不变**；唯一差异是 260568 KGST 的 generator 由 `B_NEW_PAIR_CANDIDATE` 变为 `B_FIRST_CANDIDATE`。待裁定余 161233 WBETH、126292 APT、81389 BDOT。

桶计数相应变化：`B_NEW_PAIR_CANDIDATE` 235 → 234，`B_FIRST_CANDIDATE` 45 → 46。

**2. 规则按裁定实现，未用无条件全文匹配**

`first_marker_title` 分两步：从**标题**截取 `will list` 之后至首个终止符（`on/in/at/with/for`、`-`、`& Enable`、`and Enable`、行尾）的子句；该资产代号必须作为**独立 token** 出现在该子句内才算命中。同篇其他资产不共享这个标记。正文命中优先，正文未命中时才查标题。

新增 `raw_events.first_marker_source ∈ {BODY, TITLE, null}`，实测 BODY 51 / TITLE 1 / null 850。**B_RESOLVE 直接读用该字段，不自行重算**——重算会重新引入"标题无条件匹配"的风险，两阶段口径因此必然一致。

正文仍须为该资产给出有效交易对与开盘时间（事件本就由 `OPERATION_CLAUSE` + `TIME` 产生），既有排除规则继续生效。

全语料实测：标题含 `will list` 的 B 类公告 46 篇，其中 45 篇正文亦命中（不受本规则影响），**仅 260568 为标题独有**；46 篇逐篇检查，标题子句均恰好覆盖该篇全部事件资产，未命中集合全为空，不存在资产搭便车。

**3. 反例（全部触发 fail-closed）**

| 反例 | 变异 | 结果 |
|---|---|---|
| TITLE_OTHER | 260568 标题改为 `Binance Will List **FOO** & Enable Trading Bots…` | KGST 回落 `B_NEW_PAIR_CANDIDATE` / `first_marker_source=None`；L03 三项断言失败，退出 1 |
| TIME1 | 218416 CETUS 时间改错 | 记录集失败，退出 1（旧式时间集合检查通过） |
| SWAP | 218416 APE↔CETUS 批次互换 | 记录集失败，退出 1（旧式检查通过，总数不变） |

初版 TITLE_OTHER 虽能让 KGST 正确回落，但 L03 退出码仍是 0——没有断言钉住它。已补 260568 的 L03 回归样本（`B_FIRST_CANDIDATE` + `first_marker_source=TITLE` + 完整记录集），现在反例能触发失败。**反例必须能触发 fail-closed 才算证明。**

**4. `ed is None` 已收口，但该分支仍未验收**

改为：无归档记录**且** `first_marker_source` 非空 ⟹ `ANNOUNCEMENT_ONLY`；无归档记录**且无**首次上市声明 ⟹ 新增 `PENDING_NO_ARCHIVE_EVIDENCE` 单列，不得并入前者。

无证据反例 `NEG_BR=NO_ARCH`（抹掉 GMX 与 BDOT 的归档证据）逐条去向：

| 记录 | first_marker | 去向 |
|---|---|---|
| 123079 GMX | BODY | `ANNOUNCEMENT_ONLY` |
| 229518 GMX | null | `PENDING_NO_ARCHIVE_EVIDENCE` |
| 81389 BDOT | null | `PENDING_NO_ARCHIVE_EVIDENCE` |

分支覆盖断言随即失败退出 1，证明分支条件按预期生效。

**但这两个分支现有数据均无实例，仍记为未验收**：全部 raw_events 的 base 都能查到最早成交日。反例只证明了条件分支的行为，没有证明真实数据下的判定正确性。联合阶段使用前须以真实的 `ANNOUNCEMENT_ONLY` 实例验收，并区分"未开盘"与"归档缺口"。

**5. 本轮结论的边界**

- 只覆盖 `NEW_QUOTE_PAIR_EXISTING_ASSET`、`FIRST_SPOT_LISTING`、`PENDING_ADJUDICATION` 三个有实例的分支。
- `ANNOUNCEMENT_ONLY` 与 `PENDING_NO_ARCHIVE_EVIDENCE` 只有反例行为，无真实实例。
- 未对全部 `assertions` 做代理式排查；隔离机制只验证了 T0 文件读取一条路径。
- `TIME_CHAIN` 未验收；联合母表未形成；`repro_L` 仍在 v1.8.10；C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`。

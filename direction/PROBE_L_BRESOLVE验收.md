**B_RESOLVE 验收 + 断言加固｜config v1.8.16→v1.8.18｜2026-09-06**

config v1.8.18 `13c50ed1…`、`L_03_classify.py` `932bb002…`、`L_09_b_resolve.py` `7ec03174…`、母表 `ff07df9a…`、B_RESOLVE 产物 `6a766696…`。全套归档于 [archive/v1.8.18/](archive/v1.8.18/)（31 个文件 + SHA256SUMS.txt）。L03 **118 项**断言全绿，B_RESOLVE **46 项**全绿，两阶段退出码均为 0。

**1. 代理断言已封堵，并用反例证明**

时间检查由 `any(...)` 改为比较 **(base_asset, T_scheduled, generator) 的完整多重集**（含重复次数），新增 `expect_records` 字段；12 篇的期望记录由已冻结的 `parse_fail_expectations` 按 `_record_expansion` 展开，generator 依据"标题为新增交易对通告、正文全部不含 `will list`"逐篇确认，不是从输出反推。

| 反例 | 变异 | 事件总数 | 时间集合 | 旧式 `expect_times` | 新记录集检查 |
|---|---|---:|---|---|---|
| TIME1 | 218416 CETUS 时间由 11-29 改为 11-28 | 13（不变） | 不变 | ✅ 通过 | ❌ 失败，退出 1 |
| SWAP | 218416 APE 与 CETUS 批次时间互换 | 13（不变） | 不变 | ✅ 通过 | ❌ 失败，退出 1 |

两个反例下总数与时间集合都完全不变——正是旧检查的盲区。复现：`NEG=TIME1 python3 L_03_neg.py --dryrun`。

**2. B_RESOLVE 实现与裁定分布**

证据源 `agg_earliest_day.json`（日粒度，覆盖 746 个 baseAsset）；比较基准为 **UTC-date(T_scheduled)**，未使用 `releaseDate`。脚本对 `t0_exact.json`/`t0_manifest.json` 设了 `open` 守卫，注入读取后立即 `ISOLATION VIOLATION` 退出 1（已实测）。

| 分支 | 记录数 | 样本 |
|---|---:|---|
| NEW_QUOTE_PAIR_EXISTING_ASSET | 848 | 66920（ELF 2017-12-21、POLY 2018-07-31） |
| FIRST_SPOT_LISTING | 50 | 123079（GMX，正文 `will list GMX (GMX)`，最早成交 2022-10-05 == 开盘日） |
| PENDING_ADJUDICATION | 4 | 81389 BDOT、126292 APT、161233 WBETH、260568 KGST |
| ANNOUNCEMENT_ONLY | 0 | 无实例：全部 raw_events 的 base 都能查到最早成交日。**不等于该分支不存在**，它在联合层才可能出现，须单独验收 |
| AMBIGUOUS | 0 | 仅用于证据冲突；按 base 取全部交易对最早成交日，单一 base 不产生互斥判据 |

B 候选守恒：母表 902 条 B 候选 → 裁定 902 条，无删除。待裁定 4 条全部留存 `earliest_trade_day` 证据。

**3. 两处此前被低估的问题**

- **`SAME_DAY_OPEN_ONLY` 实测 4 个实例，config 此前只记了 BDOT 一个。** 另三例经原文核验同样成立：126292《Adds APT/EUR & APT/TRY》、161233《Adds CVC/USDT & WBETH/ETH》、260568 KGST，正文均无 `will list`。语义缺口的范围此前被低估。
- **B_RESOLVE 样本初版我写错了 161233**，把它当成单资产。实为同一篇内 **CVC 判新增报价对（最早成交 2018-05-28）、WBETH 判待裁定**，按整篇集合断言直接失败。这与 L03 的记录集问题同源——集合式断言掩盖混合情形。样本已改为完整 `base → final_kind` 映射 + 逐 base 证据。

**4. 需要你裁定的一项：`first_marker` 作用域**

`B_SPLIT.layer1` 的 `first_marker`（`will list`）只在**正文**内搜索。260568 标题是 `Binance Will List KGST & Enable Trading Bots Services`，正文只有 `will open trading` 与 `KGST Listing`，因此被判 `B_NEW_PAIR_CANDIDATE`，进而落入待裁定。全语料 B 类公告中"标题含 `will list` 而正文不含"**仅此一篇**。

两个选项：①维持现状，该篇留待裁定；②比照 `EXCLUDE_SCOPE` 机制为 `first_marker` 增设 `scope=body_or_title`，KGST 转 `B_FIRST_CANDIDATE` 并按 earliest==scheduled 判 `FIRST_SPOT_LISTING`，待裁定由 4 降为 3。

已记为 `first_marker_scope_gap: PENDING_RULE_DECISION`。**我没有在验收中途自行改动冻结的分类语义。**

**5. 剩余不确定项**

- `TIME_CHAIN` 未验收（2 条样本，含 SUI 12:15→12:00）。
- 联合母表（`U_trade ∪ U_announcement`）未形成；`ANNOUNCEMENT_ONLY` 分支须在联合阶段单独验收。
- `UNSEEN_IN_ARCHIVE` 4 条仍无逐条的公告-归档对照。
- `repro_L` 停留在 v1.8.10；其 bootstrap 已默认加载同目录配置，缺的只是升级，升级时须重新固定包版本与哈希。
- C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`，本轮未触碰。
- 本轮只加固了审查直接指出的两处断言，**未对全部 `assertions` 做代理式排查**；"118 + 46 全绿"不覆盖尚未排查的部分。

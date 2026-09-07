**联合母表 U_master 验收｜config v1.8.24→v1.8.26｜2026-09-06**

config v1.8.26 `1bca9e8c…`、`L_11_join.py` `b78b4d7d…`、产物 `L_u_master.json` `1ec7e344…`。归档于 [archive/v1.8.26/](archive/v1.8.26/)（45 个文件 + SHA256SUMS.txt）。四阶段断言 **129 / 68 / 12 / 29** 全绿，退出码均为 0。

**0. 先补上的测试闭环**

CHAIN2 与 CONFLICT 现在各有**场景专属预期**，不再靠"撞上旧期望而退出 1"：

| 场景 | 结果 |
|---|---|
| CHAIN2 + 动态索引 | **退出 0**：串联 `12:15→12:00→11:45`，最终 11:45，AMBIGUOUS 0 |
| CHAIN2 + 静态索引 | **SCENARIO-FAIL 3 项**：序列只有一跳、最终停在 12:00、AMBIGUOUS 1 |
| CONFLICT | **退出 0**：原时间 12:15 保持，两条冲突证据均保留且各带原因，应用 0 条 |

顺带修了一处：场景模式原先 `FAIL.clear()` 会把上游 config 一致性检查一起清掉，现已保留。真实语料仍无多次串联实例，覆盖不足照旧注明。

**1. 逐条连接三阶段**

稳定来源身份 = `article_id : base_asset : **原定时间**`（不用更新后时间连接旧表）。1134 条身份唯一，TIME_CHAIN 覆盖全部 L03 记录，B_RESOLVE 记录是其子集。每条连接后同时带 `T_scheduled_original` / `T_scheduled_final` / `time_versions` / `final_kind` / 证据。

SUI 行可作示例：`T_scheduled_original=12:15`、`T_scheduled=12:00`、`schedule_changed=true`、`source_article_ids=[160049]`、`T0_day=2023-05-03`、`join_class=MATCHED`。

**2. A/C 最终裁定按证据，不以 generator 等同首次上市**

229 条 A/C 记录判 `FIRST_SPOT_LISTING`，依据是**归档最早成交日与公告开盘日逐条相等**，不是因为它们来自 A/C 生成器。另三分支 `ANNOUNCEMENT_ONLY` / `RELISTING_OR_AMBIGUOUS` / `AMBIGUOUS` 均为 0，且**未经真实数据验收**。

**3. 合并保留全部来源**

283 条上市类记录 → **269 个公告事件**，合并掉 14 条，非上市类 851 条。14 个多来源组：**11 组是 C2 双公告**（与冻结的「22 篇 → 11 事件」吻合），**3 组是跨 generator 的 A + C_LAUNCH_THEN_LIST**（CYBER、MEME、SEI）。每组的 `source_article_ids` 与 `source_srids` 全部留存。

**4. U_trade 独立构建，盘前成交不充当正式现货 T0**

746 个 baseAsset，独立于公告构建。RED、USUAL、SCR 的盘前对（`REDUSDT` 2025-02-28、`USUALUSDT` 2024-11-19、`SCRUSDT` 2024-10-11）被排除，三者的 T0 分别取 2025-03-06 / 2024-12-18 / 2024-10-22，已逐条断言等于正式现货开盘日。

**5. 联合结果**

U_master **746 行**：`MATCHED` 269、`TRADE_ONLY` 477，其中 `SCHEDULE_UPDATED_OR_CANCELLED` 10 条。`ANNOUNCEMENT_ONLY` 与 `AMBIGUOUS` 均为 0——269 个公告事件的 baseAsset 全在 U_trade 中且开盘日与 T0 日逐条相等。

**6. 逐条去向对账（1134 条全覆盖）**

| 去向 | final_kind | 条数 |
|---|---|---:|
| MERGED_INTO_U_MASTER | FIRST_SPOT_LISTING | 280 |
| MERGED_INTO_U_MASTER | PREMARKET_TO_SPOT | 3 |
| EXCLUDED | NEW_QUOTE_PAIR_EXISTING_ASSET | 848（既有资产的新增报价对，非上市事件） |
| EXCLUDED | PENDING_ADJUDICATION | 3（证据不足，保留待裁定，不并入） |

每条排除均带明确理由，总数守恒 1134。

**7. 无归档分支反例抓到一个真缺陷**

`NEG_JOIN=NO_ARCH`（抹掉 AERO 与 ARKM 的归档记录）第一次运行就暴露：v1.8.25 的 `LIST_KINDS` 未包含 `ANNOUNCEMENT_ONLY`，该类公告事件落入 `excluded` 而**直接从 U_master 消失**，违反冻结 `join_classes` 明写的"不得消失"。已修（v1.8.26）。修复后反例全部满足：两资产的 A/C 裁定与 join_class 均为 `ANNOUNCEMENT_ONLY`、公告事件保留为 U_master 行、同资产的 B 裁定来自上游冻结产物不受影响、对账守恒。真实数据该分支为 0，故合并与联合计数不变。

**8. 未决项**

- **269 与 477 都不是上市频率。** `TRADE_ONLY` 477 条包含公告窗口（2021-09-01 起）之前的历史资产、代码迁移改名、窗口外上市，归因未做。本轮不将候选数当作上市频率或收益结论。
- 首发上市计数仍是**已确认漏掉候选、现有计数不完整；总计数的净偏差尚未确定**；剩余 285 篇 OTHER 未逐篇证明正确。
- `ANNOUNCEMENT_ONLY`、`RELISTING_OR_AMBIGUOUS`、`AMBIGUOUS`、`PENDING_NO_ARCHIVE_EVIDENCE` 四个分支均无真实实例，只有反例行为。
- 多次时间串联无真实实例。
- 未对全部 `assertions` 做代理式排查；隔离机制只验证了 T0 文件读取一条路径。
- `repro_L` 仍在 v1.8.10；C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`。

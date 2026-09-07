**漏抓修复 + 多次时间更新｜config v1.8.22→v1.8.23｜2026-09-06**

config v1.8.23 `9b4c9723…`、`L_03_classify.py` `cf1dc4f0…`、`L_09_b_resolve.py` `239f4674…`、`L_10_time_chain.py` `14218937…`、母表 `5812bb23…`、B_RESOLVE `5e10a0da…`、TIME_CHAIN `e5b8f56a…`。归档于 [archive/v1.8.23/](archive/v1.8.23/)（41 个文件 + SHA256SUMS.txt）。三阶段断言 **129 / 62 / 12** 全绿，退出码均为 0。

**1. 漏抓范围比首轮报告更大：7 篇 / 8 条，不是 5 篇 / 6 条**

`PREMARKET_TO_SPOT_FORMAL` 规则实测命中 **3 篇**——除 RED 外，USUAL 与 SCR 也各有一篇正式现货转换公告落在 OTHER 里，与 `PREMARKET_TO_SPOT` 桶的 3 篇开始公告一一对应。首轮只发现 RED。

| 归因 | 公告 | 新增事件 |
|---|---|---|
| `A_LISTING_SPLIT`（分句式） | 80831、90387、90740、93602 | ACA、MOB、NEXO、LDO、OP（5 条） |
| `PREMARKET_TO_SPOT_FORMAL`（正式现货转换） | 228182、220167、214841 | RED 2025-03-06 13:00、USUAL 2024-12-18 11:00、SCR 2024-10-22 08:00（3 条） |

全量差异：**1126 → 1134，新增 8、删除 0、时间变化 0、generator 变化 0**。桶：OTHER 292→285，A 83→87，新增 `PREMARKET_TO_SPOT_FORMAL` 3。

`A_LISTING_SPLIT` 保留资产交叉校验与段落边界（交易对句须落在上市声明结束后 ≤120 字符内），仅在 `GEN.A` / `A_LISTING_HEAD` 均未命中时启用；全语料实测命中恰为那 4 篇，无附带影响。

**2. 交易阶段区别已保留**

`PREMARKET_TO_SPOT_FORMAL` 的 `T_scheduled` **只取** `open spot trading for the following pairs at` 的时间，Pre-Market 结束时间与充值时间被明确禁用。归档相位在 B_RESOLVE 中逐条保存：

| 资产 | 现货开盘日 | 盘前对 | 现货对 |
|---|---|---|---|
| RED | 2025-03-06 | REDUSDT @ 2025-02-28 | REDBTC / REDFDUSD / REDTRY / REDUSDC |
| USUAL | 2024-12-18 | USUALUSDT @ 2024-11-19 | USUALBTC / USUALFDUSD / USUALTRY |
| SCR | 2024-10-22 | SCRUSDT @ 2024-10-11 | SCRBTC / SCRFDUSD / SCRTRY |

已断言这三条**不得**被判为 `NEW_QUOTE_PAIR_EXISTING_ASSET`，final_kind 取 `PREMARKET_TO_SPOT`。裁定分布：848 / 51 / 3 待裁定 / 3 盘前转现货。

**3. NEXO 与 RED 的更新链接已验收**

源头补回后，`time_chain_linkage` 由 8/10 变为 **10/10，AMBIGUOUS 归零**：NEXO 2022-04-29 10:00 → 14:00（源 90387，更新 90517）；RED 2025-03-06 13:00 → 16:00（源 228182，更新 228414）。

**4. 多次时间更新：实现已改，但不称为已验收**

原实现只按原始时间建静态索引，且按 `old_time` 排序。已改为**按更新公告 `releaseDate` 发布顺序**应用，每次应用后把事件从 `(base, old)` 迁移到 `(base, new)`。

| 反例 | 行为 |
|---|---|
| `CHAIN2`（注入 SUI 第二次更新 12:00→11:45） | 动态索引下**成功链接**，`time_versions` = `12:15→12:00→11:45`，最终 11:45；冻结期望随即失败退出 1 |
| 同一反例 + **静态索引**（v1.8.21 行为） | 第二次更新变成 `AMBIGUOUS`，**且全部断言照样通过** —— 缺陷完全不可见 |
| `CONFLICT`（注入互斥的 12:15→10:00） | 两条互斥更新**全部不应用**，均标 AMBIGUOUS，SUI 保持 12:15，退出 1 |

重复更新（新时间一致）只应用一次；冲突更新（互斥新时间）全部不应用并保留记录。

**当前语料没有真实的多次串联实例**（10 个键全是单次更新）。这项能力只由注入反例验证，**不等于已有真实数据验收**。

**5. 结论边界（按审查意见收窄）**

关于首发上市计数，正确表述是：**已确认漏掉上述候选，现有计数不完整；总计数的净偏差尚未确定。** 本轮发现的是漏检，并未排除其他位置存在误计；`will list` + 时间的关键词筛查也不能证明剩余 285 篇 OTHER 已全部正确归类。

其余未决项：联合母表（`U_trade ∪ U_announcement`）尚未形成；`ANNOUNCEMENT_ONLY` 与 `PENDING_NO_ARCHIVE_EVIDENCE` 仍无真实实例；A/C 桶事件未经 B_RESOLVE 之外的裁定阶段；未对全部 `assertions` 做代理式排查；`repro_L` 仍在 v1.8.10；C1-BN 仍为 `MEASUREMENT_PENDING_CORRECTION`。

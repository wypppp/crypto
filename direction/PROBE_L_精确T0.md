> **2026-09-07 后续更新：**固定 37 条样本、130 个交易对已完成独立重新取证和完整比较，全部一致。详见[独立 T0 核验](PROBE_L_独立T0核验.md)。下文保留本阶段历史验收记录；其“独立数值核验未做”状态由该报告更新。

**精确 T0 测量 v3｜公告匹配测量子集 · FETCHABLE 206｜config v1.8.36｜2026-09-07**

> 本报告已被审查推翻并修正**四次**：v1（v1.8.32）声称 206/206 成功，实为交易对级失败仍标成功、且归档不可原样重跑；随后又查出缓存读取路径未验证、成交行内容未验证。四处缺陷是同一类问题的四个变体——**成功标记强于证据**。以本文为准。

config v1.8.36 `f53f7c44…`、产物 `L_t0_exact_v2.json`、证据包 `t0rows_evidence.tar.gz`。归档于 [archive/v1.8.36/](archive/v1.8.36/)（43 项，包内 config 与 5 个产物 sha 全一致；原样重跑 L_11+L_12 退出 0，41/41 哈希逐字节一致）。

**0. 第四处漏洞（v1.8.36 补）：成交行内容未验证**

v1.8.35 的准入只校验**元数据**，不验证实际用于计算 T0 的成交行；而且新下载路径当时**根本没有调用**准入函数（只有缓存路径调用）。审查在隔离副本中仅把 `GALABNB` 的 `first_at_or_after.ts_us` 改为阈值前 **1 微秒**，GALA 仍为 `VERIFIED_COMPLETE`、`lag = -0.000001s`、仍报 205/1、退出码 0 并写出产物。缺陷成立。

已一次补齐三处：

- `cache_ok` → **`record_ok`**，**缓存与新下载调用同一个函数**。
- **成交行验证**：`first_at_or_after` 键必须存在（可为 `None`）；非空时校验字段完整性、类型与时间范围——成交时间 **≥ 阈值**、**≥ 该对当日最早成交**、**UTC 日期匹配**；三个 id 非负且 `last ≥ first`；`price`/`qty` 可解析且为正；`is_buyer_maker` 合法。`day_min_ts_us` 亦须为 16 位微秒且日期匹配。
- **写出前独立断言**：对产物本身核验（不复用 `record_ok`）——每条非空 `T0_exact_us` 须满足 `T0 ≥ 阈值`、UTC 日期匹配、`T0_trade.ts_us == T0_exact_us`、`lag ≥ 0`、`T0` 不早于该对当日最早成交。

| 反例 | 注入 | 拒绝原因 |
|---|---|---|
| I | 成交时间 = 阈值 − 1μs | `TRADE_TS_BEFORE_THRESHOLD` |
| J | 成交时间早于该对当日最早 | `TRADE_TS_BEFORE_DAY_MIN` |
| K | `price` 为负 | `TRADE_NONPOSITIVE` |
| L | 成交行缺 `agg_trade_id` | `TRADE_MISSING_FIELDS` |
| M | 成交时间跨到次日 | `TRADE_DATE_MISMATCH` |
| N | `last_trade_id` 为负 | `TRADE_BAD_LAST_TRADE_ID` |
| P | `first_trade_id > last_trade_id` | `TRADE_ID_ORDER` |
| Q | `is_buyer_maker` 非法值 | `TRADE_BAD_FLAG` |
| **O** | **绕过准入层**后成交时间 = 阈值 − 1μs | **写出前独立断言（T0<阈值 / lag<0 / T0 早于当日最早），拒绝写出** |

I–N 经完整流程均为 204/2、退出码 1；P/Q 以 `record_ok` 直测确认；O 证明写出前断言与准入层相互独立。未注入时恢复 205/1、退出码 0。

**0b. 第三处漏洞（v1.8.35 补）：缓存读取路径**

v1.8.33 的门禁只查 `len(failed)==0`。审查在隔离副本中仅把 `GALABNB` **缓存**的 `checksum_verified` 改为 `false`——该记录被 `verified` 过滤器静默滤除、从未进入 `failed`，GALA 公告列 4 对而实际验证 3 对，仍标 `VERIFIED_COMPLETE` 并给出 `T0_exact_us`，总数仍 205/1、退出码 0 并写出正式产物。缺陷成立。

已改为**两层相互独立**的防护：

- **缓存准入**：缓存与新下载走同一套验证——字段完整、`symbol`/`day`/`threshold_us` 三者一致、`checksum_verified is True`、`official_checksum == local_sha256`、`n_rows` 为正整数、`day_min_ts_us` 为 16 位微秒。不通过即记 `CACHE_ADMISSION_FAILED`，**不静默丢弃也不静默重下**（需重取须显式删缓存或加 `--refresh`）。
- **结构性完整**：要求**已验证交易对的集合与公告清单集合相等**，缺项记 `NOT_IN_VERIFIED_SET`。任何"被过滤但未记入 failed"的路径——包括尚未预见的——都会被它捕获。

八个注入反例全部触发 fail-closed 退出 1：

| 反例 | 注入 | 拦截层 |
|---|---|---|
| A | 缓存 `checksum_verified=false` | CACHE_ADMISSION_FAILED |
| B | 缓存 `symbol` 改名 | CACHE_ADMISSION_FAILED |
| C | 缓存 `day` 改期 | CACHE_ADMISSION_FAILED |
| D | 缓存 `threshold_us` 偏移 1 微秒 | CACHE_ADMISSION_FAILED |
| E | 缓存 `n_rows=0` | CACHE_ADMISSION_FAILED |
| F | 缓存删除 `official_checksum` 字段 | CACHE_ADMISSION_FAILED |
| **G** | **绕过缓存准入**后 `checksum_verified=false` | **NOT_IN_VERIFIED_SET（第二层独立生效）** |
| H | `NEG_FAIL_PAIR` 下载级失败 | INJECTED_FAILURE |

八例均为 204/2，退出码 1；未注入时恢复 205/1、退出码 0。反例 G 是专门用来证明第二层不是冗余的。

**1. 修正一：交易对级完整性门禁**

v1.8.32 的实现把下载/校验/解析失败只记入 `errors` 便继续标 `OK`。审查在隔离副本中令 `GALABNB` 下载失败，程序仍报 **206/206、GALA=OK、退出码 0 并写出正式文件**。缺陷成立——其余交易对成功**不能证明**失败的交易对没有更早成交。

新增 `pair_completeness_gate`，事件状态改为三态：

| 状态 | 含义 |
|---|---|
| `VERIFIED_COMPLETE` | 公告所列**每一个**交易对均取证成功 ⟹ 给出 `T0_exact_us` |
| `INCOMPLETE_PAIR_EVIDENCE` | ≥1 个所列交易对未取证 ⟹ **`T0_exact_us` 置空**，只给 `T0_observed_us` 并附 caveat |
| `NO_TRADE_AT_OR_AFTER` | 全部取证成功但当日无 ≥阈值 成交 |

**修正后的结果：完整验收 205 条、证据不完整 1 条（NOT），不再是 206/206。**

注入反例 `NEG_FAIL_PAIR=GALABNB`：GALA 转 `INCOMPLETE_PAIR_EVIDENCE`，计数变 204/2，**退出码 1**，正式产物未被覆盖（仍为 205）。

**2. 修正二：归档可复现性**

v1.8.32 包内 config 为 `3e6588fd`，而 5 个产物的 `config_sha256` 全是 v1.8.31 的 `4ec6fb9c`——因为 config 是在测量**之后**才升版并一同归档，实际重跑被前置一致性检查阻断。

已按 `archive_reproducibility` 规定的顺序处理：先冻结判据 → 全链重跑 L_03→L_09→L_10→L_11→L_12 → 校验一致 → 归档。**未修改任何产物的哈希字段。**

实测：包内 config 与全部 5 个产物的 `config_sha256` 均为 `aca6c1b6…`；在归档目录内原样重跑 L_11 与 L_12 均退出 0，**42/42 文件哈希逐字节一致**。

**3. 三处结论收窄**

- **负 lag 为零是筛选条件保证的**，脚本只取 `t >= T_scheduled`，不能据此证明没有提前成交。独立证据改用 `pairs_trading_before_threshold`（当日最早时间戳早于阈值的交易对，不依赖筛选）：**751 个已取证交易对中仅 `RED/REDUSDT` 一对**，正是盘前成交，已被阈值正确排除。
- **`NOTBTC` 的 404 只证明当前证据未找到成交**，不足以证明"从未开盘"。已标 `ARCHIVE_EVIDENCE_MISSING`；NOT 的结果为"已观测交易对中的最早成交"（`NOTBNB @ 2024-05-16T12:00:00`），该事件**不计入完整验收**。
- **15 条异常只能表述为"在已检索公告范围内未找到时间变更"**。`agg_trade_id == 0` 是支持"该笔为该交易对首笔"的证据，**不扩大**为对 `archive_coverage_caveat` 所述历史覆盖风险的整体排除——该风险仍未闭合。

**4. 测量结果（范围：VERIFIED_COMPLETE 205 条）**

| 统计 | 值 |
|---|---|
| min / 中位 / 均值 / max | 0.000s / 0.000s / 518.0s / 28800s（8h） |
| 恰为 0.000s | 190 |
| ≤1s / ≤1h / >1h | 1 / 7 / 7 |

异常清单：CVX 8h、OP 4h、AIGENSYN 4h、ORDI 2h、DYM 2h、ZK 2h、VANA 1.5h、ZRO 1h、SCR 1h、ALLO 1h、SENT 1h、OPG 1h、JTO 0.5h、FF 0.5h、TIA <1s。抽取无误（原文确实写 CVX `06:00`、OP `04:00`），该公告所列的全部交易对都在更晚的同一时刻开盘，`tentatively` 措辞无判别力（延期组 2/15，准时组 1/191）。

**含义：公告时间不能当作可执行的开盘时刻。** 加强 `lambda_exec` 仍为 `UNIDENTIFIED` 的判定。

阶段边界：RED 用最终更新后的 **16:00**，当日 `REDUSDT` 的盘前成交被阈值正确排除，T0 取自 `REDBTC @ 16:00:00`。

留出隔离：`t0rows/` 中属留出集的交易对文件 **0 个**；55 条 EMBARGOED 只保留元数据。

**5. 结论边界**

- 本轮**不构成"精确 T0 已完整验收"**：NOT 一条证据不完整；`archive_coverage_caveat` 未整体闭合。
- 结果只代表公告匹配测量子集的 205 条完整验收事件，不代表完整研究母体；窗口内 TRADE_ONLY 98 条中 42 条仍为 `PENDING_EVIDENCE`。
- 本次发现**不证明现有 T0 数值错误**；但**「与旧版数值一致」也不能证明它们没有错误**——新旧版共用同一批缓存，一致性只说明读取路径未变。问题在于成功标记强于证据。
- 尚未做任何收益或价格代理计算。`lambda_exec` 仍为 `UNIDENTIFIED`。

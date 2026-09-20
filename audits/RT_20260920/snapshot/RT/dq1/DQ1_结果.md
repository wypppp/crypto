# DQ-1 结果 · pump curve 阶段：生命周期与数据可得性探针

> 2026-09-15。规格：[DQ1_卡.md](DQ1_卡.md)。主动工时约 1.4h（探针）+ 约 0.5h（SQL 结果解读），合计约 1.9h，未超出 ≤2h 预算。
>
> **结论（09-15 更新，取代下方原"BLOCKED"）：if_A，只限一个切片。**
> - **切片**：SOL 计价、经 PumpSwap 迁移的发行。
> - **依据**：3 条冻结 SQL 已由用户在 Dune 网页手动运行（A 更正一处列名，见下文），结果见下文"三条 SQL 结果"一节。在这个切片里，发行分母（含无成交的币）、curve 储备、迁移后的池地址、迁移后的池储备，都有 Dune 表可取。
> - **不覆盖**：2025-03-20 前迁往 Raydium 的分支；USDC 计价的币；2024 年初。这些是没补上的缺口，不是已补齐。
> - **后续处理**：按卡片另写测量卡，先测有限切片，**不自动启动**。测量需要逐币追踪数周成交，免费档网页执行（2 分钟超时、每月 2,500 credits）能否跑完，目前未知。
> - 抽样只有 6 天，只能发现缺口，不能证明其余日期完整。
>
> *原结论（保留为历史）*：BLOCKED，阻断点是取数通道；3 条 SQL 当时均未执行。

## 一、储备字段（交付 1）

| 事实 | 来源 | 支持到什么程度 |
|---|---|---|
| 官方 IDL 中，TradeEvent 自 2025-04-04 版起就有 `virtual_sol_reserves`、`virtual_token_reserves`、`real_sol_reserves`、`real_token_reserves` | [IDL 历史版本](https://github.com/pump-fun/pump-public-docs/commits/main/idl/pump.json)（执行者逐版读取） | 一手规格 |
| 2026-05-07 版 IDL：TradeEvent **追加**了 `quote_mint`、`quote_amount`、`virtual_quote_reserves`、`real_quote_reserves`，原 `*_sol_*` 字段保留；README 所说的"更名"发生在 **BondingCurve 账户**，不在事件里。2026-09-12 版再追加 `holder_rewards_bps`、`holder_rewards` | 同上；[README 2026-05-07 提交](https://github.com/pump-fun/pump-public-docs/commit/91db6800) | 一手规格。**文档日期不等于链上部署日期** |
| Dune 表 `pump_evt_tradeevent` 共 48 列：驼峰式（`solAmount`、`isBuy`、`virtualSolReserves` 等）与下划线式并存；有 `quote_mint`、`quote_amount`，**没有** `virtual_quote_reserves`、`real_quote_reserves`、`holder_rewards*` | Dune 数据集目录，2026-09-15 读取（[原始 JSON](raw/dune_datasets_pumpdotfun.json)） | 我方取数。说明 Dune 当前解码没有暴露追加的 quote 储备字段 |
| 2026-05-01 的一行原始数据：下划线式字段有值、驼峰式为空、`quote_mint` 为空。`virtual_sol_reserves = 62,267,082,749`，按 lamports 计为 62.27 SOL；代币数量按 6 位小数计 | 已有探针 `crypto/pump_tail_research/data/dune_entity_pump_trade_probe.csv` | **仅 1 行**，只说明单位，不说明覆盖 |

**仍未知**（冻结 SQL A 负责回答）：
- 两套字段在各时期的覆盖情况；
- 空值的含义；
- 有没有 USDC 计价的币；这类币的 `virtual_sol_reserves` 里装的是什么。

**推断，未验证**：SOL 计价的币，下划线式字段可能足以支持测量；USDC 计价的币，其 quote 单位的储备在 Dune 里没有解码，需要排除或另行解码。

## 二、发行分母（交付 2）

- **官方规格**：发行指令为 `create`，2025-11-07 版 IDL 起新增 `create_v2`。CreateEvent 自 2025-04 版起存在；带初始储备字段是从 2025-07-26 版开始。
- **Dune 表**：`pump_evt_createevent`、`pump_call_create`、`pump_call_create_v2` 都在，列结构已取得。
- **仍未知**（冻结 SQL B1 负责回答）：调用表是否只收录成功交易；事件与调用能否对上；零成交的币占多少。
- **本地已有数据集不能给分母**：`hf_*`（公开的 Slinky21 语料，5,701 个已迁移币）和 MELT（41,470 个已迁移币）都只包含毕业币。

## 三、迁移映射与退出状态（交付 3）

- **官方规格**：
  - 某次买入结束时 `real_token_reserves == 0`，`complete` 即置为 true；
  - `migrate` 是无许可指令，把流动性迁往 PumpSwap；
  - PumpSwap 文档称，迁移建立的是 index 0 的 canonical pool，地址由 `["pool", index, creator, baseMint, quoteMint]` 推导。这一条来自抓取工具的摘要，**尚未对照源码核实**。
- **时期分支**：PumpSwap 于 2025-03-20 上线，此前毕业币迁往 Raydium（[The Block](https://www.theblock.co/post/347360/pump-fun-launches-dex-called-pumpswap-to-instantly-migrate-graduated-tokens)，二手报道）。**2025-03-20 之前的窗口需要 Raydium 侧的映射，目前没有路径。**
- **Dune 表**：
  - `pump_evt_completeevent`；
  - `pump_call_migrate` 与 `pump_call_migrate_v2`（有 `account_pool`）；
  - `pump_amm_evt_createpoolevent`（有 `pool`、`index`、外层执行程序）；
  - `pump_evt_completepumpammmigrationevent`（有 `pool`，但旧债务记录它在 2026-05-21 之前没有数据，见 `crypto/pump_tail_research/01_token_metrics.sql`）。
- **迁移后的退出状态**：PumpSwap 的买卖事件带池子储备，旧实验在 2026-01～07 已经实际用过（F01、F02）。2026-07-15 起官方要求改用"有效储备 = vault 余额 + virtual_quote_reserves"，文档称后者目前为 0；Dune 的 BuyEvent/SellEvent 是否已解码这个字段，**尚未核对**。
- **仍未知**（冻结 SQL B2 负责回答）：各时期"完成 → 迁移调用 → 建池 → 迁移事件"这条链能对上多少，池地址是否一致，延迟多长。

## 四、结论、缺口与最低成本（交付 4）

**优先验证的候选范围**：SOL 计价、迁移路径可确认为 PumpSwap 的发行；字段覆盖、发行分母、映射完整性与退出状态可得性均尚待 SQL 验证。2025-03-20 来自新闻线索，不作为已经链上验证的精确切换边界。拟使用 Dune 解码表，入口 SQL 已写好（`sql/A_trade_fields.sql`、`sql/B1_denominator.sql`、`sql/B2_migration.sql`）。三条都只扫卡片列出的抽样日及其次日。

**阻断**（原始响应见 [raw/dune_access_20260915.json](raw/dune_access_20260915.json)）：
- `POST /api/v1/usage`：计费周期 2026-09-07 至 2026-09-15，`credits_used = 0`，`credits_included = 0`；
- 以 `small` 档执行，包括语法验证：HTTP 402，"would exceed your configured datapoint limit per billing cycle"；
- `medium`、`large` 档：HTTP 400，"Invalid performance tier"；
- **结果：执行 0 条，Dune 费用 0。**

**三个选项（涉及花钱，需要用户裁决）**：

| 选项 | 已知成本 | 能解决什么 | 主要风险 |
|---|---|---|---|
| **a. Dune：在账户里调整数据点上限，或开按量付费** | 线索：免费档每月 2,500 credits，超出按 $5/100 credits；月付套餐 $75（搜索摘要，未核，见 L10）。与账户显示的 `credits_included = 0` 不一致，需用户登录核对 | 直接运行 3 条冻结 SQL，回答交付 1–3 中尚未知的部分 | 单日分区查询的实际 credit 消耗未知 |
| b. NoLimitNodes 历史归档 | $200/月，每月压缩包 6–15 GB（厂商页面，未核，F37） | 从上线至今的全量 creates、trades、graduations | 超出每月 $100 数据预算；是否含未毕业币、许可条款均未说明 |
| c. 公共 RPC 或自建采集 | 工程量大 | 理论上都能取到 | 与"复用优先"相冲突，重复 rightTail 的老路 |

**建议**：先走 a，设一个明确的花费上限，只跑 3 条冻结 SQL。等探针确认 Dune 的缺口后，再决定要不要买 b。拿到结果之前，不写任何 curve 测量代码。

**用户后续指示（2026-09-15）**：Dune 额度问题由用户自行处理；上述选项保留为本轮历史记录，不再作为待用户回答的问题。DQ-4 按既定顺序推进，不等待 Dune 恢复。

### 根目录凭据恢复检查（2026-09-15 02:34 UTC）

用户指定 `/home/ancillary/.env` 中的 `DUNE_API_KEY`。本次明确从该文件读取并注入子进程，未使用子目录凭据，也未输出任何 key。

- `/usage` 请求成功，仍返回 `credits_included=0`、`credits_used=0`；说明该凭据可访问此接口，不证明 SQL 执行额度已恢复。
- 原 `A_trade_fields.sql` 以 `small` 运行语法验证，仍返回 HTTP 402：超出已配置的数据点上限。未取得 execution_id，未进入查询执行；未继续提交 B1、B2。
- 原始响应、验证日志与 SQL 哈希见 [恢复检查目录](raw/resume_20260915T023405Z/)。三条冻结查询的结果仍为未测。
- 共用取数脚本的凭据读取顺序已调整为：进程环境 → 仓库根目录 `.env` → 调用方子目录 `.env`，防止默认继续读取旧子目录配置。SQL、测量口径与原失败记录未改。

### SQL A 列名更正（2026-09-15，用户在 Dune 网页手动运行）

- **报错**：`line 42:14: Column 'outer_executing_account' cannot be resolved`（Execution ID `01M2HGJVERRXZ3WGJMMNZGFX32`）。
- **原因**：Dune 解码事件表的元数据列带 `evt_` 前缀。已保存的目录响应（`raw/dune_datasets_pumpdotfun.json`）列出的是去掉前缀的名字，写 A 时照抄了；B2 第 38 行本来就写的是 `evt_outer_executing_account`。
- **改动**：仅第 42 行 `outer_executing_account` → `evt_outer_executing_account`。抽样日、统计口径均未改。sha256 `fc55e7a3…` → `aabb852a…`。
- **核对范围**：已用目录列清单逐一核对 A、B1、B2 的其余列名，没有发现第二处元数据列漏前缀；`account_*` 列与所在 call 表对得上。驼峰列（`solAmount` 等）在目录里存在，且报错位置在第 42 行，说明第 4–41 行已通过解析。

### 三条 SQL 结果（2026-09-15，用户网页运行）

CSV：[A](raw/A_trade_fields.csv)（sha `75f62263…`）、[B1](raw/B1_denominator.csv)（`dde6f033…`）、[B2](raw/B2_migration.csv)（`b4651c1b…`）。消耗的 credits 未记录。

#### A · 成交事件字段（回答交付 1）

| 日期 | 成交行 | mint 数 | 有值的写法 | `real_sol_reserves` | `quote_mint` / `quote_amount` | `ix_name` | 外层程序为 pump |
|---|---:|---:|---|---|---|---|---:|
| 2024-03-01 | **0**（CSV 无此行） | — | — | — | — | — | — |
| 2024-09-01 | 1,671,449 | 9,690 | 驼峰 | 空 | 空 | 空 | 93.8% |
| 2025-03-01 | 2,992,365 | 55,209 | 驼峰 | 空 | 空 | 空 | 86.7% |
| 2025-09-01 | 1,857,148 | 31,511 | 驼峰 | 空 | 空 | 空 | 68.6% |
| 2026-03-01 | 2,454,952 | 35,913 | 下划线 | 有 | 空 | buy、sell、buy_exact_sol_in | 45.7% |
| 2026-09-01 | 3,937,370 | 55,265 | 下划线 | 有 | 有 | 另加 buy_exact_quote_in | 28.8% |

- **两套写法按日二选一**：每个抽样日只有一套有值，合并后虚拟 SOL 储备没有空行（`n_no_virtual_sol_any = 0`）。切换发生在 2025-09-01 与 2026-03-01 之间，具体日期未知。
- **`real_sol_reserves`**：2025-09-01 及之前全空，旧数据只能靠虚拟储备。
- **单位已确认**：
  - 虚拟 SOL 储备 ÷1e9 后，1% 分位约 30.0，与初始虚拟 30 SOL 一致，所以原始单位是 lamports；
  - 虚拟代币储备 ÷1e6 后，中位数 6.7 亿–7.5 亿，与初始 10.73 亿一致，所以是 6 位小数。
- **USDC 计价的币**：只在 2026-09-01 出现。
  - 占当日成交 91,213 行，约 2.3%；
  - 这些行的 `virtual_sol_reserves` 为 0，`quote_amount` 有值；
  - Dune 没有解码 quote 储备（交付 1 表），无法从成交表还原价格。
  - 其余 3,846,157 行的 `quote_mint` 是全 1 的系统默认地址。**推断**它代表 SOL 计价，尚未对照 IDL 核实。
- **异常值**：
  - 虚拟 SOL 储备最大值在前三个日期都是 115.005 SOL，与毕业位置相符；
  - 2026-03-01 为 1,429 SOL，2026-09-01 为 3,391 SOL。
  - 原因未查（可能是参数不同的曲线，未核）。测量时必须识别并单列。
- **外层程序为 pump 的占比**：从 94% 降到 29%，其余成交是经其他合约调用 pump 进来的。按事件表计数不受影响；若按调用表或外层程序过滤，会漏掉大部分成交。

#### B1 · 发行分母（回答交付 2）

| 日期 | 创建事件 mint | 创建调用 mint | 仅事件 | 仅调用 | 当日及次日无成交 |
|---|---:|---:|---:|---:|---:|
| 2024-03-01 | **0** | 22 | 0 | 22 | 20 |
| 2024-09-01 | 5,906 | 5,906 | 0 | 0 | 0 |
| 2025-03-01 | 20,188 | 20,188 | 0 | 0 | 30（0.15%） |
| 2025-09-01 | 18,334 | 18,334 | 0 | 0 | 24（0.13%） |
| 2026-03-01 | 26,003 | **365** | 25,638 | 0 | 901（3.5%） |
| 2026-09-01 | 36,202 | 36,202（create_v2 36,082） | 0 | 0 | 2,914（8.0%） |

- **2024-03-01 判为覆盖缺口**：创建事件为 0，创建调用只有 22，成交表当天也没有行（见 A）。只有 22 个 mint，远低于其余抽样日。
- **2024-09、2025-03、2025-09、2026-09**：事件与调用逐 mint 完全对上。
- **2026-03-01**：调用表只有 365 个，`create_v2` 调用为 0，事件表有 26,003 个。说明该日调用表缺覆盖。**分母以 CreateEvent 为准。**
- **无成交的币**：分母里能看到，占比从 0 增到 8%。这里只看当日及次日，不代表终身无成交。
- **初始储备**：创建事件中的初始储备字段从 2026-03-01 起才有值（虚拟 SOL 30、虚拟代币 10.73 亿、总量 10 亿）。2026-09-01 出现 USDC 计价与 Token-2022。
- **我方设计缺陷**：`first_trade_not_after_create_time` 用了"≤"，而 `block_time` 精度是秒，与创建同秒的首笔买入全被计入，这一列没有信息量，不作解读。

#### B2 · 完成 → 迁移映射（回答交付 3）

| 日期 | 完成 | 迁移调用 | canonical 建池（外层为 pump、index 0） | 迁移事件 | 无 PumpSwap 证据 | 池地址一致（建池 = 调用 / 建池 = 事件） | 完成→建池延迟 p50/p90/max（秒） |
|---|---:|---:|---:|---:|---:|---|---|
| 2024-03-01 | CSV 无此行（无完成事件） | | | | | | |
| 2024-09-01 | 71 | 0 | 0 | 0 | 71 | — | — |
| 2025-03-01 | 141 | 0 | 0 | 0 | 141 | — | — |
| 2025-09-01 | 139 | **0** | 135 | **0** | 4 | — | 0 / 1 / 1 |
| 2026-03-01 | 258 | 258 | 228 | 258 | 0 | 228 / 228 | 0 / 1 / 2 |
| 2026-09-01 | 1,209 | 1,209 | 1,194 | 1,209 | 0 | 1,194 / 1,194 | 1 / 2 / 22 |

- **PumpSwap 上线前（2024-09、2025-03）**：完成的币都没有 PumpSwap 证据，与迁往 Raydium 相符。Raydium 侧映射本轮没有测。
- **2025-09-01**：建池事件对上 135/139，但迁移调用表和迁移事件表当日都是 0，说明这两张表该日缺覆盖，映射只能靠建池事件。
- **2026-03、2026-09**：
  - 迁移调用与迁移事件 100% 对上；
  - 有建池记录的币，池地址三方一致，没有多池；
  - 建池事件分别漏了 30 和 15 个，原因未查（可能外层程序不是 pump）。映射应以迁移事件或迁移调用里的池地址为主。
- **迁移几乎是即时的**：p90 不超过 2 秒。
- **迁移后的退出状态**：Dune 目录中，PumpSwap 的 `pump_amm_evt_buyevent` / `sellevent` 有 `pool`、`pool_base_token_reserves`、`pool_quote_token_reserves`，**没有** `virtual_quote_reserves` 列。官方文档称该值目前为 0；它若变为非 0，Dune 的储备就不等于有效储备。

## 过程记录

- **一次误读**：抓取 Pump 程序文档时，返回摘要里出现的事件名，其实来自我自己的提问文本，文档本身并未列出事件定义。已按"未找到"处理，事件字段改以 IDL 为准。
- **额度影响**：5 次请求（3 次验证、2 次换档重试）都在进入执行前被拒，没有扫描数据。
- **SQL 状态**：冻结 SQL 的语法未能在 Dune 上验证。额度恢复后应先 `--validate`，再执行。

## 不能推出

- curve 阶段有或没有右尾；
- 任何覆盖率或完整性结论；
- 其他发射台的数据可得性。

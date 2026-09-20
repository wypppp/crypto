# DQ-4 结果 · Meteora DBC→DAMM v2：固定金额买入—持仓—退出能否低成本测量

> 2026-09-15。规格：[DQ4_卡.md](DQ4_卡.md)。主动工时约 1.6h；只读 RPC 13 次（上限 20，含 1 次 Node 连接失败）；费用 0；未签名、未广播。
>
> **定点复核后结论：if_C——发现可继续验证的事件重建报价路线，但固定金额跨迁移买入—持仓—退出的最小测量尚未闭合。**
>
> - **怎么做**：部分历史成交已能用事件状态和官方 SDK 复现；DAMM v2 复现还使用了较晚账户快照的 liquidity，尚未从事件流重建完整历史状态。能否省去历史账户快照仍待验证。
> - **验证**：3 组相邻成交复现，输出额、成交后价格、各项费用逐位一致。
> - **批量取数**：走 Dune 的 `meteora_solana` 解码表，和 DQ-1 一样等待 Dune 额度恢复。
> - **不要漏测撤池**：这个工程样本较晚快照的 liquidity 约为初值的 11%；约 226 秒时已处于该量级是报价匹配下的推断，尚未取得撤池交易直接核验。退出测量必须追踪流动性变化。

## 一、复用 RT-W00 迁移映射（交付 1）

RT-W00 已确认源池 `Ci3nUi7v…`、迁移交易（slot 446917936）、目标池 `AQ7q2Sab…` 以及 owner，本轮没有重做。

本轮只补了一样东西：零 RPC 解码已保存的迁移交易。Anchor 的 `emit_cpi` 把事件放在**内部指令 data** 里，不在日志中；RT-W00 的日志解码得到 0 个事件，原因就在这里。解码结果见 [raw/decoded_saved_events.json](raw/decoded_saved_events.json)。

| 事件 | 关键内容 |
|---|---|
| DAMM v2 `EvtInitializePool` | 目标池初始化事件字段（尚未证明包含完整报价/执行状态）：`sqrt_price` 412481737123559485、`liquidity` 9015283436793370279256537324536、价格上下界、按时间戳激活（激活点 1789370391）、`collect_fee_mode` 0、代币 A 21,856,200,227,469 基本单位、SOL 10,928,100,000 lamports |
| 费率参数（SDK 解码） | `FeeTimeScheduler`，分子 1,000,000 / 1e9，周期数 0，即恒定 10bps，与 DBC 配置 `migratedPoolFeeBps = 10` 一致 |
| `EvtLockPosition` | 第一个 LP 仓位锁定：`liquidity_per_period` 991681178047270730718219105698，cliff 1789456791（激活后约 24h） |

**枚举对照**：DBC 配置 `migratedCollectFeeMode = 1`，在 DBC 的枚举里是 OutputToken；迁移后 DAMM v2 事件中 `collect_fee_mode = 0`，在 DAMM v2 的枚举里是 BothToken。两套 SDK 枚举编号不同，这不是数据矛盾。

## 二、必要状态清单（交付 2）

状态标记：**已有** = 本地证据；**能取得** = 有明确来源，Dune 表或 RPC；**仍未知** = 本轮没有可靠来源。

### 报价（DBC 阶段，决策时点 t）

| 输入 | 来源 | 状态 |
|---|---|---|
| 配置：费率参数、曲线、`migrationSqrtPrice`、迁移门槛、`collectFeeMode`、激活类型 | DBC `PoolConfig` 账户 | **已有**（RT-W00 原始字节）。"配置在池生命周期内不变"**未核** |
| `sqrtPrice`、`quoteReserve` | t 之前最后一笔 `EvtSwap2` 的 `next_sqrt_price` 与 `quote_reserve_amount` | **能取得**（Dune `dynamic_bonding_curve_evt_evtswap2`，含 `tx_index` 排序） |
| `activationPoint` | 池账户，静态 | **已有** |
| `volatilityTracker` | 池账户，事件里没有 | 本样本未启用动态费（全零）；**启用动态费的配置：仍未知** |
| `currentPoint` | 决策时点的 slot 或时间戳 | **能取得** |
| 同一 slot 内多笔 swap 的先后 | Dune `tx_index`、`inner_instruction_index` | **能取得**；与真实执行顺序是否一致**未核**。本轮复现只用了单笔独占 slot 的配对 |

### 买入执行

| 项 | 状态 |
|---|---|
| 报价层面 | 同上 |
| 代币转账费（Token-2022） | 本样本扩展 18、19，无转账费：**已有**。其他代币须逐个检查 mint 扩展 |
| 构造、模拟、落块 | **UNRUN** |
| 抢单竞争 | DBC 池取到的 1,000 条签名中 221 条失败，DAMM v2 迁移后约 5–8 分钟的 1,000 条中 490 条失败。**我方能否成交：仍未知** |
| 我方买入对后续他人成交的影响 | 反事实假设，必须明写"不改变他人交易"；**不可观测** |

### 持仓延续（跨迁移）

| 项 | 状态 |
|---|---|
| 持仓代币 mint 不变，迁移只移动池流动性 | 规格推断，与 RT-W00 映射一致；"持有人无需任何操作"**未核** |
| 迁移时点：curve 完成 → DAMM v2 可交易 | 本样本 `finishCurveTimestamp` 1789370390、迁移交易 slot 446917936、DAMM v2 激活 1789370391：**已有**。批量取 `evt_evtcurvecomplete`、`call_migration_damm_v2`：**能取得** |
| 迁移间隙能否交易 | **仍未知** |

### 退出（DAMM v2，时点 t2）

| 输入 | 来源 | 状态 |
|---|---|---|
| 静态：费率、价格上下界、激活参数、`collect_fee_mode` | `EvtInitializePool` | **能取得**（Dune `cp_amm_evt_evtinitializepool`） |
| `sqrtPrice` | t2 之前最后一笔 `EvtSwap2` 的 `next_sqrt_price` | **能取得**（Dune `cp_amm_evt_evtswap2`） |
| `liquidity` | 拟由初始 liquidity 与各次 `EvtLiquidityChange.liquidity_delta` 重建 | **候选路径待验证**（目录中有 Dune `cp_amm_evt_evtliquiditychange`）；`change_type` 正负号、覆盖完整性及其他改变报价状态的事件**未核** |
| 费率随时点变化（时间调度、限速、市值调度） | 静态参数 + 时点 | 本样本恒定。其他调度模式理论上可算，**未验证** |
| 动态费的波动率状态 | 池账户，事件里没有 | 本样本未启用；**启用的池：仍未知** |
| 退出的构造、模拟、落块 | — | **UNRUN** |

**快照不混用**：
- RT-W00 的 DBC 账户快照（slot 446918342，迁移后）只用于取静态字段；
- DAMM v2 当前账户（slot 447136511）只用于取静态字段和当前 liquidity。将当前 liquidity 用于 slot 446918648 和 446926286 后，所检查的报价字段一致；这仅支持该输入与观测相容，不能唯一反证历史状态相等。当前 liquidity 仍是本轮复现的假设输入，完整历史重建尚未完成。

## 三、复现验证

原始文件见 `raw/rpc/`、`raw/reproduce_*.json`，脚本见 `node/reproduce_*.mjs`。

| 组 | 前一笔 → 后一笔 | 方向与金额 | 结果 |
|---|---|---|---|
| DBC | slot 446917755 → 446917756（两个 slot 各自只有这 1 笔成功交易） | 卖出 91,278,769,618 个 base → 45,274,264 lamports | 输出、`nextSqrtPrice`、`tradingFee`、`protocolFee` **全部一致** |
| DAMM v2 | slot 446918668 → 446926286（相隔约 40 分钟，中间无其他成功交易） | 卖出 6,855,418,593,202 个 A → 26,860 lamports | 输出、`nextSqrtPrice`、`claimingFee`、`protocolFee` **全部一致** |
| DAMM v2 | slot 446918647 → 446918648 | 买入 50,000 lamports（含 referral）→ 2,614,089,402,985 个 A | 输出、`nextSqrtPrice`、各项费用 **全部一致** |

**未覆盖**：
- DBC 买入方向（DBC 干净配对只有 1 对，恰好是卖出）；
- 同一 slot 多笔成交的排序；
- 动态费或非恒定费率的配置；
- DAMM V1 旧分支（F28）。

## 四、样本观察（只描述这一个工程样本，不代表发生率）

- **撤池**：迁移时锁定的第一个 LP 仓位现在 `vested_liquidity` = 当前池 liquidity，只占初始流动性的 10.999%；第二个仓位的账户已不存在（[raw/positions_now.json](raw/positions_now.json)）。
- **撤池时间**：迁移后约 226 秒（blockTime 1789370617）的成交可用当前 liquidity 复现，这与当时流动性已经下降到接近当前值的解释相容；撤池发生时点和数量仍待流动性变更事件或交易核验。该时点事件记录 SOL 储备为 7,407,304 lamports，迁移时注入 10,928,100,000 lamports；储备下降不能全部归因于撤池，成交也会改变储备。
- **对测量的含义**：迁移后的价格路径必须和流动性路径一起计算。只用价格序列算出的 M\*，可能对应一个已经没有可卖深度的池子。

## 五、下一笔研究投入（交付 3）

**判定：if_C，预算内尚未闭合整条最小测量；保留事件重建报价路线作为下一次定点验证候选。**
- **数据**：从 Dune `meteora_solana` 解码表取有序事件流，全部表都带 `block_slot`、`tx_index`、`inner_instruction_index`。
- **计算**：用官方 SDK 离线计算，DBC 用 1.5.12 的 `swapQuote2`，DAMM v2 用 cp-amm-sdk 1.4.8 的 `swapQuoteExactInput`。可复用官方协议数学；是否可以完全省去历史账户快照，取决于事件与配置能否独立重建全部必要状态。
- **新增代码**：执行者初估为约 100 行事件读取/SDK 适配代码，外加 SQL；这只是初估，未计明历史状态闭合与完整性检查的成本，不作为已经验证的工作量。

**不建议走逐笔 RPC**：本样本 DBC 池 curve 阶段约 4 分钟内就超过 1,000 笔交易，DAMM v2 迁移后前 8 分钟超过 2,000 笔，单个候选就要上千次调用。

**批量测量之前必须先补（按重要性排序）**：
1. Dune 额度恢复（用户处理中）；
2. 核对 Dune 表中 `swap_result` 结构体的字段名，以及时间覆盖范围；
3. 补 DBC 买入方向，并用预先固定 Q 得到的同一虚拟持仓数量贯穿迁移和退出；明确代币行为、持仓变化以及自身交易对后续状态影响的模型假设；
4. 找一个同一 slot 内有多笔 swap 的案例，按 `tx_index` 顺序复现 1 组；
5. 核对 `EvtLiquidityChange.change_type`，从初始化及其后的状态变更事件独立重建一个历史退出节点；当前账户只作独立对账，不能代填历史 liquidity。核对静态字段是否在目标窗口内确实不变；
6. 切片先限定为**恒定费率、未启用动态费、迁往 DAMM v2** 的配置，其他配置单独处理。

**前向取证是否需要：待定。** 如果事件与配置足以重建声明范围内的状态，可采用条件性历史报价模型；若承重状态无法重建，再比较有界前向取证或缩小适用范围的成本。当前不启动前向采集。

## 六、环境记录

- **Node 网络**：本机 Node 自带的 fetch 不读取代理环境变量，直连 RPC 超时；curl 正常。本轮所有 RPC 都用 curl 取原始响应，再交给 Node 离线计算。
- **SDK**：DAMM v2 SDK 版本为 cp-amm-sdk 1.4.8（IDL 0.2.4）；在 `dq4/node` 用 `npm install --ignore-scripts` 安装，耗时 64 秒。
- **RPC 明细**：1 次 Node 请求失败，2 次 DBC/DAMM v2 签名列表，1 次 DAMM v2 签名翻页，4 次配对交易，1 次 DAMM v2 池账户，1 次仓位账户，1 次找买入配对，1 次其前一笔交易。另有 2 次 Dune 目录搜索，不耗 SQL 额度。

## 不能推出

- DBC 家族有或没有右尾，或者撤池有多普遍；
- 真实下单能够成交；
- 其他配置（动态费、费率调度、DAMM V1）也能同样精确复现；
- 当前账户字段能够直接代表历史时点；本轮 DAMM v2 复现确实用了较晚快照的 liquidity。历史成交报价吻合也不等于我方跨迁移仓位的可执行收益。

## Codex 定点复核（2026-09-15）

- 核对原实现，DAMM v2 两组均从 slot 447136511 的账户读取 liquidity，仅将价格替换为上一笔成交后的值；未回放流动性变更事件。
- 独立从已保存交易解码，用固定 SDK 重算 DAMM v2 买卖两组，9 个结果字段（包含 referral/compounding fee）全部吻合。
- 将 liquidity 改为原值 +1、−1 或 +1,000,000,000，两组的 9 个字段仍全部吻合。证据及输入哈希见 [liquidity_quote_check.json](review_20260915/liquidity_quote_check.json)。该微小扰动只说明整数舍入下状态不能由报价唯一反推；不证明经济结果有重大误差，也不否定约 89% 的流动性下降量级。
- 按冻结卡，尚未闭合的是固定金额跨迁移测量，故记 if_C；已有报价复现与迁移解码证据保留。不为取得 if_A 延长本轮，后续按队列做 DQ-2b。
- 本轮未新增 RPC/Dune 请求、未签名广播、未改动冻结卡片或原复现产物。

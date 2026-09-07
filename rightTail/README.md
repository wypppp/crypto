# RT-A 身份归因可行性门 — v3.1

## 验证状态

**这一版跑过了，输出如下。**

```
通过 33 / 失败 0
SELFTEST PASS

25/25 覆盖
```

> 文件名去掉了下载带来的 ` (1)` 后缀 —— `covcheck.py` 的 `import rt_a_attribution`
> 本来就依赖这个名字，带后缀时它根本跑不起来。

自测从"断言行数 > 0"改成**场景 + 状态断言**：10 个场景，每个构造一种具体的失败形态，断言得到的是**该形态应有的状态码**，而不是"跑完了"。上一版 21/21 全 `ok` 也能算 PASS，这一版不会。

行覆盖也量了 —— 上一轮被指出"16 个关键分支只走到 3 个"，v3 做到 16/16，v3.1 把新增的
七处修复也纳进清单，现在 23/23。

```bash
python rt_a_attribution.py selftest      # 离线，不需要网络和 key，几秒
python covcheck.py                       # 行覆盖检查（可选）
```

---

## v3.1 修了什么

上一轮 v3 的评审又指出十条，两条高、四条中、四条低。除"`deploy_kind` 是启发式"
（那是方法固有的，只能写清楚）之外全部修掉，每条都有断言或覆盖率守着。

### 高

**`spec_hash` 认不出 v2 → v3。** v2 和 v3 的 `SPEC` 完全相同、`spec_version` 都还写着
`v2`，hash 都是 `16190d572b009bf9` —— 而 v3 改了归因口径。改口径的东西在代码里，
不在 SPEC 里，于是"改了 SPEC 就是另一次实验"这条硬约束覆盖不到自己。

修法：`spec_version` 提到 `v3.1`，并新增 `attribution_rule` 字段
（`"creator-from-ok-status-only-v3"`）。它不是开关，是**口径的记号**——
改了 `attribute()` 里 `token_creator` 的取值规则就要改它，否则两版数据会带着
同一个 hash 混进同一个库。现在 `16190d572b009bf9` → `54359e84b9865354`，可区分。

**v3 跑在 v2 建的库上直接崩。** `DDL` 用的是 `CREATE TABLE IF NOT EXISTS`，表已存在
时新增的列不会被建出来，于是 `upsert_attr` 会在 backfill 跑到一半时抛
`no column named deploy_kind`。而 `rt_a_out/` 是默认路径、跨版本不变。

修法：新增 `migrate()`，在 `db()` 连接时用 `PRAGMA table_info` 比对并
`ALTER TABLE ADD COLUMN` 补齐，同时在 stderr 说明旧行在新列上为 NULL。实测：

```
[migrate] attribution 补列 4 个：l4_subject, deploy_kind, creator_status, creator_prior_pairs_in_sample
1) v2 库已建，attribution 列 = 32
2) v3 db() 后列 = 36
3) v3 写入成功（改之前这里抛 no column named deploy_kind）
```

### 中

| 问题 | 修法 |
|---|---|
| `creator_status` 在"判不出哪侧是新币"时记成 `no_history`，被 `decisive_statuses` 计成"已判完"，报告【3b】虚高 | 兜底链里**先判 `ambiguous`**。场景 11 断言 |
| `forward` 的回看窗口硬编码 `500_000`，与 backfill 的 2.5M 不同，两份报告的 L2b 覆盖率不可比，且不进 `spec_hash` | 提为 `SPEC["forward_lookback_blocks"]`，**默认取 `RTA_LOOKBACK` 同值**，两者可比；显式设 `RTA_FWD_LOOKBACK` 分叉时报告头告警 |
| `audit_sample.csv` 没有 `token_creator` 列 —— 而手工判据要判的正是它 | 补上（第 6 列） |
| `earliest_observed_inbound` 没有主体列，`creator` 缺失时查的其实是建池发送者 | 新增 `l4_subject` 列（`creator` / `pair_created_tx_sender`），CSV 第 16 列 |

### 低

- `l2_source` 现在只认状态为 `ok` 的链路，不再出现"`token_creator` 为空、
  `l2_source` 却说 `rpc_binary_search`"的自相矛盾行
- `fully` 改为按**库里实际抓到多少**判（`COUNT(hist_sender) >= total_hist`），
  而不是按单次上限判 —— 断点续跑把历史补齐后它现在能收敛到"全覆盖"
- 场景 7 把 `l2b_receipt_scan_cap` 还原成**原值**而不是硬编码 40，
  不再把用户设的 `RTA_RECEIPT_CAP` 改掉

---

## v3 修了什么

### 1. 自测时序（上一版自测本身是坏的）

根因诊断正确：`forward()` 开头的 `l2b_self_test()` 会先消耗一次 `eth_blockNumber`，而 `head = next` 这种一次性推进**在结构上产生不出** `[1400, 1400, 1403]` 这样的序列。

不再去数具体消耗几次（数错正是上一版失败的原因），改成 `[1400] * 12 + [1403]` 的**计数排程**，对调用次数不敏感。现在 forward 稳定拿到 2 行。

你的判断也被确认了：**具名列 + 字典绑定这个结构性修复是有效的，forward 写库正常**，之前只是被坏掉的自测挡着。

### 2. `hist_status` 分支顺序（直接决定结论行的输入）

`elif not hist_fully_sampled` 排在 `api_failure` 之前，导致"没有 key"被写成"看不到更早"。**已把 `api_failure` 提前**。场景 3 专门断言这一点：

```
【场景 3】无 Etherscan key + 历史未全采样
  [PASS] hist_status = api_failure（不是 history_truncated）
```

### 3. 死分支（`earliest_s is not None` 恒假）

诊断正确：`prior_s == 0` 时 `MIN(block_number)` 必为 NULL。

改成用**自足通道实际抽到的最早区块**判断：`backfill` 计算 `MIN(block_number) FROM hist_sender` 并传进 `attribute()`，`hist_sampled_floor > hist_from` 才算截断。`backfill` 开跑时会打印这两个数：

```
[4/5] 归因 21 个候选…（自足通道实际抽到的最早区块 = 200，回看窗口起点 = 100）
```

### 4. `ambiguous` 的值不再当确定值用

`creator = (a_cr if l2a == "ok" else None) or (b_cr if l2b == "ok" else None)`。

被标 `ambiguous` 的地址仍保留在 `l2a_creator` / `l2b_creator` 里供人工看，但**不进 `token_creator`，也不拿去查历史**。新增 `creator_status` 列并在报告【3b】单列分布。

### 5. `l2_agree` 的口径差

新增 `deploy_kind` 列（`direct` / `factory` / `unknown`）。`l2_agree` **只在两条链路都判 `ok` 时才比较**；报告【3】按部署形态**分层**报一致率；`audit_sample.csv` 也**分层抽样**，不会被必然不一致的那类占满。

### 6. Etherscan 返回形状

新增 `as_rows()` 守卫。返回字符串（限流）时记 `api_failure`，不抛异常——这条是"所有失败记录成数据"的硬约束，之前破了。场景 4 断言三个调用点都不抛。

### 7. 其余

- `creator_prior_pairs` → **`creator_prior_pairs_in_sample`**，名字里带上"只统计样本内部"，避免在审计 CSV 里被误读成"该创建者历史建池数"
- forward 的 late→timeout 改写现在**同步** `creator_prior_activity_known`

---

## 填 `audit_sample.csv` 之前：判据先定好

这 20 行是唯一必须你亲手做的交付，判据不定就白填。

CSV 里现在有两列是 v3.1 补的，填之前先看它们：**第 6 列 `token_creator`** 是最终被下游
采用的那个地址（`l2a_creator` / `l2b_creator` 里状态为 `ok` 的那个；两个都不 `ok` 时为空），
**第 16 列 `l4_subject`** 说明同一行的 `earliest_observed_inbound` 查的是谁。

判据按 `deploy_kind` 分：

**`direct`（直接部署）** — 判 `token_creator` 归因是否正确

| 填 | 条件 |
|---|---|
| 正确 | `l2a_creator` 与 `l2b_creator` 一致，且在浏览器上打开该地址确实是这个代币的部署者 |
| 错误 | 两者不一致，或该地址明显是路由/聚合器/交易所热钱包 |
| 无法判断 | 有一侧缺失，或地址无法归类 |

**`factory`（工厂内部署）** — `l2b_creator` 已被标 `ambiguous` 且不进 `token_creator`，所以**只判 `l2a_creator`**：它指向的是真实项目方，还是工厂合约/部署器本身？后者填"错误"。

**所有行都要额外判一列** —— `earliest_observed_inbound`（L4）。
先看 `l4_subject`：它是 `creator` 就是在说创建者，是 `pair_created_tx_sender`
说明 `token_creator` 没取到、这条线索说的是**建池交易的发送者**，两者不是一回事：

| 填在备注 | 条件 |
|---|---|
| `真实资金关系` | 来源是一个普通 EOA，且不是已知交易所/桥 |
| `共用来源` | 来源是交易所热钱包、桥合约、路由 —— 这条关联**无效** |
| `无法判断` | 其余 |

L4 那一列的"共用来源"比例，是判断"资金家族"这条线值不值得继续的关键——**它高到一定程度，RT-A 里资金关联那一支就该砍掉，只留发行者历史那一支。**

---

## 装与跑

```bash
pip install requests "eth-utils" "eth-hash[pycryptodome]"
python rt_a_attribution.py selftest        # ← 先跑这个

export RTA_RPC_ETH="https://..."           # Alchemy / QuickNode / Infura 免费档
export ETHERSCAN_API_KEY="..."             # 以太坊 + 默认参数下【必填】，见下

python rt_a_attribution.py probe
export RTA_FROM_BLOCK=...  RTA_TO_BLOCK=...
python rt_a_attribution.py backfill
python rt_a_attribution.py forward --minutes 120   # 另开一个终端
python rt_a_attribution.py report
```

### ⚠ Etherscan key 在以太坊 + 默认参数下是**必填**，不是可选

早先版本把它写成"可选"。那是错的，而且是 v3 修 `hist_status` 分支顺序的直接后果——
`api_failure` 现在优先于抽样上限判定（这是对的，"没有 key"不该被写成"看不到更早"），
于是没有 key 时：

| 无 key，creator 取得到 | `creator_prior_activity_known` | 计入【2】 |
|---|---|---|
| 建池发送者无前科，历史**未**全采样 | `api_failure` | 否 |
| 建池发送者无前科，历史**已**全采样 | `api_failure` | 否 |
| 建池发送者有前科 | `ok` | **是** |

**加大 `RTA_HIST_SENDERS` 或缩小 `RTA_LOOKBACK` 都救不了**：`api_failure` 排在采样检查
之前，只要 creator 取得到而 Etherscan 不可用，`no_history` 在这条支路上就不可达。
【2】联合覆盖率的上界因此被压到"自足通道命中前科"的那个子集，这一跑问不出东西。

**链**：已核对 Etherscan 官方支持表，Base Mainnet (8453) 是 **Paid Tier Only**，Ethereum Mainnet (1) 免费档可用。先在以太坊跑通。

**这意味着 Base 上的免费档跑不出【2】**——那不是"多等一会"能解决的，得要么买套餐，
要么把 `required_fields_for_rule` 改成不含 `creator_prior_activity_known` 的变体
（那是另一版规则，`attribution_rule` 要跟着改）。

| 变量 | 默认 | |
|---|---|---|
| `RTA_CHAIN` | ethereum | ethereum / base |
| `RTA_FROM_BLOCK` / `RTA_TO_BLOCK` | 0 | 候选区间（必填） |
| `RTA_LOOKBACK` | 2500000 | 只用于建立历史的回看区块数 |
| `RTA_FWD_LOOKBACK` | 同 `RTA_LOOKBACK` | forward 的回看窗口。设成不同值会让两份报告的 L2b 不可比，报告会告警 |
| `ETHERSCAN_API_KEY` | — | **以太坊 + 默认参数下必填**（见上）。缺它则【2】上界被压到自足通道命中的子集 |
| `RTA_DEADLINE` | 300 | 决策截止（秒） |
| `RTA_MAX` | 400 | 最多归因多少候选 |
| `RTA_HIST_SENDERS` | 3000 | 补抓多少历史建池发送者 |
| `RTA_RECEIPT_CAP` | 40 | L2b 退化路径的回执扫描上限 |
| `RTA_L3_SCAN` | 20000 | L3 向后扫多少区块找首个 Mint |

跑 `backfill` 时第一屏会打印 **RPC 均次/候选**。自测里是 18.4；真链上应在 20–25 量级。**如果这个数上到几百，说明 L2b 掉进了退化路径，先停下来看 probe 里的 `eth_getBlockReceipts` 那一行。**

---

## 四条链路（字段名忠于实际含义）

| | 记录的是 | 明确不是 |
|---|---|---|
| **L1** | `pair_created_tx_sender` 外层交易发送者<br>`pair_created_tx_to` 该交易直接调用的地址 | 不是"建池的人"。可能是 EOA / bot / 中间合约；`to` 可能是 router |
| **L2a** | Etherscan `contractCreator` | 不是"实控人" |
| **L2b** | 纯 RPC 二分定位创建区块后的归因 + `deploy_kind` | 工厂部署时给的是**交易发起人**，标 `ambiguous`，不进 `token_creator` |
| **L3** | `first_mint_tx_sender` / `first_mint_event_sender` / `lp_token_recipient` | 三者**刻意不合并** |
| **L4** | `earliest_observed_inbound` | **不证明共同控制** |

---

## 报告怎么读

**唯一结论行是【2】联合覆盖率**。状态六类，不要合并：

| | |
|---|---|
| `ok` / `no_history` | **已判完**，计入可用 |
| `history_truncated` | 看不到更早（回看边界 / 分页打满 / 抽样上限 / 扫描上限）——**不是"没有"** |
| `api_failure` | 接口报错或无权限（没 key、Base 免费档、非归档节点） |
| `ambiguous` | 归因歧义（工厂部署、共用路由、判不出哪侧是新币） |
| `timeout` | 超过决策截止才返回 |

**能否定**：在冻结的母体、数据源、回看范围与决策截止内，**这一版归因规则**覆盖不足或来不及返回。
**不能否定**：信息不存在；RT-A 有没有 edge；换数据源后是否可行。低覆盖率也可能只意味着这条规则**只适用于一个子集**。

---

## 自足通道的作用范围（结构性事实，不是 bug）

把 `creator_prior_activity_known` 的分支按可达性穷举后：

| 分支 | 产出 | creator 已知? |
|---|---|---|
| A 外部通道确定答案 | `ok` / `no_history` | 仅已知 |
| B 外部通道截断 | `history_truncated` | 仅已知 |
| C 自足通道命中前科 | `ok` | 仅已知（v3.1 起加了 `and creator`） |
| D 外部通道不可用 | `api_failure` | 仅已知 |
| E 自足通道抽样底线 / F 未全采样 | `history_truncated` | **仅未知** |
| G 兜底 | `creator_status` | **仅未知** |

**E / F 只在 creator 未知时可达，而【2】要求 `token_creator` 非空——所以
`hist_sampled_floor` 与 `hist_fully_sampled` 从不影响结论行**，只影响【2b】分布。
自足通道对【2】的唯一贡献是 C（外部通道不可用、但发送者已被确认有前科）。

v3.1 修掉了这里的两处假阳性：C 和 G 原先在 creator 未知时也会给出 `ok` / `no_history`
（已判完），等于替一个不知道是谁的地址宣称"有/没有前科"。现在 C 要求 `creator` 非空，
G 改为回落到 `creator_status`。场景 13 断言这三点，并同时断言 creator 已知时
v3 的自足通道兜底口径不变。

**残留一支**：两条 L2 链路都判 `no_history`（一致认定该地址没有创建记录）时，
`creator_status` 是 `no_history`，G 会把它传给 `hist_status`，仍计为已判完。
那是两条链路一致的确定发现、不是凭空宣称，且 `token_creator` 为空所以进不了【2】。
留着不特判。

---

## 还没处理的

- 第二遍重算的 `creator_prior_pairs_in_sample` 仍只统计 attribution 表（≤400 个候选）内部，不含历史区间。已改名标明，但**如果这个字段要真用于判断，需要对历史区间也做 L2 归因**——那是一笔大得多的调用量，等 backfill 出了数再决定值不值。

- **`deploy_kind` 是启发式，不是事实。** 它的判据是"创建区块内该代币首条日志所属交易的
  `to` 是否为空"。若代币构造函数不发日志、而同区块内更晚的交易碰了它，`logs[0]` 就来自
  那笔交易，直接部署会被误判成 `factory`。方向是保守的（误判会落进 `ambiguous`、不进
  `token_creator`），但**上面的手工判据是按 `deploy_kind` 分派的**，误判会把行送进错误的
  判据。填 CSV 时若某行的 `deploy_kind=factory` 但 `l2a_creator` 看起来就是个普通 EOA，
  在备注里记一句，这类的数量本身就是要看的东西。

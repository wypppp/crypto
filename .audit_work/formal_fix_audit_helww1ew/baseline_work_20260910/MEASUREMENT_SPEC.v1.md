# 测量口径冻结规格 v1（待冻结）

> 上位文件：`baseline_20260909/baseline-execution-config.md` v2.1 §4/§5/§6。
> 本文件**不修改 v3 包**，只把 §5/§6 已有的原则落成**可执行判定规则**，
> 补上「原则写了但代码里没有对应判据」的那一步。
> 依据是 `verify_capabilities.py`（sha256 `bc9ea52e…`）中 `Probe.buy/sell`、
> `Verifier.override/buy/sell/find_balance_slot`、`classify_probe`、`run_controls` 的实际行为。
> 冻结前需你确认第 5 节的三个待定项。

---

## 1. 钱包执行上下文

| 项 | 冻结值 | 依据 |
|---|---|---|
| 买卖发起者 | 虚拟地址 `WALLET`，**注入 `Probe` 合约代码** | `probe_overrides()` |
| 注入前置校验 | 每个历史块上 `eth_getCode(WALLET) == "0x"`，并记录原生余额 | `Verifier.override()` |
| 注入后置校验 | 同块再读 code 与 balance，须与注入前一致（不持久化） | 同上 |
| 覆盖生效验证 | 两个历史块 × 两组 (balance, stateDiff) 数值，读回须逐项相等 | 同上 |
| 资金 | `WALLET` / `CALLER` 各 `10^20` wei | `probe_overrides()` |

**已知非等价（必须随每个样本记录，不得省略）**：

`msg.sender` 对 router 与代币而言是**合约地址**，不是 EOA。代币若含
`tx.origin == msg.sender`、`isContract`、代理/多签黑名单一类判定，其行为与真实 EOA 买家不同。
代码自身标注为 `"wallet_kind": "injected contract; not EOA equivalence"`。

**规则 W1**：任何因合约身份触发的拒绝，**分类为 `model_unsupported`，不得记为市场结论**
（不得称该代币不可买/不可卖）。判定证据：见规则 H3 的对照实验。

---

## 2. 跨期持仓状态适配

现行机制（`find_balance_slot` + `stateDiff` 注入）：

1. 在退出块对 `balanceOf(WALLET)` 用两个哨兵值做**有界槽位扫描**（上限 `--slot-limit`）
2. 要求**恰好一个槽**命中两次
3. 扫描后读回原值，确认未污染持久状态
4. 命中槽注入买入所得币数，再执行 `approve(0)`、`approve(amount)`、卖出

**槽位命中只证明 `balanceOf` 读这个槽，不证明 `transferFrom` 用同一套账。**
配置 §5 已写明这一点；下面是把它变成可执行判定。

### 充分性判据（由现有机制推出，不需新增合约）

`Probe.sell` 的行为提供了天然判别：

```
b0 = balanceOf(this);  if (b0 < amount) return stage 10;
→ approve(0) / approve(amount) → router.swap...SupportingFeeOnTransferTokens
→ ok ? stage 0 : stage 20
```

| 观察 | 判定 | 理由 |
|---|---|---|
| **H1** `stage==0` 且 `token_before==amount` 且 `token_after==0` | **状态适配充分（本路径已证）** | 成功执行本身证明 `transferFrom` 与 `balanceOf` 走同一套账 |
| **H2** `stage==10` | **`model_unsupported`** | 注入后 `balanceOf` 仍不足：账本不是那个槽（份额/重基/派生余额）。**不是不可卖** |
| **H3** `stage==20`（通用 revert） | **`execution_reverted_unknown`** | 无法区分「真实限制」与「注入的持有者没有买入历史，冷却/反抛售状态为零值」 |
| **H4** 扫描 0 或 >1 命中 | **`model_unsupported`**（`Unrun`） | 代码已明确「不是可卖性结论」 |

**规则 H3 的收窄诊断（每样本 2 次额外 `eth_call`，只缩小不判定）**：

| 诊断 | 做法 | 读法 |
|---|---|---|
| `size_probe` | 同块再卖 **1 个最小单位** | 小额成功、全额 revert → 存在与规模相关的可复现限制 |
| `identity_probe` | 同块把注入与卖出改到 `CALLER` | 同样 revert → 与本钱包的（缺失的）历史无关，指向代币侧规则 |

两项诊断**都不改变 §5 的状态**，只作为 revert 证据的附加字段落盘。

**规则 H5**：`model_unsupported` 与 `execution_reverted_unknown` 的样本
**保留在分母内**，不删样本、不记 M=0、不记 M 未知后又从分母剔除。
按配置 §7 的识别区间处理。

---

## 3. 失败与未知分类

### 探针 stage → 状态映射（唯一权威映射）

| stage | `classify_probe` | §5 状态 | Z/M |
|---|---|---|---|
| 0 | `simulated_success` | `measured_exit`（卖出）／入场成功（买入） | 记实际增量 |
| 10 | `environment_missing_balance` | **`model_unsupported`** | 均未知 |
| 11 | `environment_missing_allowance` | **`model_unsupported`** | 均未知 |
| 12 | `approval_failed_unknown` | `execution_reverted_unknown` | 均未知 |
| 20 | `execution_reverted_unknown` | `execution_reverted_unknown` | 均未知 |
| 其它 | `unknown_probe_stage` | `decode_error` | 均未知 |

> stage 10/11 在**真实代币**上出现，说明的是**我们的环境构造不足**（余额或授权没落到实处），
> 不是代币的市场属性——因此映射到 `model_unsupported` 而不是 `entry_failed_verified`。
> 受控 fixture 中 stage 10/11 是**故意构造**的，两者不可混用。

### 编排层状态

| 情形 | 状态 |
|---|---|
| 窗口截止前无 Mint | `no_mint_by_cutoff` |
| 买入 `stage==20` | `entry_failed_verified`（扣失败成本） |
| 买入 `stage∈{10,11,12}` 或槽位不可解 | `entry_unknown` / `model_unsupported` |
| RPC 报错、超预算、解码失败 | `data_missing` / `decode_error`（**不得冒充链上失败**） |
| pair 无代码 / 储备为 0 | `code_absent` / `zero_reserve_observed`（诊断字段，不单独定 M=0） |

**规则 C1**：通用 revert 永不改名为蜜罐或不可卖（代码注释已固化，本规格重申）。
**规则 C2**：过程字段（触发／入场／退出／模型／数据）**各存各的**，不用一个互斥字符串覆盖。

---

## 4. 成本口径（把 §6 落成可计算式）

```
A = 0.05 ETH（固定本金）
R = 卖出调用中 WALLET 原生余额的实际增量（尚未减 gas）
G = Σ(所有实际发生的尝试 × 该尝试的 gas 用量 × gas 单价)
I = A + G
M = R / I
本路径净现金流 = R − A − G
```

`G` 的构成（每个样本逐项落盘，缺项标未知而不是记零）：

| 项 | 情景取值 | 计一次的条件 |
|---|---|---|
| 买入 swap | 120k / **150k** / 200k | 每次买入尝试（含失败）各计一次 |
| 卖出 swap | 120k / **150k** / 200k | 每次卖出尝试（含失败）各计一次 |
| `approve` | 50k / 次 | 本规则每次卖出需 2 次（`approve(0)` + `approve(amount)`） |
| gas 单价 | `baseFeePerGas(该块) + tip`，tip ∈ {0, **0.1**, 1} gwei | 买入用 `entry_block`，卖出用 `exit_block` |

9 组情景（3 gas × 3 tip）**全部报告**，主汇总用 150k / 0.1 gwei。
**这些是设计假设，不是上下界保证**；探针 helper 的总 gas ≠ 真实单次 EOA swap gas。

**规则 G1**：`R` 不重复扣 LP 费与价格冲击——它们已体现在执行结果里。
**规则 G2**：买入成功、卖出失败的样本**仍扣一次买入 gas 与授权 gas**。
**规则 G3**：`A` 不自动记为已实现亏损；未处置的持仓成本基础与残余资产另列。

---

## 5. 需要你确认的三项（冻结前）

| # | 待定 | 我的建议 | 影响 |
|---|---|---|---|
| **D1** | `--slot-limit` 取值 | 建议 **32**。扫描成本 = 2×limit 次 `eth_call`／样本；32 覆盖绝大多数标准布局，且把最坏成本钉在 64 次 | 直接决定单候选调用量与 `model_unsupported` 比例 |
| **D2** | 是否启用 §2 的两项收窄诊断 | 建议**启用**。+2 次 `eth_call`／样本，换来 revert 证据可分层 | 成本 +2 次；不启用则 stage 20 只能整块归为未知 |
| **D3** | 入场延迟 | 配置 §4 现为 `mint_block + 1` **块末快照**。建议维持 | 改动即改口径，须重新冻结 |

---

## 6. 本规格不覆盖

- 交易被打包与排序（竞争下的 inclusion）——历史无反事实
- 自身买入对退出时池状态的影响——退出快照里我们的买入从未发生
- 30 天持有期内的到账变化、代理升级、黑白名单变更
- 该代币在 V3 / 其他 DEX 是否已有池

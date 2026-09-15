# 测量口径冻结规格 v1.8（待冻结）

> **取代 v1.7（新增 §7 资源约束与停机策略；§1–§4 判据一字未改）。**
> v1.7 原始字节保存在 `MEASUREMENT_SPEC.v1.7.md`（sha256 `b839046b0022c9875aa34ca8082a4b85f8240c48b03a463c26ec4d76dc41069f`），不追改。
>
> 本版落实 v17 复核点名的遗留项：**资源上限从"采样"变为"实测峰值 + 硬上限 + 有序停机"**。
> 这是真链串行/并行对照的前置条件。**不改任何测量判据。**

> **取代 v1.6（仅 §5 状态表、§0 差异列表；§1–§4 判据一字未改）。**
> v1.6 原始字节保存在 `MEASUREMENT_SPEC.v1.6.md`（sha256 `30853652fa452509d48d2477e9dc93d6366d018d285f5cbeb677e2c8362d7df8`），不追改。
>
> 本版记录 2026-09-10 第四轮审查（`audit_v16_20260910/`）一项修复：
> 证据绑定比对原写作 `if a is not None and a != b`，字段**缺失**即跳过，
> 六个绑定字段全都能靠"删掉"绕过。**不改任何测量判据。**

> **取代 v1.5（仅 §5 状态表、§0 差异列表；§1–§4 判据一字未改）。**
> v1.5 原始字节保存在 `MEASUREMENT_SPEC.v1.5.md`（sha256 `9c8d8480d4657aa393cec9e9a29ca8e8c4b7190bdd9cb436735956b5cdc6e34a`），
> 用 v1.5 采集的运行继续关联 v1.5，不追改。
>
> 本版记录 2026-09-10 第三轮审查（`audit_v15_20260910/REVIEW.md`）三个缺口的修复：
> 续跑证据未绑定到具体运行/候选/结果、诊断异常抹掉已到达的卖出阶段、
> 实际 HTTP 次数把未发出的请求算了进去。**不改任何测量判据。**

> **取代 v1.4（仅 §5 状态表、§0 差异列表与 §6 并行验收条件；§1–§4 判据一字未改）。**
> v1.4 原始字节保存在 `MEASUREMENT_SPEC.v1.4.md`（sha256 `ffb6ecf0dd84517e4a598d7b76a7736305347655241f1e3e23c39a098f259b5a`），
> 用 v1.4 采集的运行继续关联 v1.4，不追改。
>
> 本版记录 2026-09-10 第二轮审查（`audit_followup_20260910/REVIEW.md`）九个反例的修复。
> 这些修复改的是**采集与验收的可信度**（续跑交付、全局预算、证据完整性、
> 样本唯一性、事件元数据、成本保全），**不改任何测量判据**。

> **取代 v1.3（仅 §2 诊断落地说明与 §5 状态表；§1–§4 判据未改）。**
> v1.3 原始字节保存在 `MEASUREMENT_SPEC.v1.3.md`（sha256 `4b05269ef910fa4544113da78c35886d2fc7e9340f8ca1ba52128176010927ec`），
> 用 v1.3 采集的运行继续关联 v1.3。
>
> **取代 v1.2。** 本版实际改动 §3（买入 stage20 的映射）、§4（成本按到达阶段）与 §5 状态表；
> §1、§2 判据未改。v1.2 原始字节保存在 `MEASUREMENT_SPEC.v1.2.md`（sha256 `d97d93848ef31847d134ea8fa5b03a130747973b05db626bfeaf208ffb9d96d6`），
> 用 v1.2 采集的运行继续关联 v1.2。
>
> **取代 v1.1（仅 §5 实现状态与 §0 增补；§1–§4 判据一字未改）。**
> v1.1 原始字节保存在 `MEASUREMENT_SPEC.v1.1.md`（sha256 `ab5f8edb52828166ddb6788bf91fb0213bd3821b9acfff03885a5b48a0a157d9`）。
> 用 v1.1 采集的运行（`pilot/v4_one.*`、`pilot/v5_one.*`）继续关联 v1.1，不追改。
>
> **取代 v1。** v1 的原始字节保存在 `MEASUREMENT_SPEC.v1.md`
> （sha256 `04e673214d495c5d6876bcadc88725927e8829e1f6f55c18e53d64b0a2d368c0`），**不追改**。
> 2026-09-10 之前的运行证据里 `spec_sha256` 记的就是这个值，它们继续关联
> **v1 ＋ [PILOT_ERRATA_20260910.md](PILOT_ERRATA_20260910.md)**，历史证据不动。
>
> 本版对应代码：`pilot_measure.py` sha256 `ff052ba8326dc8a349c2e2cb62825163417384b033703b74506c399492483ca7`、
> `evidence.py` sha256 `f3ea0eee09e3c0fb3fa9d41ffaefda490faff3c12de5ca79396cb8d6398c967f`。
> 测试：9 个入口全部退出 0（`runs/gov_20260910/`）。
>
> 上位文件：`baseline_20260909/baseline-execution-config.md` v2.1 §4/§5/§6（未修改）。
> 依据 `verify_capabilities.py`（sha256 `bc9ea52e…`）的实际行为。

---

## 0. 被 v1 取代的条目

| v1 条目 | 处置 | 原因 |
|---|---|---|
| §2 H1「stage0 ⇒ 状态适配充分」 | **作废**，见本版 §2 | 反例：`unlockAt[buyer]=buyTime+90天`，注入余额而锁定字段保持默认 0 时卖出会成功并清零，真实买家却应被拒 |
| §2 判据表中 `adequate_proven_by_execution` 标签 | **作废** | 同上 |
| §5 D1「扫描成本 = 2×limit」 | **作废**，见本版 §2 | 实现是第一哨兵命中才试第二哨兵，非每槽两次 |
| §2 收窄诊断的读法「小额成功、全额 revert ⇒ 存在规模相关限制」 | **收窄**，见本版 §2 | 最小单位仍 revert 不能排除规模机制（最低输出取整为零等可并存） |
| §3「买入 stage20 ⇒ `entry_failed_verified`」 | **作废**，见本版 §3 | 未验证钱包/持仓模型时不得把通用 revert 升级为已验证入场失败 |
| §4 成本表的固定次数 | **作废**，见本版 §4 | 固定「买入1/卖出1/授权2」不反映实际到达的阶段 |

**v1.4 → v1.5 的差异**：只更新 §5 状态表、§6 并行验收条件与本节差异列表。
§1–§4 的判据、标签、公式、分类映射**一字未改**。本轮修的是采集侧的九项缺陷
（来源：`audit_followup_20260910/REVIEW.md`，回归守卫：`test_audit_followup.py`）：

| # | 缺陷（修复前的实际行为） | 修复后 |
|---|---|---|
| 1 | 检查点标了完成，删掉结果与证据后续跑仍 `exit=0`、`results=[]`、`set_complete=true` | 完成时把**结果本体连同 sha256** 写进检查点；续跑逐条校验后**并入累计交付**；校验不过者不跳过、重新测量；引用的证据文件缺失或不完整则验收不通过 |
| 2 | 检查点中段插入坏行被静默跳过 | 中段损坏 `SystemExit` 阻断（尾部半行仍按中断隔离放行） |
| 3 | `max_calls=2` 实际发生 3 次调用；启动请求、串行分支、Etherscan 都在预算外 | 闸门在**第一个请求之前**建立，覆盖启动/串行/并行/Etherscan；`max_calls` 对**逻辑请求数**与**实际 HTTP 次数**同时封顶 |
| 4 | `V.RPC` 内部对 503 的重试不经过全局限流（要求间隔 10s，实测 1.0s） | 闸门下移到**真实 HTTP 边界**（`install_http_gate` 包住 urlopen），重试同样排队同样计数；实测间隔 10.01s |
| 5 | 买入成功后槽位查询抛异常 ⇒ 成本表整个不存在 | 买入腿一旦执行，成本必然生成；退出腿未尝试记 0 次，回款 `R_wei` 独立保留未知 |
| 6 | 样本声明两个候选、`index=[1,1]` 仍 `exit=0` | 样本数量与编号唯一性在测量前校验；结果与冻结样本**逐项**比对（重复/多余/字段不符均阻断） |
| 7 | 空证据文件、只有 `rpc_end` 没有 `rpc_begin`、缺 `run_header` 均判 `complete=true` | 空文件、孤立 end、重复 `pending_id`、缺运行头一律判不完整 |
| 8 | `transactionHash='0x'`、`blockHash='WRONG'`、`logIndex='garbage'` 全部通过；sender topic 非十六进制裸抛 `ValueError` | 三者按 32 字节 hash / 非负整数校验；非十六进制返回明确拒收原因 |
| 9 | 汇总写死 `MEASUREMENT_SPEC.md v1 (draft)` | 汇总记录实际绑定的规格文件名与 sha256 |

另外补入两项机制（不属于上述缺陷，但并行验收需要）：`--pin-finalized`
让串行与并行**各自独立的检查点**绑到同一状态块；区块缓存命中逐条落
`block_cache_hit`（记录取用双方），使缓存口径可查而非靠推断。

**v1.5 → v1.6 的差异**：只更新 §5 状态表与本节差异列表。
§1–§4 的判据、标签、公式、分类映射**一字未改**。本轮修的三项
（来源：`audit_v15_20260910/REVIEW.md`，回归守卫：`test_audit_followup.py` §13–§15）：

| # | 缺陷（修复前的实际行为） | 修复后 |
|---|---|---|
| 1 | **P0** 检查点记了 `evidence_run_id`，但复用时没用它。把引用的证据换成**另一个运行**的结构完整文件，续跑仍 `exit=0`、`evidence_chain_problems=[]`、`validation_passed=true` | 新增 `verify_evidence_supports`：逐条核验证据文件里**存在该 run_id**、该运行的 `run_header` 绑定（脚本/证据模块/规格/样本/台账/finalized 块）与检查点一致、且该运行里有**这个候选**的 `candidate_result` 且其规范 hash 等于检查点记录的 `result_sha256`。任一不符即阻断复用验收 |
| 2 | **P1** 主卖出已返回 stage20，随后尺寸诊断抛异常，成本却记 `swap=0/approve=0`、basis 写"exit leg never attempted" | 卖出到达的阶段在**主卖出返回后立即**写入 `rec["exit"]["attempts"]`，不再等到诊断之后。诊断调用本身仍**不**计为交易尝试 |
| 3 | **P1** `http_calls` 名为实际次数，实为**发车前占用的额度**：排队后被时间闸门拒绝、传输只执行 1 次，仍报 2 | 拆成三个口径：`http_reserved`（预算依据，占用后不退还以保证并发安全）、`http_sent`（`note_sent()` 紧挨传输调用登记，**唯一可当作实际网络调用量**）、`http_rejected_after_wait`。恒等式 `reserved == sent + rejected`。刻意**不**保留 `calls` 这个名字，调用方必须明写口径 |

配套前提（不属于上述三项，但第 1 项依赖它）：逐候选结果在写入检查点与证据**之前脱敏一次、两处共用同一份字节**，
否则结果里一旦出现被脱敏的串，两边 hash 天然不符，hash 绑定会误伤正常续跑；顺带堵住"检查点未过脱敏"这个口子。

**v1.6 → v1.7 的差异**：只更新 §5 状态表与本节。§1–§4 判据一字未改。

| 缺陷（修复前） | 修复后 |
|---|---|
| `verify_evidence_supports` 的绑定比对是 `if a is not None and a != b` —— 运行头里**删掉**某个绑定字段就直接跳过该项。`script_sha256`/`evidence_module_sha256`/`spec_sha256`/`sample_sha256`/`universe_sha256_now`/`finalized_snapshot` 六项逐一删除，续跑均 `exit=0`、`evidence_chain_problems=[]` | 检查点绑定里**有值**的字段，运行头里必须**存在**且相等；缺失单列 `evidence_binding_field_missing` 并阻断。缺失比不符更可疑，不是更安全 |

**v1.7 → v1.8 的差异**：新增 §7（资源约束与停机策略）、更新 §5 状态表。§1–§4 判据一字未改。

此前各版反复写明「现有资源采样不是硬 RSS/CPU 上限，也不是可靠峰值」——本版关闭这一项。

**v1.2 → v1.3 的差异**：§3 把「买入 stage20」从 ⬜ 落地为已实现的
`entry_unknown`；§4 的成本改为按 `reached_attempts()` 给出的到达阶段计，
缺 `baseFeePerGas` 一律记未知；§2 新增「合约当时不存在 ⇒ 供给按定义为 0」的说明。
**§1 与 §2 的 H1–H4 判据未改。**

**v1.1 → v1.2 的差异**：只更新 §5 的实现状态表并加一条说明。
§1–§4 的判据、标签、公式、分类映射**一字未改**。
（这样做是因为 §5 随代码推进而变，而判据应当稳定；每次实现推进都会发新版本，
差异列在此处，便于核对「证据里绑定的规格」是否就是当时的判据。）

## 1. 钱包执行上下文〔已实现〕

与 v1 相同，未修订。要点：`WALLET` 是**注入 `Probe` 合约代码的虚拟地址，不是 EOA**；
注入前校验无代码并记录原生余额，注入后校验不持久化；
`msg.sender` 对 router 与代币是**合约**。规则 W1（因合约身份触发的拒绝归
`model_unsupported`，不得作市场结论）保持不变。

## 2. 跨期持仓状态适配〔标签已实现／独立依据待实现〕

### H1（重写）· 执行成功不证明持仓充分

`stage==0 且 token_before==amount 且 token_after==0` 只证明
**「在本次注入的状态里，该调用完成且余额归零」**。它**不**证明：

- 注入状态等价于真实买入后的退出状态；
- 任意状态下 `balanceOf` 与 `transferFrom` 共用同一套账。

**标签**：`holding_state = simulated_completion_under_injection`，
并记 `holding_state_basis`（当前恒为 `none_beyond_injection`）。

**统计资格**：没有独立的、可审查的状态语义依据时，
**`economic_eligible = false`**；**M / Z 不因执行成功而可判定**。
这两件事绑定——不允许只改标签而保留经济统计可用。

升级到「充分」需要另行提供状态语义依据（如反编译/源码核对锁定与冷却字段、
或构造受控合约反例证明该代币的记账路径），并在本规格再发一版。

### H2–H4（不变）

| 观察 | 判定 |
|---|---|
| `stage==10/11` | `model_unsupported`；注入未落到实处，**不是不可卖** |
| `stage==20` | `execution_reverted_unknown`；不得改名蜜罐/不可卖 |
| 扫描 0 或 >1 命中 | `model_unsupported` |

四类**全部保留在分母内**，不删样本、不记 M=0。

### 收窄诊断（读法收窄）

`size_probe`（卖 1 个最小单位）与 `identity_probe`（换虚拟地址注入）**只记录，不判定**。
特别地：**最小单位仍 revert 不能排除规模相关机制**——最低输出取整为零、
或多种限制并存都可能造成同样结果。

`identity_probe`〔已实现〕：把 `Probe` 代码注入 `CALLER` 并由它发起同一次卖出，
余额注入 `CALLER` 名下的同一映射槽。**两个虚拟身份都没有真实买入历史**，
因此两者同样失败**不能**排除「都缺历史状态」这一共同原因；结果不同只说明行为与
地址相关，不指明机制。随记录落一句 `record only; both virtual identities lack
real purchase history, so agreement does NOT exclude missing-history as a common cause`。

### 供给读数的边界情形

`totalSupply(bn)` 在**合约当时不存在**时返回 `0x`。这不是错误：
建池与首次 Mint 常在同一块，此时 `bn-1` 上 pair 尚无代码。
**合约不存在 ⇒ 供给按定义为 0**；但必须与「有代码却返回空」区分，后者仍按异常处理。
判定依据记入 `supply_basis`（`no_code_at_block` / `call`），事后可分辨
「before=0」是查出来的还是按定义推出来的。

### D1 · 槽位扫描的逻辑调用数（精确式）

```
1（扫描前原值读取）
+ limit（每槽各试一次第一哨兵）
+ H₁（第一哨兵命中的槽数 —— 每个这样的槽再试一次第二哨兵）
+ 1（移除覆盖后的恢复核验）
```

**H₁ 是第一哨兵命中数，不是最终双哨兵通过的槽数**：某槽可能第一哨兵命中、
第二哨兵不符，它仍然消耗了一次第二哨兵调用。

`limit=32`、`H₁=1` 时为 **35**。HTTP 层重试**另计**；中途失败按**实际发生次数**记录，
不从最终结果反推。

## 3. 失败与未知分类〔映射待实现〕

### 探针 stage → 状态（唯一权威映射）

| stage | §5 状态 | Z/M | 实现状态 |
|---|---|---|---|
| 0（买入） | 入场成功 | 记实际增量 | 已实现 |
| 0（卖出） | `measured_exit` | 记增量，但 `economic_eligible=false` | 已实现 |
| 10 / 11 | `model_unsupported` | 均未知 | 已实现 |
| 12 | `execution_reverted_unknown` | 均未知 | 已实现 |
| **20（买入）** | **`entry_unknown`** | 均未知 | **待实现**（现码仍写 `entry_failed_verified`） |
| 20（卖出） | `execution_reverted_unknown` | 均未知 | 已实现 |
| 其它 | `decode_error` | 均未知 | 已实现 |

> **买入通用 revert 不得升级为「已验证入场失败」。** 在钱包语义与持仓模型
> 未获独立验证之前，它只是未知。`entry_failed_verified` 需要另有依据才可使用。
>
> stage 10/11 记 `model_unsupported` 是**保守归类**，不等于已查明原因必是注入不足——
> 代币自身行为也可能导致授权或余额读数不足。

### 编排层

| 情形 | 状态 | 实现 |
|---|---|---|
| 窗口截止前无 Mint | `no_mint_by_cutoff` | 已实现，但**核验待补**（见 §6） |
| 槽位不可解 | `model_unsupported` | 已实现 |
| RPC/接口失败、超预算、解码失败 | `data_missing` / `decode_error`（**不得冒充链上失败**） | 已实现 |
| 退出快照晚于 finalized | `right_censored` | 已实现 |
| pair 无代码 / 储备为 0 | 诊断字段，不单独定 M=0 | 待实现 |

**C1**：通用 revert 永不改名蜜罐或不可卖。**C2**：过程字段各存各的，不用互斥字符串覆盖。

## 4. 成本口径〔按阶段记录待实现〕

```
A = 0.05 ETH
R = 卖出调用中 WALLET 原生余额实际增量（未减 gas）
I = A + G          M = R / I          本路径净现金流 = R − A − G
```

**G 必须按实际到达的阶段记**〔**待实现**，现码固定「买入1/卖出1/授权2」〕：

| 尝试 | 计入条件 |
|---|---|
| 买入 swap | 每次实际发出的买入尝试（含失败） |
| 卖出 swap | **仅当执行到达 swap**。stage 10 在授权前返回、stage 11/12 可能未到 swap，此时不得计 |
| `approve` | 按**实际到达的授权次数**。`doApprove=false` 或 stage 10 提前返回时为 0 |
| gas 单价 | `baseFeePerGas(该块) + tip`；**缺 baseFeePerGas 记未知，不记零**〔待实现〕 |

**不得计入交易尝试的**：HTTP 层重试、`size_probe` / `identity_probe` 等诊断调用。

情景：swap 120k/**150k**/200k × tip 0/**0.1**/1 gwei = 9 组全报，主汇总用 150k/0.1 gwei。
**均为设计假设，不是上下界保证。** helper 内联授权 ≠ 独立 EOA 两笔授权。

**G1** `R` 不重复扣 LP 费与价格冲击。**G2** 买入成功、卖出失败仍扣已发生的买入与授权成本。
**G3** `A` 不自动记为已实现亏损。

## 5. 实现状态总表（防止本版又成混合口径）

| 条目 | 状态 | 位置 |
|---|---|---|
| H1 标签 + `economic_eligible=false` | ✅ 已实现 | `pilot_measure.py` |
| D1 精确计数（含原值读取） | ✅ 已实现 | `find_slot` |
| 证据层：请求级落盘/阶段标签/脱敏/中断可读/规格阻断 | ✅ 已实现（29 项测试） | `evidence.py`、`test_evidence.py` |
| 首次 Mint 核验（address/topic/范围/分页/供给交叉） | ✅ 已实现（17 项测试） | `first_mint`、`test_first_mint.py` |
| 候选级状态校验（钱包原值与恢复、协议身份、块 hash） | ✅ 已实现 | `validate_candidate_state`、`verify_wallet_not_persisted`、`snapshot_block` |
| 买入 stage20 → `entry_unknown` | ✅ 已实现（18 项测试） | `pilot_measure.py`、`test_step4.py` |
| 成本按到达阶段、缺 base fee 记未知 | ✅ 已实现（18 项测试） | `reached_attempts`、`gas_cost` |
| 端到端阻断反例（5 种受控失败注入） | ✅ 已实现（30 项测试） | `fake_chain.py`、`test_e2e_blocking.py` |
| `identity_probe` | ✅ 已实现（e2e 12 项） | `identity_probe`、`test_e2e_blocking.py` |
| 断点续跑（绑定/跳过/失败历史/拒绝复用/快照锁定） | ✅ 已实现（23 项测试） | `evidence.Checkpoint`、`test_resume.py` |
| 续跑交付完整性（结果内联 + hash + 证据链） | ✅ 已实现（v1.5 新增） | `evidence.Checkpoint.deliverable`、`test_audit_followup.py` |
| 续跑证据与运行/候选/结果 hash 绑定 | ✅ 已实现（v1.6 新增） | `evidence.verify_evidence_supports`、`test_audit_followup.py` §13 |
| 绑定字段缺失即阻断（不可靠删除绕过） | ✅ 已实现（v1.7 新增） | `evidence.verify_evidence_supports`、`test_audit_followup.py` §13 |
| HTTP 计量分 reserved/sent/rejected | ✅ 已实现（v1.6 新增） | `evidence.SharedGate`、`test_audit_followup.py` §14 |
| 诊断异常不抹掉已到达的卖出阶段 | ✅ 已实现（v1.6 新增） | `pilot_measure.handle`、`test_audit_followup.py` §15 |
| 全局预算与限流闭合（启动/串行/并行/Etherscan/HTTP 重试） | ✅ 已实现（v1.5 新增） | `evidence.SharedGate`、`install_http_gate`、`test_audit_fixes.py` 12/12b |
| 证据结构完整性（空/孤立/重复/缺头） | ✅ 已实现（v1.5 新增） | `evidence.read_evidence` |
| 样本唯一性与结果逐项一致 | ✅ 已实现（v1.5 新增） | `pilot_measure.measure` 验收块 |
| 同快照对照机制 `--pin-finalized` | ✅ 已实现（v1.5 新增） | `pilot_measure.py`、`test_audit_followup.py` §12 |
| 串行 vs 两路并行一致性（真链） | ⬜ 待验收 | §6 |
| 资源峰值（内核 VmHWM 实测，非采样） | ✅ 已实现（v1.8 新增） | `evidence.rss_peak_kb`、`test_audit_followup.py` §16 |
| 资源硬上限与有序停机（RSS/CPU/墙钟/信号） | ✅ 已实现（v1.8 新增） | `evidence.ResourceGovernor`、§7 |
| 新增 CLI 选项不得让程序化调用者崩溃 | ✅ 已实现（v1.8 新增） | `pilot_measure.OPTIONAL_DEFAULTS`/`opt()`、§17 |

> **状态校验通过 ≠ 跨期持仓充分。** `validate_candidate_state` 只证明
> 「注入前虚拟地址干净、协议身份正确、所用区块可核验」，与 §2 的 H1 是两件事，
> 代码里随每条候选落盘一句 `state validation only; NOT evidence of
> cross-period holding adequacy`，不得相互替代。

**⬜ 的条目未实现前，本规格不得用于正式冻结或 300 样本。**

## 6. 下一步要补的核验（尚未实现，列此备查）

### 6.0 串行 / 并行真链对照的成立条件（v1.5 补入）

1. 两次运行必须绑到**同一 finalized 状态块**：用 `--pin-finalized <块号>:<块hash>`，
   两次各用**独立检查点**。共用检查点会让第二次直接跳过候选，
   各自新建又会各取各的 finalized —— 两条路都不构成同快照对照。
2. 比较**状态、金额、分类、身份判定**；耗时与请求顺序允许不同。
3. 每候选的 Etherscan 次数按候选归集（`counts_by_candidate`），
   不得用共享计数器的差值 —— 并行重叠会把别的候选算进来。
4. 区块缓存跨 worker 共享，命中逐条落 `block_cache_hit`（记 `fetched_by_worker`
   与 `used_by_worker`）。对照时缓存口径以这些记录为准。
5. 资源项只有采样，**不得**表述为「资源上限已验收」。


- **首次 Mint**：校验 `address` / `topic0` / 块号在请求范围内 / 分页是否打满；
  「无 Mint」结论须附链上状态交叉核验（如相邻 `totalSupply` 边界）与原始响应。
- **候选级状态**：逐候选钱包代码与余额原值及恢复检查、协议身份（factory/router/WETH/pair）
  与代码 hash、入场与退出块的 hash 与相邻时间戳落盘、结束时块 hash 复读。
- **退出块定位**：时间插值**只用于生成二分初始边界**；必须证明左右时间戳包围目标，
  不包围则扩展；并核验最终块与其前一块。**不得用平均出块时间替代精确定位。**

## 7. 资源约束与停机策略（v1.8 新增）

### 7.1 峰值的口径

`rss_peak_kb()` 取内核维护的高水位 **`VmHWM`** —— 进程自启动至今到达过的最高 RSS。
它是**实测**，不是采样：两次采样之间的尖峰同样计入。
`/proc` 不可用时退回 `getrusage(RUSAGE_SELF).ru_maxrss`。

证据里 `resource` 记录同时保留 `rss_kb`（采样，当前值）与 `rss_peak_kb`（峰值），
**两者不得混用**：报告资源上限只能引用后者。CPU 用 `os.times()` 的累计值，本身即精确。

### 7.2 上限与判定

| 参数 | 判据 |
|---|---|
| `--max-rss-mb` | `rss_peak_kb > 上限` |
| `--max-cpu-s` | `user+sys > 上限` |
| `--max-wall-s` | 墙钟 > 上限（与 `--max-seconds` 的 RPC 时间预算是两回事） |
| SIGTERM / SIGINT | 立即置停机标志 |

后台看门狗按 `--governor-poll-s`（默认 0.25s）巡检；证据里 `governor_report`
记录 `watchdog_observations`，可据此确认看门狗**确实在跑**而不是装了不跑。

### 7.3 停机是有序的

越线**只置标志**，由候选之间与阶段之间的**安全点**抛 `Shutdown` 并有序收尾。
**不在写证据的中途把进程打死** —— 那会留下半行、留下无配对的 `rpc_begin`，
把「资源超限」变成「证据损坏」。停机后证据仍须结构完整。

`RLIMIT_AS` 只作最后兜底且默认不设：它触发时是 `MemoryError`，位置不可控，
正是要避免的那种失败。

### 7.4 停机后的账怎么记

| 情形 | 记法 |
|---|---|
| 停机前已完成 | 正常状态，检查点标完成，续跑跳过 |
| 停机时正在进行 | `aborted_by_shutdown`，**不算完成**，检查点不标完成，续跑重做 |
| 停机时还没轮到 | 逐个进 `acceptance.not_started`（含原因），**不算静默缺失** |

`set_complete=false`、`process_completed=false`、`validation_passed=false`。

### 7.5 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部完成且验收通过 |
| 1 | 采集完成但判定不通过（集合不全、证据链断、状态校验失败、有未完成候选） |
| 2 | 前置条件不满足（缺凭据、链身份不符、样本不自洽、快照不符） |
| **3** | **有序停机**（资源越线或信号）。检查点完整，放宽限额后可续跑 |

**停机绝不报告为成功。** 退出码 3 与 0/1/2 都不同，便于自动化区分
"没做完"与"做完了但不通过"。

## 8. 本规格不覆盖

交易被打包与排序；自身买入对退出时池状态的影响；30 天内到账变化、代理升级、
黑白名单变更；该代币在 V3/其他 DEX 是否已有池。

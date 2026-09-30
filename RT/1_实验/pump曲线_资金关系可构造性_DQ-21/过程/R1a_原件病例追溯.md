# R1a v3 原件病例追溯：资金/控制关系（09-30，0 credits）

> 依据 02 §10.3：新的承重语义映射在超出冒烟规模的取数之前，取真实原件（含已知边界类型），对照一手规范逐例确认含义。执行模型做；未请第二模型构造反例（§10.8 语义例外为“可另请”）。
> 脚本：[trace_r1a_cases.py](../trace_r1a_cases.py)；逐例原始对照：[R1a_原件病例追溯.json](R1a_原件病例追溯.json)。原件为 R0 缓存（`raw/helius/back__W__t.jsonl.gz` 的第一页，≤100 笔，即 v3 的“一页”口径）；R0 的币不进入 R1a 主分析。

## 1. 要确认的映射

| 映射 | v3 用法 |
|---|---|
| 某地址是早买者 W 的“来源” | Full 层：`flows.py`（R0 口径）判为唯一可归因的流入方 |
| 持久化 nonce 提款的授权人是“来源” | 计入 Full 层来源，含义写作“**出资或控制**来源”；另做去掉 nonce 的“纯出资”敏感性 |
| 两个早买者来源相同 = 同一方在背后 | V2 |
| 来源是交易所、终端、服务 = 不相连 | 服务集合排除 |
| 页内没有唯一来源 = 未解析，不是“独立” | 强度分母不计 |

## 2. 方法

- 按 Solana System Program、SPL Token、Stake Program 的指令布局与账户顺序**另写一个独立解码**（不调用 `flows.py` 的解码）：列出资金去向是 W（W 本身或 W 名下代币账户）的每条指令及各账户角色。规范依据：`system_instruction.rs`（Transfer = [from 签名, to]；CreateAccount = [funding 签名, new]；CreateAccountWithSeed 的 lamports 在种子串之后；WithdrawNonceAccount = [nonce, recipient, recent_blockhashes, rent, authority 签名]；TransferWithSeed = [from 派生, base 签名, to]），SPL Token `instruction.rs`（Transfer = [source, destination, authority]；TransferChecked = [source, mint, destination, authority]；CloseAccount = [account, destination, owner]），Stake `Withdraw` = [stake, recipient, clock, stake_history, withdraw_authority]。
- 每类边界按 (mint, W, 签名) 的 sha256 取前 1～3 例，逐笔与 `flows.py` 的来源、控制者、证据、状态对照。
- 另对全部 R0 在曲线上的早买者，统计第一页里“唯一来源”流入所在交易是否还调用了交易类程序，检查兑换结算被当成出资的风险。

## 3. 逐例结果（18 例）

| # | 类型 | 规范解码（指向 W） | flows.py | 一致 | 含义 |
|---|---|---|---|---|---|
| 1–2 | 普通系统转账 | System Transfer，from＝唯一签名者 | 来源＝该签名者，`sys`，unique | 是 | 签名者用自己的 SOL 出资 |
| 3–5 | 持久化 nonce 提款 | WithdrawNonceAccount，authority＝签名者，nonce 账户是另一地址 | 来源＝authority，`nonce`，unique | 是（机械上） | **只证明控制**：authority 能动用 nonce 账户里的钱，钱最初由谁存入看不到。#4 同笔另有 0.00089 SOL 的普通转账，低于 0.05 SOL 门槛被忽略 |
| 6–7 | wSOL 代币转账 | TransferChecked，source 代币账户的 owner＝签名者 | 来源＝该 owner，`wsol` | 是（机械上） | **兑换结算，不是出资**：交易里有做市/聚合程序；收款钱包 `ARu4n5mF…` 经核实为**程序账户**，v3 把程序账户买家排除在关系之外，不进入信号 |
| 8 | 建账户注资（含 wSOL） | CreateAccount 为 W 的 wSOL 账户付租金 + wSOL TransferChecked | 两笔合计归到付款签名者，`sys_create+wsol` | 是（机械上） | 同上，W 为程序账户，被排除 |
| 9–10 | 余额证据·唯一 | **Stake Withdraw**：新建的质押账户把钱提给 W，withdraw_authority＝签名者 | 来源＝withdraw_authority，`balance`，unique | 是 | “质押账户中转”：付款方新建质押账户再提给 W，余额判定正确归到付款方 |
| 11 | 余额证据·多方 | W 自己签名，关闭代币账户、调用 DLMM 类程序（卖出） | `balance`，multiple | 是 | 卖出所得，不唯一 → 未解析，不当作出资 |
| 12 | PDA 来源 | 内层 System Transfer，from 为程序派生地址 | `program` | 是 | 程序付款（闪兑类）→ 未解析 |
| 13–14 | 交易所（严格标签） | System Transfer，from＝Binance 等标签地址 | unique，来源为标签地址 | 是 | 进入服务集合，不相连 |
| 15 | 终端（宽松画像） | System Transfer，from＝Axiom 终端地址 | unique | 是 | 进入服务集合，不相连 |
| 16 | 模板化 10 SOL 出资地址 | 与 #3 同笔：nonce 提款，authority＝模板地址之一 | nonce，unique | 是（机械上） | 11 个地址行为一致（每个 100 笔中 62 笔转出、34 个接收方，金额多为 10 SOL）。按 R0 画像规则（最常见金额占比 0.48 >0.2）不算服务，会参与 V2；是混币式服务还是同一操盘者无法区分 |
| 17 | 程序账户买家 | 买家地址不在 ed25519 曲线上 | `program_account` | 是 | 排除 |
| 18 | 页内无唯一来源 | 100 笔页内只有 PDA 余额流入 | 全部 `program` | 是 | 未解析，不当作独立 |

样本中没有带种子转账（`sys_seed`）；R0 全部流入里也没有这一类。关闭账户转余额在 R0 中只有 8 笔，没有落在抽中的第一页里。

## 4. 全体统计（R0 在曲线上的早买者，第一页）

- “唯一来源”流入按所在交易分：只调用基础程序（System、ComputeBudget、Token、ATA、Memo、Stake）的普通转账 1,348、nonce 577、wSOL 19 等；同时调用其他程序（主要是 pump 曲线、pump 手续费程序与几个未识别程序）的普通转账 464、建账户注资 1，**没有一笔来自对手方的 wSOL**。
- 按钱包算主来源：573 个来自只含基础程序的交易，44 个（7%）来自同时调用其他程序的交易。后者都是签名者主动发出的系统转账（例如与买入同笔的注资），按出资解读成立。
- 09-28 审计已测：一页口径与 7 天口径主来源相同 391/540（72%），一页内无唯一来源 114（21%）；去掉 nonce 边后 V2 触发不变（`results/r0_onepage_funder_sensitivity.json`、`results/r0_nonce_control_sensitivity.json`）。

## 5. 结论与写入 v3 的处理

1. **机械解析**：18 例全部与规范一致；[解析冒烟](R1a_解析冒烟.json)中 10 个 R0 币 184 个早买者，`build_r1a.py` 的主来源与 09-28 审计脚本逐个相同（含与不含 nonce 两种口径，184/184）。
2. **nonce 授权人**只证明控制。v3 主强度把它算作“出资或控制来源”，因为这个信息族问的是早买者背后是不是同一方；另报去掉 nonce 的纯出资口径。
3. **兑换结算**会以 wSOL 转入的形式出现，但在样本中只落在程序账户买家上，v3 已排除这些买家；普通钱包中没有观察到。
4. **服务地址**：交易所严格标签用 Dune 标签全表（166 个，均早于 A 周加入），宽松服务沿用 R0 画像规则，并对 R1a 中新出现、被 ≥2 个早买者当作主来源的地址按同一规则画像（1 页/地址）。
5. **模板化 10 SOL 地址**语义不清，保留为可相连来源，另报去掉这 11 个地址的敏感性。
6. **未解析**（页内无唯一来源、程序账户买家）单列，不计入强度分母。

**不能推出**：本追溯只覆盖 R0 缓存中出现过的类型；R1a 新样本若出现新的出资路径（例如新的中转程序），按“未解析”处理，不会被当作相连。

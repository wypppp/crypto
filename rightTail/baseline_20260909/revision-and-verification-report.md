# 三文件整套修订与验证记录

日期：2026-09-09。

**已完成：**逐行审查本次三份附件，修改代码、执行配置与覆盖账本，并核对它们的依赖关系。交付版本为执行配置 v2.0、覆盖账本 v2.2、验证脚本 v2.0。

**尚未完成：**真实主网端点能力验证及母体经济基线。当前环境访问公开 RPC 的首个请求返回 HTTP 403；这不是“端点不支持历史模拟”的证据，也不是用户端点的验证结果。未运行 300 个候选，未产生策略收益结论。

## 1. 一个已证实的版本问题

对本地附件做了逐字节比较：

| 本次附件 | 与之完全相同的上一版附件 |
|---|---|
| baseline-execution-config(1).md | baseline-execution-config.md |
| right-tail-coverage-ledger(3).md | right-tail-coverage-ledger(2).md |

因此，对话中承认了 Router、时间窗、样本判读和记账问题，并没有让这两份附件发生变化。本次修订直接更新文件中的规则及其依赖，不以另加一段“已知问题”保留旧执行指令。

## 2. 已修改的问题

| # | 原问题 | 已落实的修改 |
|---|---|---|
| 01 | 设计选择、外部事实、推导、实测混在一类 | 两轴证据登记：主张性质 × 验证状态；PASS 只对应具体测试 |
| 02 | 新池另一侧直接称“新代币” | 改为 target_token；保留其他场所已有交易的边界 |
| 03 | 没检查链 ID，随 latest 漂移 | 验证主网 chain id，固定 finalized 快照，保存历史 hash 并复查 |
| 04 | 首尾区块包含关系不清 | 时间窗统一为左闭右开；工厂计数用起点前一块与终点最后一块 |
| 05 | allPairs 差值被当作 WETH 候选数 | 区分 N_all 与 N；枚举必须完成资产识别，失败项不丢弃 |
| 06 | 固定 216,000 块代替 30 天 | 用实际时间戳 +2,592,000 秒定位；不假定每个 slot 都有块 |
| 07 | 首次 Mint 可能无限延后，随访成熟被猜测 | 新增窗口结束前触发资格；截止未触发仍保留并与全损区分 |
| 08 | +1 块没有说明块前/块末 | 明确为块末状态快照，不能描述成订单已在下一块内部成交 |
| 09 | 储备二分的算法前提错误 | canonical V2 的 totalSupply 二分 + 相邻边界 + 单块 Mint 日志 |
| 10 | 正常老代币只能回看 400k 块，容易直接失败 | 从可验证的历史边界定位；控制币须早于评价窗口 |
| 11 | 空 ABI 或 null 被当成零/正常结果 | 严格验证 JSON-RPC envelope、数量、ABI 长度、地址高位与日志字段 |
| 12 | supporting Router 没返回值，普通 amounts 又不等于到账 | 内嵌测量合约，在同次执行中读余额前后值；两侧都测量 |
| 13 | 只探测 trace 接口就称测量通道可用 | 移除这条假通过路径；实际执行买入/卖出测量；trace 非必需 |
| 14 | stateOverride 只要没报错便 PASS | 在两个历史快照上用两组数值验证 code/balance/stateDiff 实际生效，并验证不持久化 |
| 15 | 扫到一个余额槽便暗示完整持仓 | 两个哨兵值、唯一匹配、有界扫描、移除后读回；仍明确只是有限余额适配 |
| 16 | 卖出没有真实余额/授权建立过程 | 注入测得币数，再执行 approve(0)、approve(amount)、卖出；读取 ETH 净到账前后值 |
| 17 | 用死地址并假定原余额为零 | 专用虚拟地址，检查代码、原生余额和控制币初始余额，不依赖用户钱包 |
| 18 | T6 只比较余额变化，没有交易失败对照 | 普通、双侧税、缺余额、缺授权、受限五种合约控制；核对金额、阶段和错误码 |
| 19 | 未使用的 --honeypot 参数与不可满足的全零门槛 | 移除闲置参数；使用有定义的受控案例，按必需依赖判定，不要求可选接口全部通过 |
| 20 | 任意 revert 可能被当作不可卖 | 通用 revert 固定为 execution_reverted_unknown；仅受控已知规则可注明限制原因 |
| 21 | 零储备或合约缺失立即 M=0 | 改为诊断状态；须验证实际余额、执行环境与冻结处置规则 |
| 22 | 失败或 UNRUN 运行完仍退出 0，异常可能没日志 | 0/1/2 退出码、原子写日志、请求/返回/错误/耗时记录、预算耗尽不假通过 |
| 23 | 缺 Keccak 后端用常量自证常量，pad/word 失败未纳入退出码 | 移除 fallback；缺依赖失败；所有离线断言进入总结果 |
| 24 | RPC URL 与异常可能携带凭据 | 支持本地环境变量，日志脱敏，输出不显示原始 URL；RPC 方法只读白名单 |
| 25 | 旧免费档范围及约 5000 次调用的承诺 | 更新官方限制、按 N_all 与适配复杂度估成本，保存实际调用量；取消免费完成保证 |
| 26 | 成本缺优先费、授权和失败尝试，可能重复扣 gas | 明确 ETH 输出尚未减 gas；成本单列一次；新增未校准情景并限制结论 |
| 27 | 未触发、买入失败与未知的分母混用 | 保留全部抽样对象，分开机会率、触发率和已入场 M；不补抽失败候选 |
| 28 | 300 零命中被解释成没有 10× 空间 | H1 只检验至少 1% 的发生率；有限母体优先超几何，缺失区间不冒充置信区间 |
| 29 | 直接样本中位数当正式 H2 检验 | H2 改为 D2 描述性诊断，本轮 H1 为唯一正式主检验 |
| 30 | 看完 300 个仍保留后 150 个“未使用检验集” | 整批视为开发/描述资料；未来确认要用尚未看过的数据 |
| 31 | looks 计数被当作多重检验控制，冻结 hash 自指 | 固定终点与不择优报告；canonical payload 外置 hash；改规则保留新版本 |
| 32 | “只有超鞅才是无优势模型” | 指定比较基准；20% 是无注资、非负财富超鞅的条件上界，不是市场真实概率 |
| 33 | 已平仓收入减全部外部注资作为已实现损益 | 分开账户价值、外部现金流、累计经济损益与按处置成本配对的已实现损益 |
| 34 | 净现金流与已实现损益混淆 | 未退出本金仍有持仓成本基础；R−A−G 称路径净现金流，不自动称已实现亏损 |
| 35 | 无来源的历史数字与操作者行为成为当前判断依据 | 删除其决策用途或明确旧稿转述/待核；不推断用户账户、隐私与复算能力 |
| 36 | Parking Lot 与当前执行状态冲突 | 已纳入统计、覆盖登记和关闭规则的事项同步更新；保留 54 行维度，不按完成比例制造可信度 |

## 3. 本版新增或明确的设计选择

这些是为了让实验有确定口径而写入的设计，**不是外部已证实事实，也尚未冻结为运行结果**：

- 首次 Mint 必须在候选创建窗口结束前出现；否则本轮无触发，而不是无限等待。
- 主机会率分母为全部 WETH 新池；另报成功入场后的条件收益分布。
- 明确块末快照，而不是含糊的“下一块成交”。
- 显式成本参考情景与敏感性，包括 priority fee 和授权成本；并未声称费用已校准。
- 测量器采用临时合约钱包，避免依赖 trace 服务；钱包上下文和跨期持仓适配仍是正式样本的质量条件。

## 4. 实际执行过的验证

| 验证 | 结果 | 支持范围 |
|---|---|---|
| 最终脚本 selftest | **21 PASS / 0 FAIL / 0 UNRUN**，退出码 0 | 纯函数、严格解码、门禁与本地执行正确性 |
| 独立 py-evm 合约控制 | 普通、双侧税、缺余额、缺授权、卖出限制均符合预期 | 人工受控合约，不是主网样本 |
| 人工历史工作流 + EVM | T1–T7 对应流程、老池首 Mint、窗口边界、忽略 override 的反例通过 | 编排和测量器验证；历史头/工厂响应是人工 fixture |
| 嵌入源码重编译 | Probe、FixtureToken、FixtureRouter 三份 runtime **逐字节一致** | solc 0.8.26，优化 200 次，Istanbul，无 metadata bytecode hash |
| 无 RPC 参数运行 | 0 PASS / 0 FAIL / 8 UNRUN，退出码 2，保存日志 | 未执行不会被判通过 |
| 缺依赖运行 | 非零退出，门保持关闭，日志保留 | 不再用常量 fallback 假装通过 |
| 公开 RPC 尝试 | **0 PASS / 1 FAIL / 7 UNRUN**，退出码 1 | 首个 eth_chainId 请求 HTTP 403；没有端点能力或市场结论 |
| 文档一致性 | 54 行主维度；合约地址格式、核心版本/时间窗/统计规则核对通过 | 文件规则一致性 |

控制中的税率是人工设置：买入扣 10%，卖出再扣 10%；10,000 wei 的控制投入得到 90,000 个代币最小单位，再换回 8,100 wei。它用于验证测量器能看见两侧扣减，不是任何真实币收益。

二项公式复算：`0.995^300 = 0.2222922`；300 零命中单侧 95% 上限 `1−0.05^(1/300) = 0.00993608`。这些公式有明确模型条件，不能不经分母/缺失检查直接用于本轮样本。

## 5. 文件与使用边界

- `baseline-execution-config.md`：完整执行口径、运行命令与正式基线条件。
- `right-tail-coverage-ledger.md`：全局覆盖与决策规则；保留原六层结构。
- `verify_capabilities.py`：自包含测量源码与字节码；run 模式不需编译器；只读 RPC。
- `offline_verification.json`：实际离线记录，含脚本与字节码 hash。
- `verification_log.json`：实际公开端点失败记录；不代表用户自己的端点。

当前材料足以继续做端点验证；**不能据此宣告基线已经完成或直接启动 300 个候选。** 本次修订没有交付正式的全量采集器/基线计算器，也没有把这项后续实现伪装成已经运行。真实端点、完整 N、配置冻结、成本与候选状态适配的结果仍须记录。

账本之外的旧死亡卡、冻结总协议或其他未提供文件没有被本次修改。本报告也不声称穷尽所有未来错误。

## 6. 核查使用的原始来源

技术语义依据 [Uniswap Factory](https://github.com/Uniswap/v2-core/blob/master/contracts/UniswapV2Factory.sol)、[Pair](https://github.com/Uniswap/v2-core/blob/master/contracts/UniswapV2Pair.sol)、[ERC20](https://github.com/Uniswap/v2-core/blob/master/contracts/UniswapV2ERC20.sol)、[Router02](https://github.com/Uniswap/v2-periphery/blob/master/contracts/UniswapV2Router02.sol)、[官方部署表](https://developers.uniswap.org/docs/protocols/v2/deployments)。实际到账、最低 LP 份额、路由返回值与上下文的使用范围已分别写入配置。

RPC 对象与执行语义依据 [Geth overrides](https://geth.ethereum.org/docs/interacting-with-geth/rpc/objects)、[eth_call](https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-eth)、[tracers](https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers)；套餐与时间单位分别查 [Alchemy getLogs](https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-get-logs)、[Ethereum PoS](https://ethereum.org/developers/docs/consensus-mechanisms/pos/)。文档可用不等于用户端点实测。

文献与数学条件核对 [MELT v2 §4.4](https://arxiv.org/html/2602.13480v2)、[伯克利超鞅讲义](https://www.stat.berkeley.edu/~pitman/s205f02/lecture19.pdf)、[哥伦比亚 GBM 讲义](https://www.columbia.edu/~ks20/FE-Notes/4700-07-Notes-GBM.pdf)。覆盖登记涉及的官方页面链接直接保留在账本相应行，其余未核验实例不被当作已证实事实。


### 交付文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| verify_capabilities.py | bc9ea52ec51259d79cfe435d47dc0d846fadd56d866494e7dfcfaf3b92c15d52 |
| baseline-execution-config.md | 72c13ce1ac45865a631b845a097ebf7b08914ce468cd847db991ca65cd4f1d12 |
| right-tail-coverage-ledger.md | b458bc332169366d5749efd12209be723ced08cc0927050dfb4c83a630dcd8e1 |
| offline_verification.json | 7b2cecce4a7faad820e058db4b4449b13df73e1857597c17a3b7f5b59dd61d80 |
| verification_log.json | ebfbb4b1157521967297cfbef32837362bca06f1c1983969617d677aa021698c |

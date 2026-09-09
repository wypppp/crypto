# RT-A 身份归因取数可行性实验 — v4.1

本阶段只回答：在候选出现时，身份与历史活动信息能否及时、可靠地取得。不测收益、不判交易优势、不开户、不入金、不下单，不升级付费套餐。

母体是 Ethereum 主网 Uniswap V2 Factory `0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f` 的 `PairCreated`。当前验收与剩余事项见 [HANDOFF.md](HANDOFF.md)，原始命令输出和修改差异见 `audit_20260907/`。

## 口径

- `creation_tx_sender`：已定位创建交易的外层 `from`，不等于发行者或实控人。身份规则标识 `creation-tx-sender-v1`。
- 两路均确定时先比较创建交易 hash，再比较发送者。冲突不输出确定发送者；单路确定也不证明实控关系。
- `deployment_factory`：Etherscan 返回的 `contractFactory` 原始值；`deploy_kind` 在该字段不可得时可退回启发式，不能替代创建交易证据。
- `creator_prior_deploys`：已确认成功的直接部署正面证据。零条为 `history_truncated`，不能解释成无历史、首次发行或没有恶意历史。历史部署/建池本身不表示恶意。
- 自足历史通道只在建池发送者与创建交易发送者相同且命中更早活动时可为该主体提供正面证据。`sender_prior_pairs` 与 `creator_prior_pairs_in_sample` 的范围不同，后者仅限归因样本内部。
- `earliest_observed_inbound` 以 `l4_subject` 指明查询主体。它是观察到的入账线索，不能直接证明共同控制。
- `creator_is_7702_delegated` 查询候选所在块；非空代码不能自动解释为普通合约。该列仅记录、不参与规则。
- 首次 Mint 的最低流动性锁定单独记录，零地址不作为实际 LP 接收者。

## 执行

```bash
pip install requests eth-utils 'eth-hash[pycryptodome]'
# 在独立临时工作目录运行：selftest 会建立自己的 rt_a_selftest。
cd "$(mktemp -d)"
python /absolute/path/rightTail/rt_a_attribution.py selftest
python /absolute/path/rightTail/covcheck.py
python /absolute/path/rightTail/audit_integration.py --out "$(mktemp -d)"
```

`covcheck.py` 输出实际导入的源码路径；指定行缺失、未覆盖或普通锚点歧义时返回非零。行覆盖不证明分支输出正确，必须结合进程退出码和产物断言。

生产脚本读取环境变量，不自动加载 `.env`。现有 `.env` 的命名标签格式可由 `audit_live_reconcile.py` 读取；辅助脚本只允许显式指定的小区间，不输出密钥、不请求归因接口，并保存公开请求/响应证据。

```bash
export RTA_RPC_ETH='现有 Ethereum RPC URL'
export ETHERSCAN_API_KEY='现有 key'
export RTA_CHAIN=ethereum
export RTA_PAIR_LOGS=etherscan
export RTA_OUT='/独立输出目录'
export RTA_FROM_BLOCK='已确定的小区间起点'
export RTA_TO_BLOCK='已确定的小区间终点'
python rt_a_attribution.py reconcile
```

`reconcile` 强制历史回看为 0，只抓候选区间日志、查询边界 `allPairsLength`；显式 Etherscan 来源时不运行 L2b 的历史二分探测。它不归因、不生成覆盖率报告，返回 0 表示对账通过、1 表示不通过。保留 `collection_<batch>.json`、冻结规格和数据库完整性记录。该入口不代表正式回填窗口已冻结。

小区间通过后，使用真正冻结的正式候选起止块和历史回看范围，建立独立输出目录再执行 `backfill`。**缩小候选窗口不会缩小默认 2,500,000 块历史回看**。

```bash
# 以下变量必须按正式冻结规格填写，不能照抄 mock 的 1000–1200。
export RTA_FROM_BLOCK='正式起点'
export RTA_TO_BLOCK='正式终点'
export RTA_LOOKBACK='正式历史回看块数'
export RTA_OUT='/正式窗口独立输出目录'
python rt_a_attribution.py backfill
python rt_a_attribution.py report
# 正式回填验收后才能开始前向只读观察
python rt_a_attribution.py forward --minutes 120
python rt_a_attribution.py report
```

正式窗口现已选定为 `[25800000,25900000]`，历史回看2,500,000块，显式Etherscan，最多抽样400个PairCreated。启动记录及冻结规格位于 `formal_B_25800000_25900000_v5/`；执行状态见 HANDOFF。`rt_a_selftest/spec_frozen_*.json` 是 mock 数据，不能当作正式配置。`probe` 给出的范围也只是建议，不能自动视为用户冻结窗口。

## 来源选择与实际请求范围

| 配置 | 默认 | 含义 |
|---|---|---|
| `RTA_PAIR_LOGS` | auto | auto / rpc / etherscan |
| `RTA_MIN_BULK_SPAN` | 500 | auto 对 RPC 的固定批量跨度标准，不随 chunk 降低 |
| `RTA_LOG_CHUNK` | 2000 | RPC 分块大小；与来源选择标准分开 |
| `RTA_PAIR_LOGS_PAGE` | 1000 | Etherscan 满页时递归切分，单块仍满页则留缺口 |
| `RTA_FROM_BLOCK` / `RTA_TO_BLOCK` | 0 | 必须显式配置候选区间 |
| `RTA_LOOKBACK` | 2500000 | backfill 历史回看、L2b 二分范围 |
| `RTA_FWD_LOOKBACK` | 同 LOOKBACK | forward L2b 回看范围 |
| `RTA_MAX` | 400 | 候选最多归因数；超限使用冻结随机种子抽样 |
| `RTA_HIST_SENDERS` | 3000 | 每次历史建池发送者补抓上限 |
| `RTA_DEADLINE` | 300 | 前向决策截止秒数 |
| `RTA_RECEIPT_CAP` | 40 | L2b 回执退化扫描上限 |
| `RTA_L3_SCAN` | 20000 | L3 Mint 扫描块数；前向不超过观察链头 |
| `RTA_SCAN_QPS` / `RTA_RPC_QPS` | 3 / 8 | 现有请求节奏，不意味着套餐保证 |

PairCreated 历史请求范围是 `[max(1, from-lookback), from-1]`，候选范围是 `[from,to]`。完整归因还会调用候选时间戳、L2b 创建定位、Mint、交易回执、7702 状态；外部部署历史从块 0 查至候选前一块，L4 从块 0 查至候选块。这些范围不能用候选窗口大小替代。

用户曾测得其 RPC 的日志跨度仅 10。auto 在有 Etherscan key 时会选择 Etherscan，测试核验完整 backfill 首次 fetch。显式 `RTA_PAIR_LOGS=etherscan` 可避免依赖 auto。来源与分页策略进入规格 hash，但更换来源不改变身份字段含义，不应因此修改 `attribution_rule`。Etherscan 授权/限流错误留缺口，不盲目递归放大请求。

## 完整性与报告验收

每次采集使用独立 UUID 批次；规格 hash 不是批次 ID。`collection_runs` 保存批次范围、状态和规格，`batch_integrity` 保存分区对账，归因行带 `batch`。`run_integrity` 保留兼容诊断汇总，**不是报告的放行依据**。

对每个区间 `[a,b]`：

```
预期事件数 = allPairsLength(b) - allPairsLength(a-1)
```

去重条数、池序号连续性、首尾边界、日志形状/Factory/topic/范围和缺口状态都要成立。预期 0 且日志 0 正确通过。backfill 历史与候选分别核验；完整性失败仍保留日志与诊断归因，但返回 1，自动输出 `.INCOMPLETE.md` 并移除旧正式报告。零归因失败也必须如此处理。

`report` 检查每条归因对应的批次及规格，并纳入最新失败/空批次；前向累计观察包含所有批次的完整性。缺批次、未完成、混合规格均不得输出正常结论。无证据的旧库只能产生诊断报告。报告解释字段使用采集时保存的规格；当前进程设置不改写采集时规格。N 是实际归因样本数，未必是整个候选母体，完整日志不意味着所有候选都被归因。

`log_gaps` 主键包含 chain / factory / role / batch / 起止块。旧表会重建主键，未知归属旧记录保留为 unknown/legacy，不自动猜测归属。前向只补本次批次且位于本次起点至已观察链头范围内的缺口，补回日志必须通过对账；不会改写历史归因或历史样本角色。前向每个新区间也对账，静默少日志同样留缺口。

历史/候选缺口通过再次运行同一冻结窗口的 backfill 恢复，只有已核验覆盖的区间才销账。其他批次的前向遗留缺口不自动归入新观察；相应旧观察仍不完整，需另行设计显式恢复，不能拿新批次结果覆盖失败事实。不同链/范围应使用独立库；已有前向归因的库禁止重跑 backfill 改角色。

## 人工审计判据

查看 `audit_sample.csv` 的创建交易和两路证据：判断 `creation_tx_sender` 是否等于**已确认创建交易的外层 from**。不要凭地址是 router、工厂或热钱包就判“错误”；如果它确为该交易外层发送者，字段可正确，但不能推出其为发行者。浏览器地址标签不能替代交易/回执证据。

工厂部署应额外确认目标合约确由该交易内部创建；证据不足填“无法判断”。`creator_status=conflict` 检查两路交易冲突来源，不先选一方。L4 单独判断实际入账证据与查询主体，公共服务来源不能证明共同控制。

报告【2】仅描述规则必需字段的联合可用比例。`history_truncated`、`api_failure`、`ambiguous`、`conflict`、`timeout` 不能合并成“没有”。前向截止按必需字段各自返回时间判断；历史回填不能证明候选当时及时可得。

## 既有真实记录的证据边界

交接记录中的三个工厂部署正对照显示：`txlistinternal(address=EOA)` 找不到 create，按 txhash 能命中。该记录由用户提供，本轮无其原始响应，不声称独立复核。旧 README 的 29/29、22/22 等观察也不构成所有创建交易的普遍保证。

小区间 25919774–25921774 曾由用户测得 34 条日志、池序号 521010..521043；本轮独立复核结果及公开响应保存在验收目录，详见 HANDOFF。除此之外不扩大真实验收范围。

正式窗口新增实测兼容：Etherscan偶尔把零日志索引编码为`0x`。已用匹配交易的RPC回执核实为`0x0`，仅在Etherscan来源规范化索引字段，原始响应保留，其他非法值仍拒绝。`logs_normalization`进入规格hash。L3日志跟随显式Etherscan来源；HTTP 4xx除429不重试，429与5xx保留现有重试策略。

最新实测：正式400样本回填已通过，联合可用329/400（82.25%），前向结果单独记录于 [FORMAL_RESULTS.md](FORMAL_RESULTS.md)。恢复运行的内存上限、资源采样、实时/缓存请求区分与退出码见run_formal.py及各运行目录execution.json。

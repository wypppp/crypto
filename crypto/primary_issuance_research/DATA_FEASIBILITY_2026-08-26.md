# 一级发行与 Pump entity 数据可得性记录

> 检查时间：2026-08-26；本文件记录协议冻结后的工程事实，不修改实验口径。

## 1. MetaDAO 母体不是官网的 21 个 complete

官方文档/仓库列出的 launchpad 程序与 Solana 主网只读 `getProgramAccounts` 初查如下。账户用 Anchor `Launch` discriminator `903333a3ce55d526`（base58 `R7vQE78exjo`）过滤：

| 版本 | 程序地址 | 当前 Launch 账户 |
|---|---|---:|
| delayed-twap-v0.4.1 | `AfJJJ5UqxhBKoE3grkKAZZsoXDE9kncbMKvqSHGsCNrE` | 6 |
| v0.5.0 | `mooNhciQJi1LqHDmse2JPic2NqG2PXCanbE3ZYzP3qA` | 7 |
| v0.6.x | `MooNyh4CBUYEKyXVnjGYQ8mEiJDpGvJMdvrZx1iGeHV` | 41 |
| v0.7.0 | `moontUzsdepotRGe5xsfip7vLPTJnVuafqdUWexVnPM` | 143 |
| v0.8.0 | `moonDJUoHteKkGATejA5bdJVwJ6V6Dg74gyqyJTx73n` | 0 |

合计 197 个当前未关闭的 `Launch` 账户。正式采集器以官方仓库 commit
`6c373b35e34ec1a0dc6d55de67f0870d095ad987` 的五代 IDL 解码，197/197 成功，状态为：

| 状态 | 数量 |
|---|---:|
| Complete | 65 |
| Refunding | 102 |
| Live | 14 |
| Initialized | 11 |
| Closed | 5 |

全部账户的 quote mint 均为主网 USDC。65 个 `Complete` 中，按各版本的
`finalRaiseAmount` / `totalApprovedAmount` / `totalCommittedAmount` 机械取已接受额，22 个不少于
10,000 USDC，43 个低于 10,000 USDC。大量 0.5、1、10 USDC 的 complete 说明链上状态会混有测试、
垃圾及经济上不可部署的发行，不能把 197 或 65 直接当投资机会分母。另一方面，“22 个至少 1 万
美元”与官网约 21 个 complete 接近，说明官网很可能是在做经济/编辑筛选；它仍不是可直接使用的
完整母体，因为筛选规则和失败项没有公开固定。

当前账户开始时间中可解析部分覆盖 2025-04-02 至 2026-08-20。五个 `Closed` 均在约 14 秒内关闭、
接受额为零，明显是部署测试；历史上已经释放租金并关闭的其他账户仍可能被当前状态查询漏掉。

下一步按事前机械规则区分：

- initialized but never started；
- started and publicly fundable；
- failed/refunding；
- completed；
- liquidated/closed；
- test/spam。

若账户已关闭，当前 `getProgramAccounts` 会漏掉历史 launch，仍需用初始化事件或历史签名补回并与官网核对。

已生成的审计产物：

- `data/metadao_current_launch_accounts.json`：SHA-256
  `7a0f90423e80c4ff7308c469f13c02ca5d3d5de11053f023f81fcdba13f55853`；
- `data/metadao_current_launch_accounts.csv`：SHA-256
  `679833b3e3dda45a80c5bd844118272e280f423c41dcb7fa5ad5bf20fbfaa871`；
- `data/metadao_current_launch_audit.json`：SHA-256
  `03499414ad351bbbd79484d272931955d537564f1799045089c69388e474219a`。

## 2. CCA 可从官方 append-only registry 枚举

Uniswap 官方 SDK 当前保留四类历史/当前 auction factory：

- v1 TWA；
- v2 early test；
- v2 legacy；
- 2026-07-09 current factory。

官方 SDK 同时列出 Ethereum、Unichain、Base、Arbitrum、Avalanche、XLayer、Robinhood 及测试网部署。实验只保留主网，但历史 factory 不能删除。链上事件与 auction state 足以构造成功、失败和未迁移分母。

## 3. MELT E0 数据

官方仓库已确认：

- `feature.pkl` 包含预生成 122 特征；
- `group2_*` 是地址级持仓集中度；
- `group4_*` 是 bundle/entity 聚类后的持仓、用户数、集中度及相对 group2 的 delta；
- 标签 CSV 41,470 行和 feature-generation 源码可直接取得；
- 原始交易大于 1 TB，不适合作为 E0 起点。

2026-08-26 直接下载作者 Google Drive 的 `feature.pkl` 返回 quota exceeded，随后找到 Hugging Face
的 `Zinteck/MELT` parquet 镜像。字段、行数、时间范围与官方说明一致：41,470 行、无重复 mint、
6 个 group1、59 个 group2、22 个 group3、35 个 group4 特征；时间为 2024-12-09 至 2025-02-28。

镜像哈希：

- `melt_feat.parquet`：`7acdc3ed98cc70e874d1b76b1abeb8142bcc1ab435601dc800311148daed3a6b`；
- `melt_label.parquet`：`9fcf8aff60d2102b70a612521303a16a54e9a017ab57d2ce9134ea0ee704d13f`。

E0 已执行，详见 `../pump_tail_research/output/melt_entity_ablation.md`。按官方有效样本过滤后
21,635 行；非线性模型中加入 group4 后，AUPRC 增加 0.0293、top-10% precision 增加 3.69 个
百分点，按日 block bootstrap 95% 区间分别为 `[+0.0174,+0.0418]` 与 `[+0.39pp,+5.98pp]`。
三个测试时间块的 AUPRC 增量均为正。E0 因此通过“存在独立信息”的门，但目标只是 MELT 风险标签，
没有证明 10x 或净交易收益。

## 4. 当前凭据

`DUNE_API_KEY` 没有导出到当前 shell，但现有 runner 能从本地忽略的 `.env` 读取，未输出密钥。
2026 entity E1 的 schema probe 已写好；本轮两次外部执行均被权限审批超时中止，尚未形成 Dune 结果。
这不是数据表不存在的证据。

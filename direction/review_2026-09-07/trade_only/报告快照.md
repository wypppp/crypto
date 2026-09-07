# TRADE_ONLY 42 条补证 · 2026-09-07

**42 条已逐项建立证据记录：38 条有旧代号关联，ACE 为确定的公告漏检，BDOT / WBETH 为质押凭证，NBT 仍有交易场所疑点。此次补证没有把任何待定项直接排除，也没有产生收益结论。**

这是对 v1.8.36 联合表的证据补充，使用当前 v1.8.37 配置作基线校验；正式联合表仍为 746 行、1,134 条来源记录，公告匹配测量子集仍为 261 条。所有输入版本与哈希由 [baseline_manifest.json](review_2026-09-07/trade_only/baseline_manifest.json) 固定。

## 会改变后续工作的发现

**ACE：不是没有首发公告，而是已有公告未被解析。** 本地 185740 明确给出 2023-12-18 06:00 UTC 及 ACE/BTC、ACE/USDT、ACE/BNB、ACE/FDUSD、ACE/TRY。它使用 `tentatively set to list`，当前 C1 起始模板只接受 `will then list`，因此整篇落入 OTHER。五个交易对的归档最早日均为同日。[币安原公告](https://www.binance.com/en/support/announcement/detail/2cb7b8a617b548e5b765bcb0f3beb680)

隔离运行只给 C1 增加该措辞分支，并从原文预先写入 ACE 的记录预期。实测退出 0，来源记录 1,134 → 1,135：仅新增 ACE，删除 0；原 1,134 条完整记录逐项不变，包括原时间、generator 与 announced_pairs。新记录保留全部五个交易对。初次运行时我把新增回归样本误写为对象，而现有接口要求三元组；fail-closed 正确拒绝，修正测试输入结构后通过，原失败日志保留。这不是发现了另一个生产解析错误。

实验配置、产物及 [impact.json](review_2026-09-07/trade_only/ace_impact/impact.json) 均单独存放。**尚未发布为正式版本，也未运行新增 ACE 的精确 T0。** 正式化须重跑裁定、时间链、联合表，生成新的取数清单。原 37 条核验样本和已经归档的 205 条完整测量结果不能因此改写。

**PDA：此前“完全无提及”仅表示本地已抓目录无提及。** 官方公告明确 PLA → PDA，换币比例 1:1，并计划于 2024-03-01 08:00 UTC 开放 PDA/BTC 与 PDA/USDT。这是可引用的身份关联，不能继续把 PDA 描述为全网没有公告。类似换币信息需要跨公告目录补证。[币安 PLA→PDA 公告](https://www.binance.com/en-AU/support/announcement/detail/f0fafa66fedf4e058aaacb57c206c597)

**NBT：找到了上市身份，但尚不能确认本地归档的交易场所。** Tokocrypto 官方公告将其标为 NanoByte，列出 NBT/BIDR、NBT/USDT 于 2022-03-11 13:00 UTC+7 开盘。两对与日期均与本地一致，本地 pair 来源为 fallback。此吻合是场所核查线索，不能据此认定 Binance Global 已上市，也不能反向证明 Binance 从未上市或归档已经污染。[Tokocrypto 上市公告](https://support.tokocrypto.com/hc/en-us/articles/4693749255309-NBT-is-going-to-be-Listed-on-Tokocrypto)、[官方上市活动确认](https://support.tokocrypto.com/hc/en-us/articles/4722887851405-Join-TKO-x-NBT-Trading-Competition-to-win-more-than-IDR-1-Billion)

## 身份证据与研究资格分开

38 条旧代号关联是有一手来源的关系，尚不是完成了经济资产合并的白名单。比例、合约、执行时点及多对一合并仍需逐事件记录；例如 NU + KEEP → T 不是简单改名，旧 LUNA → LUNC 不等于新 LUNA，FXS → FRAX 不能与历史同名稳定币按字符串合并。某些来源是计划公告，不能统一宣称换币完成或精确首开时间已验收。

对首次经济资产上市与 U_trade 收益统计必须分别裁定。即便旧资产延续不应新增一次经济资产首发，也不能据此从 U_trade 中删行。收益口径本来允许 TRADE_ONLY 参与，当前证据层只补充事实，42 条正式资格仍保留 PENDING。BDOT / WBETH 的质押凭证身份不自动决定其研究资格，也不替代 SAME_DAY_OPEN_ONLY 的最终裁定。

来源使用边界：D / GFT / POL 引用币安官方认证公告账号，非 Square 普通用户观点；REI 引用官方中文公告频道；NOM 引用回顾性 Academy 资料；OOKI 的入口停用通知只在此证明 BZRX→OOKI 关联。这些网页按 2026-09-07 检索现状用于身份审计，未证明历史时点可见版本，不能作为策略当时可用的交易信号。

## 逐项证据

下表的日期是既有 T0_day 元数据，不是本轮重新测出的精确 T0。留出资产仅补充身份元数据，本轮补证新增行情下载为零。

| 资产 | 既有 T0_day | 隔离标记 | 证据类别 | 关联 / 来源 |
|---|---|---|---|---|
| A | 2025-05-28 | EMBARGOED | 旧代号关联 | [EOS → A](https://www.binance.com/en-AE/support/announcement/detail/f5a19fab8c5d4078a1235a17f542dfc5) |
| A2Z | 2025-07-30 | EMBARGOED | 旧代号关联 | [LOKA → A2Z](https://www.binance.com/en/support/announcement/detail/8584e37a223f44559a2c90785d5dc839) |
| ACE | 2023-12-18 | FETCHABLE | 首发公告漏检 | [原始公告](https://www.binance.com/en/support/announcement/detail/2cb7b8a617b548e5b765bcb0f3beb680) |
| AWE | 2025-05-21 | EMBARGOED | 旧代号关联 | [STPT → AWE](https://www.binance.com/en/support/announcement/detail/ad0f6c6b7d6640eea285538c96e2cd42) |
| BDOT | 2022-01-28 | FETCHABLE | 质押凭证 | [原始公告](https://www.binance.com/en/support/announcement/detail/c2e9a43244424e26a4f086ba798660d9) |
| BEAMX | 2023-11-14 | FETCHABLE | 旧代号关联 | [MC → BEAMX](https://www.binance.com/en/support/announcement/detail/c8705b752c7c47fc814a373a0f1856ee) |
| BTTC | 2022-01-25 | FETCHABLE | 旧代号关联 | [BTT → BTTC](https://www.binance.com/en/support/announcement/detail/2722e6da4f5141dd9b2fb07b5b1f3f75) |
| COMBO | 2023-06-02 | FETCHABLE | 旧代号关联 | [COCOS → COMBO](https://www.binance.com/en/support/announcement/detail/45852dc155b641bc9e1c23bc41d8ded6) |
| D | 2025-01-09 | FETCHABLE | 旧代号关联 | [DAR → D](https://www.binance.com/en/square/post/17759237581553) |
| EPIC | 2025-03-13 | FETCHABLE | 旧代号关联 | [ERN → EPIC](https://www.binance.com/en/support/announcement/detail/53d4f5fd4d9a49ec917d712b1d1fb58e) |
| EPX | 2022-05-23 | EMBARGOED | 旧代号关联 | [EPS → EPX](https://www.binance.com/en/support/announcement/detail/4e21b7d402a840928c652e1f74812547) |
| FORM | 2025-03-19 | FETCHABLE | 旧代号关联 | [BNX → FORM](https://www.binance.com/en/support/announcement/detail/7d5accdcf8f446f3ba3d79f8747a28e2) |
| FRAX | 2026-01-15 | FETCHABLE | 旧代号关联 | [FXS → FRAX](https://www.binance.com/fr/support/announcement/detail/a17352ba70414c96882cd881591dd36d) |
| G | 2024-07-19 | FETCHABLE | 旧代号关联 | [GAL → G](https://www.binance.com/en-BH/support/announcement/detail/6df074e0264648448c260b1430240e2f) |
| GFT | 2023-02-08 | FETCHABLE | 旧代号关联 | [GTO → GFT](https://www.binance.com/en/square/post/204800) |
| GRAM | 2026-07-02 | FETCHABLE | 旧代号关联 | [TON → GRAM](https://www.binance.com/en/support/announcement/detail/8177254072cf4da3b9d8fcaacceb0a2c) |
| HEI | 2025-02-13 | FETCHABLE | 旧代号关联 | [LIT → HEI](https://www.binance.com/az-AZ/support/announcement/detail/f65ece87c4a7406eba416b9b1f514cec) |
| HIFI | 2023-01-12 | EMBARGOED | 旧代号关联 | [MFT → HIFI](https://www.binance.com/en/support/announcement/detail/0e5b302a17014b7aa0af476731588e8b) |
| KAIA | 2024-10-31 | FETCHABLE | 旧代号关联 | [KLAY → KAIA](https://www.binance.com/en/support/announcement/detail/f75f933759ee49d0af1dfbce7e32144c) |
| LEVER | 2022-07-13 | EMBARGOED | 旧代号关联 | [RAMP → LEVER](https://www.binance.com/zh-TC/support/announcement/detail/38c31026a58d465086b015a89b06c19b) |
| LUMIA | 2024-10-18 | FETCHABLE | 旧代号关联 | [ORN → LUMIA](https://www.binance.com/en/support/announcement/detail/066ba1773ce4480492b983f8d4764c91) |
| LUNC | 2022-05-30 | FETCHABLE | 旧代号关联 | [LUNA(old) → LUNC](https://www.binance.com/en/support/announcement/detail/c52fa3c686be4b2b9d5df50de15847ec) |
| MANTRA | 2026-03-04 | FETCHABLE | 旧代号关联 | [OM → MANTRA](https://www.binance.com/en-TR/support/announcement/detail/a65e70f8431a40e8b5ce809bbb61ed59) |
| MULTI | 2022-04-06 | FETCHABLE | 旧代号关联 | [ANY → MULTI](https://www.binance.com/en/support/announcement/detail/cd39354caeee4361badf9a57e92cd5da) |
| NBT | 2022-03-11 | FETCHABLE | 交易场所待核 | [原始公告](https://support.tokocrypto.com/hc/en-us/articles/4693749255309-NBT-is-going-to-be-Listed-on-Tokocrypto) |
| NOM | 2025-10-01 | FETCHABLE | 旧代号关联 | [OMNI → NOM](https://www.binance.com/en/academy/articles/what-is-the-omni-network) |
| OOKI | 2021-12-24 | EMBARGOED | 旧代号关联 | [BZRX → OOKI](https://www.binance.com/en/support/announcement/detail/57f017dd5d474f06bc82d029bc412cba) |
| PDA | 2024-03-01 | FETCHABLE | 旧代号关联 | [PLA → PDA](https://www.binance.com/en-AU/support/announcement/detail/f0fafa66fedf4e058aaacb57c206c597) |
| POL | 2024-09-13 | FETCHABLE | 旧代号关联 | [MATIC → POL](https://www.binance.com/en-NG/square/post/12771540527345) |
| POLYX | 2022-10-17 | FETCHABLE | 旧代号关联 | [POLY → POLYX](https://www.binance.com/en/support/announcement/detail/9f6c57e9fa924eeab275f410332df567) |
| REI | 2022-05-04 | FETCHABLE | 旧代号关联 | [GXS → REI](https://t.me/s/binance_cn?before=3779) |
| RENDER | 2024-07-26 | FETCHABLE | 旧代号关联 | [RNDR → RENDER](https://www.binance.com/en-IN/support/announcement/detail/7aa2bb48ab194bb9aebbc3f72b5819ed) |
| S | 2025-01-16 | FETCHABLE | 旧代号关联 | [FTM → S](https://www.binance.com/en-IN/support/announcement/detail/aec6fcbc84b749eeab6690e6bcac2f3d) |
| SLF | 2024-08-30 | FETCHABLE | 旧代号关联 | [FRONT → SLF](https://www.binance.com/pt-BR/support/announcement/detail/65f69bc68ca64182b6df3d958f14f38e?hl=pt-BR) |
| SSV | 2021-10-22 | FETCHABLE | 旧代号关联 | [CDT → SSV](https://www.binance.com/en/support/announcement/detail/96e8866829784919a739c1855d21ef76) |
| T | 2022-02-25 | EMBARGOED | 旧代号关联 | [NU+KEEP → T](https://www.binance.com/es/support/announcement/detail/249dfc101d104246b892d0604a623314) |
| USDP | 2021-09-10 | EMBARGOED | 旧代号关联 | [PAX → USDP](https://www.binance.com/en/support/announcement/detail/627ea984daa44ee4a5ac27fe658cc180) |
| USTC | 2022-05-30 | FETCHABLE | 旧代号关联 | [UST → USTC](https://www.binance.com/en/support/announcement/detail/c52fa3c686be4b2b9d5df50de15847ec) |
| VANRY | 2023-12-01 | EMBARGOED | 旧代号关联 | [TVK → VANRY](https://www.binance.com/en/support/announcement/detail/4701f3d28a244d1f824aa05f009ddc40) |
| VIC | 2023-11-24 | FETCHABLE | 旧代号关联 | [TOMO → VIC](https://www.binance.com/en/support/announcement/detail/0491a610ab2d4ab3af6d15dce961c5ae) |
| WBETH | 2023-05-12 | EMBARGOED | 质押凭证 | [原始公告](https://www.binance.com/en/support/announcement/detail/c968644475a74284a292ecd3af39e6ff) |
| XNO | 2022-01-28 | FETCHABLE | 旧代号关联 | [NANO → XNO](https://www.binance.com/en-TR/support/announcement/detail/3dc8f6de281f4781a246a1658a21cb80) |

机器可读记录见 [JSON](review_2026-09-07/trade_only/qualification_evidence.json) / [CSV](review_2026-09-07/trade_only/qualification_evidence.csv)，每条保留来源、原归因、交易对元数据、留出标记和未完成要求。来源标题另存于 source_observations.json；这是引用与观察记录，不是网页历史快照。

## 复现与剩余工作

`build_evidence.py` 只读固定输入，校验输入和来源表哈希、42 条身份覆盖、38+1+2+1 互斥分区以及逐资产留出规则；不读取行情、不改变资格。已实测相同输入重建 JSON/CSV 逐字节相同；ACE 隔离脚本重放的实验配置与母表也逐字节相同。这类检查验证证据表的结构与可复现性，**不替代对外部来源语义的人工核验**。

下一项具体实现是将 ACE 修复正式版本化并重跑至联合表；与之独立的是为 38 条关联建立事件级身份记录，为 BDOT/WBETH 明确资格规则，并查清 NBT 的交易场所。已有 NOT 的归档缺口、archive_coverage_caveat、其余 OTHER 的召回风险仍保留。本轮没有计算价格代理、上市频率或收益。

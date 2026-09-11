# RT-A 交接与独立验收

当前：A/B/C已关闭，正式回填已验收（400样本，联合可用329/400）；30分钟前向只读观察及结束后链上复核均已验收（2个事件，必需信息30.0/31.1秒内取得）。最新结果见 [FORMAL_RESULTS.md](FORMAL_RESULTS.md)，下文按时间保留交接和修复历史。

## 目标与边界

只验证候选出现时身份与历史活动能否及时可靠取得。母体：Ethereum 主网 Uniswap V2 Factory 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f 的 PairCreated。不测收益、不判交易优势、不开户、不入金、不下单；只用现有数据源与额度，不升级套餐。
creation_tx_sender 是创建交易外层 from，不等于发行者或实控人；历史部署/建池不代表恶意。creator_prior_deploys 仅提供直接部署正面证据，零条未知。

## 接手时记录（后续核验见下文）

用户与前任确认旧基线 selftest 67/0、covcheck 35/35；补充版本声称 79/0、46/46。覆盖指定行不等于正确性证明，存在多匹配锚点。
已交接修复：两路 hash 冲突禁确定发送者；排除失败创建；自足通道主体一致；最低流动性与 LP 接收者区分；7702 查候选块；持久化缺口；身份规则与日志来源分记。
用户提供的真实记录（无原始响应，本轮未独立复核）：三个工厂部署正对照按 EOA 查 internal 无 create、按 txhash 命中；25919774–25921774 日志34条，allPairsLength差34，序号521010..521043连续且边界一致。

## 三个待验收集成问题

A：auto 标准被 chunk 下调污染。补充版用 min_bulk_log_span=500；需核验完整 backfill 首次 fetch。
B：对账失败仍出正式报告。补充版有 run_integrity、历史/候选分对账、INCOMPLETE 与 reconcile 入口；需核验批次绑定、进程退出及空产物。
C：forward 补历史缺口污染样本。补充版有 chain/factory/role/batch；需核验批次、观察上下界、旧表迁移、历史恢复及对账后销账。

## 执行约束

所有测试独立临时目录，不覆盖原数据。接手源码快照 /tmp/rta-audit-baseline；最终保存差异及命令/退出码。无项目 AGENTS.md 被发现。不得猜测正式窗口；离线验收后先小区间对账，再按真实冻结正式窗口回填，再前向只读观察。

## 接手时状态

独立审计进行中；三个问题暂未验收关闭。正式窗口配置尚未核实。

## 2026-09-07 本轮最终实测更新

**A/B/C 在本轮离线验收覆盖范围内关闭；真实小区间对账通过。正式回填及前向观察未开始，缺少真实冻结窗口。**

接手基线独立复跑为 79/0、46/46，与补充交接一致；源码仍标 v2/v3.1、README 多处沿用旧口径。现统一实现版本 v4.1，身份规则仍为 creation-tx-sender-v1。未把改采集方式等同于改身份规则。

### A：auto 来源选择 — 关闭

补充版已经修复，完整 backfill 实测首次 fetch 为 etherscan（RPC 上限10，配置chunk2000，固定批量标准500）。本轮保留该修复；未声称当前基线仍能复现已修复的“先降标准再选RPC”。仍可显式 RTA_PAIR_LOGS=etherscan。

### B：完整性约束执行及产物 — 关闭

新增反例证实：失败 backfill 返回 None→CLI 0；零归因失败跳过 report，残留旧正式报告；其他规格通过记录可错误放行 foreign 归因；reconcile 记录混入 backfill。已修复：独立 UUID batch，collection_runs/batch_integrity 与归因绑定；保留 run_integrity 仅作兼容诊断；历史/候选分别核验。失败 backfill 返回1、自动生成 INCOMPLETE 并删除旧正式文件，零归因同样处理。reconcile 独立模式、历史0、不执行归因能力二分、不出覆盖率报告。

12场景进程级验收含 CLI真实退出1与产物、无日志真空区间通过、无日志缺失区间失败、跨批次拒绝、同窗口历史恢复后正式报告恢复。对账保存边界计数和池序号；原始采集日志持久化到 collection_<batch></batch>.json。接口失败不再盲目递归切分放大调用。

### C：前向缺口与历史角色 — 关闭

补充版已挡住历史role，但仍取其他批次、超过链头的缺口：mock链头1403却fetch1404..1406。旧表仅加列未迁移主键，同区间跨role覆盖。现缺口主键包含chain/factory/role/batch/区间；迁移保留未知旧归属。forward只补本批、起点以上且链头以下区间，不替换已有候选/归因。新区间也对账，静默少日志留缺口，重试全区间通过才销账。历史缺口由同冻结窗口backfill恢复，核验覆盖后才销账。

原自测要求“高于链头也补回”的断言已纠正，并另加真实本批范围内静默截断→补齐→销账的正向验收。独立测试逐列确认历史归因不变，历史角色仍0。跨进程前向遗留缺口不会自动被新批次接管，旧观察仍不完整。

### 最终验证与证据

- selftest：81通过/0失败，退出0。
- covcheck：46/46，退出0，无普通锚点歧义，明确导入 /home/ancillary/rightTail/rt_a_attribution.py。覆盖数量未增加；返回码现在可用于检查失败。
- 独立进程验收：12场景全符合预期，整体退出0；其中两条失败入口预期进程退出1。
- py_compile：退出0。
- 完整命令、退出码与断言见 [COMMANDS.md](audit_20260907/COMMANDS.md)。接手/最终SHA256与接手后差异 `source-hashes.json`、`changes.patch`；初始/最终进程产物分别归档。原 rightTail/rt_a_selftest 数据未改写；该目录接手时已有的Git差异保留。

### 真实小区间独立复核 — 通过

使用现有 `.env` 标签格式凭据，辅助入口 audit_live_reconcile.py；未打印密钥。执行范围25919774..25921774（2001块）。4次接口请求：chainId=1；Etherscan PairCreated日志34条；RPC allPairsLength(25919773)=521009，allPairsLength(25921774)=521043。差值34、去重34、序号521010..521043连续且边界一致，缺口0，退出0。

实际历史回看0；无归因/历史部署/Mint/入账请求，未生成覆盖率报告，数据库归因0行。原始公开响应保存在 [requests.json](audit_20260907/live-reconcile/requests.json)，日志和完整性数据库一并保存。此小区间现在有本轮独立证据；用户提供的三个工厂正对照仍无本轮原始响应，不宣称独立复核。

### 本轮修改文件

- rt_a_attribution.py：批次及完整性绑定、失败退出与产物、空母体、前向范围和重试、旧主键迁移、日志校验/采集证据、v4.1与报告文字。
- covcheck.py：对应新代码锚点、精确L2b定位、显示导入路径、未覆盖/歧义返回非零。
- audit_integration.py：独立临时目录进程级验收，明示预期退出及产物。
- audit_live_reconcile.py：现有凭据只读小区间辅助入口，保存公开请求证据、隐去凭据。
- README.md：清理旧发行者判据、来源改动必须改身份规则、工厂口径必然不一致、付费升级等冲突说明；同步实际运行与报告判据。
- HANDOFF.md、audit_20260907：交接、差异与验收证据。

### 当时未关闭项与下一步

1. **唯一阻碍正式推进的配置：真实冻结正式候选起止块及历史回看块数/规格文件。** RPC与Etherscan凭据均已用本次对账确认可用。仅发现 rt_a_selftest/spec_frozen_343cc2cc47503dea.json，1000..1200、lookback900，是mock，不能作为正式窗口。已向用户请求正式规格。
2. 取得正式规格后：独立输出目录→明确打印候选和历史实际范围→正式backfill→完整性/报告/人工样本验收→前向只读观察。默认历史回看250万块不会因缩小候选而缩小；不要猜测正式窗口。
3. 前向跨进程遗留缺口的显式恢复仍是后续能力；当前会保守阻断旧观察正式结论，不自动迁移样本角色。完整性通过不证明归因正确或及时，真实正式归因与前向时效仍未验收。

### 继续推进时的配置复查

已再次检查 rightTail 的隐藏/忽略文件及项目中 RTA_FROM_BLOCK、RTA_TO_BLOCK、candidate_from_block 引用：仍仅发现 mock 冻结规格与本轮小区间 reconcile 规格，没有正式 backfill 冻结窗口。用户的“继续”未给出起止块；按原要求不猜测，正式回填尚未发起。

## 正式窗口已于本轮选定

用户明确此前没有正式窗口，并提出方案B。现采用候选[25800000,25900000]（闭区间100001块），history_lookback=2500000，因此历史区间[23300000,25799999]。显式etherscan，max_candidates=400，hist_sender_cap=3000，随机种子20260906，L3_SCAN=20000。独立输出 formal_B_25800000_25900000；先单独reconcile（历史0），通过后按完整正式规格backfill。冻结时验证chainId=1和head>=25920000，记录实际链头及源码SHA256。
注意当前代码对所有PairCreated候选抽样，包括new_token为空者；N不等于可判定新币数量，400是上限。窗口更宽扩大时间覆盖，不能将14天样本外推为所有以太坊新池。历史回看还影响本地token_had_prior_pair的历史池检索；不改变外部部署历史从块0开始的查询。
两处新修复已核对：HTTP4xx（除429）立即返回；L3按etherscan来源取日志。原selftest的4xx场景替换了整个rpc函数，不能证明真实rpc重试行为；本轮另以假HTTP Session调用真实rpc验证400一次、429三次，均通过。用户提供的真链L3耗时对照仍标注为用户记录。

正式首次对账失败（未进入backfill）：1423条日志中一条Etherscan的logIndex为"0x"。已从独立RPC交易回执核实同事件logIndex="0x0"，证据 formal_B_25800000_25900000/zero-index-proof.json。仅在Etherscan日志来源复制并规范化零索引，不把缺失/其他非法值当零，不修改RPC输入。规范化策略进入SPEC，正式重跑用独立目录 formal_B_25800000_25900000_v2；保留第一次规格与失败产物。

## 整机卡死／重启中断（用户确认）

第三次执行formal_B_25800000_25900000_v3在reconcile通过后、历史日志采集时被环境中断。execution.json最后记录运行47.9秒，HTTP RPC34次/Etherscan35次，接口错误0；无退出码、未开始归因。用户确认整台电脑卡死后重启；WSL新启动，原进程消失。Windows与Linux事发日志曾保存于 incident_20260907/；该目录已于 2026-09-09 经用户决定删除（未再卡死，不再保留）。当前没有证据确定回填程序导致整机故障；先前未采集进程内存峰值，不能排除间接资源压力。正式回填暂停，候选窗口及历史规格不变，不把中断状态当作完成。/tmp文本日志随WSL重启丢失；项目内冻结规格、请求证据和SQLite保留。后续恢复应将运行日志落在项目目录，并加资源采样与进程内存上限。

## 重启后继续（用户已授权）

恢复保持同一候选/历史范围、max400及原请求节奏，不加并发。run_formal.py现设置进程虚拟内存硬上限768MiB、nice=10；每5秒采样RSS/峰值/CPU到resources.jsonl，run.log落项目目录，execution.json最多每5秒更新，避免逐请求频繁替换状态文件。正式入口require_complete=True：历史或候选完整性失败时在归因前退出并保留INCOMPLETE；默认离线诊断行为保留。16个进程验收全部符合预期，含严格模式不执行任何归因。恢复输出目录formal_B_25800000_25900000_v4，不覆盖前三次证据。

## 2026-09-08 继续执行

v4进程已消失且无正常退出记录，最后累计895秒、峰值RSS191MiB，日志/历史完整性已通过，但尚未写候选；记录到4次SSLError，未将失败响应缓存为成功。本次用磁盘缓存流式恢复v4请求证据中的完整JSON行，仅复用同规格成功的固定历史读取；链头、chainId及allPairsLength边界仍真实重查，latest/失败响应不复用。缓存命中单独标记并保留原请求来源，不当作新网络调用，更不作前向时延证据。验证包含未写gzip尾部的重启恢复和失败/动态状态排除。v5使用独立会话后台进程，保持768MiB上限与资源采样；输出formal_B_25800000_25900000_v5。

## 2026-09-09 正式回填验收通过
v5已完整退出0，reconcile/backfill/report均0，耗时4851.5秒。历史64429/64429、候选1423/1423通过，3000条历史发送者均非空；实际400归因与独立预生成随机样本逐池一致，规格hash542bbdecb29787fb，未解决缺口0。联合可用329/400=82.25%，确定创建发送者394/400，LP接收者ok392/400；历史未知71（65条直接部署零证据、6条主体不确定），不解释为无历史。资源峰值226292KiB≈221MiB，未触发768MiB上限；本次实际HTTP RPC14662、Etherscan1595，无最终接口错误。缓存命中单独计数，不能作前向时效。
20行CSV抽样的新鲜链上核验：14行有确定创建发送者，外层from、成功回执、创建块与目标创建证据全匹配（工厂路径额外按txhash查internal）；6行按规则无法确定，未强行给发送者；needs_review=0。证据sample_receipt_audit.json。独立验收结果acceptance.json。此验证不确认发行者、实控人或L4资金家族。
已启动30分钟前向只读观察forward_B_20260909_30m，复制已验收的backfill数据库，核验规格一致；实时请求、无缓存，仍768MiB上限和nice10。前向完成前不据回填82.25%推断及时可用。

## 2026-09-10 前向验收完成
观察25940110..25940258，共149块、148个连续采集区间、2个事件。forward/report退出0；独立verify_forward_run.py退出0，确认2/2在300秒截止内联合可用（30.0秒、31.1秒），缺口0，历史/候选65852行和回填归因400行逐行不变，无缓存。实际HTTP RPC616、Etherscan158，最终错误0，耗时1817.5秒，峰值RSS50208KiB约49MiB。
结束后再次对同一区间作只读链上对账，退出0，4次请求，2/2，计数/序号/边界全部通过；历史回看0、不归因、不出覆盖率报告。证据见forward_B_20260909_30m/acceptance.json及final_reconcile/，命令见formal_verification/final_execution.md。

已关闭：三条集成反例、相关离线回归、真实小区间对账、冻结正式窗口回填及抽样证据复核、本轮30分钟前向观察。此前失败/中断运行独立保留，不拼入正式分母。核心代码本轮未再修改，已有selftest85/0、covcheck46/46与16项独立集成验收结果继续适用。
未关闭：整机卡死原因没有充分证据；本次低内存成功运行不能排除此前程序相关性。跨进程旧前向缺口的显式恢复仍为后续能力，当前保守阻断不完整结论。
下一步：如继续评估总体及时可靠性，需要增加前向样本；当前2例只证明这两个实例及时取得，不足以验收总体覆盖率。外层from不等于发行者/实控人，历史正面证据不等于恶意历史，零证据仍未知。本轮授权执行链已完成，无待运行进程或待补正式产物。

## 2026-09-10：前向证据边界与经济基线分母推进
前向2/2的单侧95%二项精确下界0.223607（双侧下界0.158114），均以固定率和独立抽样等假设为条件；不据此验收总体及时率。各lag为顺序流程中的累计时延，不据接近数值判断固定开销或窄分布。后续300例零超时/约75小时估算、失败与删失口径详见FORMAL_RESULTS.md；本轮不启动该长观察。

经济基线v3保持原字节。边界候选值24136053..24781026、全资产N_all=16510、索引[476626,493136)来自现有端点证据；本次将在独立baseline_work_20260910中真实复核并重建分母。采用现有Etherscan PairCreated序号重建台账，保留计数/连续性/边界核验和注册表抽查；不宣称逐一调用所有allPairs。仅冻结采集口径，不将整套经济实验视为已冻结，不读取候选收益，不启动300样本。运行结论以后续实测验收为准。

## 2026-09-10：经济基线分母已验收
已真实复核24136053..24781026（时间边界和结束复读hash一致），工厂计数476626→493136。事件完整重建16510个索引：WETH16044＋非WETH466＋待识别0。10个分散索引的allPairs/token0/token1/getPair抽查全部一致；不宣称全量逐索引RPC调用。原始HTTP响应独立逐行复算CSV通过。采集与验收均退出0，7项离线测试通过，RPC55/Etherscan47次，50.755秒，峰值采样RSS145224KiB约141.8MiB。
新执行补充、逐项产物和命令见baseline_work_20260910/EXECUTION_ADDENDUM.md；原baseline_20260909 v3包保持不变。collection_frozen.json仅冻结采集，完整经济实验仍baseline_ready=false；未读取收益、未抽300样本。下一步是可执行的钱包/持仓状态适配、成本和失败分类冻结及少量端到端质量验证，再进入正式样本。无需重采本次完整母体，也无需先做75小时前向观察。

## 2026-09-10：经济基线资源计量条件
正式n=300前必须完成真实候选全流程调用量/耗时剖析，并记录分支失败、缓存/重试、共享成本和资源峰值。已从既有DAI端点证据复算：Mint定位59次/84.252秒、买入9次/13.295秒、槽扫描与退出36次/84.313秒；合计104次/181.860秒，机械串行300次约15.155小时，但不是候选预测或上下界。控制池与候选二分范围、状态适配不同；实际买/卖模拟单调用各约1秒。证据baseline_work_20260910/control_cost_profile.json，执行条件RESOURCE_SIZING.md。原8小时是追加主动工作预算，机器时间另计；不默认提高预算或缩样本。真实候选计量仍待完成，本次仅重分析已有记录，无新增网络调用。

## 2026-09-10：最新并行/续跑交付全量审核未通过
审核当前pilot_measure.py/evidence.py、规格v1.4、全部7个测试入口及既有v2..v7证据；未修改实现、未新增真链请求。原测试5个入口退出0；e2e_blocking与resume因Namespace缺parallel退出1。审计仅补parallel=1后两者41/0、23/0，但不冒充当前原入口172项全绿。
独立反例确认：并行预算/worker异常可产生exit0且n=0假成功；blk闭包使用外层RPC，worker区块请求缺候选归属、计数遗漏；HTTP重试/Etherscan不全过全局闸门；改slot_limit仍恢复旧结果；checkpoint截断追加丢完成记录、完整结果提交与checkpoint非原子、续跑不重建累计结果；正确无Mint分支无法标完成；缺rpc_end证据仍complete；成本部分已知信息丢失；畸形Mint仍被接受；最终结果JSON错误路径未脱敏。当前不可启动真链并行对照或正式300样本。
进展保留：首次性前后供给、递归右区间、fresh复读、身份闭环、stage20归未知、stage12授权区间和economic_eligible=false已落地；v3包校验0，历史规格完整hash可匹配。完整报告与13条离线审计观测、源码hash/快照、命令/退出码见baseline_work_20260910/audit_full_20260910/REVIEW.md。下一步先修上述阻断并统一测试入口，再交付审核；经济资格仍需独立持仓状态依据，不因工程清单全勾自动放开。

## 2026-09-10：200 项修复后复核仍未通过
本次独立顺序复跑8个原入口全部exit0，29+17+27+18+41+23+20+25=200项断言成立；未修改实现、未新增真实请求。线程失败阻断、worker RPC显式传入、汇总计数、参数/原语hash绑定、结果先持久化、脱敏等修复有效。
仍复现：旧结果与证据丢失后续跑exit0且results=[]/set_complete=true；检查点中段损坏静默接受；并行max_calls=2仍发生3次模拟RPC；原RPC的503重试未遵守共享HTTP间隔；买入后槽位查询异常遗漏已知成本；空文件/孤立rpc_end仍判证据complete；重复候选index被判集合完整；Mint元数据校验不全。详细范围、源码快照/hash、命令与退出码见baseline_work_20260910/audit_followup_20260910/REVIEW.md。下一步先修恢复交付与全局预算，再补其余验收；真链并行和正式300样本仍未放行，economic_results_eligible保持false。

## 2026-09-10：第二轮审查九项反例已修复，交付复核（规格 v1.5）
先在修复前源码上逐条复现审查方两个反例脚本，8条观测与retry限流反例结果与其remaining.log/retry.log完全一致，源码hash与其source_hashes.json逐字节相同。
两个P0已闭合：①检查点标"完成"时把结果本体连同sha256一并持久化，续跑逐条校验后并入累计交付，校验不过者不跳过而重新测量，引用的证据缺失或不完整则验收不通过；中段损坏SystemExit阻断，尾部半行仍按中断隔离放行。②闸门在第一个请求之前建立并覆盖启动/串行/并行/Etherscan，且下移到真实HTTP边界（包住urlopen），V.RPC内部的503重试同样排队同样计数；max_calls对逻辑请求数与实际HTTP次数同时封顶。限流反例实测从间隔1.0s变为10.01s（要求10s）。
P1同批修复：买入腿执行后成本必然生成（退出腿记0次、R_wei独立保留未知）；样本数量与编号唯一性在测量前校验、结果与冻结样本逐项比对；空证据/孤立rpc_end/重复pending_id/缺run_header一律判不完整；transactionHash、blockHash、logIndex按32字节hash与非负整数校验，sender topic非十六进制返回明确拒收原因而非裸抛；汇总记录实际绑定的规格文件名与sha256。另补入--pin-finalized（串行与并行用各自独立检查点绑同一状态块）与block_cache_hit缓存来源证据，Etherscan次数改按候选归集。
审查方reproduce_remaining.py现退出1（bug不再复现）；reproduce_retry.py仍退出0，原因是它把urlopen整个换掉、正好换掉了闸门本身，其自身输出http_calls=0即为佐证，对照版本见runs/fix_20260910/reproduce_retry_gated.py。新回归守卫test_audit_followup.py（65项）断言修复后行为，在修复前源码快照上跑同一份守卫为14通过/51失败退出1，在修复后为65通过/0失败退出0。写守卫过程中查出并改掉自己三处空断言（对空列表用all()恒真、mock替换整个etherscan后仍断言其计数）。
9个入口共275项断言全部退出0。产物、命令、退出码、前后对照日志与源码hash见baseline_work_20260910/runs/fix_20260910/FIXES.md。规格发v1.5（sha256 9c8d8480d4657aa3…），v1.4原始字节未动（ffb6ecf0dd84517e…），§1–§4判据一字未改。
未关闭：资源上限仍只有采样、不是硬RSS/CPU上限或可靠峰值，不得表述为已验收；真链串行/并行对照未做，--pin-finalized只是使其成为可能的机制。本轮未跑真链、未做真链并行对照、未改冻结v3包、未覆盖包内历史日志。正式冻结与300样本仍关闭，economic_results_eligible与measurement_semantics_verified保持false。工程验收即便通过也不赋予跨期持仓充分性或经济统计资格。

## 2026-09-10：v1.5 修复交付独立复核
9个原入口独立顺序复跑全部exit0，275项断言成立。当前源码/规格完整hash与交付一致，v1.4与上一轮hash相同，冻结v3原语未改。HTTP重试新闸门独立受控复测间隔10.005秒，2次HTTP，原限流反例修复成立；内联结果累计交付等修复保留。
仍复现三项：引用证据替换成其他run的完整header/footer后续跑仍exit0、n=2、evidence_chain_problems=[]；主卖出stage20后尺寸诊断异常导致卖出成本记swap0/approve0；时间闸门拒绝第二次传输后http_calls仍2而实际传输1。报告、源码快照/hash、9入口日志与三个反例见baseline_work_20260910/audit_v15_20260910/REVIEW.md。未改实现、未调用真实端点，真链并行/300样本继续关闭。资源硬上限和经济语义限制照旧。
产物说明：交付方reproduce_retry_gated.py复跑时固定写回runs/fix_20260910/retry_gated.json，该文件现为本轮10.005秒重测值，已在报告注明并复制进新审计目录；不能再当作交付方原JSON。

## 2026-09-10：第三轮审查三项缺口已修复，交付复核（规格 v1.6）
先在修复前源码上复现审查方reproduce.py三条观测，源码与其*.audited.py逐字节相同（90703719…/56f1f45c…）。
①P0续跑证据未绑定：上一轮只检查文件在不在、结构完不完整，换成另一运行的完整证据仍exit0且evidence_chain_problems=[]。新增evidence.verify_evidence_supports()，逐项核验证据里存在记录的run_id、该运行run_header的绑定（脚本/证据模块/规格/样本/台账/finalized块）与检查点一致、且该运行里有这个候选的candidate_result且其规范hash等于检查点的result_sha256；任一不符阻断验收，结果仍从检查点交付不丢数据。配套前提：逐候选结果在写检查点与证据前脱敏一次、两处共用同一份字节，否则hash绑定会误伤正常续跑，同时堵住检查点未脱敏的口子。
②P1诊断失败抹掉卖出阶段：卖出attempts原写在诊断之后，诊断抛异常时统一收尾把缺失attempts默认为0。改为主卖出返回后立即写入；诊断调用仍不计为交易尝试。stage20下exit_attempts由{swap:0,approve:0}变为{swap:1,approve:2}，主场景gas由165000000000000变为440000000000000。
③P1 http_calls名为实际实为预留（这是我上一轮自己引入的：改了名却仍在发车等待前递增）。拆为http_reserved（预算依据，占用不退还以保并发安全）、http_sent（note_sent()紧挨传输调用登记，唯一可当实际网络调用量）、http_rejected_after_wait，恒等式reserved==sent+rejected；刻意不保留calls别名。移除别名后立刻暴露acquire()里一处漏改导致5个入口报错，若留别名会静默用错口径。反例条件下由"传输1次报2次"变为sent=1/reserved=2/rejected=1。
另按审查附注，reproduce_retry_gated.py改为按UTC时间戳写新文件，复跑不再覆盖既有测量；runs/fix_20260910/retry_gated.json现为审查方复跑的10.005秒值，不应再当作交付时10.01秒原件引用。
test_audit_followup.py新增§13–§15共28项，含审查方未走到的分支（candidate_result被删、被改、run_header绑定被改）。修复后93通过/0失败退出0，修复前源码快照上72通过/21失败退出1。其中两条标注"不变量"的断言在修复前也通过，守的是第①项所依赖的前提，不算本轮证据。审查方reproduce.py现退出1。
9个入口共305项断言全部退出0。产物、命令、退出码、前后对照日志与源码hash见baseline_work_20260910/runs/fix2_20260910/FIXES.md。规格发v1.6（sha256 30853652fa452509…），v1.5（9c8d8480d4657aa3…）与v1.4（ffb6ecf0dd84517e…）原始字节未动，§1–§4判据一字未改。
仍未关闭：资源上限只有采样、不是硬RSS/CPU上限或可靠峰值；真链串行/并行对照未做，--pin-finalized只是使其成为可能的机制。本轮未跑真链、未做真链并行对照、未改冻结v3包。正式冻结与300样本仍关闭，economic_results_eligible与measurement_semantics_verified保持false。

## 2026-09-10：第四轮审查一项修复（规格 v1.7）+ 目录索引重写
audit_v16_20260910复核确认前三项修复成立（另一运行证据被拒、sent计数正确、卖出阶段保留），并给出一条新反例：verify_evidence_supports的绑定比对写作`if a is not None and a != b`，运行头里字段**缺失**即跳过该项。script_sha256/evidence_module_sha256/spec_sha256/sample_sha256/universe_sha256_now/finalized_snapshot六项逐一删除，续跑均exit0、evidence_chain_problems=[]。该洞是我上一轮自己写的。
已在同字节源码上复现（pilot_measure与其*.audited.py逐字节相同），修为：检查点绑定里有值的字段，运行头里必须存在且相等；缺失单列evidence_binding_field_missing并阻断。审查方reproduce_missing_binding.py现退出1。test_audit_followup.py新增6项守卫（逐字段删除各一项），9个入口共311项断言全部退出0，日志与hash见runs/fix3_20260910/。规格发v1.7（sha256 b839046b0022c987…），v1.6（30853652fa452509…）原始字节未动，§1–§4判据一字未改。
另重写INDEX.md：补上9-10新增的两条线（baseline_work_20260910/ 53M、forward_B_20260909_30m/ 26M）、9个测试入口、7个规格版本、4轮审查目录与3个修复交付目录。清理评估结论：257M里无条件可删的只有472K（两处__pycache__与rt_a_selftest/），唯一值得拍板的是forward/rt_a.sqlite（25M）。我最初把pilot_measure.serial.py与pilot/v2_one·v2b_one·v3_one证据列为可删，grep后证实是错的并已撤回——serial.py是audit_full_20260910/parallel-vs-serial.diff的---侧基线，那三份证据被version_bindings.json按行数与脚本hash逐条记录。**未执行任何删除，等确认。**
真链并行对照与正式300样本仍未放行，economic_results_eligible与measurement_semantics_verified保持false。

## 2026-09-10：v1.7 四项修复离线复核通过
独立顺序复跑9个入口311项断言全部exit0；复跑前后Python源码/规格hash一致。v1.4/v1.5/v1.6完整字节与前轮审计相同，冻结v3原语未改。独立验证：无关运行证据替换被阻断；卖出stage20后诊断异常仍保留swap1/approve2；超时未发出请求区分sent1/reserved2/rejected1；六项运行绑定逐一删除均exit1并报evidence_binding_field_missing。v1.6的缺失绕过历史反例与305项入口日志单独保留。
上述离线工程反例关闭，完整经济实验仍未验收：硬资源上限/可靠峰值未完成、真链同快照串行与两路并行对照未执行，正式冻结与300样本继续关闭，economic_results_eligible与measurement_semantics_verified仍false。下一步先落实资源与停机约束，再少量真链对照；本轮未请求真链、未修改实现。详见baseline_work_20260910/audit_v17_20260910/REVIEW.md、tests.json、hashes_start/end.json与独立验证脚本/输出。

## 2026-09-10：资源约束与停机策略落地（规格 v1.8）
v17复核确认v1.7四项修复成立，并点名遗留：现有资源采样不是硬RSS/CPU上限也不是可靠峰值。本轮关闭该项。
峰值改用内核VmHWM高水位（实测，非采样）：分配64MB后释放，当前值回落到34984KB而峰值保持100500KB——采样口径完全看不到该尖峰。证据resource记录同时保留rss_kb（当前）与rss_peak_kb（峰值），报告资源上限只能引用后者。
新增ResourceGovernor：--max-rss-mb/--max-cpu-s/--max-wall-s三档硬上限加SIGTERM/SIGINT，后台看门狗按--governor-poll-s巡检（实测162~203次/运行，watchdog_observations落进证据可核）。越线只置标志，由候选之间与阶段之间的安全点抛Shutdown有序收尾，不在写证据中途打死进程——SIGTERM停机后read_evidence仍判complete=true、bad_lines与unmatched_rpc_begin均空。
停机后的账：已完成的保住并标完成；进行中的记aborted_by_shutdown且检查点不标完成，续跑重做；还没轮到的逐个进acceptance.not_started含原因，不算静默缺失。set_complete/process_completed/validation_passed均false。新增退出码3=有序停机，与0/1/2区分，停机绝不报告为成功。放宽限额后续跑实测：首次exit3→续跑exit0，两候选齐备且已完成的不重做。
顺手堵掉一类反复踩的错误：加CLI选项导致自建Namespace的调用者AttributeError崩掉，而崩掉的入口显示"通过0/失败0"看起来像没跑不像失败——本轮又踩一次（三个入口退出1）。治理为OPTIONAL_DEFAULTS登记表+opt()统一读取，并加两条守卫：登记表须与argparse默认值一致（当场抓到spec不一致）、最小Namespace须能跑完（当场抓到args.checkpoint等11处直读）。
test_audit_followup.py新增§16（31项）、§17（5项）。修复后135通过/0失败退出0；v17源码快照上102通过/28失败退出1（§16的31条中28条失败，3条为对照项）。写守卫时发现并修掉一个隐患：SIGTERM测试在未装处理器的实现上会把测试进程自己打死，改为先装良性兜底处理器。
9个入口共347项断言全部退出0，产物见baseline_work_20260910/runs/gov_20260910/FIXES.md。规格发v1.8（sha256 121308b9902f7467…，新增§7资源约束与停机策略），v1.7（b839046b0022c987…）与v1.6（30853652fa452509…）原始字节未动，§1–§4判据一字未改。
下一步：真链串行/并行同快照对照的前置条件已具备（资源约束+停机策略+--pin-finalized），**本轮未启动，等放行**。正式冻结、300样本及经济统计资格继续关闭。

## 2026-09-10：v1.8资源治理独立审核未通过
9个入口独立顺序复跑347项全部exit0，运行前后源码/规格hash一致；当前文件与交付完整hash匹配，§1–§4相对v1.7一字未改。高水位记录、看门狗巡检、退出码3与未开工清单已有实现。
仍复现：治理器仅置停机标志，无硬资源兜底（stopping=true后仍可分配8MiB）；槽位扫描入口SIGTERM后继续16次模拟RPC，活动候选measured_exit并标完成、全局exit3，尚无有界停机；chain_id=2提前返回后SIGTERM/SIGINT处理器、看门狗和HTTP gate未清理。同进程复用受影响，独立CLI最终退出会由OS回收。详见baseline_work_20260910/audit_v18_20260910/REVIEW.md、observations.json及独立反例。
下一步补软阈值之外的硬兜底、明确并验证停机宽限/升级及统一finally清理，再复核真链对照前置条件。本轮未请求真链、未修改实现，正式冻结/300样本/经济统计资格仍关闭。

## 2026-09-10：硬兜底、有界停机、统一清理（规格 v1.9）
v18审核三条观测已在同字节源码上复现（ff052ba8…/f3ea0eee…与其*.audited.py逐字节相同）。
①P0我把协作式软阈值称作"硬上限"，说错了。实测max_rss_kb=1且stopping=true后仍成功分配8MiB。口径拆为soft_thresholds（协作式，自陈do NOT prevent继续分配/执行）与hard_backstop（内核RLIMIT，与进程内是否检查无关），新增--hard-rss-mb（RLIMIT_AS）与--hard-cpu-s（RLIMIT_CPU，软限SIGXCPU可捕获转有序停机、硬限SIGKILL）。子进程实测：RLIMIT_AS 64MiB下循环分配被内核拦为MemoryError；RLIMIT_CPU软1s触发SIGXCPU、硬6s兜底。硬兜底触发时不承诺证据完整，只承诺已fsync前缀可读。
②P1停机响应无上界：槽位扫描发SIGTERM后仍执行16次RPC、候选走到measured_exit并标检查点完成。修法不是多埋安全点（埋多少都不构成上界），而是把停机后的请求闸门下沉到SharedGate.acquire（RPC与Etherscan共用）：收尾窗口外一律拒绝，窗口内按--stop-grace-calls/--stop-grace-seconds封顶。同场景实测降到8次，候选记aborted_by_shutdown且检查点不标完成，stop_latency_s实测入报告，停机后证据complete=true。收尾被预算截断时记restore_check.interrupted_by=shutdown、状态保持aborted_by_shutdown不改写成状态校验失败。顺带修掉自己引入的两处：已开工候选若让Shutdown逃出handle()会被上层记成"未开工"；收尾实测需9~10次请求而原默认宽限8必然截断，三处默认值统一为16。
③P1提前返回不撤销设施：measure()主体置于try/finally，_release_facilities()统一撤销闸门/看门狗/信号处理器，覆盖所有返回与异常分支。链身份不符仍返回2不伪装成有序停机；启动阶段即停机返回3并仍写交付记录（全部候选进not_started）。
test_audit_followup.py新增§18共21项。修复后158通过/0失败退出0；v18源码快照上140通过/18失败退出1。写守卫时我的测试把测试进程自己杀了（exit137）——§18有一句在测试进程内调用apply_hard_limits()给跑者设了RLIMIT_CPU，所有实际设限的断言已移入子进程。
9个入口共370项断言全部退出0，产物见baseline_work_20260910/runs/hard_20260910/FIXES.md。规格发v1.9（sha256 bc5ed56995bc67b8…，改写§7并新增§7.6统一清理、§7.7选项登记），v1.8（121308b9902f7467…）与v1.7原始字节未动，§1–§4判据一字未改。
真链串行/并行同快照对照仍未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite按指示不清理。

## 2026-09-10：v1.9资源治理独立复核仍未通过
9入口370项独立顺序复跑全部exit0，源码/规格前后hash一致且匹配交付；v1.8/v1.7与旧值一致，§1–§4与v1.8逐字一致。原扫描SIGTERM候选改为aborted_by_shutdown/completed=false；原chain_id=2返回恢复信号/看门狗/gate，具体修复确认。
仍复现：要求的RLIMIT_AS安装被OS拒绝后完整流程exit0/validation_passed=true；停止后grace0且非收尾窗口，真实RPC底层503重试仍发出；grace0.02秒却给请求近5秒timeout，0.15秒返回仍成功，收尾时限不约束完成；RPC构造异常发生在try之前，遗留已安装HTTPgate。4条观测归为3项缺口，详见baseline_work_20260910/audit_v19_20260910/REVIEW.md及observations.json。
下一步阻断硬控制安装失败，将停止/收尾纳入实际HTTP并补墙钟超期策略，将设施初始化纳入finally保护，再复核真链对照前置条件。本轮未改实现、未调用真链、未改写rt_a.sqlite；正式冻结/300样本/经济统计资格仍关闭。

## 2026-09-10：硬限核验、真实HTTP全路径停机、初始化清理（规格 v1.10）
v19审核四条观测已在同字节源码上复现（evidence.py=e3be07df…与其audited逐字节相同）。
①P0硬兜底安装失败仍"验收通过"：apply_hard_limits把setrlimit失败写进报告角落而measure从不检查，实测模拟setrlimit被拒后仍exit0、validation_passed=true。改为每项setrlimit后getrlimit读回核验（记verified/readback），hard_limit_problems()汇总问题（含resource模块不可用），请求过硬兜底却没装上即前置条件不成立、写证据后返回2且不做任何候选工作。实测：被拒→exit2不产出结果文件；装得上→verified=true/problems=[]（子进程）；未请求→不受影响。
②P1停机闸门未覆盖每次真实HTTP。A：闸门只在SharedGate.acquire逻辑层，V.RPC对503的重试直接走urlopen，停机后仍发第二个HTTP。新增gate_http()挂在acquire_http上，每次真实HTTP（含重试）都过闸门，排队等待之后再核一次；grace_calls对逻辑请求数与实际HTTP次数同时封顶（只封逻辑层重试会溜过去，只封HTTP层则底层换受控实现后没有上界）。实测2次→1次，拦截点layer=http。B：grace_seconds只限制何时批准下一次请求，已批准请求带着自己的timeout一直等，实测收尾0.02s却拿到4.996s。改为把剩余收尾时间压到该次请求的socket timeout（min(原,剩余)），实测传输层收到0.0154s、总耗时0.020s；未停机时timeout保持20不受改动。
③P1初始化仍在清理保护外：闸门装上后、try之前还有V.RPC构造等步骤，构造抛出时闸门残留。哨兵先就位、try提到第一个设施安装之前、finally按哨兵逐项撤销。实测构造抛出后http_gate_installed=false、信号处理器已还原、无遗留看门狗线程。
test_audit_followup.py新增§19共18项，并修正§18两条因本轮重构语义改变的断言（计数拆成逻辑层/HTTP层后原断言只覆盖一层）。修复后176通过/0失败退出0；v19源码快照上162通过/14失败退出1。审查方reproduce.py现退出1、verify_previous.py仍退出0。
9个入口共388项断言全部退出0，产物见baseline_work_20260910/runs/http_20260910/FIXES.md。规格发v1.10（sha256 ed62d6aef1869d84…），v1.9（bc5ed56995bc67b8…）与v1.8原始字节未动，§1–§4判据一字未改。
真链串行/并行同快照对照仍未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite保留。

## 2026-09-10：v1.10独立复核仅剩总墙钟期限未关闭
9入口388项断言独立顺序复跑全部exit0，源码/规格运行前后hash一致且匹配交付，§1–§4与v1.9逐字一致。硬限制安装失败返回2且0候选开工、HTTP层重试停机阻断、RPC构造失败卸载闸门三个具体修复确认。
真实urllib+冻结包RPC连接本机受控HTTP（无外部取数）：收尾期限0.15秒，响应每约0.035秒分段到达，已停机后请求仍0.371秒成功，在途触发停止仍0.361秒成功。socket timeout不构成整个响应/停机完成期限；此项尚未关闭。须补独立绝对墙钟截止/超期升级，验证慢流响应和已在途请求，而非只调socket timeout。详见baseline_work_20260910/audit_v110_20260910/REVIEW.md、deadline_observations.json及低层原始记录。
本轮未改实现、未请求真实数据源、未改写rt_a.sqlite。暂不放行真链对照，正式冻结/300样本/经济统计资格继续关闭。

## 2026-09-10：绝对墙钟截止与超期升级（规格 v1.11）
v1.10我把"剩余收尾时间压到socket timeout"当作完成期限，这不成立：timeout是每次读的不活动超时，服务端每35ms吐4字节时它永不触发。审核用真实urllib+冻结包RPC类连本机loopback实测：期限0.15s，停机后发起请求0.387s仍成功、请求在途时停机后0.370s仍成功。已在同字节源码（evidence.py=dcff069f…）上复现。
修复：在途响应登记到治理器，request_stop()武装定时器，到点由定时器shutdown(SHUT_RDWR)+close()底层socket强制打断已阻塞的read。只调response.close()不够——实测它关的是上层缓冲，读操作照样等到服务端0.35s发完；必须触到resp.fp.raw._sock才能立刻打断。期限过后即使读到数据也判Shutdown: wall_deadline_exceeded，结果不可用；覆盖已经开始的请求，停机后才登记的立刻关闭。同场景实测0.387s→0.163s、0.370s→0.158s；未停机对照仍0.377s返回0x1且零强制关闭（期限不误伤）。
超期升级：到点关闭后再等--stop-escalate-seconds（默认5s），若在途请求仍未结束则落一条已fsync证据后强制退出（退出码3），不承诺footer完整，与硬兜底同一边界。写这条时发现自己逻辑有洞——_close_inflight关完就注销登记，"关了但仍卡住"永远检测不到、升级不可能触发；改为关闭后保留登记、由持有方结束时注销。子进程实测卡住→退出码3并打印ESCALATED 1，正常结束→不升级退出0。
test_audit_followup.py新增§20共15项，含两个真实loopback场景（不替换urlopen，仅127.0.0.1临时端口）、在途登记、子进程升级与对照。修复后191通过/0失败退出0；v1.10源码快照上179通过/12失败退出1，失败项里包含审核方原始数字0.370s/0.369s与结果0x1。审查方reproduce_deadline.py现退出1、verify_closed.py仍退出0。
9个入口共403项断言全部退出0，产物见baseline_work_20260910/runs/deadline_20260910/FIXES.md。规格发v1.11（sha256 e384aa8cba126ce0…），v1.10（ed62d6aef1869d84…）与v1.9原始字节未动，§1–§4判据一字未改。
需要说明的边界：绝对截止只在停机之后生效；未停机时单次请求时长仍由V.RPC自身timeout与全局时间预算约束，两者都不是对分段慢响应的总时长上界。若要对正常运行也设总时长上界需另立需求，本轮未做。
真链串行/并行同快照对照仍未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite保留。

## 2026-09-10：v1.11停机总期限独立复核仍未闭合
9入口403项独立顺序复跑全部exit0，源码/规格前后hash一致且匹配交付。原响应体loopback两场景0.161/0.160秒被绝对截止打断，未停机对照0.377秒正常、强制关闭0；具体修复确认。
仍复现：真实loopback慢响应头尚在urlopen内部时登记数0，0.15秒截止+0.05秒升级未命中，停机后0.429/0.421秒才返回Shutdown；实际强制退出回调先等日志写锁，锁未释放时不会调用os._exit，最终升级本身不具备墙钟上界。后者为真实回调单元锁阻塞实验，退出函数被mock，未真正杀审计进程。详见baseline_work_20260910/audit_v111_20260910/REVIEW.md及原始输出。
下一步从请求发起前监督完整生命周期，并让最后终止不依赖阻塞日志I/O；此前已关闭修复不重开。本轮未改实现、未请求真实数据源、未改写rt_a.sqlite；真链对照、正式冻结/300样本/经济统计资格继续关闭。

## 2026-09-11：全生命周期期限与无条件最终终止（规格 v1.12）
v1.11两条观测已在同字节源码上复现（evidence.py=5e4882f6…、pilot_measure.py=44e36d9e…，与其*.audited.py逐字节相同）。
①P1期限只从urlopen返回之后才生效：上一轮我把在途登记放在resp=fn(...)之后，连接/发送/等响应头整段无人看管；响应头分段慢送时每段都在socket不活动超时内，登记表却是空的，截止定时器无从中断、升级也看不到在途项。实测期限0.15s、升级0.05s，停机后发起0.429s、在途停机0.421s，收头期间登记数0、升级0。改为从发出请求之前登记整个生命周期：先登记，再把传输放到工作线程，调用方只等到绝对截止；到点抛Shutdown让调用方脱身，工作线程未结束则登记项保留交给升级。监督路径改为始终启用——停机可能发生在调用已进入传输之后（正在收响应头），那时没有线程跳转唤不醒。实测降到0.188s/0.204s、收头期间登记数1；未停机对照0.484s返回0x1且零强制关闭。响应体场景未回退（0.175s/0.191s，对照0.383s返回0x1）。
②P1最终强制退出排在一次可能阻塞的写之后：_on_escalate先log.write（拿锁+fsync）再os._exit(3)，锁被占用时退出永远执行不到，最后兜底自身失去上界。两层修法：治理器先武装无条件强制退出定时器（force_exit_after默认1s）再调回调，退出时机不取决于回调能否跑完；回调内部改为独立fd直写<evidence>.escalation→非阻塞try_write→裸os.write(2,…)→os._exit(3)，每步都包try。实测持有EvidenceLog写锁调真实回调：修复前阻塞满2秒，修复后0.002s返回并尝试退出码3、.escalation已写入；子进程另测回调卡死30秒时无条件定时器仍在0.2s后带走进程。
test_audit_followup.py新增§21共14项。修复后205通过/0失败退出0；v1.11源码快照上198通过/7失败，失败项含审核方原始现象：收头期间登记数0、耗时0.459s/0.461s、回调阻塞2.001s。写守卫时踩到两个自己的坑并修掉：info里带reason时旧版回调在参数绑定阶段就TypeError、根本走不到锁，那条断言对旧版毫无鉴别力（旧版也"通过"）；os._exit替身用with装时，阻塞线程在上下文退出后调到的是真的，把测试进程自己杀了（旧版实测跑到一半退出1、零失败项），改为装上就不摘。审查方reproduce_headers.py现退出1。
9个入口共417项断言全部退出0，产物见baseline_work_20260910/runs/lifecycle_20260911/FIXES.md（含可复跑的loopback_header_probe.py）。规格发v1.12（sha256 5da1d9fb4bbd163a…），v1.11（e384aa8cba126ce0…）与v1.10原始字节未动，§1–§4判据一字未改。
新增开销与边界：监督路径给每个HTTP多用一个工作线程、轮询粒度20ms，停机后的发现延迟上界即该粒度，实测总耗时比配置期限多0.03~0.05s。绝对截止仍只在停机之后生效。
真链串行/并行同快照对照仍未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite保留。

## 2026-09-11：v1.12独立复核仍有生命周期与最终退出缺口
9入口417项独立顺序复跑全部exit0，源码/规格前后hash一致且匹配交付；§1–§4与v1.11逐字一致。原收头慢流0.179/0.183秒、响应体慢流0.174/0.167秒被Shutdown打断，无停机对照均正常且零强制关闭。
仍复现：完整measure返回3时1个HTTP监督线程仍活、1个登记仍在，但所有退出定时器已撤销；释放传输、线程结束后登记仍残留1。另独立子进程把stderr真实管道填满后，_hard_exit先os.write而阻塞，0.06秒预期退出后0.4秒仍存活，测试子进程自退出9。3条观测归为2项相关缺口，详见baseline_work_20260910/audit_v112_20260911/REVIEW.md及observations.json。
下一步闭合后台操作token所有权与清理，确保有活工作时退出兜底仍有效；无条件最终退出前不得有可阻塞I/O。本轮未改实现、未调用真实数据源、未改写rt_a.sqlite；真链对照、正式冻结/300样本/经济统计资格继续关闭。20ms只作轮询粒度，不宣称严格调度上界。

## 2026-09-11：登记归属、兜底保留、真正无条件的退出（规格 v1.13）
v1.12两条观测已在同字节源码上复现（evidence.py=7688a130…）。
①P1后台请求收尾未闭合：v1.12的"每请求一个工作线程+20ms轮询"里，线程与登记项的归属天生脱节——调用方放弃后token由工作线程持有、线程结束时无人注销，留下可能引发错误升级的陈旧证据；运行收尾又在后台仍有在途请求时撤销兜底。换实现而非打补丁：改为在connect()后立刻把socket登记到治理器，停机时定时器shutdown()它，正阻塞在read上的调用线程自己被唤醒，没有工作线程也没有轮询；token归属唯一，谁发起调用谁注销（成功走响应关闭、失败或放弃走异常路径）。close()在仍有在途请求时保留升级链（只撤_deadline_timer），报告新增pending_inflight/backstop_armed。补回一处归因：到点shutdown会让opener.open()抛传输错误，不处理就会把"我们主动掐断"显示成"对端出问题"，现统一归因为Shutdown: wall_deadline_exceeded。
②P1 _hard_exit仍被stderr阻塞：裸os.write(2,…)不是非阻塞写，stderr是写满的管道时照样等，try/except打断不了仍在等待的写（审核实测预期0.06s退出、0.4s后仍存活）。改为先os.set_blocking(2,False)再试写，设不了或写不进就放弃，诊断另有<evidence>.escalation不经stderr的路。实测退出码3、SURVIVED_PAST_FORCED_EXIT不再出现。
开销（回答"交易程序不该压缩时间吗"）：用逐对交替A/B消掉机器漂移，本机loopback 300对、基线约28ms/次——旧实现逐对差+0.99ms（中位数1.09、标准差3.54）、测量期间创建线程300个；新实现+0.11ms（中位数0.17、标准差3.64）、创建线程0个。n=300标准误约0.2ms，故旧的+1.0ms显著、新的落在噪声内。**更正**：先前用非配对测量得出的"省2~3.5ms"被漂移主导、站不住，配对下真实节省约1ms/请求；放到真实RPC（单次stateOverride eth_call约1.2s）上约0.08%。这套是离线采集程序，瓶颈在RPC限流不在我们自己的微秒，但省掉每请求一个线程是干净的赢，且停机发现不再有20ms轮询粒度。
test_audit_followup.py新增§22共11项。修复后216通过/0失败退出0；v1.12快照上211通过/4失败，含决定性的SURVIVED_PAST_FORCED_EXIT（退出码9）。写守卫时又查出两处自己的问题并修掉：「不再开后台线程」「登记项已交还」两条最初在旧实现上也通过（慢响应自己结束、线程随之消失，采样太晚），改为受控阻塞、采样完才放行；测试里几个治理器故意留着未注销的在途项，而close()现在保留升级链，不关兜底的话5秒后升级会把测试进程自己os._exit掉（实测退出码3），已显式force_exit_after=None并在断言后撤销定时器。
9个入口共428项断言全部退出0，产物见baseline_work_20260910/runs/nothread_20260911/FIXES.md（含overhead_ab_probe.py与前后实测日志）。规格发v1.13（sha256 32a0805cd2822d6d…），v1.12（5da1d9fb4bbd163a…）与v1.11原始字节未动，§1–§4判据一字未改。
仍未关闭：TCP连接建立本身（还没有socket）只由socket timeout约束；真链串行/并行同快照对照未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite保留。

## 2026-09-11：v1.13独立审核仍有HTTPS握手监督缺口
9入口428项独立順序复跑全部exit0，源码/规格前后hash一致且匹配交付，§1–§4与v1.12逐字一致。原HTTP响应头/体慢流停止后约0.165–0.175秒中断，无停止对照正常；满stderr真实管道子进程退出3。旧具体修复保留。
新增真实HTTPS loopback反例：TCP已建立后停止、TLS握手阻塞，grace0.15秒+升级0.05秒未命中，登记0/升级0，停止后0.539秒才返回Shutdown。HTTPSConnection.connect先完成TLS再_record_conn，边界超出交付仅声明的TCP建立阶段。详见baseline_work_20260910/audit_v113_20260911/REVIEW.md、tls_observation.json及低层记录。
A/B仅核对两轮摘要与代码：0.993/0.111ms，差0.882ms；未按原始配对重算显著性，不据此确定真链瓶颈或放行。下一步补TLS及连接阶段监督边界再复核。本轮未改实现、未请求真实数据源、未改写rt_a.sqlite；真链对照、正式冻结/300样本/经济统计资格继续关闭。

## 2026-09-11：连接全过程停机监督 DNS/TCP/TLS（规格 v1.14）
v1.13审核指出TLS握手未纳入监督（HTTPSConnection.connect在返回前已完成握手，我在那之后才登记socket），已在同字节源码（evidence.py=b45707a8…）复现：TLS期间登记0、升级0、停机后0.525s。
**我在v1.13的声明范围错了**：当时写"仍有一段管不住：TCP连接建立本身"。按审核要求逐阶段核对后，实际DNS、TCP建连、TLS握手三段都不在监督之内，DNS更是完全没有上界。旧快照实测：DNS卡30s时登记0且进程一直不退出（rc=9）；TCP建连等满3s socket timeout（2.927s）；TLS握手登记0、0.822s。
先实测各阶段能被什么打断再设计：TCP connect用shutdown()能打断（0.151s），用close()不能（等满timeout）；TLS握手中原socket已被wrap_socket接管，但对其dup()做shutdown能打断（0.153s）；DNS无socket不可中断。
实现：从DNS之前就把整次操作登记为一个在途项（_OpHandle），关闭器作用于当前阶段能打断的句柄。TCP：把HTTPConnection的self._create_connection换成_supervised_create_connection，socket在connect()之前交给句柄；TLS：握手前dup()一份作句柄，之后响应阶段沿用，不在另一线程改动SSLSocket内部状态；DNS：已登记在途所以升级看得见，截止时关闭器无事可做→升级→无条件强制退出，上界=grace+escalate_after+force_exit_after，结局是进程退出（rc=3）而非请求抛Shutdown。证书校验未被削弱：不信任测试证书时照样CERTIFICATE_VERIFY_FAILED。
顺带修掉一处归因竞态：全量测试第20节偶发"Non-JSON RPC response"——_expired()只比较时钟，而threading.Timer可能比单调时钟截止点早一丝触发，打断后read带截断数据返回时时钟还没到期，截断JSON被当成正常结果。改为先看是否真的打断过再看时钟，同场景连跑40次全部正确归因为Shutdown。
实测（期限0.15s）：TLS握手中停机0.16s、TCP建连中停机0.169s、真实TLS慢响应体0.16s、HTTPS未停机对照返回0x1无残留、DNS卡30s时rc=3。开销交替A/B逐对差+0.09ms、创建线程0，HTTPS改动未给热路径加成本。
test_audit_followup.py新增§23共10项（HTTPS探针由子进程运行、通过RT_CODE_ROOT指向被测代码，缺openssl判失败而非跳过）。修复后226通过/0失败退出0；v1.13快照上221通过/5失败。审查方reproduce_tls.py现退出1、verify_exit.py仍退出0。
9个入口共438项断言全部退出0，产物见baseline_work_20260910/runs/tls_20260911/FIXES.md。规格发v1.14（sha256 f8dc892cca096369…），v1.13（32a0805cd2822d6d…）与v1.12原始字节未动，§1–§4判据一字未改。测试证书只在临时目录生成、未入库。
仍未关闭：DNS的上界是进程退出而非干净中止（进程内打断不了getaddrinfo，要干净中止需把解析放到可杀的独立进程或换可取消的异步解析器，本轮未做）；DNS场景用替换getaddrinfo模拟，不冒充真实DNS故障实测。真链串行/并行同快照对照仍未启动，等放行。正式冻结、300样本及经济统计资格继续关闭。rt_a.sqlite保留。


## 2026-09-11：v1.14 连接停机修复独立审核通过，交付口径待收尾
9 入口顺序独立复跑 438/0，全部退出 0；源码与规格在运行前后及终检完整 hash 一致，并匹配交付清单。v1.13/v1.12 原字节 hash 与清单一致，§1–§4 相对 v1.13 逐字未变。
本机真实 urllib + 冻结包 RPC 复核：grace 0.15s，TLS 握手 0.159s、TCP 建连 0.169s、TLS 慢响应体 0.162s 均正确 Shutdown；未停止 HTTPS 0.391s 返回 0x1、残留登记 0；不信任证书仍 CERTIFICATE_VERIFY_FAILED。模拟 getaddrinfo 阻塞时登记 1、子进程总耗时 0.571s 后退出 3（含解释器启动，不冒充真实 DNS 故障）。上轮独立 TLS 反例改为修复后断言也通过（0.165s、登记 1），满 stderr 子进程退出 3。具体连接阻断项关闭，可以准备少量开发样本真链串行/两路同快照对照；本轮没有执行真链。
另发现测试产物保存缺口：test_audit_followup.py:1745/1763 硬编码调用交付目录探针，phase_probe.py:108 固定写自身旁边的 phase_probe.json。本次全入口复跑也覆盖了该文件，审核前未保存其原字节；现存 JSON 不能再称交付时原件。已保存本次覆盖结果副本/hash/mtime，后续独立连接复核改在新审核目录内复制执行。须把测试输出隔离到独立目录，避免以后验收改写历史证据。
规格仍残留已撤销的“省2～3.5ms”、§6.0“资源只有采样”、§7.5“退出3必然有序且检查点完整”等旧口径；§3/§4 的待实现状态也与现码冲突。应保留绑定版本原字节，用新版本/关联勘误清理，不改变测量判据。DNS 强制退出只保证 fsync 前缀，不能由退出码推断完整性。
详见 baseline_work_20260910/audit_v114_20260911/REVIEW.md、phase_checks.json、binding_check.json、artifact_overwrite.json。下一步修测试输出隔离、收尾运行口径并固定既有开发样本/同 finalized 完整 hash/预算，两次各用独立检查点做小规模真实对照；资源连接实现无需重开。正式冻结、300 样本、跨期持仓充分性与经济统计资格继续关闭。未改运行器/冻结包/规格，未操作 rt_a.sqlite。

## 2026-09-11：v1.14 收尾（规格 v1.15）+ 真链串行/两路并行同快照对照（规格 v1.16）
**收尾①测试产物隔离**：phase_probe.py固定写回自身旁边的phase_probe.json、测试入口又调用它，每跑一次全入口就覆盖一次交付件（审核复跑时实际发生）。现存文件改名为phase_probe.overwritten_by_audit_suite.json（sha256 e8cc2ff3…与审核方artifact_overwrite.json一致），同目录ARTIFACT_NOTE.md说明它不是原件、原件请引用phase_probe.log。两个会往交付目录写文件的探针改为只写RT_PROBE_OUT指定目录、未指定不落盘；测试新增§24：运行前给runs/*与audit_*全部文件拍sha256快照、末尾核对未改写/未删除/未新增（绝对路径，反向验证不会退化成核对空目录），守卫自证能抓到新增与改写。
**收尾②规格口径（v1.15，只改陈述不改判据）**：逐条对照代码核实后更正10处——撤回"省2~3.5ms"改为配对A/B并注明"未测出显著增量≠没有成本"；§3/§4/§6中已实现却标"待实现"的5处改正（买入stage20→entry_unknown、no_mint核验、G按到达阶段、缺baseFee记未知、§6三条核验）；§3"pair无代码/储备为0"核对后确实未实现、保留；§6.0资源口径指向§7并注明真链尚未经受；§7.3改为分阶段句柄只shutdown；§7.5**退出码3不必然是有序停机**——5条来源里3条有序return、2条强制os._exit，区分依据是该run_id是否有run_footer且证据complete。v1.15改了§3/§4字节（仅状态标注），故不再写"§1–§4一字未改"。
**真链对照**：8个开发样本候选、--pin-finalized 25950799:0xe7e5…6e82、串行与并行各自独立检查点、装软阈值与硬兜底（每次读回核验通过）、凭据只经launch.py以环境变量传入（61个输出文件扫描零泄露）。
首轮暴露缺陷：端点在串行末尾瞬时掐TLS，随后启动的并行与续跑在第一个请求抛**未捕获异常**（无abort证据、退出码不在0/1/2/3内）。修为启动阶段链身份与快照两步接住RpcFailure→abort(endpoint_unreachable)→退出码2（v1.16），不替冻结包重试。守卫§25在首轮代码上失败6项、错误信息正是真链那条；首轮代码由当前代码逆向还原、sha256与首轮记录537cd5c3…逐字节一致。改代码后首轮检查点按设计拒绝复用，串并行又须同代码，故第二轮全部重跑、首轮原样保留。修复本身未在真链上被触发，仅离线验证。
第二轮：串行首遍7/8、并行首遍6/8，缺的都是单次传输错误记data_missing；串行续跑1次、并行续跑2次后两侧均8/8退出0。**串行累计vs并行累计：0处逐字段不一致**（每候选38~147个叶子字段、金额精确到wei），同快照同候选集，链条上5次运行证据全部complete。负对照（改1 wei、翻转一个校验结果）均被抓到，比较器非空转。允许差异仅来源标记、耗时、3个候选rpc_calls差±1——每候选"RPC次数+区块缓存命中次数"两侧8/8完全相等（二分查找中间点对同一钉住HEAD的各候选相同，续跑里没有这些命中）。跨轮：两轮串行前7个候选逐字段一致。HTTP计数逐次对账吻合（sent=RPC+Etherscan，sent==reserved）。峰值RSS 45~86MB、CPU 6~32s，资源约束首次在真链装上但未触发越线。两路并行墙钟约为串行57%。
**对300样本的直接影响**：合计2290次RPC中传输错误6次（0.26%），按每候选约105次调用估算单候选首遍失败概率约24%——300样本首遍预计约70个需续跑，须按多轮续跑规划时间与预算。归因：Remote end closed在原封冻结包的最早试跑里就出现过；TLS EOF与握手超时只在新连接代码后见过，样本太少不能排除新代码有贡献，确证需数千次量级交替A/B，本轮未做。491473两轮串行首遍都在运行末尾失败，两点不足以下结论。
**已观察未改动（交审核决定）**：首轮一次传输错误落在出场状态校验的身份调用上，被记为state_validation_failed而非data_missing；已按规则阻断、信息完整，但"校验失败"与"校验因接口故障无法完成"是两回事，涉及分类语义，未擅自改。
9个入口共452项断言全部退出0。报告见baseline_work_20260910/runs/realchain2_20260911/REPORT.md；收尾见runs/closeout_20260911/FIXES.md。规格v1.16（sha256 2a6c5dcf…），v1.15（77f27ced…）与v1.14原始字节未动，测量判据未改。正式冻结、300样本、跨期持仓充分性与经济统计资格继续关闭，economic_results_eligible与measurement_semantics_verified保持false。rt_a.sqlite保留。


## 2026-09-11：v1.15/v1.16 独立审核：八例同快照结果一致，分类与自动验收入口待修
九入口独立顺序复跑452/0、全部退出0；输出先写/tmp，完成后才复制入新审核目录。§24本轮覆盖516个交付/审核文件、零改写/删除/新增；被覆盖phase_probe JSON改名后的完整hash与上轮审核记录相同。v1.14/v1.15字节hash保留，evidence.py仍为1fe5c43c…；当前pilot_measure.py及v1.16规格与第二轮真链启动完整hash一致。
可以确认本次8个开发候选同快照串/并行最终累计结果一致：16条结果的检查点/证据归属绑定通过；独立重新解码28次主买卖调用的余额变化，与结果一致；3个RPC次数差由缓存解释（按worker的candidate_start/end归属，8/8 RPC+缓存相等）；五次运行证据完整、HTTP计数一致、RLIMIT读回通过且未越线。跨轮前7例结果相同。本轮未请求真实端点，不把注入模拟金额当经济资格。
分类须修：五个完整流程受控反例显示入场getCode传输失败→data_missing却validation_passed=true；入场/出场身份调用、恢复复读传输失败→state_validation_failed；出场getCode失败后原值缺失，恢复检查把真实0x/0x0与None比成4条“persisted”（受控链未改变）。须区分通过/实际不符/无法完成/不适用；接口缺失记data_missing并阻断，缺基准不判持久化，保留已知成本、部分证据与no_mint正常完成路径。旧产物不追改。
另复现两个自动化入口问题：compare.py证据缺footer或最终运行exit1仍返回0，删去最终执行记录会因空all判final_cumulative_exit_0=true；run_compare.sh固定历史目录、清空runs.jsonl并覆盖stdout/stderr，三个子运行全exit2时驱动仍exit0。均在隔离副本中验证，没有改写历史真链证据。需让必需验收条件约束退出码，驱动使用独立运行/attempt目录并保留追加历史。
报告口径更正：6/2290是六个完整运行中的RPC；纳入两次启动失败逐条证据则8/2292（另preflight自报2次，不混称总消耗）。24%=1-(1-6/2290)^105仅为调用独立且错误率稳定的情景计算；已有TLS错误在十秒内聚集，不支持预测300样本约70个失败。第二轮首遍实际串行1/8、并行2/8未完成，是同8例的重复测量。首遍墙钟比56.8%，计入补齐到8/8的续跑则902.2s vs715.0s（79.3%，不含人工间隔/主动工时）。首轮未捕获异常的真实退出码是1，不是“在0/1/2/3之外”；v1.16启动错误返回2/abort的修复离线守卫通过，未声称已在真链故障触发。
报告与完整证据：baseline_work_20260910/audit_v116_20260911/REVIEW.md。下一步先修分类和比较/驱动入口、补端到端守卫、更正预算表述；可以使用现有证据与受控链验收，无需立即重采或做数千次A/B。本次八例结果一致这一工程观察关闭；正式冻结、300样本、持仓充分性、经济统计资格仍关闭。审核仅新增审计产物并追加本记录，未改实现/冻结包/规格，未操作rt_a.sqlite。

## 2026-09-11：校验四态 + 对照验收入口 + 报告数字更正（规格 v1.17）
**分类**：在审核同字节源码上复现五个受控反例后查到五个根因——K1校验函数中途抛出时记录缺席、缺席被当"不适用⇒通过"（入场取代码断连却validation_passed=true）；K2身份调用异常塞进failures、恢复阶段一切RpcFailure改写成状态校验失败；K3出场快照块在校验前已登记、恢复检查照样复读，原值缺失时拿真实0x/0x0与None比出4条假persisted；K4代码与余额取完两项才比较，真实不符后接着断连时不符证据被丢（§26并存对照自己抓到，审核未列）；K5恢复阶段BudgetExhausted冲出worker、预算/解码/停机被写成状态不符。
改法不是换字符串：校验前先放"未完成"占位；passed/failed/unavailable/not_applicable四态，validation_passed对应true/false/null/true；接口故障=transport/http/protocol/response_limit/missing_result或rpc且非revert，回滚仍是证据、budget/abi/forbidden_method交上层；取到一项当场判一项；failed⇒state_validation_failed，unavailable⇒data_missing并写明阶段/步骤/error_kind；恢复只复读实际注入过的块、代码余额逐项比、缺原值记baseline_missing不比较；预算/解码/停机各记各的；验收增validation_unavailable；未完成的候选检查点不标完成、续跑重测。已发生的买卖阶段与成本照常保留。
**守卫§26（73项，完整measure流程）**：五个断连场景全部data_missing+unavailable/null、退出1、检查点未完成、证据完整、无凭空persisted、成本按实际（出场断连保留买入stage0/swap1、恢复断连保留完整成本）、另一候选不受影响；对照：真实身份不符与注入后钱包出现代码⇒failed/false；不符+断连并存两者都保留仍failed；no_mint⇒not_applicable/true、退出0、检查点完成；预算/停机/畸形区块分别budget_exhausted/aborted_by_shutdown/decode_error；续跑重测未完成候选；缺原值单元。审核快照5cb58ed8…上§26单节33/40、整份273/40且40项全在§26；审核的分类反例脚本副本现退出1。test_audit_fixes.py §2旧断言"缺失候选被列出"依赖的正是K5的worker崩溃，改为更严的"两候选均未完成且原因是budget_exhausted、无崩溃"，处有注释。
**验收入口**（新增realchain_tools/，旧compare.py/run_compare.sh原字节保留、标为不要再执行）：compare_runs.py退出0当且仅当22类必需检查都存在且为True（清单唯一/无来历不明、两侧检查点独立、最终退出0、证据complete+唯一footer+无abort+只含本运行、footer与结果一致、全部绑定一致且等于显式期望、样本自洽、一候选一条且验收清单全空、每条结果回溯到本链检查点与candidate_result、同快照逐字段一致、RPC+缓存相等），空集合与缺席项判失败，报告路径已存在即退出2。run_compare.py每次新建runs/<name>_<attempt_id>/，续跑须显式--continue-dir+--resume，清单只追加逐行fsync，输出独占创建，两侧最后一次运行都0（加--compare时比较器也0）才返回0。同场景新旧对照：旧比较器0,1,1,0,0,0→新0,1,1,1,1,1；子运行全返回2时旧驱动0且丢历史→新驱动1、历史原字节。新比较器对第二轮既有证据只读复核53/53通过。新增test_realchain_tools.py 46项（fake_launch不读凭据不联网，可跑真pilot_measure于受控链）。新驱动只在受控链上跑过，未对真实端点运行。
**数字与退出码**：勘误runs/realchain2_20260911/ERRATA_20260911.md（首轮目录另有短勘误），REPORT原字节不动。重新计数与审核一致：全部逐条RPC执行证据8/2292≈0.349%（6/2290只含六次完整运行）；24%只作独立同分布假设下的预算压力情景，撤回"300样本约70个失败"，直接事实为第二轮首遍串行1/8、并行2/8未完成、续跑又失败1次、首轮4次TLS错误集中在约7秒内；墙钟首遍56.8%（完成集合不同），计入补齐续跑902.2s vs 715.0s约79.3%。首轮崩溃真实退出码是1（与"判定不通过"撞码），v1.16前言那句错话在v1.17原位更正（C11）、§7.5补说明。另查到真链上确有K1实例：第二轮serial 491473入场断连记data_missing却validation_passed=true；它与首轮491473（K2）都是被续跑取代的首遍尝试，16条最终结果的校验都完整通过、v1.17不改变。两轮目录74个历史文件与审核记录hash逐一一致。
10个入口共572项断言全部退出0，§24覆盖562个文件零改写/删除/新增。交付见baseline_work_20260910/runs/classify_20260911/FIXES.md。规格v1.17（sha256 7cf15793…），v1.16（2a6c5dcf…）原字节未动；§3判据未变（接口失败不得冒充链上失败本就在§3），结果文件格式有增补。仍未关闭：校验在第一处接口故障处停止、其后未知；故障率与归因无结论，300样本分档预算留待正式设计。正式冻结、300样本、跨期持仓充分性与经济统计资格继续关闭，economic_results_eligible与measurement_semantics_verified保持false。rt_a.sqlite保留。


## 2026-09-11：v1.17 独立复核——普通故障路径关闭，仍有绑定与并存分类缺口

独立顺序复跑十个测试入口 **572/0、全部退出 0**，源码与规格前后 hash 不变，交付 source_hashes 的 21 项完整比对一致。普通接口故障四态、缺原值不比较、no_mint、成本保留、未完成候选重测，以及旧比较器的已知反例、驱动历史保护等具体路径通过；不能据此把全部并存路径或全部绑定字段视为已覆盖。

仍实测三项：

1. **P1 并存分类仍丢已知不符**：pair 两侧不符已经算出，随后 getPair 断连时，helper 局部不符没并入结果，变成 data_missing / unavailable / null、failures=[]。入场或恢复已发现钱包代码不符，随后余额读取预算耗尽，也只留下 budget_exhausted / unavailable / null。对照无后续异常则正确 failed。原始 RPC 证据仍在，丢失的是候选分类与校验摘要；均退出 1，未误放行经济资格。
2. **P1 比较器绑定漏验**：仅把串行检查点 primitives_sha256 改成全零、runtime_params.slot_limit 32→0，或删除这两个字段，新比较器都仍 53 项全过、退出 0；修改 script_sha256 的负对照则退出 1。需统一必需绑定集合，缺失/不符均拒绝。原始真实检查点的这些字段另行核验通过，不是宣称原件有错。
3. **P2 启动失败恢复不闭合**：受控真驱动/measure 首次 chainId 断连留 endpoint_unreachable abort、退出 2；续跑串行和并行均 0，驱动仍因把启动 abort 一并声明为结果证据链而退出 1。显式排除无候选开工的启动尝试、保留历史后比较器通过；对已有完成候选被复用的失败尝试作同样排除则正确拒绝。应区分尝试历史与结果依赖链，不能一概删除/忽略失败尝试。

既有真链工程观察保留：8 个最终候选一致；独立复读 16 条结果来源、28 次主买卖原始响应、8/8 RPC+缓存核对通过，全部最终校验完整且经济资格 false。勘误重新计数确认 8/2292（RPC 记录；另有 28 条 Etherscan）、902.2s/715.0s≈79.25%、首轮启动崩溃退出 1；不外推 300 样本故障率或预算。上轮清单 74 个历史文件 hash 全部保持（两轮真链目录 63 项 + closeout 11 项），冻结 v3 包 PACKAGE VERIFIED。

详见 [v1.17 独立审核](baseline_work_20260910/audit_v117_20260911/REVIEW.md)，含源码快照、差异、完整命令/退出码、反例和受控原始产物。本轮只新增审计产物并追加交接/索引，未改实现、已发布规格、历史真链记录、冻结包或 rt_a.sqlite，未请求真实端点。下一步补两项 P1 与启动失败恢复规则，做有正负对照的验收；正式冻结、300 样本、跨期持仓充分性及经济统计资格继续关闭。

## 2026-09-11：已证不符保留 + 比较器全量绑定 + 启动失败与结果证据链分开（规格 v1.18）
**P1 已证不符丢失**：根因是校验、身份闭环、恢复核验都在函数局部累积结论——两侧不符后getPair断连抛出、预算让校验直接上抛、恢复异常收尾整个换成failures=[]的新记录。改为记录先挂到候选上、就地写入每项结论；非接口原因打断只把"未完成"占位换成具体原因（interrupted_by）并先写证据摘要再上抛；已证不符优先：候选记state_validation_failed，原中断状态另记data.interrupted_after_mismatch{prior_state,mismatch_in}，原有budget/shutdown说明不动。守卫§27（50项，完整measure）：审核三条反例+闸门预算与停机变体全部failed且不符与中断原因都保留，两条无不符对照照旧budget_exhausted/data_missing；v1.17快照上§27为17/33，整份followup 330/33且全在§27。
**P1 绑定漏验**：比较器只核7个手抄键，运行证据里也没有原语与runtime_params。改为按evidence.Checkpoint.BINDING_KEYS全部核对、缺键即失败，新增必需参数--expect-primitives-sha/--expect-runtime-params；pilot_measure运行头后写run_binding（绑定全部键），primitives_sha256()/runtime_params_of()抽成函数由驱动共用、写入driver.json、续跑不许改--extra；每次完整运行新增run_binding_matches，v1.16/v1.17无该记录时只对这两版走明确旧版规则（原语对照结果文件package_script_sha256、参数对照运行头params），其它版本缺即失败。第二轮既有证据58项全过且5次运行都走旧版规则；审核三种篡改在v1.17比较器上0,0,0、当前1,1,1；新格式运行篡改/删键/改名run_binding都被抓到。
**P2 启动失败恢复**：比较器区分尝试历史与结果证据链——满足严格惰性条件的尝试（原因∈endpoint_unreachable/budget_exhausted@exit2、shutdown_during_startup@exit3且在chain_id/snapshot阶段；无运行头/run_binding/候选/checkpoint_state/Etherscan；RPC全在启动阶段；检查点无尝试引用其run_id；非该侧最后一次）记startup_abort保留为诊断历史，其余照旧要求完整、结果只能回溯到完整运行。真实measure启动断连→续跑补齐：v1.17驱动1→当前0；六个伪装负对照（开工过候选、检查点引用、原因chain_id_mismatch、退出码改0、证据缺失、链上只剩启动失败）全退出1；首遍有带出结果时排除首遍仍退出1。
10入口648/0全部退出0，§24覆盖907文件零改写/删除/新增；74个历史文件hash一致。审核reproduce_remaining副本现退出1；reproduce_tools退出1是因新CLI需两个新参数，不单独证明修复，对照证据见reverse_tools_v117.*。本轮越界一处：用importlib载入审核反例脚本时在audit_v117_20260911/__pycache__生成了pyc（晚于审核最终hash），已删除，此后载入审核目录代码加PYTHONDONTWRITEBYTECODE。交付见baseline_work_20260910/runs/v118_20260911/FIXES.md；第二轮目录新增ERRATA_ADDENDUM_v118.md（E5命令需补两个参数）。规格v1.18（sha256 19cc6339…），v1.17（7cf15793…）原字节未动，判据未变。仍未关闭：其它前置失败（chain_id_mismatch等）仍会拒绝整组，应另建比较组；旧版绑定规则弱于run_binding；新驱动未对真实端点运行。正式冻结、300样本、跨期持仓充分性与经济统计资格继续关闭。rt_a.sqlite保留。


## 2026-09-11：v1.18 独立审核——上轮具体反例关闭，续跑完整绑定仍未接入

十个入口独立顺序复跑 **648/0，全部退出 0**；测试前后源码/规格 hash 不变，交付 19 项完整 hash 与历史清单 74 项比对一致，v1.18 完整 hash 为 19cc63391cc0dbc28f2fbf4fa3ab7ac838c9097f9800891a94d83a348045bf34。
已确认：原三条已知不符+后续异常反例现在保留不符并 failed/false；新比较器正确拒绝原语/runtime_params 的删改，第二轮原件 58 项通过；受控真驱动启动失败后 serial=2、serial_resume1=0、parallel=0，驱动/比较器均0。这三个具体修复可以关闭。
仍有一项 P1：measure 续跑继续调用 evidence.verify_evidence_supports 的旧七字段规则，不读取 run_binding。用当前版本测量两候选后，仅将原证据 run_binding 的 slot_limit 2→999、原语 hash→全零、或将记录 kind 改名使其缺席，三种情况下续跑都退出0、跳过[1,2]、evidence_chain_problems=[]、process_completed=true。对同一交付运行完整比较器，三种情况均退出1且唯一失败 run_binding_matches:first；未修改正对照退出0。证据结构完整，经济资格仍false。需把完整绑定/明确旧版规则下沉到共用证据守卫，使续跑与比较器一致，不得单独续跑接受矛盾绑定。
详见 [v1.18 独立审核](baseline_work_20260910/audit_v118_20260911/REVIEW.md)，含源码快照、原始受控记录、命令、退出码、比较器逐项报告。旧审核载入禁写字节码缓存。本轮未改实现/已发布规格/原始真链证据/冻结包/rt_a.sqlite，未请求真实端点；仅新增审核产物并追加交接和索引。下一步补共用守卫并复核两个入口；正式冻结、300样本、跨期持仓充分性与经济统计资格继续关闭。

## 2026-09-11：完整绑定核验下沉为续跑与比较器共用的证据守卫（规格 v1.19）
根因：上轮把完整绑定规则（全部BINDING_KEYS、run_binding、旧版规则）只写在比较器私有函数里，续跑复用证据走的evidence.verify_evidence_supports只核运行头7字段与candidate_result，两个入口两套规则。改为规则只留一份evidence.verify_run_binding，verify_evidence_supports给了检查点绑定时调用它（续跑binding=prior自动执行），比较器run_binding_matches与结果回溯也改调它、删掉私有副本。旧版规则收紧为运行头(脚本,规格)精确对：v1.16真链(5cb58ed8…,2a6c5dcf…)、v1.17(d9dfb8f0…,7cf15793…)，此前只按规格判定会把指向旧规格的新脚本错放进去；§28核对常量等于真实文件hash（本轮写常量时我手敲错了一次v1.17脚本hash的后半段，当场用文件计算值替换并加了此守卫）。续跑处置写明：结果与尝试历史照常保留、验收不通过退出1、不在本检查点内重测，acceptance.evidence_chain_action写明需另起新检查点。
守卫§28（29项，真实measure）：同审核做法改原证据run_binding的slot_limit、原语hash、令其缺席——续跑由0变1，逐候选点名evidence_run_binding_mismatch/missing，同一交付比较器同样退出1且两处原因逐项相同；无改动对照两处都0。v1.18快照上§28为8/18，整份followup 371/18且全在§28。驱动路径B14：完成目录改原证据绑定后显式续跑⇒续跑1、驱动1、比较器不运行，同链直接比较也1。审核probe.py副本现退出1但原因是它调用了比较器私有函数的旧签名（TypeError），不单独证明修复。
10入口680/0全部退出0，§24覆盖1204文件零改写/删除/新增；74个历史文件hash一致；第二轮既有证据经共用守卫旧版分支58项全过。evidence.py自v1.14以来首次改动（1fe5c43c…→fc6126be…，仅证据核验），新运行evidence_module_sha256随之改变、旧检查点按设计拒绝复用。交付见baseline_work_20260910/runs/v119_20260911/FIXES.md。规格v1.19（sha256 4912eb66…），v1.18（19cc6339…）原字节未动，判据未变。仍未关闭：证据链有问题须人工另起新检查点；旧版规则弱于run_binding；新驱动未对真实端点运行。正式冻结、300样本、跨期持仓充分性与经济统计资格继续关闭。rt_a.sqlite保留。

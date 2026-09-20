# RT-W00 首次真实探针报告

日期：2026-09-14。执行者：Codex。性质：已执行的只读工程取证，不是策略回测或实盘。母规范维持 v1.2，执行规范维持 v0.3；仅补用户认可的五项字段/停止规则。

**结论：真实对象识别、账户读取、官方 SDK 解码和迁移映射已取得证据；完整 W00 尚未通过。** 没有取得固定投入的成交数量、持仓延续和退出净现金流，Mπ/M* 均未计算。不能把下列工程产物写成可兑现收益或筛选有效。

## 本次实际做了什么

先使用公共 Solana RPC 读取 DBC 程序最新五条签名，按事前规则选择第一条成功且能由官方 IDL 识别池地址的交易。最多检查三条交易；实际一条即定位成功。没有查看涨幅后挑赢家，也没有把 SDK 的 localnet 测试代币当主网候选。

随后安装固定版本 `@meteora-ag/dynamic-bonding-curve-sdk@1.5.12`，使用 SDK 自带的 Anchor coder 解码账户，使用其 RPC 客户端取得同一 context 的池、配置和两种 mint。SDK 安装在本环境耗时约 27 秒、安装 85 个包；这是单次安装观察，不能外推所有部署。依赖锁文件已保留。安装禁用了 lifecycle scripts，原生 bigint 加速未加载而使用纯 JavaScript；没有为消除这个非阻断提示另外重建环境。

报价子探针事前固定 `Q = 0.01 SOL`、ExactIn、50 bps 滑点参数、不使用 referral。Q 仅是工程报价输入，不含网络/账户创建/优先费用，无资金投入，不改变个人账户金额或 W01 规格。还没有选定可验收的退出政策。

**在调用报价之前，真实状态暴露了迁移边界。** 最初账户状态尚未迁移，后续快照已迁移；脚本停止套用 DBC 报价，没有输出貌似有效的买入数量。第三个有界子探针使用 SDK 指令解码器识别迁移交易，并核对目标池 owner。

## 真实对象与时间证据

| 项目 | 结果 |
|---|---|
| Base mint | `8irnNcd5b8UDcoijasSk5M148aJSuQpuqNUPd48K8kN9` |
| Quote mint | `So11111111111111111111111111111111111111112`，wrapped SOL |
| 原 DBC 池 | `Ci3nUi7vQVisQsb6bosAP3NGf64kR8i5RNRqD6h3yPtW` |
| DBC 程序 | `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN` |
| 首次定位交易 | slot `446917776`，识别为 `swap2`，交易 meta.err 为 null |
| 初始账户快照 | slot `446917811`，`isMigrated = 0`，`migrationProgress = 0` |
| 实际迁移交易 | slot `446917936`，识别为 `migrationDammV2`，交易 meta.err 为 null |
| 后续 DBC 快照 | slot `446918342`，`isMigrated = 1`，`migrationProgress = 3`；配置 `migrationOption = 1` |
| 目标 DAMM V2 池 | `AQ7q2SabJfGSTsSZzZhNvj7Mddj3KHjKBEMfJ9SusH3T` |
| 目标池 owner | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`，与 SDK 的 DAMM V2 程序常量一致 |
| 目标池取证 context | slot `446918693` |

完整签名、请求、响应、账户 bytes、配置、原始交易和解码结果见证据包。账户 context slot 是读取状态的上下文，不等于账户最后一次修改 slot。已核对 `446917811 < 446917936 < 446918342`，不能把这三个快照当作同一时间状态。

SDK 版本 1.5.12、参考 IDL metadata 0.2.1 与链上部署代码版本是不同的标识。本次未取得部署代码指纹，因此 `venue_version` 保留未知，程序地址和状态时点已明确。

## 验收状态

| 检查或主张 | 状态与边界 |
|---|---|
| 存在真实 DBC 交易与池账户 | 已取得 RPC 原始响应；owner、IDL 账户类型、池/配置/mint 映射一致 |
| SDK 可以解析该候选状态 | 已执行；另用 SDK 解码首次保存的账户，与前一条薄字段映射交叉核对 |
| DBC→DAMM V2 迁移关系 | 已取得实际迁移指令、源池、目标池和目标 owner；不是仅凭文档推测 |
| 当前入场报价 | UNRUN：在报价调用前识别迁移；不是 quote 函数算错或交易经济失败 |
| 交易构造、程序仿真、买入、持仓、退出 | UNRUN |
| 指定过去时点的完整账户/程序状态 | 尚未取得，不能用当前快照补齐过去 |
| Mπ / M*、100×机会率、人民币收益 | 未测；本次没有经济分母，也没有冻结完整收益政策 |
| 第二模型独立验收 | UNRUN；本次为同一 Codex 执行与交叉检查，不能称双模型独立复核 |
| 信源独立性 | RPC 数据来自一个公共端点；官方 SDK 解码不是第二个链上信源 |

`economic_status = undetermined`。W01 尚未冻结，`membership_status = unresolved`，本次 `analysis_role = development`。若该对象将来属于冻结母体，应保留其成员身份，并记录本次已查看的信息，不能重新称为未查看确认样本。

## 对工程决定的影响

1. **当前账户和迁移取证已能直接使用公共 RPC＋官方 SDK。** 为这一步购买数据或部署 Carbon 没有已出现的必要性；这不保证公共 RPC 适合 W01 大批回填。
2. **迁移适配现在是实际缺口。** 后续继续该候选时，优先接对应 DAMM V2 能力。不能因为最初是 DBC 池，后续所有时点继续调用 DBC 曲线；也不需要重新搜索整套交易平台。
3. **仍缺的是具体状态与持仓测量。** 初始快照只保存了 DBC 池，后续取得的配置/mint 不能未经论证倒填到更早时点。下一工作包先列清目标入场/退出节点的必要状态，复用已保存输入；缺失时只查相应供应商或改成明确的前向取证计划，不写一个假设数据齐全的历史仿真器。
4. **暂不以这个单例启动 W01 批量收益计算。** 身份与迁移路径可复用，完整测量链仍待补齐。候选是否值得投资、Meteora 是否比其他母体更有优势，本次没有证据。

本次选型停止在这个具体结论，不继续安装 Jupiter、Surfpool、Carbon 或新建 skill。下一项可直接交给 Claude：复用证据包中的源池/目标池与状态，核对 DAMM V2 官方 SDK 所需输入，完成一个预先声明时点与 Q 的报价/仿真检查；先报告必要状态的缺口，不默认重建历史。Codex 按该明确主张检查原始输入、状态时点和现金流，尚未完成的持仓/退出不能被提升为 W00 通过。

## 运行与复用

证据包含三个有父子关系的子运行：01 身份，02 状态/报价尝试，03 迁移；各有运行规格、结果与 manifest。正式 RPC 请求分别为 4、1、5，共 10 次；另有最初一次未归入正式原始证据包的 `getVersion` 连通性检查，本轮 RPC 总数为 11。公共端点无 API 付费、无签名广播、无资金投入；本环境计算/网络的分摊成本未计量，不记为已测的零成本。

保存的三个脚本共 184 行，仅承担一次取证、SDK 调用和输出归档，未实现协议数学、路由器、通用采集器或收益引擎。首个 Python 脚本只解码指令 discriminator 并按官方 IDL 映射字段；后续使用现成 SDK coder。无需将这三个探索脚本原样升级为平台。复用时优先取原始资料和 SDK 调用方式。

manifest 由事后汇总脚本根据已保存的规格/响应/命令结果生成，明确区分 process_status 与研究结论；不是在线闸门已经部署的证明。没有把 SDK 本地测试文件的存在记作测试已运行。

证据包为不可变的本次运行记录。重新 live smoke 时使用新目录和新 run_id，勿在原目录重跑后覆盖结果。`npm ci --ignore-scripts --no-audit --no-fund` 可根据锁文件恢复依赖，但重新请求当前状态不会复现本次历史快照。不要把重新取数叫 fixture replay。

## 外部依据

- [固定 commit 的官方 DBC SDK](https://github.com/MeteoraAg/dynamic-bonding-curve-sdk/tree/aa1595c29a0457b23a80cfcf9843a04603954858)：IDL、账户和迁移接口的源码依据。链上对象与迁移事实来自本次 RPC 原始证据。
- [Solana getAccountInfo 文档](https://solana.com/docs/rpc/http/getaccountinfo)：返回账户与 context，配置含 commitment、encoding、dataSlice、minContextSlot。该接口文档没有给出任意历史时点完整状态的选择接口；本次读取成功仅证明所保存 context 下的账户可得，不证明过去状态可得。

Context7 已用于定位 SDK 文档；返回示例的对象包装方式与安装版本类型并不完全一致，实际调用按固定安装版本的类型/源码核对。这是文档检索工具能减少查找、但不能替代版本核验的具体案例。

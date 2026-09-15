# 测量口径冻结规格 v1.19（待冻结）

> **取代 v1.18（§6.0：完整绑定核验下沉为续跑与比较器共用的证据守卫；旧版规则收紧为精确的 (脚本, 规格) 对；
> 续跑遇到证据链问题的处置写明）。§1–§4 判据未变。**
> v1.18 原始字节保存在 `MEASUREMENT_SPEC.v1.18.md`（sha256 `19cc63391cc0dbc28f2fbf4fa3ab7ac838c9097f9800891a94d83a348045bf34`），不追改。
>
> 来源：`audit_v118_20260911/REVIEW.md` 一项 P1。`evidence.py` 自 v1.14 以来首次改动（仅证据核验，停机/连接实现未动）。

> **取代 v1.17（§3：已证不符与后续中断并存时的记法；§6.0：绑定核对补全、启动失败尝试与结果证据链分开；
> 运行证据新增 `run_binding` 记录）。§1–§4 判据未变。**
> v1.17 原始字节保存在 `MEASUREMENT_SPEC.v1.17.md`（sha256 `7cf15793c7626ce725c133ce748920998083bb46b32ef6913f17604a1ada3542`），不追改。
>
> 来源：`audit_v117_20260911/REVIEW.md` 两项 P1、一项 P2。差异见下方「v1.17 → v1.18」。

> **取代 v1.16（§3 编排层：校验的四态与接口故障分类；§6.0：对照验收入口；
> 更正 v1.16 前言中的退出码说法）。§3 的判据本身未变 —— 「接口失败不得冒充链上失败」
> 自 v1.1 起就在 §3，是实现没有做到；本版把校验侧改到符合它。**
> v1.16 原始字节保存在 `MEASUREMENT_SPEC.v1.16.md`（sha256 `2a6c5dcf613d263f8ec9067b047805e0c675a6b6df159896414b0bde4b756606`），不追改。
>
> **结果文件格式有增补**：每条候选新增 `validation_status`（四态），`validation_passed`
> 可以为 `null`（未完成），验收新增 `validation_unavailable`。按 v1.16 及以前产出的
> 真链记录**保留原字节与原分类**，不按本版追改；差异见 `runs/realchain2_20260911/ERRATA_20260911.md`。

> **取代 v1.15（补 §7.5 退出码 2 的一种来源；判据不变）。**
> v1.15 原始字节保存在 `MEASUREMENT_SPEC.v1.15.md`（sha256 `77f27cedf928684aa327625f30d3262c4725c5f94265d9c0bf65418361d66f8e`），不追改。
>
> 首轮真链串行/并行对照（`runs/realchain_20260911/`）中，端点瞬时断连
> （TLS EOF）让并行与续跑在**第一个请求**就抛出未捕获异常 —— 没有 abort 证据，
> ~~退出码也不在本规格定义的 0/1/2/3 之内~~ **〔v1.17 更正，见 C11：两次运行的 `runs.jsonl`
> 实际都记 `exit=1`（Python 未捕获异常的默认退出码）。错误不在于"码不在表内"，而在于
> 它与「1 = 采集完成但判定不通过」撞码，且没有 abort / footer，违反前置失败分类与证据收尾语义〕**。
> 本版把它归入退出码 2。**不改任何测量判据。**

> **取代 v1.14。本版只更正正文中与当前实现不符的陈述，不改任何测量判据。**
> v1.14 原始字节保存在 `MEASUREMENT_SPEC.v1.14.md`（sha256 `f8dc892cca09636989ce919418edeb870601fac47a32a7f4e7f0590c55d189f0`），不追改。
>
> **注意：本版改动了 §3/§4 的字节。** 此前各版都写「§1–§4 判据一字未改」，
> 那是字节层面的事实；但字节未改不等于其中的实现状态标注正确（审查 v1.14 §4）。
> 本版更正其中已过时的「待实现」标注 —— **stage→状态映射、成本公式、计入条件、
> 情景设定这些判据本身一个字都没动**，逐条差异见下方 v1.14 → v1.15。

> **取代 v1.13（改写 §7.3 的连接阶段部分；§1–§4 判据一字未改）。**
> v1.13 原始字节保存在 `MEASUREMENT_SPEC.v1.13.md`（sha256 `32a0805cd2822d6dffb567d982561d446335d7a4c8a28057a865df7826eb8a7f`），不追改。
>
> v1.13 声称「仍有一段管不住：TCP 连接建立本身」。**这个声明范围错了。**
> 实际上 DNS、TCP 建连、TLS 握手**三段**都不在停机监督之内：
> socket 在 `HTTPSConnection.connect()` 完成握手之后才登记（审查 v1.13：TLS 卡住时
> 期限 0.15s，实测 0.539s，登记 0、升级 0）；TCP 建连等满 socket timeout；
> DNS 卡住时**没有任何上界**。本版三段都补上。**不改任何测量判据。**

> **取代 v1.12（改写 §7.3 的监督实现与终止部分；§1–§4 判据一字未改）。**
> v1.12 原始字节保存在 `MEASUREMENT_SPEC.v1.12.md`（sha256 `5da1d9fb4bbd163a1360b0508f66201a3d7318e595e87b00e025d98dd76db050`），不追改。
>
> v1.12 用「每请求一个工作线程 + 20ms 轮询」实现全生命周期监督：
> 线程与登记项的归属会脱节（调用方放弃后无人注销），
> 且运行收尾时会在后台仍有在途请求的情况下撤销兜底；
> `_hard_exit` 又把裸 `os.write(2,…)` 排在 `os._exit` 之前，
> stderr 是写满的管道时照样阻塞（审查 v1.12）。
> 本版换成**在 `connect()` 时登记 socket**，去掉线程与轮询。
> **不改任何测量判据。**

> **取代 v1.11（补 §7.3 的生命周期与终止部分；§1–§4 判据一字未改）。**
> v1.11 原始字节保存在 `MEASUREMENT_SPEC.v1.11.md`（sha256 `e384aa8cba126ce0f8fe59bd4e1fdf7018832c216c2d7d8c8da1087d6ca52058`），不追改。
>
> v1.11 的绝对截止**只从 `urlopen` 返回之后**才开始登记：连接、发送、
> 等响应头这一整段无人看管，响应头分段慢送时同样拖到期限之外；
> 而最终的强制退出**排在一次可能阻塞的日志写之后**，日志锁被占时退不出去
> （审查 v1.11）。本版逐条关闭。**不改任何测量判据。**

> **取代 v1.10（改写 §7.3 的期限部分；§1–§4 判据一字未改）。**
> v1.10 原始字节保存在 `MEASUREMENT_SPEC.v1.10.md`（sha256 `ed62d6aef1869d8474c16f1b0e3c2cd3ac64f9398b2958850da86d47e588166a`），不追改。
>
> v1.10 把「剩余收尾时间压到 socket timeout」当成完成期限，**这是不成立的**：
> socket timeout 是**每次读的不活动超时**，分段慢响应每段都在其内，
> 整段却可以拖到任意长（审查 v1.10 真实 loopback 实测：期限 0.15s，实际 0.387s）。
> 本版补**绝对墙钟截止 + 超期升级**。**不改任何测量判据。**

> **取代 v1.9（补 §7.2/§7.3/§7.6；§1–§4 判据一字未改）。**
> v1.9 原始字节保存在 `MEASUREMENT_SPEC.v1.9.md`（sha256 `bc5ed56995bc67b8db477c55ace65b0e3329abee296e119730bcc9a994756833`），不追改。
>
> v1.9 把停机闸门挂在**逻辑请求层**，底层对 503 的重试直接走 urlopen 绕了过去；
> 收尾秒数只限制「何时批准下一次请求」，不限制已批准请求的等待；
> 请求过硬兜底却装不上时仍继续跑；初始化阶段抛出时闸门仍残留（审查 v19）。
> 本版逐条关闭。**不改任何测量判据。**

> **取代 v1.8（改写 §7；§1–§4 判据一字未改）。**
> v1.8 原始字节保存在 `MEASUREMENT_SPEC.v1.8.md`（sha256 `121308b9902f74679f29bc185daf13949f989ee1d12ce16d81b595a80954df2a`），不追改。
>
> **v1.8 的 §7 把协作式软阈值称作「硬上限」，这是不成立的**（审查 v18）。
> 本版把口径改回诚实：软阈值就叫软阈值，另补内核强制的硬兜底、
> 停机后工作的确定上界、以及所有返回路径的统一清理。**不改任何测量判据。**

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
> 本版对应代码：`pilot_measure.py` sha256 `5cb58ed878751a22396bb4284e10a44b70ab18c7ac7387c5370871207439ba1e`、
> `evidence.py` sha256 `1fe5c43c57420b1213c7f272619f844469bc95a8c39f196d236ef2e9f5f7420d`。
> 测试：9 个入口共 452 项断言，全部退出 0（`runs/realchain2_20260911/tests/`）。
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

**v1.8 → v1.9 的差异**：改写 §7，新增 §7.6/§7.7。§1–§4 判据一字未改。

| # | v1.8 的问题 | v1.9 |
|---|---|---|
| 1 | 协作式软阈值被称作「硬上限」。越线只置 Event，内存仍可继续分配（实测：`max_rss_kb=1` 且 `stopping=true` 之后仍成功分配 8 MiB） | 口径拆开：`soft_thresholds`（协作式，自陈「不阻止继续分配或执行」）与 `hard_backstop`（内核 RLIMIT，与进程内是否检查无关）。新增 `--hard-rss-mb`（RLIMIT_AS）与 `--hard-cpu-s`（RLIMIT_CPU，软限 SIGXCPU 可捕获→有序停机，硬限 SIGKILL） |
| 2 | 安全点只有两处，停机后无上界。实测在槽位扫描发 SIGTERM 后仍执行 16 次 RPC，候选走到 `measured_exit` 并标检查点完成 | 停机后的请求闸门下沉到 `SharedGate.acquire`（RPC 与 Etherscan 共用）：窗口外一律拒绝，收尾窗口内按 `--stop-grace-calls`/`--stop-grace-seconds` 封顶。实测同场景降到 8 次，候选记 `aborted_by_shutdown` 且检查点**不**标完成 |
| 3 | 前置失败提前返回不撤销设施：信号处理器、看门狗线程、HTTP 闸门都留在进程里 | `measure()` 主体置于 `try/finally`，`_release_facilities()` 统一撤销所有返回与异常分支 |

**v1.9 → v1.10 的差异**：补 §7.2（硬兜底安装核验）、§7.3（真实 HTTP 全路径与收尾期限）、§7.6（初始化纳入清理）。§1–§4 判据一字未改。

| # | v1.9 的问题 | v1.10 |
|---|---|---|
| 1 | `apply_hard_limits()` 把 `setrlimit` 失败写进报告角落，`measure()` 不检查。实测：模拟 `setrlimit` 被拒后仍 `exit 0`、`validation_passed=true` | 每项限额 `setrlimit` 后**读回核验**；`hard_limit_problems()` 汇总问题；请求过硬兜底却没装上 ⇒ 前置条件不成立，写证据后返回 **2**，不做任何候选工作 |
| 2A | 停机闸门只在 `SharedGate.acquire()`（逻辑层）。底层对 503 的重试直接走 urlopen，停机后仍发出第二个 HTTP | 新增 `gate_http()`，挂在 `acquire_http()` 上 —— **每一次真实 HTTP**（含重试）都过闸门；排队等待之后**再核一次**。`grace_calls` 对逻辑请求数与实际 HTTP 次数**同时**封顶 |
| 2B | `grace_seconds` 只限制「何时批准下一次请求」。实测收尾 0.02s，请求却拿到近 5s 的 timeout | 剩余收尾时间**压到该次请求的 timeout 上**（`min(原timeout, 剩余)`）。实测 0.02s 收尾窗口下传输层收到 0.0154s |
| 3 | 闸门安装之后、`try` 之前还有 RPC 构造、治理器安装等步骤。构造抛出时闸门残留 | 哨兵先就位，`try` 提到**第一个设施安装之前**，`finally` 逐项撤销已装上的部分 |

**v1.10 → v1.11 的差异**：改写 §7.3 的期限部分。§1–§4 判据一字未改。

| v1.10 的问题 | v1.11 |
|---|---|
| 只把剩余收尾时间压到 socket `timeout`。真实 loopback 实测：期限 0.15s，服务端每 35ms 吐 4 字节，两种场景分别 **0.387s / 0.370s** 后仍成功返回 | 另设**绝对墙钟截止**：到点由定时器 `shutdown(SHUT_RDWR)` + `close()` **底层 socket**，强制打断已阻塞的 `read`。同场景实测降到 **0.158s / 0.166s**，结果判为 `Shutdown: wall_deadline_exceeded`，不再返回成功 |
| 停机若发生在请求**开始之后**，原 timeout 不会被重设 | 在途响应登记到治理器，`request_stop()` 武装定时器；停机之后才登记的立刻关闭 |
| 关不掉的情形无兜底 | 到点关闭后再等 `--stop-escalate-seconds`（默认 5s），仍有在途请求则落一条已 fsync 的证据后**强制退出**（退出码 3） |

**v1.11 → v1.12 的差异**：补 §7.3 的生命周期与终止部分。§1–§4 判据一字未改。

| # | v1.11 的问题 | v1.12 |
|---|---|---|
| 1 | 只在 `urlopen` 返回后才登记在途 ⇒ 连接/发送/收响应头整段无人看管。真实 loopback（响应**头**每 25ms 送 4 字节、共 17 段）实测：期限 0.15s、升级等待 0.05s，仍到 **0.429s / 0.421s**，收头期间登记数 **0**、升级 **0** | **从发出请求之前**登记整个操作生命周期；传输放到工作线程，调用方只等到绝对截止为止。同场景实测 **0.179s / 0.182s**，收头期间登记数 ≥1 |
| 2 | `_on_escalate` 先做一次要拿日志锁并 fsync 的写，再 `os._exit(3)`。锁被占用时退出永远执行不到 —— 最后兜底自己失去上界 | 升级时**先武装一个无条件的强制退出定时器**（`force_exit_after`，默认 1s），再调回调；回调内部改为「独立 fd 直写 + 非阻塞日志尝试 + 裸 `os.write(2,…)`」，每一步都是尽力而为，任何一步都挡不住退出 |

**v1.12 → v1.13 的差异**：改写 §7.3 的监督实现与终止部分。§1–§4 判据一字未改。

| # | v1.12 的问题 | v1.13 |
|---|---|---|
| 1 | 每请求开一个工作线程 + 20ms 轮询。`measure()` 返回 3 时后台线程仍活着、兜底定时器却已撤销；线程后来结束，登记项仍未清除，变成陈旧证据 | 改为在 `connect()` 后**立刻登记 socket**：停机时定时器 `shutdown()` 它，**正阻塞在 read 的调用线程自己**被唤醒。**没有工作线程、没有轮询**。token 归属唯一：谁发起调用谁注销，成功走响应关闭、失败/放弃走异常路径 |
| 1b | `close()` 无条件撤销全部定时器 | 仍有在途请求时**保留升级链**（`_deadline_timer` 之外的都留着）；报告新增 `pending_inflight` / `backstop_armed` |
| 2 | `_hard_exit` 先 `os.write(2, …)`。裸写不等于非阻塞，stderr 是写满的管道时它一样等；实测预期 0.06s 退出、0.4s 后进程还活着 | 先 `os.set_blocking(2, False)` 再试写，设不了或写不进就直接放弃 —— 诊断另有 `<evidence>.escalation` 那条不经 stderr 的路。实测退出码 3 |

**顺带的性能结果**（v1.15 更正，见 C1）：

v1.13 发布时这里写的是非配对测量（200 次、重复 3 轮）与「省下每请求约 2～3.5ms」。
**该数字已撤回** —— 非配对测量被机器漂移主导，重测时同一实现的增量在 −0.9～+2.5ms 间摆动。
改用交替 A/B（同一轮内逐次切换治理器开关，300 对，本机 loopback，基线约 28ms/次）：

| 实现 | 逐对差均值 | 中位数 | 标准差 | 测量期间创建线程 |
|---|---:|---:|---:|---:|
| v1.12（线程 + 轮询） | +0.99 ms | +1.09 ms | 3.54 | 300 |
| v1.13（connect 时记 socket） | +0.11 ms | +0.17 ms | 3.64 | 0 |

n=300 时标准误约 0.2ms：v1.12 的 +1.0ms 显著；v1.13 的 +0.11ms 未测出显著增量。
**「未测出显著增量」不等于「没有成本」**，只说明在该环境、该精度下测不出来。
本地 loopback 的结果**不能用来推断真链瓶颈** —— 真链上的主导项是 RPC 往返与限流。
线程数 300 → 0 是结构事实，不受测量噪声影响；停机发现也不再有 20ms 的轮询粒度。

**v1.13 → v1.14 的差异**：改写 §7.3 的连接阶段部分。§1–§4 判据一字未改。

| 阶段 | v1.13（旧快照实测） | v1.14 | 机制 |
|---|---|---|---|
| DNS（`getaddrinfo` 卡 30s） | 登记 **0**，进程**一直不退出** | 登记 1，升级兜底强制退出（退出码 3） | 操作级登记从 DNS 之前开始；DNS 不可中断，只能靠升级 |
| TCP 建连（socket timeout 3s） | **2.927s**（等满 timeout） | **0.169s** | socket 在 `connect()` **之前**交给句柄，`shutdown()` 打断 |
| TLS 握手（TCP 已建立） | 登记 **0**，**0.822s** | 登记 1，**0.16s** | 握手前 `dup()` 一份作句柄，`shutdown()` 打断 |
| TLS 慢响应体 | — | 0.16s | 句柄沿用那份 dup，不碰 SSLSocket 内部 |
| 未停机 HTTPS 对照（校验开启） | — | 正常返回 `0x1`，无残留登记 | — |
| 不信任证书 | — | 照样 `CERTIFICATE_VERIFY_FAILED` | 证书校验**没有被削弱** |

另修一处归因竞态：`_expired()` 原先只比较时钟，而定时器可能比单调时钟的截止点
早一丝触发 —— 打断后 `read` 带着截断数据返回时时钟判断还没到期，截断的 JSON
被当成正常结果（本轮全量测试中实测出现过 `Non-JSON RPC response`）。
改为**先看是否真的打断过，再看时钟**；同场景连跑 40 次全部正确归因为 `Shutdown`。

**v1.18 → v1.19 的差异**：来源 `audit_v118_20260911/REVIEW.md`。

| # | 问题（审核受控复现） | v1.19 |
|---|---|---|
| K11 | 只改原运行证据的 `run_binding`（参数 / 原语 hash / 让它缺席），`measure` 续跑仍退出 0、跳过两个候选、`evidence_chain_problems=[]`；同一份交付比较器退出 1 —— 完整绑定核对只在比较器里 | 规则只保留一份：`evidence.verify_run_binding()`。`verify_evidence_supports()` 给了检查点绑定时调用它，续跑因此执行同一核对；比较器的 `run_binding_matches` 与结果回溯也改为调用它。问题原因两处一致：`evidence_run_binding_mismatch` / `_field_missing` / `_missing` / `_duplicated`、`checkpoint_binding_field_missing`、`result_doc_primitives_mismatch`、旧版规则的 `legacy_*` |
| K12 | v1.18 的旧版规则按**规格** sha256 判定：v1.18 脚本若被指向 v1.16/v1.17 规格文件、其证据的 `run_binding` 又被删，会被放进较弱的旧版规则 | 旧版规则只对运行头 (脚本 sha256, 规格 sha256) **恰为** v1.16 真链运行那一对或 v1.17 那一对时开放（`evidence.LEGACY_BINDING_RULES`，守卫核对常量等于真实文件 hash）；旧版规则需要结果文件（原语对照 `package_script_sha256`），拿不到即问题 |
| K13 | 续跑遇到证据链问题时「重测还是阻断」没有写明 | 维持 v1.6 起的处置并写明：结果与尝试历史照常保留、候选以带出结果出现在交付里、验收不通过（退出 1）、**不在本检查点内重测**；`acceptance.evidence_chain_action` 写明 `carried_but_blocked…start a new checkpoint`，无问题时为 `none` |
| C13 | v1.18 §6.0 第 6 条「规格为 v1.16/v1.17 的历史运行…走明确的旧版规则」 | 按 K12 收紧，已原位更正 |

**v1.17 → v1.18 的差异**：来源 `audit_v117_20260911/REVIEW.md`。

| # | 问题（审核受控复现） | v1.18 |
|---|---|---|
| K7 | 已证不符之后又被打断，结果只剩「未知」：pair 两侧不符后 getPair 断连 ⇒ `data_missing`/`null`、`failures=[]`、`identity_closure` 缺席；恢复复读代码已变后读余额预算耗尽、入场钱包已有代码后预算耗尽 ⇒ `budget_exhausted`/`null`、`failures=[]` | 校验、身份闭环、恢复核验改为向**候选记录上的累积器就地写入**，每得出一项当场落下；非接口原因打断时只把「未完成」占位换成具体中断原因。**已证不符优先**：候选记 `state_validation_failed`、`validation_status=failed`，打断原因另记 `data.interrupted_after_mismatch{prior_state, mismatch_in}`，原有 `data`（预算说明、停机原因）不动；证据里的校验摘要同样带着不符与 `interrupted_by` |
| K8 | 比较器只核对检查点绑定的 7 个键，漏了 `primitives_sha256` 与 `runtime_params`：改掉或删掉，仍 53 项全过、退出 0 | 检查点绑定按测量程序自己的 `Checkpoint.BINDING_KEYS` **全部**核对，缺键即失败；新增必需参数 `--expect-primitives-sha`、`--expect-runtime-params`；每次运行新增必需检查 `run_binding_matches`（见 §6.0 第 6 条） |
| K9 | 运行证据里没有原语 hash 与 runtime_params，比较器无从核对「这次运行」与检查点在这两项上一致 | `pilot_measure` 在运行头之后写 `run_binding` 记录，内容即检查点绑定的全部键（v1.18 起）。v1.16/v1.17 的历史运行头**不改写**，按明确的旧版规则核对 |
| K10 | 启动即断连后两侧续跑都成功，驱动仍因早先的 abort 拒绝整组（保守拒绝，不是误放行） | 比较器区分**尝试历史**与**结果证据链**：满足严格惰性条件的启动失败尝试记为 `startup_abort`，保留为诊断历史、不要求结果文件/运行头/footer；其余一切运行照旧要求完整，任何结果被复用的运行都必须完整（§6.0 第 8 条） |
| C12 | v1.17 §6.0 第 6 条称「检查点绑定行一致」 | **不完整**：当时只核对 7 个键（K8）。已在第 6 条原位更正 |

**v1.16 → v1.17 的差异**：来源 `audit_v116_20260911/REVIEW.md` 三项 P1。

| # | 问题（审核受控复现） | v1.17 |
|---|---|---|
| K1 | 入场校验取代码遇传输错误 ⇒ `data_missing` 却 `validation_passed=true`：校验函数中途抛出时记录缺席，缺席被当成「不适用 ⇒ 通过」 | 校验开始前先放「未完成」占位；四态 `passed/failed/unavailable/not_applicable`；`validation_passed` 只在全部已开始的校验 passed、或无需校验时为 `true`，未完成为 `null` |
| K2 | 入场 / 出场身份调用、恢复复读遇传输错误 ⇒ `state_validation_failed` | 接口故障（见 §3「接口故障的判定」）记 `unavailable`，候选 `data_missing`，写明阶段、步骤与 `error_kind`；链上回滚仍是证据 |
| K3 | 出场取代码失败后，恢复检查用缺失的原值与真实 `0x`/`0x0` 比较，报出 4 条凭空的 `persisted` | 只复读**实际做过注入**的块；缺注入前原值的项记 `baseline_missing`，不比较；代码、余额逐项独立 |
| K4 | 已到手的真实不符与随后的接口故障并存时，不符证据被丢（§26 并存对照发现，审核未列） | 每取到一项当场判定，两者都保留；有不符即 `failed` |
| K5 | 恢复阶段预算耗尽使 worker 崩溃、候选无结果；解码/预算/停机被改写成状态不符 | 各记各的：`budget_exhausted` / `decode_error` / `aborted_by_shutdown`；只有完整可比的不符才记 `state_validation_failed` |
| K6 | 旧比较器 / 驱动假成功（证据缺 footer、最终运行退出 1、运行记录缺失都退出 0；子运行全失败驱动退出 0，复跑截断清单、覆盖日志） | 新入口 `realchain_tools/compare_runs.py`、`run_compare.py`，见 §6.0 第 6、7 条；历史脚本原字节保留、不再作为验收入口 |
| C11 | v1.16 前言「退出码不在 0/1/2/3 之内」 | **错误**，已在上方原位更正；§7.5 补「退出码 1 也可能来自未捕获异常」 |

**v1.15 → v1.16 的差异**：只补 §7.5 退出码 2 的来源。判据不变。

| 问题（真链实测） | 修复 |
|---|---|
| 启动阶段 `eth_chainId` 或固定 finalized 快照时遇到传输错误（实测 `TLS/SSL connection has been closed (EOF)`），`measure()` 抛**未捕获异常** | 两步都接住 `RpcFailure`，写 `abort`（`reason=endpoint_unreachable`，注明 `stage`），返回 **2**。冻结包 RPC 不重试传输错误，这里也**不替它重试** —— 如实失败，由操作者重跑 |

**已观察、未改动**（留待审核决定）：同一轮里，一次传输错误发生在**出场状态校验的身份调用**上，
候选被记为 `state_validation_failed`（失败项为 `identity_call_failed: <urlopen error … EOF>`）。
该候选已按规则阻断（`validation_passed=false`、检查点不标完成、续跑会重测），信息也没丢；
但「校验失败」与「校验因接口故障而无法完成」是两回事，§3 编排层要求接口失败**不得冒充链上失败**。
是否应改记 `data_missing`，涉及分类语义，本版不擅自改动。
**〔v1.17：审核判定应修，已改，见 K1–K5。首轮那条记录保留原字节与原分类。〕**

**v1.14 → v1.15 的差异**：只更正陈述，不改判据。来源：`audit_v114_20260911/REVIEW.md` §4。
每条都先核对了当前代码再改；核对后**确实未实现**的标注保留不动（见 C4）。

| # | 位置 | v1.14 的陈述 | 核对结果 | v1.15 |
|---|---|---|---|---|
| C1 | §0 v1.12→v1.13 差异 | 「去掉线程省下每请求约 2～3.5ms」及其非配对数据表 | **已撤回**：非配对测量被机器漂移主导 | 换成交替 A/B 配对结果，并注明「未测出显著增量 ≠ 没有成本」、不据此判断真链瓶颈 |
| C2 | §3 标题、stage 20（买入）行 | 「映射待实现」「待实现（现码仍写 `entry_failed_verified`）」 | **已实现**：`pilot_measure.py` 买入 stage≠0 写 `entry_unknown`；`test_step4.py` 覆盖 | 改为已实现 |
| C3 | §3 编排层 `no_mint_by_cutoff` 行 | 「已实现，但**核验待补**（见 §6）」 | **核验已实现**：`first_mint` 的 address/topic0/范围/分页/供给交叉；`test_first_mint.py` 17 项 | 改为已实现 |
| C4 | §3 编排层「pair 无代码 / 储备为 0」行 | 「待实现」 | **确实未实现**：代码里只有供给核验的 `no_code_at_block`，没有储备为 0 的诊断字段 | **保留「待实现」不动** |
| C5 | §4 标题、「G 按实际到达阶段记」 | 「按阶段记录待实现」「现码固定『买入1/卖出1/授权2』」 | **已实现**：`reached_attempts()` 按 `Probe.buy/sell` 控制流给出到达阶段 | 改为已实现 |
| C6 | §4「缺 baseFeePerGas 记未知」 | 「〔待实现〕」 | **已实现**：`gas_cost()` 在 base fee 缺失时返回 `unknown` | 改为已实现 |
| C7 | §6 标题及三条待办 | 「下一步要补的核验（尚未实现，列此备查）」 | **均已实现**，与 §5 状态表冲突 | 标题改为「核验项与真链对照条件」，三条改为已实现并注明位置 |
| C8 | §6.0 第 5 条 | 「资源项只有采样」 | 与 §7 冲突：现有 VmHWM 实测峰值、软阈值、内核 RLIMIT 硬兜底 | 改为指向 §7，并说明**离线已测、真链上尚未经受** |
| C9 | §7.3 绝对截止一段 | 「定时器 `shutdown(SHUT_RDWR)` + `close()` 底层 socket」 | 与同节后文「只 shutdown」冲突；实测 `close()` 打断不了阻塞中的 `connect()` | 改为分阶段句柄、**只 shutdown** |
| C10 | §7.5 退出码 3 | 「**有序停机**…检查点完整，放宽限额后可续跑」 | **错误**：退出码 3 也来自强制终止（升级回调、`_hard_exit`）；DNS 卡死场景实测即为强制终止的 3 | 拆成两类，给出区分依据：**必须读证据与检查点，不能只看退出码** |

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

## 3. 失败与未知分类

### 探针 stage → 状态（唯一权威映射）

| stage | §5 状态 | Z/M | 实现状态 |
|---|---|---|---|
| 0（买入） | 入场成功 | 记实际增量 | 已实现 |
| 0（卖出） | `measured_exit` | 记增量，但 `economic_eligible=false` | 已实现 |
| 10 / 11 | `model_unsupported` | 均未知 | 已实现 |
| 12 | `execution_reverted_unknown` | 均未知 | 已实现 |
| **20（买入）** | **`entry_unknown`** | 均未知 | 已实现（v1.15 更正标注，见 C2） |
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
| 窗口截止前无 Mint | `no_mint_by_cutoff` | 已实现，含核验（v1.15 更正标注，见 C3） |
| 槽位不可解 | `model_unsupported` | 已实现 |
| RPC/接口失败 | `data_missing`（**不得冒充链上失败**） | 已实现；校验与恢复阶段 v1.17 起符合（K1–K3） |
| 超预算 | `budget_exhausted`（该 HTTP 未发出） | 已实现；恢复阶段 v1.17 起不再让 worker 崩溃（K5） |
| 解码失败 | `decode_error` | 已实现 |
| 有序停机打断 | `aborted_by_shutdown` | 已实现 |
| 状态校验有完整可比证据且确实不符 | `state_validation_failed` | 已实现；v1.17 起**只有**这一种情形（K2、K5） |
| 退出快照晚于 finalized | `right_censored` | 已实现 |
| pair 无代码 / 储备为 0 | 诊断字段，不单独定 M=0 | 待实现（v1.15 已核对：确实未实现，见 C4） |

**C1**：通用 revert 永不改名蜜罐或不可卖。**C2**：过程字段各存各的，不用互斥字符串覆盖。

### 校验的四态（v1.17）

入场校验 `state_validation`、出场校验 `state_validation_exit`、恢复核验 `restore_check`
各自记 `status`：

| status | 条件 | `passed` |
|---|---|---|
| `failed` | 有完整可比的证据且确实不符（`failures` 非空）。与接口故障**并存时两者都保留**，仍是 failed | `false` |
| `unavailable` | 开始了但没做完（`unavailable` 非空）：接口故障、缺注入前原值、预算/停机/解码打断 | `null` |
| `passed` | 做完且没有不符 | `true` |
| `not_applicable` | 该路径根本不需要这项校验（如 `no_mint_by_cutoff` 不走入场） | —（不产生记录） |

候选级汇总 `validation_status`：任一 failed ⇒ `failed`；否则任一 unavailable ⇒ `unavailable`；
否则有已做的校验 ⇒ `passed`；一项都不需要 ⇒ `not_applicable`。
`validation_passed` 对应 `false` / `null` / `true` / `true`。

**未完成不是通过**：`unavailable` 与 `failed` 一样阻断检查点「完成」、经济资格、验收，
续跑时**重测而不跳过**。验收把两者分列：`validation_failed`（不符）、`validation_unavailable`（未完成）。

候选状态：`failed` ⇒ `state_validation_failed`；`unavailable` ⇒ `data_missing`（`data.validation_unavailable`
或 `data.restore_unavailable` 写明阶段、步骤、`error_kind`），但已有更具体的原因
（`aborted_by_shutdown` / `budget_exhausted` / `decode_error`）时**保留原因**。
已发生的买卖阶段与成本照常保留（§4 G2）。

**已证不符 + 后续中断（v1.18，K7）**：任何一项校验里已有完整可比的不符，之后无论被接口故障、
预算、停机还是解码异常打断，该项仍是 `failed`，候选记 `state_validation_failed`；
打断原因记在该项的 `unavailable`（`error_kind` 为 `transport`/`budget`/`shutdown`/…）与 `interrupted_by`，
若候选原本已被记成中断状态，另写 `data.interrupted_after_mismatch = {prior_state, mismatch_in}`，原有 `data` 保留。
「已证」只看已经落进 `failures` 的结论；没有不符时，中断照旧按各自原因记（上一段）。
为此校验、身份闭环、恢复核验都向候选记录上的累积器**就地写入**，异常路径只追加中断原因，不再换成空记录。

**接口故障的判定**：冻结包 `RpcFailure` 的 `kind` 为 `transport` / `http` / `protocol` /
`response_limit` / `missing_result`，或 `kind=rpc` 且错误消息不含 `revert` —— 链没有给出可比的答案。
`kind=rpc` 且含 `revert` 是链的答案（证据）；`budget` / `forbidden_method` / `abi` 不是接口故障，交上层按各自原因记。
校验在第一处接口故障处停止，其后步骤记为未做（未知），不推断。

**恢复核验**只复读实际做过状态注入的块（买入前被阻断的候选没有注入，不做恢复核验）；
每个地址的代码与余额逐项比较，缺哪项注入前原值就只有那项记 `baseline_missing`、不比较。

## 4. 成本口径

```
A = 0.05 ETH
R = 卖出调用中 WALLET 原生余额实际增量（未减 gas）
I = A + G          M = R / I          本路径净现金流 = R − A − G
```

**G 必须按实际到达的阶段记**〔已实现：`reached_attempts()`；v1.15 更正标注，见 C5〕：

| 尝试 | 计入条件 |
|---|---|
| 买入 swap | 每次实际发出的买入尝试（含失败） |
| 卖出 swap | **仅当执行到达 swap**。stage 10 在授权前返回、stage 11/12 可能未到 swap，此时不得计 |
| `approve` | 按**实际到达的授权次数**。`doApprove=false` 或 stage 10 提前返回时为 0 |
| gas 单价 | `baseFeePerGas(该块) + tip`；**缺 baseFeePerGas 记未知，不记零**〔已实现；v1.15 更正标注，见 C6〕 |

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
| 串行 vs 两路并行一致性（真链） | ◐ 8 个**开发**候选同快照一致（审核 v1.16 独立确认，工程观察已关闭）；正式规模未做 | §6、`runs/realchain2_20260911/` |
| 校验四态、接口故障不冒充不符（v1.17） | ✅ 已实现 | `pilot_measure.py`、`test_audit_followup.py` §26 |
| 对照验收入口：比较器退出码受全部必需条件约束、驱动不丢历史且反映子运行失败（v1.17） | ✅ 已实现（受控） | `realchain_tools/`、`test_realchain_tools.py` |
| 已证不符 + 后续中断两者都保留（v1.18） | ✅ 已实现 | `pilot_measure.py`、`test_audit_followup.py` §27 |
| 比较器全量绑定核对、运行证据 `run_binding`、惰性启动失败与结果证据链分开（v1.18） | ✅ 已实现（受控） | `realchain_tools/compare_runs.py`、`test_realchain_tools.py` |
| 完整绑定核验下沉为共用证据守卫，续跑与比较器一致（v1.19） | ✅ 已实现（受控） | `evidence.verify_run_binding`、`test_audit_followup.py` §28 |
| 资源峰值（内核 VmHWM 实测，非采样） | ✅ 已实现（v1.8 新增） | `evidence.rss_peak_kb`、`test_audit_followup.py` §16 |
| 资源硬上限与有序停机（RSS/CPU/墙钟/信号） | ✅ 已实现（v1.8 新增） | `evidence.ResourceGovernor`、§7 |
| 新增 CLI 选项不得让程序化调用者崩溃 | ✅ 已实现（v1.8 新增） | `pilot_measure.OPTIONAL_DEFAULTS`/`opt()`、§17 |

> **状态校验通过 ≠ 跨期持仓充分。** `validate_candidate_state` 只证明
> 「注入前虚拟地址干净、协议身份正确、所用区块可核验」，与 §2 的 H1 是两件事，
> 代码里随每条候选落盘一句 `state validation only; NOT evidence of
> cross-period holding adequacy`，不得相互替代。

**⬜ 的条目未实现前，本规格不得用于正式冻结或 300 样本。**

## 6. 核验项与真链对照条件

### 6.0 串行 / 并行真链对照的成立条件（v1.5 补入）

1. 两次运行必须绑到**同一 finalized 状态块**：用 `--pin-finalized <块号>:<块hash>`，
   两次各用**独立检查点**。共用检查点会让第二次直接跳过候选，
   各自新建又会各取各的 finalized —— 两条路都不构成同快照对照。
2. 比较**状态、金额、分类、身份判定**；耗时与请求顺序允许不同。
3. 每候选的 Etherscan 次数按候选归集（`counts_by_candidate`），
   不得用共享计数器的差值 —— 并行重叠会把别的候选算进来。
4. 区块缓存跨 worker 共享，命中逐条落 `block_cache_hit`（记 `fetched_by_worker`
   与 `used_by_worker`）。对照时缓存口径以这些记录为准。
5. 资源约束见 §7（v1.15 更正，见 C8）：内核 VmHWM 实测峰值、协作式软阈值、内核 RLIMIT
   硬兜底、有界停机。这些**离线已测**，但**尚未在真链运行中经受**；在真链对照留下
   实际证据之前，不得表述为「资源上限已在真链验收」。
   〔v1.17 注：第二轮真链对照中硬兜底已装上并读回核验，但**没有触发任何越线**，
   越线后的真链表现仍只有离线证据。〕
6. 〔v1.17〕**验收入口是 `realchain_tools/compare_runs.py`，退出码 0 当且仅当全部必需检查都存在且通过**：
   清单里每个声明的运行恰好一条、没有来历不明的条目、两侧检查点独立且各自一致；
   两侧最终运行退出 0；每次运行的结果文件存在、证据 `complete` 且恰有一个 `run_footer`、无 `abort`、
   证据只含该运行、footer 的验收与结果文件一致、并行路数与侧别相符；
   所有运行的脚本/证据模块/规格/样本/台账/快照/参数彼此一致且等于显式给出的期望值，检查点绑定行一致
   〔v1.18 更正，见 C12：v1.17 实际只核对了 7 个键；现按 `Checkpoint.BINDING_KEYS` **全部**核对，
   含 `primitives_sha256` 与 `runtime_params`，并与显式期望 `--expect-primitives-sha` / `--expect-runtime-params`
   比对，缺键即失败〕；每次完整运行的证据与检查点绑定逐键一致（`run_binding_matches`）：
   v1.18 起逐键比对证据里的 `run_binding` 记录；规格为 v1.16/v1.17 的历史运行没有这条记录，
   **只对这两个版本**走明确的旧版规则 —— 原语 hash 对照结果文件里运行结束时独立计算的 `package_script_sha256`，
   `runtime_params` 逐键对照运行头 `params`；其它版本缺 `run_binding` 一律失败，不跳过
   〔v1.19 更正，见 C13/K12：旧版规则按运行头 (脚本, 规格) **精确对**判定，不再只看规格；
   规则本身在 `evidence.verify_run_binding`，**续跑守卫与比较器共用**，见 K11〕；
   样本自洽；最终累计结果一候选恰好一条且与样本逐项一致、验收清单全空、每条 `validation_passed` 恰为 `true`、
   经济资格与测量语义仍为 `false`；每条最终结果回溯到本链检查点的完成尝试与本链某次运行的 `candidate_result`
   （hash、run_id、绑定、带出标记与来源一致）；两侧同快照、同候选集、除耗时/RPC 次数/带出标记外逐字段一致，
   每候选「RPC + 缓存命中」两侧相等。**空集合不算通过**，必需检查缺席即失败。报告路径已存在则拒绝写。
7. 〔v1.17〕**驱动是 `realchain_tools/run_compare.py`**：每次全新执行新建 `runs/<name>_<attempt_id>/`；
   续跑必须显式 `--continue-dir … --resume serial|parallel`，沿用该目录的检查点、新标签、清单只追加、
   所有输出独占创建；两侧最后一次运行都退出 0（给 `--compare` 时比较器也退出 0）才返回 0。
   `runs/realchain2_20260911/run_compare.sh` 与 `compare.py` 保留原字节，**不再对交付目录执行**。
   〔v1.18〕期望的原语 hash 与 `runtime_params` 由 `pilot_measure.primitives_sha256()` / `runtime_params_of()`
   按驱动将传给子进程的同一组参数推导，写进 `driver.json`；续跑不接受改动 `--extra`。
8. 〔v1.18〕**尝试历史 ≠ 结果证据链**。一次运行满足以下**全部**条件时记为 `startup_abort`：
   清单退出码与 abort 原因为 (`endpoint_unreachable`, 2)、(`budget_exhausted`, 2) 或 (`shutdown_during_startup`, 3)
   之一，且 abort 阶段为 `chain_id` / `snapshot`；证据只含该运行、结构无损；没有运行头、`run_binding`、
   候选记录、`checkpoint_state`、Etherscan 记录；RPC 全在启动阶段且不属于任何候选；
   检查点里没有任何尝试引用它的 `run_id`；它不是该侧最后一次运行。
   这样的尝试保留为诊断历史，只核对上述条件（`startup_abort_inert`），不要求结果文件/运行头/footer，
   也不参与绑定一致性（它没有运行头）。**其余一切运行照旧逐项要求完整**；最终结果只能回溯到完整运行。
   不满足条件的失败尝试（例如首遍有候选完成、其结果被续跑带出）不能被排除或忽略。


### 6.1 核验项（v1.15 更正：以下均已实现，见 C7）

- **首次 Mint**〔已实现：`first_mint`、`_validate_log`；`test_first_mint.py`〕：校验 `address` /
  `topic0` / 块号在请求范围内 / 分页是否打满；「无 Mint」结论附链上状态交叉核验
  （截止块 `totalSupply` 与首次性前后供给）与原始响应。
- **候选级状态**〔已实现：`validate_candidate_state`、`verify_wallet_not_persisted`、
  `snapshot_block`；`test_step3.py`、`test_e2e_blocking.py`〕：逐候选钱包代码与余额原值及恢复检查、
  协议身份（factory/router/WETH/pair）与代码 hash、入场与退出块的 hash 与相邻时间戳落盘、
  结束时块 hash 复读。
- **退出块定位**〔已实现：二分定位 + `snapshot_block(bracket_target=…)`；`test_step3.py`〕：
  证明左右时间戳包围目标、核验最终块与其前一块。当前实现不使用时间插值，
  因此不存在「用平均出块时间替代精确定位」。

## 7. 资源约束与停机策略（v1.9 改写）

### 7.1 峰值的口径

`rss_peak_kb()` 取内核高水位 **`VmHWM`** —— 实测，不是采样。
证据里 `resource` 同时保留 `rss_kb`（采样）与 `rss_peak_kb`（峰值），**不得混用**。

### 7.2 软阈值 ≠ 硬上限

**必须分清，措辞不得含糊：**

| | 软阈值 | 硬兜底 |
|---|---|---|
| 参数 | `--max-rss-mb` `--max-cpu-s` `--max-wall-s` | `--hard-rss-mb` `--hard-cpu-s` |
| 机制 | 看门狗巡检 → 置停机标志 → **各处协作检查** | 内核 `RLIMIT_AS` / `RLIMIT_CPU` |
| 能否阻止继续分配/执行 | **不能** | 能 |
| 触发点 | 可控（安全点/请求闸门） | **不可控**（任意位置 MemoryError；SIGKILL） |
| 证据 | 承诺结构完整 | **只承诺已 fsync 的前缀可读** |

软阈值应设得低于硬兜底，让有序停机先发生；硬兜底只是最后一道。

**请求了硬兜底就必须装得上。** 每项 `setrlimit` 之后立即 `getrlimit` **读回核验**；
任一项失败（含 `resource` 模块不可用）即 `hard_limit_problems()` 非空 ⇒
**前置条件不成立**，写证据后返回退出码 2，不做任何候选工作。
把失败塞进报告角落然后继续跑，等于使用者要的控制没生效却当作具备。
`limits()` 分 `soft_thresholds` / `hard_backstop` / `stop_grace` 三块，各自带 `kind` 自陈。

`RLIMIT_AS` 限的是**地址空间**，不等于 RSS，作为兜底偏保守。
`RLIMIT_CPU` 软限发 `SIGXCPU`（可捕获 → 转为有序停机），硬限（软限 + 5s）为 `SIGKILL`。

### 7.3 停机后的工作有确定上界

请求闸门下沉到 `SharedGate.acquire()` —— **RPC 与 Etherscan 共用这条路径**。
停机之后：

* **收尾窗口之外**：任何请求立即抛 `Shutdown`。主测量工作**立刻**停止发起。
* **收尾窗口之内**（`gov.winddown()`，用于注入后复读/恢复核验）：
  按 `--stop-grace-calls`（默认 16）与 `--stop-grace-seconds`（默认 15）封顶。

闸门挂在**两层**，缺一不可：

* `gate_request()` —— 逻辑请求层（`SharedGate.acquire`，RPC 与 Etherscan 共用）；
* `gate_http()` —— **每一次真实 HTTP**（`acquire_http`），**含 `V.RPC` 内部对
  429/502/503/504 的重试**。只挂逻辑层的话，重试直接走 urlopen 就溜过去了。

`grace_calls` 对两种口径**同时**封顶（`winddown_logical_requests` /
`winddown_http_requests` 分开报）。排队等待之后**再核一次** ——
排在队里的请求不得带着过期的许可发出。

**收尾秒数是完成期限，不只是批准期限。** 两条机制叠加，缺一不可：

1. **socket timeout 收紧**：剩余收尾时间压到该次请求的 `timeout`
   （取 `min(原timeout, 剩余)`）。它管住的是「一直没有数据」。
2. **绝对墙钟截止**：`timeout` 是**每次读的不活动超时**，不是整段响应的完成
   期限 —— 服务端每 35ms 吐一小段，0.15s 的 timeout 永远不会触发，整体却能
   拖到任意长（实测 0.387s）。所以整次操作登记到治理器，到点由定时器对
   **当前阶段的可中断句柄只做 `shutdown()`**（句柄随阶段替换，见下方表格），
   强制打断已阻塞的读或建连；仅调 `response.close()` 不够，实测关不掉正在进行的读；
   对 socket 调 `close()` 也不行，实测打断不了阻塞中的 `connect()`（v1.15 更正，见 C9）。
   期限过后即使读到数据也判 `Shutdown: wall_deadline_exceeded`，结果不可用。

**监督必须从发出请求之前开始，覆盖整个生命周期。** 只在拿到 response
之后才登记是不够的：连接、发送、等响应头都在那之前，而响应头本身也可以
分段慢送（每段都在 socket 不活动超时之内），此时登记表是空的，
截止定时器无从中断、升级也看不到任何在途项（实测 0.429s / 期限 0.15s）。

做法：**从 DNS 之前**就把整次操作登记为一个在途项，其关闭器作用于
「当前阶段能打断的那个句柄」。句柄随阶段推进而替换：

| 阶段 | 句柄 | 能否从另一线程打断（实测） |
|---|---|---|
| DNS | 无 | **否** —— `getaddrinfo` 不可中断 |
| TCP 建连 | 原 socket（在 `connect()` **之前**交出） | `shutdown()` 能（0.151s）；**`close()` 不能**（等满 timeout） |
| TLS 握手 | 原 socket 的 `dup()` | 能（0.153s）；原 socket 已被 `wrap_socket` 接管，不能再对它操作 |
| 响应头/体 | 同上（plain socket 或那份 dup） | 能 |

停机时定时器对句柄 `shutdown()`，**正阻塞的调用线程自己**被唤醒 ——
不额外开线程、不轮询，稳态开销落在测量噪声内。

**只用 `shutdown()`，不用 `close()`**：实测 `close()` 打断不了阻塞中的 `connect()`。
TLS 起一直用 dup 作句柄，是为了不在另一线程里改动 SSLSocket 的内部状态。

**DNS 的上界来自升级，不是干净的中止**：没有可打断的句柄，只能等升级触发
强制退出，上界 = `grace_seconds + escalate_after + force_exit_after`，
且结局是**进程退出**（退出码 3），不是当前请求抛 `Shutdown`。

**登记项的归属唯一**：谁发起这次调用谁负责注销 —— 成功时随响应关闭注销，
失败或放弃时在异常路径注销。（上一版由工作线程持有、调用方放弃后无人注销，
线程结束后登记项还在，变成可能引发错误升级的陈旧证据。）

**归因依据实际发生的事，而不是时钟读数。** 一次请求若被我们打断过，
就判为 `Shutdown: wall_deadline_exceeded`（并注明阶段），不论时钟是否恰好到点 ——
否则定时器早一丝触发时，截断的响应会被当成正常结果交出去。

**运行收尾时不得撤销尚有用的兜底**：还有在途请求就保留升级链，
否则"运行已收尾"与"后台还卡着一个请求"会同时成立而兜底已经没了。

绝对截止**覆盖已经开始的请求**：停机若发生在请求开始之后，`request_stop()`
武装定时器；停机之后才登记的在途请求立刻关闭。

**超期升级**：到点关闭之后再等 `--stop-escalate-seconds`（默认 5s），
若在途请求**仍未结束**（说明线程卡在 I/O 里、关闭没能解开），强制退出（退出码 3）。

**最终终止不得依赖任何可能阻塞的写。** 升级时**先武装一个无条件的强制退出
定时器**（`force_exit_after`，默认 1s），然后才调回调 —— 回调里要写日志、
写 stderr，这些都可能卡住（拿不到日志锁、fsync 卡住、管道写满），
一旦卡住 `os._exit` 就永远执行不到，"最后兜底"本身失去上界。
退出的时机不能取决于回调能不能跑完。

回调内部同样按此原则：独立 fd 直写 `<evidence>.escalation`（不碰日志锁）→
非阻塞的日志尝试（拿不到锁就跳过）→ 输出 → `os._exit(3)`，
每一步都包在 try 里，任何一步失败或阻塞都挡不住退出。

**"不阻塞"必须落到写本身，不能只靠 try/except。** 裸 `os.write(2, …)` 不是
非阻塞写：stderr 若是写满的管道，它照样等在那里，而 `try/except` 打断不了
一个仍在等待的写。所以最终退出前的输出要先 `os.set_blocking(fd, False)`，
设不了或写不进就放弃输出 —— 诊断信息另有不经 stderr 的路。

强制终止时**不承诺 footer 完整** —— 与硬兜底同一边界：
已 fsync 的前缀可读，未完成部分交给检查点与恢复机制。

未停机时不改动任何 timeout，也不会强制关闭任何响应。

因此「信号之后还会发多少次请求、最多再等多久」都由预算决定，
**不取决于安全点埋得够不够密，也不取决于看门狗的巡检频率**。
报告里 `stop_latency_s` 与 `requests_refused_or_graced_after_stop` 给出实测值。

已发出的请求正常完成并写配对的 `rpc_end`；被闸门拒绝的请求未发出，同样写配对记录。

### 7.4 停机后的账

| 情形 | 记法 |
|---|---|
| 停机前已完成 | 正常状态，检查点标完成，续跑跳过 |
| 停机时正在进行 | `aborted_by_shutdown`，**不算完成**，检查点不标完成，续跑重做 |
| 收尾被宽限预算截断 | `restore_check.interrupted_by="shutdown"`，状态仍是 `aborted_by_shutdown`，**不改写成状态校验失败** |
| 停机时还没轮到 | 逐个进 `acceptance.not_started`（含原因） |
| 启动阶段即停机 | 仍写交付记录，全部候选进 `not_started`，退出码 3 |

`set_complete=false`、`process_completed=false`、`validation_passed=false`。

### 7.5 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部完成且验收通过 |
| 1 | 采集完成但判定不通过（**也可能是未捕获异常**：Python 默认以 1 退出，见下）〔v1.17 补〕 |
| 2 | 前置条件不满足（缺凭据、链身份不符、样本不自洽、快照不符、**启动阶段端点不可达**〔v1.16〕） |
| **3** | **已停机，但未必有序** —— 见下表区分（v1.15 更正，见 C10） |

**退出码 3 有两个来源，不能只看退出码判断检查点是否可用：**

| 来源 | 代码位置 | 运行尾 `run_footer` | 结果 JSON | 证据 |
|---|---|---|---|---|
| **有序停机**：软阈值越线、SIGTERM/SIGINT/SIGXCPU、启动阶段即停机 | `measure()` 的三处 `return 3` | **有** | **有**，`acceptance.shutdown.stopped=true` | 该运行 `read_evidence(…).complete == true` |
| **强制终止**：升级回调、无条件 `_hard_exit` | `_on_escalate` 与 `ResourceGovernor._hard_exit` 的 `os._exit(3)` | **无** | 通常无 | 只有已 fsync 的前缀；可能有 `<evidence>.escalation`（尽力写入，**不可依赖其存在**） |

判定步骤：读取该 `run_id` 的证据 —— 有 `run_footer` 且 `complete == true` 才按有序停机处理；
否则一律按强制终止处理：检查点只有已落盘的尝试记录可信，未完成的候选交给续跑重做。
DNS 卡死由升级兜底带走的场景（§7.3）就是强制终止的退出码 3。

其它异常退出不在上表内：`RLIMIT_CPU` 硬限触发 `SIGKILL`（退出码非 3）；
`RLIMIT_AS` 越界是任意位置的 `MemoryError`，退出码不可预期。

**退出码 1 同样不能单独读**〔v1.17，见 C11〕：未捕获异常以 1 退出，与「判定不通过」撞码。
首轮真链的并行与续跑就是这样（`runs.jsonl` 记 `exit=1`、stderr 有 traceback、证据无 abort/footer）。
区分依据与退出码 3 相同：该运行有 `run_footer` 且证据 `complete` 才是「采集完成、判定不通过」。

**停机绝不报告为成功。** 前置失败保留自己的退出码 2，**不伪装成有序停机**。

### 7.6 设施必须统一撤销

闸门、看门狗、信号处理器都是**进程级**的。

哨兵（`gate=None` / `gov=None` / `gate_installed_by_us=False` / `_prev_signals={}`）
**先就位**，`try` 提到**第一个设施安装之前** —— 只把已完成初始化之后的部分
纳入保护是不够的：闸门装上了、`V.RPC` 构造却抛出，闸门就留在进程里了。
`_release_facilities()` 按哨兵逐项撤销，幂等，覆盖**所有**返回与异常分支。
（CLI 单次运行靠进程退出回收，掩盖了这个问题；程序化调用不会。）

### 7.7 新增运行选项不得让程序化调用者崩溃

`OPTIONAL_DEFAULTS` 登记全部可选参数及默认值，`opt()` 统一读取。
必须有守卫核对它与 `argparse` 默认值一致，并核对最小 `Namespace` 能跑完。
理由：加一个 CLI 选项就让自建 `Namespace` 的调用者 `AttributeError` 崩掉，
而崩掉的入口显示「通过 0 / 失败 0」，**看起来像没跑而不像失败**。

## 8. 本规格不覆盖

交易被打包与排序；自身买入对退出时池状态的影响；30 天内到账变化、代理升级、
黑白名单变更；该代币在 V3/其他 DEX 是否已有池。

# 全量交付独立审核 · 2026-09-10

**结论：不通过当前交付验收；先修离线可复现的阻断，再做真链串行/两路并行对照。正式冻结和300样本保持关闭。**

此次只审核：读取当前实现、规格、测试和既有真实请求证据；未修改交付实现/测试/冻结包，未新增网络请求。新增独立反例、复跑日志、源文件hash及审查报告存本目录。不要将本目录的 `.audited.py` 源码快照作为新实现运行。

## 已确认的进展

- 首次性增加前后totalSupply验证、递归不再错误继承全局供给；此前A/B主要逻辑已修。
- 入场/退出的fresh复读、父链接失败阻断、token0/token1/getPair闭环、买入stage20归未知、stage12授权次数区间已落地。
- 原v3包verify_package退出0；历史v2至v7运行所绑定规格完整SHA-256均能匹配保留版本。见package.log、version_bindings.json。
- v7有334条记录，其中RPC begin/record/end各107：105次候选＋2次共享；经济资格仍关闭。它证明当时单候选版本的那次执行，不验证后来新增的并行/恢复实现。
- 新规格与产物继续区分注入模拟和持仓充分，经济统计未被放开。

## 实际测试复跑

| 当前原始测试入口 | 退出码 | 结果 |
|---|---:|---|
| test_evidence.py | 0 | 29/0 |
| test_first_mint.py | 0 | 17/0 |
| test_step3.py | 0 | 27/0 |
| test_step4.py | 0 | 18/0 |
| test_e2e_blocking.py | 1 | Namespace缺parallel，断言前中断 |
| test_resume.py | 1 | Namespace缺parallel，断言前中断 |
| test_parallel.py | 0 | 17/0 |

不能把历史各版通过数相加，称当前组合172项全过。为继续审核，另用**仅在审计进程补默认parallel=1**的适配器复跑后两项，分别41/0和23/0；没有编辑原测试，日志标为compat-only。适配后通过也不抵消下述反例。

## P0-1 工作线程失败可被主线程验收为成功

位置：pilot_measure.py:803–879（线程启动/join及最终验收）。

Thread中的异常不传播给主线程；最终只检查results已有项，没有核对“声明集合 = 本次结果 ∪ 已完成且证据有效的恢复结果”。独立反例：两个候选、parallel=2，共享预算100耗尽，工作线程在恢复检查中再次触发预算异常退出；主线程exit=0、results=[]、n=0、validation_passed=true。另注入worker初始化失败，也得到同样假成功。

修复要求：收集所有worker异常并统一非零退出；每个声明候选必须恰有一个有效终态或可验证恢复结果，未处理/线程丢失明确计入未完成。增加预算耗尽、初始化失败、落盘失败、恢复检查异常的完整执行与产物断言。process_completed语义说明不能替代集合完整性。

## P0-2 blk闭包绕过worker隔离，统计与请求身份失真

位置：pilot_measure.py:516–526、handle、worker。

blk引用measure外层rpc和共享_bc，不引用handle参数rpc。因此worker的eth_getBlockByNumber仍经过同一个外层RpcTap/底层RPC：共享records、请求ID和drain游标；真实I/O释放线程后存在竞态。_bc也跨worker共享，缓存命中无独立消费记录。

反例：最近一次2候选模拟实际145次RPC，doc只报49；47条worker区块请求candidate=None（线程调度下计数可略变，遗漏机制不变）。原test_parallel只对candidate非空检查归属，恰好跳过这些请求。RpcTap的pending_id也是实例局部，外层tap与worker tap能产生同一(run,worker,pending_id)，独立反例记录了重复键。

修复要求：块读取显式注入当前worker/candidate上下文；共享缓存若保留，需同步、绑定块身份、记录命中及原始证据来源；请求/尝试ID全局唯一。按实际transport记录重算总数、分worker/候选/阶段数，不仅判断标签里出现了0和1。同一handle函数并不保证依赖对象或副作用一致。

## P0-3 SharedGate不是全局HTTP额度闸门

位置：evidence.py:RpcTap.request/call、SharedGate；pilot_measure.py:etherscan和worker调度。

- gate.acquire仅在外层逻辑调用前执行一次，V.RPC内部重试不经过gate。用真实V.RPC＋模拟HTTP 503→成功，max_calls=1，实际发2次HTTP，gate仍为1。
- Etherscan在gate外独立sleep；两路可叠加速率，调用/递归/超时不纳入共享预算。
- 启动2次共享RPC也在gate创建前。worker各自的max_seconds从创建起算，不是同一全程截止。
- acquire检查时间后预约未来时刻，等待结束不再检查。反例0.01秒预算，第二次请求在约0.05秒后仍获准发出。
- 当前入口没有复用已有RLIMIT_AS等进程资源上限，只在少数阶段读取RSS/CPU；不是周期峰值采样或硬限制。不要把原RT-A运行器的768MiB约束归给此入口。

应在每次transport尝试处统一计数/限速/截止，分别管理RPC与Etherscan供方速率及全局额度；重试必须计入。耗尽要终止并保留未完成状态。资源限制和周期采样需在实际运行入口接入，不能通过提高worker自身rps替代验收。

## P0-4 检查点不绑定实际测量参数及全部实现依赖

位置：evidence.py:Checkpoint.BINDING_KEYS；pilot_measure.py:486–500。

slot_limit/diagnostics未加入绑定，测量原语verify_capabilities.py hash也未加入；仅记录pilot/evidence源码和规格文件名义hash不够。独立反例：先slot_limit=2完成，再改0、同一检查点，仍exit0并跳过[1,2]。这会把不同实际测量配置混在一起。

绑定canonical有效测量配置、原语/运行时代码等依赖；调度参数与测量参数分开，允许事先声明的parallel变化不意味着允许slot_limit或diagnostics变化。恢复前对所有必要绑定缺失/不匹配严格拒绝。

## P0-5 检查点有丢行窗口，且恢复没有完整结果集

位置：evidence.py:Checkpoint.__init__/record_attempt；pilot_measure.py:handle前部及787–800。

- Checkpoint跳过所有坏JSON行，却没有EvidenceLog的尾部隔离；半行后追加的新attempt和旧残片粘连。反例：写入时completed={1}，重开后completed为空。中间损坏也被无条件跳过。
- completed=true检查点先fsync，candidate_end完整记录后写。两者之间被杀，下一轮跳过候选，但检查点没有完整结果/证据路径hash，完整结果可能从未落盘。单一evidence_run_id不能证明对应结果可取回。
- 续跑跳过候选后不装载其原始结果；同一out路径最终覆盖为results=[]、n=0。不能将空的新结果当作完整样本交付。需区分本次增量与累计结果并对账。
- completed采用“曾经一次成功”而不是验证有效的结果提交，文件未校验seq、run绑定、候选身份/结果摘要；恢复没有复核对应证据完整性。

应先持久化完整结果与证据引用，再提交可验证checkpoint（或原子事务）；故障注入覆盖两次写之间的中断、半行、中间损坏、缺结果、重复候选及续跑累计产物。恢复快照hash锁定是进展，但不能替代结果提交完整性。

## P1-6 no_mint正对照在完整编排中永远不通过

位置：pilot_measure.py:575–593、772–792。

无Mint路径不执行state_validation，而validation_passed默认要求入场state_validation.passed。因此正确no_mint_by_cutoff也为false、exit1、不能checkpoint完成；续跑会反复处理。独立2候选空日志/零供给反例精确复现。

应按分支定义必要检查：无触发仍需确认pair身份、截止/供给证据等，但不应要求不存在的入场与退出校验；未执行项记不适用。不能简单把no_mint强设true跳过其实际必要证据。入场前失败分支与右删失也需完整流程验收。

## P1-7 read_evidence.complete未验证请求配对或运行结构

位置：evidence.py:330–367。

反例：run_header→rpc_begin→run_footer，没有rpc_end，diag.complete仍true。函数只排序检查seq集合，有footer即可；没有检查begin/end、header唯一性与位置、footer后的未完成工作、重复pending ID。空文件也能得complete=true。

T12自行比较列表发现未知，不代表正式读取器会阻断。配对应绑定全局唯一attempt ID、结果/错误及run/worker/candidate；有footer也不能掩盖缺少完成记录。尾部诊断“可恢复”与“可作为完整证据验收”分开。

## P1-8 成本已改善，但已知成本仍可丢失

位置：pilot_measure.py:402–434、买入后异常路径、诊断路径。

- _mul先检查price=None，即使units=0也返回unknown。买入成功/失败已得到有效stage、退出根本未尝试且没有退出base fee时，9情景全部unknown，已知买入成本不能单独复算。独立函数反例已保存。零次未执行不需要该侧价格，应该保留已知成本与确实未知项。
- 成功买入之后，在退出定位/状态校验失败、right_censored、slot扫描传输失败等分支没有统一cost落盘。size_probe异常还会跳过已经发生的主卖出尝试成本；可选诊断不应清除主路径证据。
- “buy总会调用router”仅适用于已成功解码的预期Probe返回路径；balanceOf前置读取/外层EVM失败仍可发生在router调用之前。没有stage证据时记未知，不能凭发出eth_call就计成已达swap。
- 未映射stage、序列化后的UNKNOWN/区间等也应严格处理；_mul用字符串对象身份is作哨兵不适合跨JSON恢复。

需每阶段落盘尝试账，已知部分不丢、未尝试为0、无法证明到达为未知；原始模拟现金变化与有充分语义依据的经济可用现金继续分开。

## P1-9 规范事件和状态缺失边界尚未全部关闭

位置：pilot_measure.py:_validate_log、snapshot_block、supply_at。

独立反例：data='0x'+'z'*128、sender topic='NOT_AN_ADDRESS'、transactionHash='0x'、错误blockHash仍通过_validate_log。仅长度和前缀不是ABI/hash验证；没有将Mint事件块hash与RPC块hash关联。供给跃迁可定位首次发生块，但不能把畸形事件当作已验证定位证据。

代码判无代码接受None和空字符串，而规范无代码结果应明确0x；当前V.RPC拒绝null，但空字符串仍可能通过envelope，不能当作无代码。snapshot_block也只检hash长度/前缀，前块number和完整十六进制格式未全核验。补正确不存在与响应缺失的分离反例，不能把这类缺陷归为“离线永远测不出来”；假链缺场景和实现假设都需要修。

## P1-10 独立串行/并行真链对照入口尚不完备

当前新检查点各自读取当时finalized；共用检查点又会跳过已有成功候选，不能直接得到同一快照的两套独立执行。应提供只读冻结快照/实验manifest输入，两个独立结果目录，各自实际执行同一开发集合；不要手工伪造checkpoint替代受审查入口。

并行测试用6个index却全是同一pair/token/创建块，且假RPC records没有真实id/完整响应，Etherscan被直接mock而没有真实证据记录。它没有覆盖不同候选缓存/分支、HTTP重试、限流时间、预算耗尽、worker崩溃或资源上限。17条通过不能支持这些未断言的主张。

## P2 文档与口径

MEASUREMENT_SPEC.v1.4的§3仍写“映射待实现”“现码仍entry_failed_verified”，§4仍写固定计数待实现，与§5勾选矛盾；§6又称首次Mint/状态校验尚未实现。运行结果doc.spec仍硬编码v1草案。保留历史版本，发布准确的新索引/勘误，不覆盖历史证据。

SharedGate total=sum(per_worker)是同一计数器的恒等式，不证明请求总量、速率或预算正确。6例或1例延迟不能证明没有长尾，166秒×300只能是串行机械外推。性能比较与经济可判定性分开；即便工程清单通过，仍须有持仓状态语义依据才能放开经济资格，不能靠清空复选框自动进入正式收益统计。

## 交付与下一步

源码快照和完整hash：audited_sources.json、*.audited.py。新增独立反例：reproduce.py、counterexamples.json、counterexamples.log；只依赖假链/模拟HTTP，无真实网络。原始测试日志与仅兼容补参日志分开保存。串行到并行的现有差异见parallel-vs-serial.diff。

优先修P0：线程异常/集合完整性→worker依赖隔离及transport预算→checkpoint绑定/提交/恢复；同时补无Mint、成本丢失与证据完整性反例。统一最新版测试入口，复跑全部及独立反例。通过后才开展小规模真链同快照对照。此次未授权或执行300样本，也未修改被审实现。

## P0-11 最终结果JSON绕过统一脱敏

Etherscan包装器对日志error脱敏后仍raise原始异常；measure通用except把str(e)写入rec.data，最终doc直接write_text，没有通过EvidenceLog.redact。独立反例使用真实Etherscan包装器＋模拟urlopen异常（只有假凭据）：JSONL不含FAKE_ONLY_SCAN_KEY，最终结果JSON却包含它。此测试没有使用或输出真实凭据。

应统一净化所有产物、异常、摘要及检查点，不能只净化JSONL。错误证据中保留类型/阶段和脱敏诊断。该项也应在任何新真链运行前修复。

## 本轮命令与退出状态

工作目录为rightTail/baseline_work_20260910。逐脚本python3运行结果见test_results.json，各stdout/stderr单独保存；原入口5个退出0、2个退出1。仅审计补parallel=1的两份compat-only日志退出0，不冒充原入口通过。

```
python3 rightTail/baseline_work_20260910/audit_full_20260910/reproduce.py
python3 rightTail/baseline_20260909/verify_package.py
```
从仓库根目录执行，两条最终均退出0；前者完成13条审计观测及相应反例断言，退出0表示反例成功复现，不表示被测系统通过。重试反例使用真实V.RPC及模拟HTTP响应；首次调试时模拟响应ID未跟随重试变化，修正为实际第二次ID后再验，不改被测实现。

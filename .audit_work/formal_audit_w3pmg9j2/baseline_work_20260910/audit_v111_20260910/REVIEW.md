# v1.11 独立复核

结论：**响应体慢流的原反例已关闭，停机总时限仍未完整闭合，暂不放行真链对照。** 本轮只审查停机后路径，不要求增加未停机时的正常运行总时限。

## 已确认修复

独立运行交付方loopback_deadline_probe.py，输出保存本目录body_probe.log，并独立解析断言：

- 停机后发起的慢响应体：0.161秒，Shutdown:wall_deadline_exceeded，强制关闭1次。
- 请求在途时停机的慢响应体：停止后0.160秒，同样被打断。
- 未停机对照：0.377秒正常返回0x1，强制关闭0次。

三项原行为得到独立复核；该脚本只写stdout及临时数据，本轮没有改写旧交付产物。body_assertions.json记录审计方断言结果。当前源码/规格完整hash与交付清单一致，见delivery_verification.json。

## 尚未闭合：整个请求生命周期与最终退出

### 1. P1：等待响应头时尚未登记，截止与升级都漏掉

位置：evidence.py:1075–1096（先resp=fn，再_DeadlineResponse登记）；:587–607（仅按_inflight数量升级）。

真实urllib连接本机loopback服务，响应头本身每约0.025秒送4字节，17段；不是只把响应体变慢。期限0.15秒，升级等待0.05秒。两个场景都处于已请求停机的范围：

| 场景 | 实际停机后耗时 | 升级次数 | 响应头接收期间登记数 |
|---|---:|---:|---:|
| 停机后发起请求 | 0.429秒 | 0 | 0 |
| 请求在途、接收头前停机 | 0.421秒 | 0 | 0 |

最后都返回Shutdown:wall_deadline_exceeded，**没有把超期结果当成功**；问题在于必须等头读完、urlopen返回后才开始登记并发现超期。0.15秒截止和0.20秒升级时登记表为空，定时器什么都没中断。数据持续到达也不会触发单次socket不活动超时。

需从发起HTTP之前登记整个操作生命周期。即便连接/握手/响应头阶段还拿不到response对象，也必须能被升级监督发现并终止；不能仅在response返回后登记。测试应保留body成功修复的三项，再加本轮header两项。

这两个反例使用真实TCP+urllib+冻结包RPC+当前gate；网络仅127.0.0.1，未访问任何真实数据源。完整记录见header_observations.json、headers.log、stop_before_headers.jsonl、stop_during_headers.jsonl；原始低层RPC记录不冒充完整measure运行。

### 2. P1：强制退出依赖可能阻塞的日志写入

位置：pilot_measure.py:624–638。

实际_on_escalate在os._exit(3)前同步执行log.write（拿日志锁、flush/fsync）和stderr打印。捕获Exception只能处理已经抛出的异常，不能让仍在等待的写入返回。

独立单元级验证使用**measure创建的真实回调**：持有EvidenceLog写锁后调用它，确认已进入写日志路径；等待0.1秒，回调仍阻塞、没有尝试os._exit。释放锁后才调用退出码3。os._exit在测试全程被替换成计数器，审计进程没有被真正终止。

这不是完整measure卡盘集成实验，也不宣称已测磁盘故障率；它直接证明当前最终退出依赖日志锁释放，不是有界的最后兜底。若日志锁/fsync/输出阻塞，固定5秒升级也不能保证退出。

要求：最后一级终止不要依赖同一工作进程的阻塞日志锁/同步I/O成功；用独立监督、非阻塞或有界的最后记录策略。保留此前已fsync前缀即可，不应为了强制退出前追加一条日志而失去退出上界。强制退出不保证footer完整的既有边界继续适用。

## 命令、退出码与产物

```bash
python3 rightTail/baseline_work_20260910/runs/deadline_20260910/loopback_deadline_probe.py
python3 rightTail/baseline_work_20260910/audit_v111_20260910/reproduce_headers.py
python3 rightTail/baseline_work_20260910/audit_v111_20260910/reproduce_escalation_log.py
```

均退出0。第一条输出另经审计断言通过；后两条退出0表示独立缺口复现成立。第二条是真实loopback传输实验，第三条是实际退出回调的受控锁阻塞实验。退出回调测试输出中的“强制退出”文字来自真实回调，但os._exit被mock，不能把该文字当作实际进程已终止。

被测源码快照见*.audited.py；复跑前后hash见hashes_start/end.json。未修改实现、未改写rt_a.sqlite、未向真实端点取数。正式冻结、300样本、经济统计资格仍关闭；下一步只补齐上述总期限缺口，不重开其他已关闭测量反例。未独立重跑交付方旧源码反向守卫，179/12不冒充本轮执行结果。

## 独立全入口复跑：403/0

在baseline_work_20260910目录依次运行 `python3 test_<入口>.py`；9入口全部exit0，源码/规格前后hash一致。

| 入口 | 退出码 | 通过/失败 |
|---|---:|---:|
| test_evidence | 0 | 29/0 |
| test_first_mint | 0 | 17/0 |
| test_step3 | 0 | 27/0 |
| test_step4 | 0 | 18/0 |
| test_e2e_blocking | 0 | 41/0 |
| test_resume | 0 | 23/0 |
| test_parallel | 0 | 23/0 |
| test_audit_fixes | 0 | 34/0 |
| test_audit_followup | 0 | 191/0 |

完整stdout/stderr见test_*.log，退出码汇总tests.json。

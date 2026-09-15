# v1.12 独立复核

结论：原收头/响应体慢流场景已能及时让调用方返回，但**后台请求的结束处理和最终退出仍有缺口，暂不放行真链对照。** 本轮只审查停机后的全生命周期与兜底，不增加正常运行总期限需求。

## 确认的进展

独立复跑两个交付loopback脚本，并对输出另加审计断言（probe_assertions.json）：

| 场景 | 停机后耗时 | 结果 |
|---|---:|---|
| 停机后开始收头 | 0.179s | Shutdown:wall_deadline_exceeded |
| 收头时停机 | 0.183s | 同上 |
| 停机后开始读响应体 | 0.174s | 同上 |
| 读响应体时停机 | 0.167s | 同上 |
| 无停机对照 | 收头0.467s、响应体0.395s | 返回0x1，强制关闭0次 |

收头期间确有登记。以上确认原反例具体修复，但“调用方已返回”不等于“后台传输已结束”。

当前源码/规格完整hash匹配交付清单，v1.11/v1.10与清单一致，§1–§4相对v1.11逐字一致。见delivery_verification.json、criteria_unchanged.json。

## 未关闭项

### 1. P1：后台传输未结束就撤销退出兜底，传输结束后登记又不清除

位置：evidence.py:1143–1193（_supervised_open）；:880–886（close取消全部定时器）；pilot_measure.py:1324及外层finally。

独立完整measure流程在槽位步骤注入受控等待传输，使用本次真实_supervised_open与治理器：

- 调用方超期，measure退出3，候选正确为aborted_by_shutdown；
- 返回时还有1个http-supervised线程、1个在途登记；
- deadline、escalate、force_exit三个定时器却已全部撤销；
- 释放受控传输，让HTTP线程真正结束后，线程数归零，**登记数仍为1**。

原因有两处：measure正常汇总前先gov.close()，无条件取消兜底；监督函数超期raise后，工作线程finally只done.set()，不负责清除该登记项。留着登记原本用于判断线程仍卡住，但线程已经结束后它就变成陈旧证据，可能导致错误升级。

这是同一Python进程调用measure的受控复现；独立CLI若随后立即结束，操作系统会终止daemon线程，不能据此声称每次CLI退出都会残留进程。不过当前代码确实在汇总写盘之前取消了兜底，也不能承诺在同进程返回后继续由升级机制处理后台请求。

要求：明确请求token所有权与交接；被调用方放弃后，由工作线程在真正结束时释放token，消除重复/遗漏注销；尚有活工作时不能无条件撤销兜底或声称运行已清理完。验证“放弃后迟到完成”与“放弃后一直卡住”两个方向，并核对measure完整退出/产物写入和同进程恢复行为。

### 2. P1：“无条件”hard_exit仍被stderr输出阻塞

位置：evidence.py:647–653。

_hard_exit先调用阻塞的os.write(2,...)，然后才os._exit(3)。裸os.write不等于非阻塞；它一样可能等满管道腾出空间，try/except也不能打断仍在等待的写。

本次在独立子进程中创建自己的管道、填满后恢复阻塞模式并设为stderr，保留读端但不消费。通过**真实治理器定时升级**调用真实_hard_exit，没有mock退出函数：

- grace0.02s＋升级0.02s＋force_exit0.02s，预期约0.06s到强制退出；
- 0.4s后子进程仍存活，打印SURVIVED_PAST_FORCED_EXIT；
- 测试子进程随后自退出9，未出现治理器的预期退出3。

实验仅占用一条小管道，父进程有3s超时保护，没有让用户环境挂住。完整结果见observations.json、reproduce.log。

要求：最末一级直接执行不可被日志/输出I/O阻挡的退出动作；此前日志仅尽力而为，不能再排在无条件终止之前。测试需覆盖真正写满的stderr管道，而不是只覆盖日志锁。

## 命令与证据

```bash
python3 rightTail/baseline_work_20260910/runs/lifecycle_20260911/loopback_header_probe.py
python3 rightTail/baseline_work_20260910/runs/deadline_20260910/loopback_deadline_probe.py
python3 rightTail/baseline_work_20260910/audit_v112_20260911/reproduce.py
```

均退出0；前两条是原loopback场景验证，第三条断言当前缺口存在。第三条内的完整measure返回3，满管道子进程自退出9，各自含义单独记录，不拼成“验收成功”。后台受控传输在测试结束前释放并join，不留下真实工作线程。

源码快照*.audited.py与hashes_start/end.json区分本轮版本。未改实现、未改写rt_a.sqlite、未调用真实数据源；真实网络仅本机loopback。未覆盖旧交付产物。正式冻结、300样本和经济统计资格继续关闭。

补充口径：20ms是轮询粒度，不是操作系统调度下的严格发现延迟上界。只报告实测延迟及可验证的退出策略。交付旧源码反向验证未在本轮重跑，其198/7与退出码只属于交付方记录。

## 独立全入口复跑：417/0

在baseline_work_20260910目录依次运行 `python3 test_<入口>.py`，9入口全部exit0；源码与规格运行前后hash完全一致。

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
| test_audit_followup | 0 | 205/0 |

逐入口完整输出test_*.log，汇总tests.json。测试尾部“强制退出”文字来自测试中的回调，不等于测试入口真实以3退出；实际入口退出码为0。

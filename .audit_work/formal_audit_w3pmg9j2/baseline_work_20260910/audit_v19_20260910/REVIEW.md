# v1.9 硬兜底与停机独立复核

结论：**9 个入口370项断言独立复跑通过；本轮资源前置条件仍未通过，暂不放行真链对照。** 以下发现仅覆盖新增控制的相关边界，不重开此前关闭的经济测量反例。

## 已确认的修复

- 软阈值与内核RLIMIT兜底已分开；RLIMIT_AS限制地址空间，并不等同于RSS，代码已有说明。硬触发可能损失未完成证据的边界已写明。
- 原槽位扫描SIGTERM反例：独立复测exit3，活动候选aborted_by_shutdown，检查点completed=false；未开工候选单列。本次10次模拟RPC发生于信号后，不将交付方本次8次数字冒充独立结果。
- 原chain_id=2反例：独立复测返回2后，信号处理器已恢复、看门狗停止、HTTP gate卸载。
- 版本完整hash与交付清单一致，v1.8/v1.7与已保留值一致；§1–§4和v1.8逐字相同。见delivery_verification.json、criteria_unchanged.json。

## 未关闭项

### 1. P0：请求的硬兜底安装失败仍可“验收通过”

位置：evidence.py:547–585；pilot_measure.py:623。

apply_hard_limits捕获setrlimit失败并写error，但measure未检查安装结果。完整受控流程请求hard_rss_mb=64，只把操作系统setrlimit替换成PermissionError（没有真的给测试进程设限）：**exit0、validation_passed=true**，报告同时记录 `RLIMIT_AS.error=controlled setrlimit rejection`。

请求的必要控制失败后不能继续当作前置条件具备。需验证实际安装/读回值，失败即前置条件不通过并阻断候选工作，保留失败证据。资源模块不可用路径也要同样处理；不能仅在报告角落留error。

### 2. P1：停机闸门仍未覆盖每次真实HTTP，收尾秒数不是完成期限

位置：evidence.py:520–545、:688–739、:777。

**反例A——底层重试绕过停机。** 使用冻结包的真实RPC类、当前RpcTap与HTTP gate，只在闸门之下mock传输。第一个HTTP返回503前请求停止，grace_calls=0且grace_seconds=0，未进入winddown。底层约1秒后仍发送第二个HTTP并返回0x1；governor的停机后请求计数为0。

根因：governor仅在SharedGate.acquire逻辑请求层检查；底层重试经过acquire_http，却不经过停机检查。全局调用预算/速率依然会检查，此处缺的是新加入的停机/收尾规则，不能拿既有HTTP限流测试代替。

**反例B——收尾期限未传递到在途请求。** grace_seconds=0.02，winddown内发一个请求。实际传给传输层的timeout接近5秒；受控传输耗时0.15秒后正常成功，stop_latency超过0.1秒。传输没有违反其收到的timeout，违反的是把0.02秒声称为收尾完成上界。完整数值见observations.json。

目前grace_seconds只限制“何时可批准下一次逻辑请求”，不限制已批准请求的等待和完成。墙钟软阈值也只置标志，CPU/地址空间RLIMIT不能对阻塞I/O提供墙钟终止上界。

要求：停机/收尾规则落到每次实际HTTP（含重试、等待后再次检查），给逻辑数/实际数分别准确定义；把剩余收尾时间传递给请求与等待，并有独立的墙钟超期兜底/升级策略。若策略只承诺停止发新请求，应明确承认它不等于完成时限，但仍需满足本轮要求的有界停机。补测停止发生在重试、排队和慢响应中的行为。

### 3. P1：初始化异常仍在统一清理范围之外

位置：pilot_measure.py:602–653。

HTTP gate安装后，RPC构造、ResourceGovernor安装/启动等步骤都在try之前。受控RPC构造抛RuntimeError，调用返回到测试方时 **http_gate_installed=true**。

此次try/finally修复了原chain_id=2路径，但“覆盖所有异常”还不成立。应从第一个设施安装前进入外层保护，使用未初始化哨兵逐项撤销已安装设施。此反例复现后已主动卸载闸门，未污染其他审计进程。

## 执行与证据

以下两脚本均exit0：前者断言本轮缺口存在，后者断言上一轮具体修复成立，不混为“验收通过”。

```bash
python3 rightTail/baseline_work_20260910/audit_v19_20260910/reproduce.py
python3 rightTail/baseline_work_20260910/audit_v19_20260910/verify_previous.py
```

输出：observations.json / reproduce.log（4条观测，归属上述3项）、previous_fixes.json / verify_previous.log。均为临时目录和mock网络。独立反例不在当前审计进程设置真实RLIMIT；交付测试内的真实RLIMIT验收在子进程执行。未重新运行交付方旧代码反向守卫，其140/18计数不冒充本轮观测。

本轮未改实现、未请求真链、未覆盖旧日志；rt_a.sqlite未删除或改写。正式冻结、300样本、measurement_semantics_verified及economic_results_eligible边界不变。下一步先关闭上述安装失败、实际请求与超期控制、初始化清理，再复核真链对照前置条件。

## 全入口独立复跑：370/0

在baseline_work_20260910目录依次执行 `python3 test_<入口>.py`；源码/规格运行前后hash一致。

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
| test_audit_followup | 0 | 158/0 |

完整日志见test_*.log，汇总见tests.json；源码快照与hashes_start/end.json用于区分被测版本。

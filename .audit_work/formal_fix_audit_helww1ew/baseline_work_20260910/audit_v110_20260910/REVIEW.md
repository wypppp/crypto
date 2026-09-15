# v1.10 独立复核

结论：硬限制安装失败阻断、HTTP重试停机和初始化清理的具体修复通过；**阻塞I/O的总墙钟上界仍未成立，暂不放行真链对照。** 本轮不扩大到无关测量语义。

## 已关闭的具体反例

独立verify_closed.py退出0，closed_observations.json记录：

- setrlimit被拒绝：measure返回2，候选开工0，不生成结果JSON；测试只mock操作系统拒绝，没有对审计进程设置真实RLIMIT。
- 503后请求停止、grace0且不在winddown：只发出1次真实RPC类的受控HTTP调用，重试在layer=http被Shutdown阻断。mock装在HTTP闸门之下。
- RPC构造异常：已安装HTTP gate正确卸载。

因此不重开这些旧反例。当前文件与交付完整hash一致，v1.9/v1.8与清单一致，§1–§4相对v1.9逐字相同；见delivery_verification.json、criteria_unchanged.json。

## 唯一未关闭项：socket timeout不是整个响应/停机的完成期限

位置：evidence.py:869–884；冻结包verify_capabilities.py的urlopen后response.read路径。

_gated_urlopen把剩余收尾秒数作为socket timeout传下去，这能缩短等待，却不能保证整段响应在该时间内读完。并且停止前已开始的请求不会在停止发生时自动重设原socket timeout。

本次使用**真实urllib、真实冻结包RPC类和当前HTTP gate**，连接本机127.0.0.1临时端口上的受控HTTP服务；没有替换urlopen，没有向任何真实数据源请求。服务立即发响应头，然后每约0.035秒发4字节有效JSON，共11段：每段间隔都小于0.15秒，但整体超过0.15秒。

两种场景均已复现，完整数值在deadline_observations.json：

| 场景 | 设定收尾期限 | 实际行为 |
|---|---:|---|
| 已停机，winddown内发请求 | 0.15秒 | 约0.38秒后仍成功返回0x1 |
| 请求在途时才触发停止 | 0.15秒 | 停止后约0.36秒才成功返回0x1 |

这不是“mock故意无视timeout”：实验使用真实TCP和urllib，数据分段持续到达，传输遵守现有socket超时语义。精确单调时钟值、段间隔与原始RPC记录见结构化输出；stop_before_request.jsonl / stop_during_request.jsonl保留低层请求证据。它们是传输层测试记录，不冒充完整measure运行。

前一轮单个sleep/TimeoutError受控传输证明timeout参数被缩短，不能据此证明整个慢响应或在途请求的总期限。

要求：给出并实现独立的绝对墙钟截止/超期升级机制，覆盖已开始请求、分段响应、HTTP重试与排队；不能仅再缩socket timeout。可采用独立监督者对工作进程施加有界宽限和终止兜底，或其他能实证同等期限的实现。不得靠CPU/地址空间RLIMIT推断阻塞I/O的墙钟上界。超过期限后的前缀证据/未知结果/检查点恢复沿用既有硬兜底边界，不承诺强制终止时完整footer。

验收应包含本轮两种真实loopback传输场景，以及停止后在途任务结束/被终止的明确证据。仅增加mock断言或把timeout改名为deadline不足以关闭此项。

## 命令与执行边界

```bash
python3 rightTail/baseline_work_20260910/audit_v110_20260910/verify_closed.py
python3 rightTail/baseline_work_20260910/audit_v110_20260910/reproduce_deadline.py
```

两脚本均退出0：前者表示修复后预期成立；后者表示总期限缺口成功复现，不表示验收通过。输出分别closed.log/closed_observations.json、deadline.log/deadline_observations.json。

本輪未修改实现、未调用真实数据源、未启动真链对照、未覆盖旧运行产物；仅本机loopback使用真实网络栈。未改写rt_a.sqlite。正式冻结、300样本、经济统计资格继续关闭；前面已通过的工程修复维持。

未独立重跑交付方旧源码反向守卫，其162/14不作为本轮实际执行结果。

## 全入口独立复跑：388/0

在baseline_work_20260910目录依次执行 `python3 test_<入口>.py`，全部exit0；运行前后Python源码/规格hash完全一致（hashes_start/end.json）。

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
| test_audit_followup | 0 | 176/0 |

完整日志见test_*.log、tests.json。最终loopback复测精确停机延迟：已停机后发请求 0.371s、在途才停机 0.361s，均超过0.15s。

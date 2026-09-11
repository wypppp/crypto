# v1.14 独立审核

本轮 DNS / TCP / TLS 停机监督修复通过离线复核，上一轮 TLS 阻断项关闭。没有在本轮受测连接场景中发现新的运行器阻断缺陷；可以推进**少量开发样本的真链串行／两路并行同快照对照**。下述测试产物隔离和规格口径应在下一次交付前收尾，不需要重做已通过的连接实现。

这不是正式实验验收：真链对照尚未执行，正式冻结、300 样本、跨期持仓充分性与经济统计资格继续关闭。`economic_results_eligible` / `measurement_semantics_verified` 仍须为 false。本轮没有访问真实数据源。

## 1. 独立复核结果

环境：Linux，Python 3.8.18，详见 `environment.json`。九个入口顺序执行，合计 **438 通过 / 0 失败，全部退出 0**。不是汇总交付方以前的日志。

| 入口 | 退出码 | 通过 / 失败 |
|---|---:|---:|
| test_evidence.py | 0 | 29 / 0 |
| test_first_mint.py | 0 | 17 / 0 |
| test_step3.py | 0 | 27 / 0 |
| test_step4.py | 0 | 18 / 0 |
| test_e2e_blocking.py | 0 | 41 / 0 |
| test_resume.py | 0 | 23 / 0 |
| test_parallel.py | 0 | 23 / 0 |
| test_audit_fixes.py | 0 | 34 / 0 |
| test_audit_followup.py | 0 | 226 / 0 |

完整退出码在 `tests.json`，输出在 `test_*.log`。程序与规格完整 hash 在运行前、全入口运行后、全部检查结束后均相同；当前源码与交付 `runs/tls_20260911/source_hashes.json` 的完整 hash 匹配。v1.13/v1.12 完整 hash 与清单相同，v1.14 的 §1–§4 与 v1.13 逐字相同，详见 `binding_check.json`。

- pilot_measure.py：`44f54f2cb67b9310453a13ed116b819ede9f3cd2e617ea5e5b3f6b1810dc2cc9`
- evidence.py：`1fe5c43c57420b1213c7f272619f844469bc95a8c39f196d236ef2e9f5f7420d`
- v1.14：`f8dc892cca09636989ce919418edeb870601fac47a32a7f4e7f0590c55d189f0`
- 冻结包 verify_capabilities.py：`bc9ea52ec51259d79cfe435d47dc0d846fadd56d866494e7dfcfaf3b92c15d52`

## 2. 真实本机连接检查

使用当前 gate、冻结包真实 RPC 类及真实 urllib，服务端仅在 loopback。DNS 一项替换 `getaddrinfo` 模拟阻塞；不称为真实 DNS 故障。证书和私钥在临时目录生成，结束后删除。

| 场景 | 本轮独立结果 |
|---|---|
| TLS 握手中停止，grace 0.15s | 0.159s 返回 `Shutdown:wall_deadline_exceeded(tls_handshake)`，在途登记 1 |
| TCP 建连中停止，原 socket timeout 3s | 0.169s 返回 `Shutdown:wall_deadline_exceeded(tcp_connect)` |
| HTTPS 慢响应体，grace 0.15s | 0.162s 返回 `Shutdown:wall_deadline_exceeded(response)` |
| HTTPS 慢响应体、不停止、校验开启 | 0.391s 正常返回 `0x1`，残留登记 0 |
| 不信任本机证书 | `CERTIFICATE_VERIFY_FAILED`，残留登记 0 |
| DNS 模拟阻塞 30s | DNS 期间登记 1；子进程退出 3，含解释器启动总耗时 0.571s |
| 上轮独立 TLS 反例改为修复后断言 | 0.165s 返回 Shutdown，登记 1，升级次数 0，验证脚本退出 0 |
| stderr 真实管道写满、强制退出子进程 | 退出 3，没有 `SURVIVED_PAST_FORCED_EXIT` |

原始输出在 `phase_checks.json`、各探针 `.log`，上轮 TLS 反例的低层请求记录在 `tls.jsonl`。这些是连接探针，不能冒充完整候选测量证据。

源码核对确认：操作在 DNS 之前登记；TCP socket 在 connect 之前交出；TLS 之前复制 fd 作为 shutdown 句柄，沿用标准库 SSL context 与 hostname；错误路径或响应释放路径交还登记；响应判停机同时检查实际中断标记。未重新做 300 对微基准，也未独立重跑交付方的旧版 221/5 反向全入口结果，不把这些数字记为本轮独立证据。

DNS 的结果是进程强制终止，不是干净的请求取消。强制退出只保留已 fsync 前缀；不能因退出码为 3 就宣称 footer / 检查点完整。耗时表是本机观测，不是对任意 OS 调度或任意阻塞代码的数学上界。

## 3. P1：测试入口会改写历史交付产物

位置：`test_audit_followup.py:1745`、`:1763`；`runs/tls_20260911/phase_probe.py:108`。

测试硬编码调用交付目录的探针；探针无输出参数，固定把结果写到自身旁边的 `phase_probe.json`。因此正常跑一次全入口测试，也会覆盖交付方历史 JSON。临时证书、临时测试数据目录不能隔离这次写入，反向测试同样经过该路径。

**本次审核的全入口复跑也触发了该覆盖。** 审核前未另存该 JSON 原始字节，不能假装未改写，亦不能从旧摘要重建“原件”。现存内容的副本及 hash/mtime 分别保存为 `phase_probe.overwritten_by_suite.json`、`artifact_overwrite.json`，必须标作本次审核复跑产物。交付 `.log` 仍可单独引用，但现存 JSON 不再可称为交付时原件。

后续独立连接复核已复制探针到本审核目录再执行，输出保存在这里，没有再次覆盖交付目录。需要执行方将测试使用的探针输出指向每次独立临时／新运行目录，消除硬编码交付路径；增加一次运行前后历史产物 hash 不变的检查。此项涉及测试证据保存，未发现它会改变 `pilot_measure` 真链运行的候选结果。

## 4. 规格仍有旧口径，须收尾

这些不否定第 1–2 节的具体实测结果，但不应随下一轮报告继续流传：

- v1.14 §0 第 203–210 行仍保留已撤销的“省 2～3.5ms”。采用后来的配对描述也不能将“未测出显著增量”说成“没有成本”，不据此认定真链瓶颈。
- §6.0 第 414 行仍写资源只有采样，与当前 VmHWM / RLIMIT 实现及 §7 冲突。
- §7.5 第 571 行把退出 3 一概定义成有序停机、检查点完整；本轮 DNS 子进程恰好说明退出 3 也可能来自强制终止。必须读取证据完整性与检查点校验，不能只看退出码。
- §3/§4 的若干“待实现／现码固定次数”仍与 §5 及当前实现冲突。`§1–§4 未改字节` 已证实，但这不等于正文实现状态全部正确。
- §7.3 前段仍写 shutdown + close，后段又明确只 shutdown；应以当前分阶段句柄机制表述，清理被取代的操作说明。

保留已绑定版本原始字节，通过新的版本或明确关联的勘误收窄。实际测量判据、统计资格和已验证程序语义不应顺带改变。

## 5. 实际命令、下一步与修改范围

本次全入口的实际工作目录为 `rightTail/baseline_work_20260910`，依次执行：

```bash
python3 test_evidence.py
python3 test_first_mint.py
python3 test_step3.py
python3 test_step4.py
python3 test_e2e_blocking.py
python3 test_resume.py
python3 test_parallel.py
python3 test_audit_fixes.py
python3 test_audit_followup.py
```

均退出 0。上面是**执行记录**；修正第 3 节输出路径前，最后一个入口不宜当成无副作用的历史证据复跑命令。

后续独立探针执行：

```bash
python3 rightTail/baseline_work_20260910/audit_v114_20260911/run_phase_checks.py
```

退出 0，关键输出 `PHASE CHECKS PASSED`；内部四个探针均退出 0。需要复跑时应将本审核目录复制到新的同级目录，保留本次原始输出。

下一步在独立进程与输出目录中，对**同一个既有开发样本、同一个 finalized 块号和完整 hash、同版源码／规格／运行参数**，各自独立检查点跑串行与两路并行。先固定本次调用、墙钟、软阈值与硬兜底预算；保留两轮实际 HTTP/RPC/Etherscan 计数、峰值、失败/停机/续跑证据，比较状态、金额、分类和候选证据归属。按实测更新预算，不由 n=1 的耗时乘 300 当验收。

测试输出隔离和上述运行口径应随这次准备一起修正。本轮资源修复不再作为“等待新一轮连接实现”的阻断项；正式冻结和经济资格仍须后续独立验收。

审核新增本目录的报告、复核脚本、日志、源码快照和 hash 清单，追加 HANDOFF。未修改运行器或冻结规格，未操作 rt_a.sqlite，未调用真实端点。旧交付 JSON 被测试入口覆盖的例外已在第 3 节如实记录。

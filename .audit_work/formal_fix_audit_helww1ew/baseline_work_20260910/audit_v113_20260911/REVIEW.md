# v1.13 独立复核

结论：去除请求工作线程、已连接HTTP的慢流中断、满stderr管道下最终退出均有进展；**HTTPS握手阶段仍不受停机截止及升级监督，暂不放行真链对照。** 此处比交付中仅声明的“TCP连接建立未覆盖”更宽。

## 已确认

- 真实HTTP loopback：收头两场景停止后0.165/0.171s返回Shutdown；响应体两场景0.175/0.170s返回Shutdown。未停机对照0.472/0.387s返回0x1、强制关闭0。
- 原满stderr管道反例独立子进程复测：退出3，SURVIVED_PAST_FORCED_EXIT没有出现。见verify_exit.py、exit_observation.json。
- 源码不再为每次HTTP创建工作线程；连接token在错误路径与响应释放路径交还，close对pending保留升级链。现有HTTP场景不能替代HTTPS验证。
- 当前文件完整hash匹配交付清单，v1.12/v1.11与清单一致，§1–§4相对v1.12逐字一致；见delivery_verification.json、criteria_unchanged.json。

## P1：HTTPS的socket登记晚于TLS握手

位置：evidence.py:1190–1193（_RecordingHTTPSConnection.connect）。

实现先super().connect()，然后_record_conn(self.sock)。当前Python标准库HTTPSConnection.connect在返回前会完成TLS wrap/handshake；其本地源码摘录保存在stdlib_https_connect.txt。因此TCP已经建立并存在socket，但TLS仍阻塞时，治理器的登记表仍为空。

独立反例使用**真实urllib HTTPS客户端 + 当前gate + 冻结包RPC + 本机TCP服务**。服务端接受TCP连接后请求停止，但不回应TLS握手，0.5秒后关闭连接；未接触任何真实数据源，也不涉及证书验证绕过。

实测（tls_observation.json）：

- TCP已建立，所处阶段为TLS握手；
- grace=0.15s，升级等待0.05s；
- TLS期间在途登记0，升级回调次数0；
- 停止后0.539s才返回Shutdown:wall_deadline_exceeded。

这不是把超期结果误判成功；问题是0.15s截止与0.20s升级都未接管在途TLS，只能等传输自行失败。停机在调用已开始后发生，原socket timeout也不会因为调用前的min(timeout,remaining)自动被重设。

需要把TLS握手纳入操作监督：在可阻塞握手之前登记可终止的socket，或使用覆盖连接全过程的独立操作登记/升级；保证正常HTTPS验证行为不受影响。应再核对DNS/TCP等尚未拿到可关闭socket的阶段，明确它们实际采用的截止/兜底，不把“socket timeout”泛称为整个连接过程的停机上界。本文只对上述TLS场景给出实测结论，不冒充已验证DNS场景。

此项关系到真实HTTPS数据源，HTTP-only的loopback全绿不能直接证明真链对照前置条件完成。

## A/B记录口径

已读取before/after两份摘要并核对脚本：旧版治理器开/关均值差0.993ms，新版0.111ms，两摘要差0.882ms；按所报标准差和n=300计算朴素标准误约0.204/0.210ms。见overhead_record_check.json。

这分别是两轮“治理器开/关”的配对测量，不是同一轮旧版/新版直接随机交错对比；代码固定先on后off。相邻配对可以减轻慢漂移，不能声称漂移完全消除。交付摘要未含逐对计时序列，本轮没有据原始配对重算误差、独立性或显著性，也没有重新做300对微基准。

约1ms只是本机微基准的描述性估计，不据此认定真链瓶颈是限流、也不据此放行。去掉线程是实现选择，不是正确性证明；线程token归属问题也不是所有线程方案天生不可避免。

## 命令与执行边界

```bash
python3 rightTail/baseline_work_20260910/audit_v113_20260911/reproduce_tls.py
python3 rightTail/baseline_work_20260910/audit_v113_20260911/verify_exit.py
python3 rightTail/baseline_work_20260910/runs/lifecycle_20260911/loopback_header_probe.py
python3 rightTail/baseline_work_20260910/runs/deadline_20260910/loopback_deadline_probe.py
```

均退出0：第一条表示TLS缺口复现，第二条验证满管道退出修复，后两条另经过审计断言验证原场景。TLS低层原始记录tls.jsonl不冒充完整measure运行；tls.log和tls_observation.json保留细节。

本轮只访问本机loopback，未请求真实数据源、未修改实现、未改写rt_a.sqlite或旧交付日志。正式冻结、300样本、经济统计资格继续关闭。先补TLS及连接边界的监督，再复核；不重开已关闭的其他测量反例。旧版反向守卫未在本轮独立重跑，其211/4不冒充本轮结果。

## 独立全入口复跑：428/0

从baseline_work_20260910依次运行 `python3 test_<入口>.py`，9入口全部exit0；运行前后Python源码与规格hash一致，见hashes_start/end.json。

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
| test_audit_followup | 0 | 216/0 |

完整输出test_*.log，退出码汇总tests.json。测试中的“强制退出”打印不替代实际入口退出码。

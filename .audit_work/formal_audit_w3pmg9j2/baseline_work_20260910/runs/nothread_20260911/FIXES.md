# 登记归属 · 兜底保留 · 真正无条件的退出（规格 v1.13）

对应审核：`audit_v112_20260911/REVIEW.md`。源码 hash 见 `source_hashes.json`。
规格 **v1.13**（`32a0805cd2822d6d…`）；v1.12（`5da1d9fb4bbd163a…`）、v1.11 原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

两条观测在同字节源码（`evidence.py` = `7688a130…`）上先复现。

## 一、P1 后台请求收尾未闭合 —— 换掉整个实现，不是打补丁

v1.12 用「每请求一个工作线程 + 20ms 轮询」做全生命周期监督。问题不在细节：
线程与登记项的**归属天生会脱节** —— 调用方放弃后，token 由工作线程持有，
线程结束时无人注销，留下可能引发错误升级的陈旧证据；而运行收尾又在
后台仍有在途请求时撤销了兜底。

改成**在 `connect()` 后立刻把 socket 登记到治理器**：停机时定时器
`shutdown()` 它，**正阻塞在 read 上的调用线程自己**被唤醒。
**没有工作线程、没有轮询。** token 归属唯一 —— 谁发起调用谁注销：
成功走响应关闭，失败或放弃走异常路径。

另外，`close()` 在仍有在途请求时**保留升级链**（只撤 `_deadline_timer`），
报告新增 `pending_inflight` / `backstop_armed`。

顺带补回一处归因：到点 `shutdown` 掉 socket 会让 `opener.open()` 抛
传输错误，若不处理就会把「我们主动掐断」显示成「对端出问题」。
现在 deadline 已过时统一归因为 `Shutdown: wall_deadline_exceeded`。

## 二、P1 `_hard_exit` 仍被 stderr 阻塞

裸 `os.write(2, …)` **不是**非阻塞写：stderr 若是写满的管道，它照样等在那里，
`try/except` 打断不了一个仍在等待的写。审核实测：预期 0.06s 退出，0.4s 后进程还活着。

改为先 `os.set_blocking(2, False)` 再试写，设不了或写不进就直接放弃 ——
诊断另有 `<evidence>.escalation` 那条不经 stderr 的路。
实测：stderr 是写满的管道时，退出码 **3**，`SURVIVED_PAST_FORCED_EXIT` 不再出现。

## 三、开销：交替 A/B 实测

这是本轮被问到的重点，所以用**逐对交替**测量消掉机器漂移
（`overhead_ab_probe.py`，本机 loopback，300 对，基线约 28ms/次）：

| 实现 | 逐对差均值 | 中位数 | 标准差 | 测量期间创建的线程数 |
|---|---:|---:|---:|---:|
| v1.12（线程 + 轮询） | **+0.99 ms** | +1.09 ms | 3.54 | **300**（每请求一个） |
| v1.13（connect 记 socket） | **+0.11 ms** | +0.17 ms | 3.64 | **0** |

n=300 时标准误约 0.2ms：旧实现的 +1.0ms 是显著的，新实现的 +0.11ms
落在噪声内。**线程数 300 → 0 是结构事实，不受噪声影响。**

**更正**：我先前用非配对测量得出"省 2～3.5ms"，那个差值被机器漂移主导，
站不住。配对测量下真实节省约 **1ms/请求**。放到真实 RPC（单次
stateOverride `eth_call` 实测约 1.2s）上是 ~0.08%；这套程序是**离线采集**，
瓶颈在 RPC 限流，不在我们自己的微秒。但省掉每请求一个线程本身是干净的赢，
而且停机发现不再有 20ms 的轮询粒度。

## 四、回归守卫与反向验证

`test_audit_followup.py` 新增 §22（11 项）。

| 被测源码 | 结果 |
|---|---|
| 修复后 `85b75dfa…` / `b45707a8…` | **216 通过 / 0 失败，退出 0** |
| 修复前（v1.12 快照 `7688a130…`） | **211 通过 / 4 失败** |

旧版失败项含审核方的决定性现象：`SURVIVED_PAST_FORCED_EXIT`（退出码 9）。

写守卫时又发现两处我自己的问题，都已修：

* 「不再为每个请求开后台线程」「登记项已交还」两条最初在旧实现上**也通过** ——
  因为慢响应自己就结束了、后台线程随之消失，采样太晚。改为**受控阻塞**：
  服务端卡住不发完，采样完毕才放行，这样后台线程若存在必然还活着。
* 测试里几个治理器**故意**留着未注销的在途项，而 `close()` 现在保留升级链 ——
  不关掉兜底的话，5 秒后升级会把测试进程自己 `os._exit` 掉（实测退出码 3）。
  已给这些治理器显式 `force_exit_after=None` 并在断言后撤销定时器。

## 五、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/216
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 428 项断言，9 个入口全部退出 0

$ python3 runs/nothread_20260911/overhead_ab_probe.py     # 交替 A/B 开销实测
$ python3 runs/lifecycle_20260911/loopback_header_probe.py # 响应头期限（未回退）
$ python3 runs/deadline_20260910/loopback_deadline_probe.py # 响应体期限（未回退）
```

## 六、仍未关闭

- **真链串行/并行同快照对照未做。** 本轮未启动，等放行。
- 仍有一段管不住：**TCP 连接建立本身**（还没有 socket），由 socket timeout
  约束，停机时该 timeout 已被压到剩余收尾时间。
- 强制终止（硬兜底 RLIMIT、超期升级）触发时不承诺证据完整，只承诺已 fsync 前缀可读。
- 绝对截止只在**停机之后**生效。未停机时单次请求时长仍由 `V.RPC` 自身 timeout
  与全局时间预算约束，两者都不是对分段慢响应的总时长上界。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

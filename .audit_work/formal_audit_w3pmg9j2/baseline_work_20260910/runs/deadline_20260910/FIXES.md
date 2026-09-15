# 绝对墙钟截止与超期升级（规格 v1.11）

对应审核：`audit_v110_20260910/REVIEW.md`。源码 hash 见 `source_hashes.json`。
规格 **v1.11**（`e384aa8cba126ce0…`）；v1.10（`ed62d6aef1869d84…`）、v1.9 原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

## 一、我上一轮的说法是错的

v1.10 把「剩余收尾时间压到 socket `timeout`」当作完成期限。**这不成立。**

`timeout` 是**每次读的不活动超时**，不是整段响应的完成期限：服务端每 35ms
吐 4 字节，0.15s 的 timeout 永远不会触发，整体却能拖到任意长。
审核用真实 urllib + 冻结包 RPC 类连本机 loopback 实测：

```
期限 0.15s → 停机后发起请求      0.387s 后仍成功返回 0x1
             请求在途时才停机      停机后 0.370s 仍成功返回 0x1
```

在同字节源码（`evidence.py` = `dcff069f…`）上复现一致。

## 二、绝对墙钟截止

在途响应登记到治理器；`request_stop()` 武装定时器，到点由定时器
**`shutdown(SHUT_RDWR)` + `close()` 底层 socket**，强制打断已阻塞的 `read`。

只调 `response.close()` **不够** —— 实测它关的是上层缓冲，另一个线程仍卡在
底层 recv 上，服务端还要 0.35s 才发完，读操作照样等到了 0.35s。
必须触到 socket 本身（`resp.fp.raw._sock`），实测把等待立刻打断。

期限过后即使读到数据也判 `Shutdown: wall_deadline_exceeded`，结果不可用。
**覆盖已经开始的请求**：停机发生在请求开始之后同样管住；停机之后才登记的
在途请求立刻关闭。

同一 loopback 场景实测（`loopback_deadline_after.log`）：

| 场景 | 期限 | 修复前 | 修复后 |
|---|---:|---:|---:|
| 停机后发起请求 | 0.15s | 0.387s，返回 `0x1` | **0.163s**，`Shutdown: wall_deadline_exceeded` |
| 请求在途时停机 | 0.15s | 0.370s，返回 `0x1` | **0.158s**，同上 |
| **未停机（对照）** | — | 0.377s，返回 `0x1` | **0.377s，返回 `0x1`，零强制关闭** |

对照项很重要：期限**不误伤**未停机的慢响应。

## 三、超期升级

到点关闭之后再等 `--stop-escalate-seconds`（默认 5s），若在途请求**仍未结束**
（说明线程卡在 I/O 里、关闭没能解开），落一条已 fsync 的证据后**强制退出**（退出码 3）。

**强制终止时不承诺 footer 完整** —— 与硬兜底同一边界：已 fsync 的前缀可读，
未完成部分交给检查点与恢复机制。

写这条时发现自己的逻辑有洞：`_close_inflight` 关完就注销登记，于是
「关了但仍卡住」永远检测不到，升级不可能触发。改为**关闭后保留登记**，
由持有方在真正结束时注销；仍在表里的即为卡住。子进程实测：卡住→退出码 3
并打印 `ESCALATED 1`；正常结束→不升级、退出 0。

## 四、回归守卫与反向验证

`test_audit_followup.py` 新增 §20（15 项），含**两个真实 loopback 场景**
（不替换 urlopen，仅 127.0.0.1 临时端口）、在途登记、以及子进程里的升级与对照。

| 被测源码 | 结果 |
|---|---|
| 修复后 `44e36d9e…` / `5e4882f6…` | **191 通过 / 0 失败，退出 0** |
| 修复前（v1.10 快照 `dcff069f…`） | **179 通过 / 12 失败，退出 1** |

旧版失败项里包含审核方的原始数字：`0.370s` / `0.369s`、结果 `0x1`。

审查方 `reproduce_deadline.py` 现退出 1（缺口不再复现）；
`verify_closed.py` 仍退出 0（此前各轮修复未回退）。

## 五、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/191
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 403 项断言，9 个入口全部退出 0

$ python3 runs/deadline_20260910/loopback_deadline_probe.py   # 本机 loopback 实测
$ python3 audit_v110_20260910/verify_closed.py       # 退出 0（旧修复未回退）
$ python3 audit_v110_20260910/reproduce_deadline.py  # 退出 1（缺口不再复现）
```

## 六、仍未关闭

- **真链串行/并行同快照对照未做。** 本轮未启动，等放行。
- 强制终止（硬兜底 RLIMIT、超期升级）触发时不承诺证据完整，只承诺已 fsync 前缀可读。
- 绝对截止只在**停机之后**生效。未停机时单次请求时长仍由 `V.RPC` 自身 timeout
  与全局时间预算约束 —— 这两者都不是对分段慢响应的总时长上界。
  若要对正常运行也设总时长上界，需要另立需求，本轮未做。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

# 硬兜底 · 有界停机 · 统一清理（规格 v1.9）

对应审核：`audit_v18_20260910/REVIEW.md`。源码 hash 见 `source_hashes.json`。
规格 **v1.9**（`bc5ed56995bc67b8…`）；v1.8（`121308b9902f7467…`）、v1.7 原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

三条观测在同字节源码（`ff052ba8…` / `f3ea0eee…`，与 `*.audited.py` 逐字节相同）上先复现。

## 一、P0 软阈值被称作硬上限 —— 这话我说错了

v1.8 的 §7 标题写「硬上限」，实际只是置一个 Event。审核实测：
`max_rss_kb=1`、`check()` 后 `stopping=true`，随后仍成功分配 8 MiB。**属实。**

口径拆成三块，各自带 `kind` 自陈：

| | 软阈值 | 硬兜底 |
|---|---|---|
| 参数 | `--max-rss-mb` `--max-cpu-s` `--max-wall-s` | `--hard-rss-mb` `--hard-cpu-s` |
| 机制 | 看门狗巡检 → 置标志 → **各处协作检查** | 内核 `RLIMIT_AS` / `RLIMIT_CPU` |
| 能否阻止继续分配/执行 | **不能**（自陈 "do NOT prevent…"） | 能 |
| 触发点 | 可控 | **不可控** |
| 证据 | 承诺结构完整 | **只承诺已 fsync 前缀可读** |

子进程实测（RLIMIT 会影响整个进程，不能在测试进程里设）：

```
RLIMIT_AS  64MiB  → 循环分配 8MiB×200，进程内从未检查，仍被内核拦下 MemoryError
RLIMIT_CPU 软1s/硬6s → 烧 CPU 触发可捕获的 SIGXCPU（转有序停机），硬限 SIGKILL 兜底
```

## 二、P1 停机响应没有上界

审核实测：槽位扫描时发 SIGTERM，之后仍执行 **16 次** RPC，候选走到 `measured_exit`
并把检查点标为完成 —— 与交付所写的中途停机策略不符。**属实。**

修法不是多埋几个安全点（埋多少都不构成上界），而是把停机后的请求闸门**下沉到
`SharedGate.acquire()`** —— RPC 与 Etherscan 共用这条路径：

* 收尾窗口**之外**：任何请求立即抛 `Shutdown`，主测量工作**立刻**停止发起；
* 收尾窗口**之内**（`gov.winddown()`，用于注入后复读/恢复核验）：
  按 `--stop-grace-calls`（16）与 `--stop-grace-seconds`（15）封顶。

同场景实测：

```
信号后 RPC 次数   16 → 8（全部是有界收尾）
候选 1           measured_exit / checkpoint completed=true
                 → aborted_by_shutdown / checkpoint completed=false
停机耗时          实测 stop_latency_s 记入报告（不再靠 0.25s 巡检频率推断）
停机后证据        complete=true，bad_lines=[]，unmatched_rpc_begin=[]
```

收尾若被宽限预算截断，记 `restore_check.interrupted_by="shutdown"`，
状态**保持** `aborted_by_shutdown` —— 不改写成"状态校验失败"，那是另一回事。

顺带修掉两个自己引入的问题：
* 已开工的候选若让 `Shutdown` 逃出 `handle()`，会被上层记成「未开工」——
  把"开工了没做完"说成"根本没轮到"。改为记 `worker_errors` 并单独落证据。
* 收尾实测需 9–10 次请求（2 块 × 2 地址 × 2 调用 + 2 次块复读），
  原默认宽限 8 会**必然**截断收尾。三处默认值统一为 16。

## 三、P1 提前返回不撤销设施

`measure()` 主体置于 `try/finally`，`_release_facilities()` 统一撤销闸门、
看门狗、信号处理器，覆盖**所有**返回与异常分支。链身份不符仍返回 **2**，
不伪装成有序停机。启动阶段即停机则返回 3，并仍写交付记录（全部候选进 `not_started`）。

## 四、回归守卫与反向验证

`test_audit_followup.py` 新增 §18（21 项）。

| 被测源码 | 结果 |
|---|---|
| 修复后 `73252572…` / `e3be07df…` | **158 通过 / 0 失败，退出 0** |
| 修复前（v18 快照 `ff052ba8…` / `f3ea0eee…`） | **140 通过 / 18 失败，退出 1** |

写守卫时我的测试**把测试进程自己杀了**（exit 137）：§18 有一句在测试进程内调用
`apply_hard_limits()`，给跑者设了 `RLIMIT_CPU`，而它早已烧掉远超 1 秒 CPU。
所有实际设限的断言已移入子进程。

## 五、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/158
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 370 项断言，9 个入口全部退出 0
```

## 六、仍未关闭

- **真链串行/并行同快照对照未做。** 本轮未启动，等放行。
- 硬兜底触发时**不承诺证据完整**，只承诺已 fsync 前缀可读；未完成部分交给
  检查点与恢复机制。这是硬兜底的固有代价，不是缺陷，但必须写明。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

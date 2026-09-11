# 硬限核验 · 真实 HTTP 全路径停机 · 初始化清理（规格 v1.10）

对应审核：`audit_v19_20260910/REVIEW.md`。源码 hash 见 `source_hashes.json`。
规格 **v1.10**（`ed62d6aef1869d84…`）；v1.9（`bc5ed56995bc67b8…`）、v1.8 原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

四条观测在同字节源码（`evidence.py` = `e3be07df…`，与 `evidence.audited.py` 逐字节相同）上先复现。

## 一、P0 硬兜底安装失败仍"验收通过"

`apply_hard_limits()` 把 `setrlimit` 失败写进报告角落，`measure()` 从不检查。
实测：模拟 `setrlimit` 被拒后仍 `exit 0`、`validation_passed=true`。**属实。**

* 每项 `setrlimit` 之后立即 `getrlimit` **读回核验**，记 `verified` 与 `readback`；
* `hard_limit_problems()` 汇总问题（含 `resource` 模块不可用）；
* **请求过硬兜底却没装上 ⇒ 前置条件不成立**：写证据后返回 **2**，不做任何候选工作。

使用者要的控制没生效，就不能当作前置条件具备。

```
setrlimit 被拒 → 修复前 exit 0 / validation_passed=true
               → 修复后 exit 2，不产出结果文件
装得上时       → verified=true，problems=[]（子进程实测）
未请求硬兜底   → hard_requested=false，problems=[]，不受影响
```

## 二、P1 停机闸门没覆盖每次真实 HTTP；收尾秒数不是完成期限

**A. 底层重试绕过停机。** 闸门只挂在 `SharedGate.acquire()`（逻辑层），
`V.RPC` 对 503 的重试直接走 urlopen。实测停机后仍发出第二个 HTTP 并返回 `0x1`。

新增 `gate_http()`，挂在 `acquire_http()` 上 —— **每一次真实 HTTP（含重试）**
都过闸门，且排队等待之后**再核一次**（排队里的请求不得带着过期许可发出）。
`grace_calls` 现在对**逻辑请求数**与**实际 HTTP 次数**同时封顶：
只封逻辑层，重试溜过去；只封 HTTP 层，底层换成受控实现时就没有上界了。

```
停机后底层重试   2 次真实 HTTP → 1 次，拦截点 layer=http
```

**B. 收尾期限没传到在途请求。** `grace_seconds=0.02`，请求却拿到近 5 秒 timeout。
原因是 `grace_seconds` 只限制"何时批准下一次请求"，不限制已批准请求的等待。

剩余收尾时间现在压到该次请求的 socket `timeout` 上（`min(原timeout, 剩余)`）。

```
收尾 0.02s → 传输层收到的 timeout  4.996s → 0.0154s；实测总耗时 0.020s
未停机     → timeout 保持 20，不受任何改动
```

## 三、P1 初始化仍在清理保护之外

闸门装上之后、`try` 之前还有 `V.RPC` 构造、治理器安装等步骤。构造抛出时闸门残留。

哨兵（`gate=None` / `gov=None` / `gate_installed_by_us=False` / `_prev_signals={}`）
**先就位**，`try` 提到**第一个设施安装之前**，`finally` 按哨兵逐项撤销。

```
V.RPC 构造抛出 → 异常如实抛给调用方；http_gate_installed=false、
                 信号处理器已还原、无遗留看门狗线程
```

## 四、回归守卫与反向验证

`test_audit_followup.py` 新增 §19（18 项），并修正 §18 两条因本轮重构而语义改变的断言
（计数拆成逻辑层/HTTP 层两个口径后，原断言只覆盖其中一层）。

| 被测源码 | 结果 |
|---|---|
| 修复后 `2c15b2ee…` / `dcff069f…` | **176 通过 / 0 失败，退出 0** |
| 修复前（v19 快照 `e3be07df…`） | **162 通过 / 14 失败，退出 1** |

审查方 `reproduce.py` 现退出 1（缺口不再复现）；`verify_previous.py` 仍退出 0
（此前各轮修复未回退）。

## 五、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/176
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 388 项断言，9 个入口全部退出 0

$ python3 audit_v19_20260910/reproduce.py        # 退出 1（缺口不再复现）
$ python3 audit_v19_20260910/verify_previous.py  # 退出 0（旧修复未回退）
```

## 六、仍未关闭

- **真链串行/并行同快照对照未做。** 本轮未启动，等放行。
- 硬兜底触发时**不承诺证据完整**，只承诺已 fsync 前缀可读。
- 墙钟软阈值本身仍是协作式；对阻塞 I/O 的墙钟上界来自**收尾期限压到 socket
  timeout** 这条路径，只在停机之后生效。未停机时的单次请求时长仍由
  `V.RPC` 自身 timeout 与全局时间预算约束。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

# 资源约束与停机策略 · 交付（规格 v1.8）

关闭 v17 复核点名的遗留项：**资源上限从「采样」变为「实测峰值 + 硬上限 + 有序停机」**。
这是真链串行/并行对照的前置条件。

源码 hash 见 `source_hashes.json`。规格 **v1.8**（`121308b9902f7467…`）；
v1.7（`b839046b0022c987…`）、v1.6（`30853652fa452509…`）原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

## 一、峰值：从采样改为内核高水位

`rss_peak_kb()` 取 `VmHWM` —— 进程自启动至今到达过的最高 RSS，是**实测**不是采样。
实测对比（分配 64MB 后立即释放）：

```
之前 34964 KB → 峰值 100500 KB；尖峰过后当前值回落到 34984 KB，峰值不回落
```

采样口径在这个场景下会完全看不到那 64MB。证据里 `resource` 记录同时保留
`rss_kb`（当前）与 `rss_peak_kb`（峰值），**报告资源上限只能引用后者**。

## 二、硬上限与停机触发

| 参数 | 判据 | 实测退出码 |
|---|---|---:|
| `--max-rss-mb` | `rss_peak_kb > 上限` | 3 |
| `--max-cpu-s` | `user+sys > 上限` | 3 |
| `--max-wall-s` | 墙钟 > 上限 | 3 |
| SIGTERM / SIGINT | 立即置停机标志 | 3 |

看门狗按 `--governor-poll-s`（默认 0.25s）巡检，`governor_report` 里记
`watchdog_observations`（实测一次运行 162～203 次），可据此确认它**真的在跑**。

## 三、停机是有序的

越线**只置标志**，由候选之间与阶段之间的安全点抛 `Shutdown` 有序收尾。
不在写证据的中途把进程打死 —— 那会留下半行、留下无配对的 `rpc_begin`，
把「资源超限」变成「证据损坏」。实测：SIGTERM 停机后
`read_evidence` 仍判 `complete=true`，`bad_lines=[]`、`unmatched_rpc_begin=[]`。

## 四、停机后的账

| 情形 | 记法 | 实测 |
|---|---|---|
| 停机前已完成 | 正常状态，检查点标完成 | 候选1 `measured_exit`，checkpoint completed=**true** |
| 停机时正在进行 | `aborted_by_shutdown`，不算完成 | 候选2 `aborted_by_shutdown`，completed=**false**，`incomplete=[2]` |
| 停机时还没轮到 | 进 `acceptance.not_started`（含原因） | `[{index:1,reason:rss_limit_exceeded},…]`，`missing_candidates=[]` |

`set_complete=false`、`process_completed=false`、`validation_passed=false`。
**停机绝不报告为成功。**

放宽限额后续跑实测：首次 exit 3 → 续跑 exit 0，两个候选齐备，已完成的不重做。

## 五、退出码 3

| 码 | 含义 |
|---|---|
| 0 | 全部完成且验收通过 |
| 1 | 采集完成但判定不通过 |
| 2 | 前置条件不满足 |
| **3** | **有序停机**。检查点完整，放宽限额后可续跑 |

## 六、顺手堵掉一类反复踩的错误

加 CLI 选项 → 自建 `Namespace` 的调用者 `AttributeError` 崩掉，而崩掉的入口显示
「通过 0 / 失败 0」，**看起来像没跑而不像失败**。这一轮又踩了一次：
`test_e2e_blocking` / `test_resume` / `test_parallel` 三个入口因 `max_rss_mb` 缺失退出 1。

治理：`OPTIONAL_DEFAULTS` 登记所有可选参数及默认值，`opt(args, name)` 统一读取
（未登记的名字直接 `KeyError`）。守卫两条：
* `OPTIONAL_DEFAULTS` 必须与 `argparse` 实际默认值一致 —— 这条**当场抓到**了
  `spec` 的不一致（登记 v1.8、argparse 还是 v1.7）；
* 只填必需项的最小 `Namespace` 必须能跑完 —— 这条**当场抓到**了 `args.checkpoint`
  等 11 处直读。

## 七、回归守卫与反向验证

`test_audit_followup.py` 新增 §16（资源与停机，31 项）、§17（选项漂移，5 项）。

| 被测源码 | 结果 |
|---|---|
| 修复后 `ff052ba8…` / `f3ea0eee…` | **135 通过 / 0 失败，退出 0** |
| 修复前（v17 快照 `5aa7df20…` / `6602381f…`） | **102 通过 / 28 失败，退出 1** |

§16 的 31 条里 28 条在旧版失败，3 条是对照项（旧版本就该通过的行为）。

写守卫时发现一个隐患并修掉：SIGTERM 测试在**没有装处理器**的实现上会把测试进程
自己打死（旧版实测如此，日志显示 `Terminated`）。改为先装一个良性兜底处理器 ——
被测实现若接管了信号，兜底处理器收不到；没接管则断言正常报 FAIL 而不是进程消失。

## 八、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py        # 0  / 29      $ python3 test_resume.py         # 0  / 23
$ python3 test_first_mint.py      # 0  / 17      $ python3 test_parallel.py       # 0  / 23
$ python3 test_step3.py           # 0  / 27      $ python3 test_audit_fixes.py    # 0  / 34
$ python3 test_step4.py           # 0  / 18      $ python3 test_audit_followup.py # 0  / 135
$ python3 test_e2e_blocking.py    # 0  / 41
                                  # 合计 347 项断言，9 个入口全部退出 0
```

## 九、仍未关闭

- **真链串行/并行同快照对照未做**。资源约束与停机策略是它的前置条件，现已具备；
  `--pin-finalized` 提供同快照绑定。**本轮未启动，等放行。**
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

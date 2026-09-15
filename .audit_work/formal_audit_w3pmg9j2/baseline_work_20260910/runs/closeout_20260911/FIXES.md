# v1.14 审核收尾：测试产物隔离 + 规格口径更正（规格 v1.15）

对应审核：`audit_v114_20260911/REVIEW.md` §3、§4。源码 hash 见 `source_hashes.json`。
规格 **v1.15**（`77f27cedf928684a…`）；v1.14（`f8dc892cca096369…`）原始字节未动。
**测量判据未改；连接/停机实现未改（`evidence.py` 与审核通过的 v1.14 逐字节相同，`1fe5c43c…`）。**

## 一、测试产物隔离

**问题**：`phase_probe.py` 固定写回自身旁边的 `phase_probe.json`，测试入口 §23 又调用它，
于是每跑一次全入口就覆盖一次交付件。审核方 v1.14 复跑时实际发生了覆盖，原件不可恢复。

**处置**
* 现存文件改名为 `runs/tls_20260911/phase_probe.overwritten_by_audit_suite.json`，
  sha256 `e8cc2ff3…` 与审核方 `artifact_overwrite.json` 记录一致；
  同目录 `ARTIFACT_NOTE.md` 说明它**不是交付原件**，交付原件请引用 `phase_probe.log`。
* 两个会往交付目录写文件的探针（`phase_probe.py`、`reproduce_retry_gated.py`）改为
  **只写到 `RT_PROBE_OUT` 指定目录，未指定则不落盘**；测试给它们传每次新建的临时目录。
* 新增 §24：在任何一节运行**之前**给 `runs/*` 与 `audit_*` 下全部文件拍 sha256 快照，
  末尾逐一核对「未改写、未删除、未新增」。用绝对路径，反向验证时不会退化成核对空目录。
  守卫自证：临时写入一个文件、改写一个交付件，两者都被抓到；清理后快照完全复原。
  本次全量运行：442 个文件，零改写、零删除、零新增。

## 二、规格口径更正（v1.15，只改陈述不改判据）

每条都先对照当前代码核实，核实后**确实未实现**的标注保留不动：

| # | 更正 |
|---|---|
| C1 | 撤回「省 2～3.5ms」及其非配对数据，换成交替 A/B 配对结果；注明「未测出显著增量 ≠ 没有成本」，本地结果不用于推断真链瓶颈 |
| C2 | §3 买入 stage20 → `entry_unknown`：待实现 → **已实现** |
| C3 | §3 `no_mint_by_cutoff` 核验：待补 → **已实现** |
| C4 | §3 pair 无代码/储备为 0 诊断：核对后**确实未实现，保留「待实现」** |
| C5 | §4 G 按到达阶段计：待实现 → **已实现**（`reached_attempts()`） |
| C6 | §4 缺 baseFee 记未知：待实现 → **已实现** |
| C7 | §6 三条"下一步要补的核验"：**均已实现**，与 §5 冲突；改标题并注明位置 |
| C8 | §6.0「资源项只有采样」→ 指向 §7，并说明**离线已测、真链尚未经受** |
| C9 | §7.3「`shutdown` + `close()`」→ 分阶段句柄、**只 shutdown**（实测 `close()` 打断不了 `connect()`） |
| C10 | §7.5 退出码 3：「有序停机、检查点完整」是**错的** —— 它有两个来源 |

C10 细节 —— 代码里产生退出码 3 的五处：

| 来源 | 位置 | `run_footer` | 结果 JSON |
|---|---|---|---|
| 有序停机 | `measure()` 三处 `return 3`（启动·链身份、启动·快照、候选之后） | 有 | 有，`shutdown.stopped=true` |
| 强制终止 | `_on_escalate`、`_hard_exit` 两处 `os._exit(3)` | **无** | 通常无 |

**区分依据是该 `run_id` 的证据是否有 `run_footer` 且 `complete==true`**，不是退出码，
也不是 `.escalation` 文件（它是尽力写的，可能不存在）。

**关于「§1–§4 一字未改」**：此前各版这句话是字节事实；本版改了 §3/§4 的字节（仅状态标注），
所以不再这样写。stage→状态映射、成本公式、计入条件、情景设定本身未动。

## 三、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/230
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 442 项断言，9 个入口全部退出 0
```

本目录的测试日志先写到临时目录、运行结束后才拷入 —— 否则运行中被重定向进 `runs/` 的日志
本身会被 §24 判为「新增文件」。

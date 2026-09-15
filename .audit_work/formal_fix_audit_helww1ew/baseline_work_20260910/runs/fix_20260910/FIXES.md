# 第二轮审查九项反例 · 修复交付

对应审查报告：`audit_followup_20260910/REVIEW.md`
被测源码 hash：见本目录 `source_hashes.json`
规格：**v1.5**（`MEASUREMENT_SPEC.v1.5.md`，sha256 `9c8d8480d4657aa3…`）；
v1.4 原始字节未动（sha256 仍为 `ffb6ecf0dd84517e…`）。

**未跑真链。未做真链并行对照。正式冻结与 300 样本仍关闭。**
本轮全部输出写在 `runs/fix_20260910/`，未覆盖包内历史日志，未改冻结的 v3 包。

## 一、先复现，再修

审查方给的两个反例脚本在**修复前**的代码上逐条复现，结果与其 `remaining.log`
/ `retry.log` 完全一致（8 条观测 + 1 条限流反例）。源码 hash 与其
`source_hashes.json` 逐字节相同，确认审的就是同一份代码。

## 二、逐条修复

| # | 反例（修复前实际行为） | 修复 | 位置 |
|---|---|---|---|
| 1 | **P0** 删掉旧结果与证据后续跑仍 `exit=0`、`results=[]`、`set_complete=true` | 完成时把结果本体 + sha256 写进检查点；续跑逐条校验并**并入累计交付**；校验不过者不跳过、重新测量；引用的证据缺失/损坏则验收不通过 | `evidence.Checkpoint.record_attempt` / `.deliverable`、`pilot_measure.measure` |
| 2 | **P0** 检查点中段坏行被静默跳过 | 中段损坏 `SystemExit` 阻断；尾部半行仍按中断隔离到 `.orphan` 后放行 | `evidence.Checkpoint.__init__` |
| 3 | **P0** `max_calls=2` 实际 3 次；启动、串行、Etherscan 在预算外 | 闸门在**第一个请求之前**建立并覆盖全程；`max_calls` 对**逻辑请求数**与**实际 HTTP 次数**同时封顶 | `pilot_measure.measure`、`evidence.SharedGate.acquire` |
| 4 | **P0** `V.RPC` 内部 503 重试不经全局限流：要求 10s 间隔，实测 **1.0s** | 闸门下移到**真实 HTTP 边界**（包住 urlopen），重试同样排队同样计数。实测间隔 **10.01s** | `evidence.install_http_gate` / `SharedGate.acquire_http` |
| 5 | **P1** 买入成功后槽位查询抛异常 ⇒ 成本表整个不存在 | 买入腿一旦执行成本必然生成；退出腿未尝试记 0 次；`R_wei` 与退出 base fee 独立保留未知 | `pilot_measure.handle` 统一异常收尾 |
| 6 | **P1** 声明 2 个候选、`index=[1,1]` 仍 `exit=0` | 测量前校验样本数量与编号唯一性；结果与冻结样本**逐项**比对（重复/多余/字段不符均阻断） | `pilot_measure.measure` |
| 7 | **P1** 空证据、孤立 `rpc_end`、缺 `run_header` 判 `complete=true` | 空文件、孤立 end、重复 `pending_id`、缺运行头一律判不完整 | `evidence.read_evidence` |
| 8 | **P1** `transactionHash='0x'`、`blockHash='WRONG'`、`logIndex='garbage'` 全通过；sender topic 非十六进制裸抛 `ValueError` | 按 32 字节 hash / 非负整数校验；非十六进制返回明确拒收原因 | `pilot_measure._validate_log`、`_is_hash32`、`_as_uint` |
| 9 | **P1** 汇总写死 `MEASUREMENT_SPEC.md v1 (draft)` | 记录实际绑定的规格文件名与 sha256 | `pilot_measure.measure` |

顺带补入并行验收所需的两项机制：

- `--pin-finalized <块号:块hash>`：串行与并行用**各自独立的检查点**绑到同一状态块。
  共用检查点会让第二次直接跳过候选，各自新建又会各取各的 finalized ——
  两条路都不构成同快照对照。
- 区块缓存命中逐条落 `block_cache_hit`（`fetched_by_worker` / `used_by_worker` /
  块号 / 块 hash），缓存口径可查而非靠推断。
- 每候选 Etherscan 次数改为按候选归集（`counts_by_candidate`），
  不再用共享计数器差值（并行重叠会把别的候选算进来）。

## 三、关于 `reproduce_retry.py`：它在修复后仍会"复现"

必须说清楚：**审查方原件在修好之后跑仍然退出 0**，但这不是修复失败。

原件用 `patch.object(V.urllib.request, 'urlopen', ...)` 把 urlopen 整个换掉，
而本次修复正是在**这一层**包住 urlopen；换掉它等于把闸门一并换掉。
原件自己的输出即为佐证 —— 它报 `"http_calls": 0`，闸门一次都没被调用过。

对照版本 `reproduce_retry_gated.py` 只改一处：受控传输通过
`install_http_gate(gate, transport=...)` 装在**闸门之下**，其余（同一个真实 RPC 类、
同一个 RpcTap/SharedGate、同样的 503 重试）完全一致。结果：

```
修复前（原件）: http_start_seconds [0.018, 1.020]  间隔 1.00s   http_calls 0
修复后（对照）: http_start_seconds [0.024, 10.034] 间隔 10.01s  http_calls 2
                required_http_interval_seconds = 10.0
```

## 四、回归守卫必须自己先被证伪

审查方的 `reproduce_remaining.py` 断言的是 **bug 存在**，修好之后它必然失败
（现在停在第 18 行 `assert rc==0 and not doc['results']`），因此不能当回归守卫。
新写 `test_audit_followup.py`（65 项）断言**修复后**行为，并在**修复前的源码快照**上
跑同一份守卫作为反向验证：

| 被测源码 | 结果 |
|---|---|
| 修复后（`pilot_measure.py` `90703719…` / `evidence.py` `56f1f45c…`） | **65 通过 / 0 失败，退出 0** |
| 修复前（审查快照 `d5b036c6…` / `68722955…`） | **14 通过 / 51 失败，退出 1** |

前后对照日志：`test_audit_followup.log`（修复后）、
`test_audit_followup.ON_PREFIX_CODE.log`（修复前）。
修复前那 14 项通过的是"本不该回归"的对照项（例如"规范事件仍然通过"、
"尾部半行被隔离而非阻断"），不是守卫本身。

写守卫过程中查出并改掉了我自己的**三处空断言**（对空列表用 `all(...)` 恒为真，
以及整流程里 `P.etherscan` 被 mock 整体替换、真函数根本没跑却断言其计数）——
这些若留下，旧代码同样能"通过"。

## 五、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py          # 退出 0   通过 29 / 失败 0
$ python3 test_first_mint.py        # 退出 0   通过 17 / 失败 0
$ python3 test_step3.py             # 退出 0   通过 27 / 失败 0
$ python3 test_step4.py             # 退出 0   通过 18 / 失败 0
$ python3 test_e2e_blocking.py      # 退出 0   通过 41 / 失败 0
$ python3 test_resume.py            # 退出 0   通过 23 / 失败 0
$ python3 test_parallel.py          # 退出 0   通过 23 / 失败 0
$ python3 test_audit_fixes.py       # 退出 0   通过 32 / 失败 0
$ python3 test_audit_followup.py    # 退出 0   通过 65 / 失败 0
                                    # 合计 275 项断言，9 个入口全部退出 0

$ python3 runs/fix_20260910/reproduce_retry_gated.py     # 退出 0
$ python3 audit_followup_20260910/reproduce_remaining.py # 退出 1（bug 已不复现）
$ python3 audit_followup_20260910/reproduce_retry.py     # 退出 0（见第三节：绕过了闸门）
```

## 六、本轮**未**解决、仍需保留的限制

- **资源上限未实现**。现有只是启动/候选起止/关闭的**采样**，不是硬 RSS/CPU 上限，
  也不是可靠峰值。不得表述为"资源上限已验收"。已写入规格 v1.5 §5 状态表。
- **真链串行/并行对照未做**。`--pin-finalized` 只是让对照**成为可能**的机制，
  机制本身在受控链上验证过（6 项），但对照本身尚未运行。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

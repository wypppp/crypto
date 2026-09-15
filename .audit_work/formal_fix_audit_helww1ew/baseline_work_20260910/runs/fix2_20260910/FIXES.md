# 第三轮审查三项缺口 · 修复交付

对应审查报告：`audit_v15_20260910/REVIEW.md`
源码 hash：见本目录 `source_hashes.json`
规格：**v1.6**（`MEASUREMENT_SPEC.v1.6.md`，sha256 `30853652fa452509…`）；
v1.5（`9c8d8480d4657aa3…`）与 v1.4（`ffb6ecf0dd84517e…`）原始字节未动。

**未跑真链。未做真链并行对照。正式冻结与 300 样本仍关闭。**
本轮输出写在 `runs/fix2_20260910/`，未覆盖 `runs/fix_20260910/` 的上一轮记录。

## 一、先复现

审查方 `reproduce.py` 在修复前源码上跑，三条观测全部复现，且
`pilot_measure.py` / `evidence.py` 与其 `*.audited.py` **逐字节相同**
（`90703719…` / `56f1f45c…`），确认审的是同一份代码。

## 二、逐条修复

### 1. P0 —— 续跑证据必须绑定到具体运行、候选与结果 hash

上一轮我只检查了「文件在不在、结构完不完整」。审查方把引用的证据换成
**另一个运行**的结构完整文件，续跑照样 `exit=0`、`evidence_chain_problems=[]`。
文件结构完整与「它支持这条结果」是两回事，我把前者当成了后者。

新增 `evidence.verify_evidence_supports()`，逐项对上：

1. 文件可读、（排除进行中的运行后）结构完整；
2. 里面**存在**检查点记录的那个 `run_id`；
3. 该运行的 `run_header` 绑定（脚本 / 证据模块 / 规格 / 样本 / 台账 /
   finalized 块号与 hash）与检查点绑定一致；
4. 该运行里有**这个候选**的 `candidate_result`，且其 `record` 的规范 hash
   等于检查点记的 `result_sha256`。

任一不符即列入 `evidence_chain_problems` 并阻断验收（结果仍从检查点交付，
不丢数据，但不判通过）。

配套前提：逐候选结果在写入检查点与证据**之前脱敏一次、两处共用同一份字节**。
否则结果里一旦出现被脱敏的串，两边 hash 天然不符，上面的 hash 绑定会误伤
正常续跑。顺带堵住了「检查点未过脱敏」这个口子。

### 2. P1 —— 诊断失败不得抹掉已到达的卖出阶段

卖出的 `attempts` 原来写在诊断之后；诊断抛异常时，我上一轮加的统一收尾
把「缺 attempts」默认成 0，于是已经发生的 swap 被记成「未尝试」。
改成**主卖出返回后立即**写入 `rec["exit"]["attempts"]`。诊断调用本身仍
**不**计为交易尝试。

```
修复前  sell.stage=20 → exit_attempts {swap:0, approve:0} basis "exit leg never attempted"
修复后  sell.stage=20 → exit_attempts {swap:1, approve:2} basis "reached swap"
        主场景 gas 165000000000000（只有买入腿）→ 440000000000000（含卖出腿）
```

### 3. P1 —— `http_calls` 名为实际、实为预留

这是我上一轮自己引入的：把计数改名成「实际 HTTP 次数」，却仍在**发车等待之前**
递增；等待后被时间闸门拒绝的请求根本没发出，却已经计进去了。名字比事实跑得快。

拆成三个口径：

| 字段 | 含义 |
|---|---|
| `http_reserved` | 已占用的额度，**预算判定依据**。并发下必须先占后发，占用后不退还 |
| `http_sent` | `note_sent()` 紧挨传输调用登记，**唯一可当作实际网络调用量** |
| `http_rejected_after_wait` | 占了额度、排队后被时间闸门拒绝，请求并未发出 |

恒等式 `reserved == sent + rejected`。并**刻意不保留** `calls` 这个名字 ——
它正是「名为实际、实为预留」的来源，调用方必须明写口径。
（移除别名后立刻暴露出 `acquire()` 里一处漏改，5 个入口当场报错；
若留着别名，这处会静默地继续用错口径。）

```
反例条件 rps=10、max_seconds=0.02：第一次发出，第二次排队后被拒
修复前  传输实际执行 1 次，http_calls 报 2
修复后  http_sent=1、http_reserved=2、http_rejected_after_wait=1
```

## 三、回归守卫与反向验证

`test_audit_followup.py` 新增 §13–§15（28 项），断言**修复后**行为。
其中不止复刻审查方的反例，还补了它没走到的分支：
候选 `candidate_result` 被删、被改（hash 不符）、`run_header` 绑定被改。

| 被测源码 | 结果 |
|---|---|
| 修复后 `ea6d940e…` / `60827b66…` | **93 通过 / 0 失败，退出 0** |
| 修复前（审查快照 `90703719…` / `56f1f45c…`） | **72 通过 / 21 失败，退出 1** |

日志：`test_audit_followup.log`、`test_audit_followup.ON_PREFIX_CODE.log`。

两条标注为「不变量」的断言在修复前也通过（检查点与证据 hash 一致、检查点
不含明文凭据）—— 它们守的是第 1 项修复所依赖的前提，不是反例本身的守卫，
不应算作本轮的证据。

审查方 `reproduce.py` 现退出 1（第 19 行断言不再成立），符合预期：
它断言的是缺陷存在。

## 四、命令与退出码

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py          # 退出 0   通过 29
$ python3 test_first_mint.py        # 退出 0   通过 17
$ python3 test_step3.py             # 退出 0   通过 27
$ python3 test_step4.py             # 退出 0   通过 18
$ python3 test_e2e_blocking.py      # 退出 0   通过 41
$ python3 test_resume.py            # 退出 0   通过 23
$ python3 test_parallel.py          # 退出 0   通过 23
$ python3 test_audit_fixes.py       # 退出 0   通过 34
$ python3 test_audit_followup.py    # 退出 0   通过 93
                                    # 合计 305 项断言，9 个入口全部退出 0

$ python3 audit_v15_20260910/reproduce.py   # 退出 1（三条缺陷均不再复现）
```

## 五、关于 `retry_gated.json` 被复跑覆盖

审查方指出该脚本固定写回同一文件名，复跑会把交付时的原始测量冲掉 —— 属实。
已改为按 UTC 时间戳写新文件（`retry_gated.<stamp>.json`）并打印路径，
复跑不再覆盖既有测量。`runs/fix_20260910/retry_gated.json` 现存的是审查方
本轮复跑的 10.005 秒值，不是交付时的 10.01 秒原件；该文件不应再被当作
上一轮的原始 JSON 引用。

## 六、仍未关闭

- **资源上限未实现**。只有启动/候选起止/关闭的采样，不是硬 RSS/CPU 上限，
  也不是可靠峰值。不得表述为「资源上限已验收」。
- **真链串行/并行对照未做**。`--pin-finalized` 只是使其成为可能的机制。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。

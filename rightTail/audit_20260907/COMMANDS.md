# 2026-09-07 独立验收命令与结果

所有测试数据位于 `/tmp`；`rightTail/rt_a_selftest` 在本轮未被测试写入。源码原有未提交修改保留，`changes.patch` 以接手快照为基准，而非 Git HEAD。

## 接手基线

```bash
mkdir -p /tmp/rta-audit-baseline
cp rightTail/rt_a_attribution.py rightTail/covcheck.py rightTail/README.md /tmp/rta-audit-baseline/
cd /tmp/rta-audit-baseline
python rt_a_attribution.py selftest > selftest.log 2>&1
python covcheck.py > covcheck.log 2>&1
```

两命令退出码均为 0。selftest 79/0；指定行 46/46，有 L2b 重复锚点告警。完整输出：`baseline-selftest.log`、`baseline-covcheck.log`。

```bash
python rightTail/audit_integration.py --source /tmp/rta-audit-baseline/rt_a_attribution.py --out /tmp/rta-audit-before
```

初始七场景版本，整体退出 1。auto 退出 0；missing、empty_missing、foreign_integrity、reconcile、forward_scope、gap_migration 各退出 1。见 `before-results.json` 与 `before-integration-artifacts.tar.gz`。

关键原版反例：

- 缺一条候选日志：backfill 返回 None，CLI 会映射为 0；已有 report 虽能拒绝非空失败样本，不能约束 backfill 退出。
- 预期一条、返回零条：attribution=0；report 跳过无归因模式，旧正式文件仍存留。
- 归因 spec_hash 改为 foreign：另一个规格的通过记录仍让 report 返回 0。
- reconcile 将结果写入 backfill/history 与 backfill/candidate，并调用了反向空区间 fetch(1000,999)。后者不一定产生网络请求，但证实入口不是独立采集批次。
- 链头 1403：forward 实际 fetch(1404,1406)，还 fetch(1401,1403)，未限制批次和上界。
- 旧 log_gaps 主键仅有区间：相同区间的 history/forward 插入互相覆盖。

## 修改后

```bash
python rightTail/audit_integration.py --out /tmp/rta-audit-accepted
```

整体退出 0，12 个场景符合预期：

| 场景 | 子进程退出 | 验收 |
|---|---:|---|
| auto | 0 | 完整 backfill 首次 fetch 走 etherscan |
| missing | 0 | 5→4，backfill/report 返回 1，INCOMPLETE，移除旧正式文件 |
| empty_missing | 0 | 1→0，零归因仍拒绝正式报告 |
| foreign_integrity | 0 | 无本批完整性证据的行不得借用其他批次通过记录 |
| reconcile | 0 | 只 fetch(1000,1040)，无历史/归因/报告，不写 backfill 对账 |
| forward_scope | 0 | 不补其他批次未来区间，已有历史行及归因逐列不变 |
| gap_migration | 0 | 旧 unknown 与同区间 history/forward 三行均保留 |
| forward_retry | 0 | 首轮静默少一条，整区间重试对账后销账，共两归因 |
| history_retry | 0 | 历史缺口回填成功后销账，样本仍为历史，正式报告恢复 |
| empty_success | 0 | 真空母体，backfill/report=0，N=0/n/a |
| cli_missing | 1（预期） | main 实际退出1且已有 INCOMPLETE 产物 |
| cli_reconcile_missing | 1（预期） | reconcile main 实际退出1，无覆盖率报告 |

汇总见 `accepted-results.json`。每场景数据库、进程输出和报告在 `accepted-integration-artifacts.tar.gz`。

```bash
cd /tmp/rta-audit-verify
python /home/ancillary/rightTail/rt_a_attribution.py selftest > selftest-final.log 2>&1
python /home/ancillary/rightTail/covcheck.py > covcheck-final.log 2>&1
```

退出码均 0；81/0、46/46，无普通锚点歧义告警。导入路径 `/home/ancillary/rightTail/rt_a_attribution.py`。输出见 `selftest.log`、`covcheck.log`。既有未来区块“应补回”的断言改为“不得补回”，另加本批范围内重试成功的正向断言，未删除验收要求。

```bash
python -m py_compile rightTail/rt_a_attribution.py rightTail/covcheck.py rightTail/audit_integration.py rightTail/audit_live_reconcile.py
```

退出 0。

## 真实只读小区间

```bash
python rightTail/audit_live_reconcile.py --from-block 25919774 --to-block 25921774 --out /tmp/rta-live-reconcile-20260907 > /tmp/rta-live-reconcile.log 2>&1
```

退出 0。使用 `.env` 已配置 Etherscan key 与 Alchemy endpoint，未升级套餐。日志见 `live-reconcile.log`；请求/响应与数据库见 `live-reconcile/`。

总计 4 次接口调用，无重试：

1. RPC eth_chainId → 1。
2. Etherscan logs/getLogs：Factory PairCreated，25919774..25921774，offset=1000 → 34 条。
3. RPC allPairsLength at 25919773 → 521009。
4. RPC allPairsLength at 25921774 → 521043。

差值 34，日志去重 34，池序号 521010..521043 连续且边界一致，缺口0。历史回看0；无 L2b 历史探测、无归因接口、无 Mint/入账/历史部署请求。数据库 candidates/hist_sender/attribution/log_gaps 均0行，collection_runs=1；无覆盖率报告。`collection_*.json` 保留34条日志和对账详情。

环境缺少运行时 keccak 后端，脚本使用既有已校验 topic 常量；真实 PairCreated 响应与 allPairsLength 对账通过。不据此宣称完整归因链路或前向时效通过。

## 未执行

正式 backfill 与 forward：未找到真实冻结正式窗口，仅有 selftest 1000..1200、lookback900 的 mock 规格。没有猜测起止块，没有将小区间通过扩大为正式窗口验收。已向用户请求正式起止块及历史回看规格。

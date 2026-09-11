# 最终执行与验收记录

工作目录：`/home/ancillary`。正式和前向执行的核心源码SHA256均与当前文件一致：`3c761f2f79e8f95be67612a2dd0aab3bd2aabce417a27ab9544585f673acf3b4`。

## 正式回填

```bash
/home/claude/miniconda3/bin/python -u /home/ancillary/rightTail/run_formal.py --from-block 25800000 --to-block 25900000 --lookback 2500000 --memory-mib 768 --reuse-evidence /home/ancillary/rightTail/formal_B_25800000_25900000_v4/public_requests.jsonl.gz --out /home/ancillary/rightTail/formal_B_25800000_25900000_v5
```

进程最终退出0；详见对应输出目录execution.json。

## 30分钟前向观察

```bash
/home/claude/miniconda3/bin/python -u /home/ancillary/rightTail/run_formal.py --from-block 25800000 --to-block 25900000 --lookback 2500000 --memory-mib 768 --observe-minutes 30 --seed-db /home/ancillary/rightTail/formal_B_25800000_25900000_v5/backfill/rt_a.sqlite --out /home/ancillary/rightTail/forward_B_20260909_30m
```

进程最终退出0；详见对应输出目录execution.json。

## 2026-09-10最终独立验收

```bash
python3 rightTail/verify_forward_run.py --run rightTail/forward_B_20260909_30m --seed-db rightTail/formal_B_25800000_25900000_v5/backfill/rt_a.sqlite
```

退出0：149块，148个连续采集区间，事件2/2，截止内联合可用2/2，时延30.0/31.1秒，历史逐行不变，缺口0，缓存命中0。

```bash
python3 rightTail/audit_live_reconcile.py --from-block 25940110 --to-block 25940258 --out rightTail/forward_B_20260909_30m/final_reconcile
```

退出0：4次真实请求；预期2、去重2，计数/连续性/边界通过。历史回看0，不归因、不生成覆盖率报告。

既有离线验收：selftest85通过/0失败、covcheck46/46、独立集成16项通过；日志和逐场景退出状态保存在本目录。核心代码未再改动，本轮新增最终产物验收，未重复全部回归。

本轮文档修改：FORMAL_RESULTS.md填写最终前向结果与结论边界；HANDOFF.md关闭本轮执行项并保留故障原因未知和后续项；README.md同步实际结果。最终文档差异见final_documentation.patch。

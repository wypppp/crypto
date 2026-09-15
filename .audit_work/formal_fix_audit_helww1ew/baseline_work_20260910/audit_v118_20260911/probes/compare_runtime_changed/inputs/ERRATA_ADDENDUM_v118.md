# 勘误补记（规格 v1.18）

`ERRATA_20260911.md` 保留原字节。其 E5 给出的 `compare_runs.py` 只读复核命令，自 v1.18 起还需要两个必需参数
（比较器此前漏验检查点的原语 hash 与 runtime_params，审核 v1.17 P1；缺这两个参数时退出 2 并提示）：

```bash
    --expect-primitives-sha bc9ea52ec51259d79cfe435d47dc0d846fadd56d866494e7dfcfaf3b92c15d52 \
    --expect-runtime-params '{"slot_limit": 32, "diagnostics": true, "cutoff_block": 24781026, "amount_wei": 50000000000000000}'
```

本目录五次运行是 v1.16 产出的，运行证据里没有 `run_binding` 记录；比较器对它们走明确的旧版规则
（原语 hash 对照结果文件的 `package_script_sha256`，runtime_params 对照运行头 `params`），58 项必需检查全部通过。
结果见 `../v118_20260911/recheck_realchain2_v118.json`。驱动 `run_compare.py` 会自动传这两个参数，无需手填。

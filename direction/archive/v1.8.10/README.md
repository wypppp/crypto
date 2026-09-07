# Probe L 复现包 · v1.8.10 · 2026-09-06

本包可独立离线重跑 **L03_CLASSIFY**，包含 1,453 篇正文、输入清单、脚本、配置和正式输出。默认配置来自包内脚本同目录；跨目录选配置必须显式设置 `L_CONFIG`。运行时须进入本包目录（输入使用相对路径）。

```bash
cd direction/repro_L
sha256sum --check SHA256SUMS.txt
env -u L_CONFIG python3 -B L_03_classify.py
```

运行会写入 `L_mother_events.json`。它的 `stage` 是 `L03_CLASSIFY`，内容是未作最终裁定的候选，并非最终联合母表。验收结果：97 项检查通过、退出码 0；24 条 L03 回归执行，另 1 条 B_RESOLVE 和 2 条 TIME_CHAIN 未执行。A=82、B_FIRST=45、C2 来源=22/分组=11、OTHER=292、PARSE_FAIL=13、raw_events=1076、candidate_groups=1062、A_FALLBACK=4。计数一致只证明复现一致，不构成分类正确性的独立证据。

SUI 本阶段保持 12:15；12:00 留待 TIME_CHAIN 验收。CYBER/SEI 增加来源不重复计上市次数；MBOX 位于回看缓冲区。13 篇解析失败仍待评估。尚未重算频率、容量或收益。

`L03_run.log` 是正式运行日志；`isolated_run.log` 是工作目录外副本运行日志，输出字节一致。两份 `injected_failure*.log` 是在隔离副本把 C1 期望 98 故意改成 99 的反例：均退出 1，已有产物未覆盖、无产物时未新建。它们不是正式配置失败。结果见 `validation.json`。

`provenance.json` 列明当前运行输入和历史附属文件。其他采集/T0 脚本及数据保留旧包原字节和原生产配置哈希，未在本轮重跑；本包不宣称完整流水线已升级验收。复现无须运行这些采集脚本。原 v1.6 包及原哈希表完整保存在 `direction/archive/repro_L_v1.6_before_v1.8.10/`。新版本快照位于 `direction/archive/v1.8.10/`。

`SHA256SUMS.txt` 覆盖本包所有文件（除自身），包括全部正文与日志。日志内临时目录是执行位置记录，不是运行依赖。详细当前状态见 `direction/当前状态.md`。

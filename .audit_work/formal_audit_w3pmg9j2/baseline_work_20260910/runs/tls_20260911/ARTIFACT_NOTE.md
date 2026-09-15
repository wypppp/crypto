# 本目录产物说明

## `phase_probe.overwritten_by_audit_suite.json` —— 不是交付原件

交付时 `phase_probe.py` 固定把结果写到自身旁边的 `phase_probe.json`，
而测试入口 `test_audit_followup.py` §23 会调用这个探针 ——
于是**每跑一次全入口测试就覆盖一次该文件**。审核方 v1.14 复跑（`audit_v114_20260911/`）
时实际发生了覆盖，审核前未另存原始字节，原件已不可恢复。

现存文件是某次测试复跑写下的内容，已改名以免被当作交付原件引用。
其 sha256 为 `e8cc2ff34dc7f4e976ae0602ad0ccaf5c10eac6f49f1f3ec21372953b4f62ff5`，
与审核方 `artifact_overwrite.json` 记录的 `current_sha256` 一致 —— 改名的正是被覆盖的那份。
审核方另存了一份副本及其 hash/mtime：`../../audit_v114_20260911/phase_probe.overwritten_by_suite.json`、
`artifact_overwrite.json`。

**交付原件请引用 `phase_probe.log`** —— 它由交付时的命令重定向写入，
测试入口只捕获探针的 stdout，不写该日志。

## 修正

探针现在只写到环境变量 `RT_PROBE_OUT` 指定的目录，未指定则不落盘。
测试入口给它传一个每次新建的临时目录，并在整次运行前后核对
`runs/` 与 `audit_*/` 下全部文件的 sha256 不变（`test_audit_followup.py` §24）。

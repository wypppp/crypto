# 真链对照 · 首轮（保留原样，不作为对照结论）

串行 8 个候选跑完（`serial.*`），但端点在运行末尾瞬时掐断 TLS 连接：最后一个候选 491473
在出场状态校验时遇到 `TLS/SSL connection has been closed (EOF)`，记为 `state_validation_failed`；
随后几秒启动的并行（`parallel.*`）与续跑（`resume_serial.*`）在第一个请求就抛出未捕获异常。

这暴露了启动阶段的缺陷，已在规格 v1.16 修复。代码变更后本轮检查点按设计不可复用，
对照改在 `../realchain2_20260911/` 用修复后的代码重跑。结论与完整分析见那里的 `REPORT.md`。

本轮串行的前 7 个候选与第二轮串行逐字段一致（`../realchain2_20260911/cross_round_report.json`）。

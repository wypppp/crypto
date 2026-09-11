# v1.6 离线复核（已由 v1.7 修复接续）

本目录是审查进行中的工作产物，曾先落反例与日志、后补报告；不代表未告知的另一项任务。

9 个入口本轮顺序执行均退出 0，305 项断言：29+17+27+18+41+23+23+34+93。原三项修复通过独立验证（verify_three.py / observations.json）：无关 run 证据拒绝；主卖出 stage20 后诊断失败仍保留 swap1/approve2，主场景440000000000000wei；实际传输1次时sent1/reserved2/rejected1。

仍复现一个同类缺口：verify_evidence_supports 使用 `if a is not None and a != b`，删除绑定字段会跳过比较。script/evidence_module/spec/sample/universe/finalized_snapshot 六项分别删除后，完整续跑均 exit0、n2、validation_passed=true、evidence_chain_problems=[]。完整反例见 reproduce_missing_binding.py、missing_binding.json；被测源码与交付完整hash一致，见 hashes.json 与 *.audited.py。

用户在审核期间同步：其他实现者已根据这个反例修成 v1.7。因此本目录保留 v1.6 的历史失败证据，不覆写成修复后成功；最新结论见 ../audit_v17_20260910/REVIEW.md。9入口日志为305项版本，不用它证明311项版本。

本轮只离线审核，未修改实现、未请求真链、未覆盖交付方旧重试结果。

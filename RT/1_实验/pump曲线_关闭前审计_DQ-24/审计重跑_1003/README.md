# C1 审计重跑 v2（代码审计 10-03 第 2、12 处，10-02）

> 依据：总控第十轮第 2 条（[存档](../../../3_审计/2026-10-02_总控第十轮_GPT代码审计14处.md)）。结论与新旧对照见 [修复记录](../../../3_审计/2026-10-02_代码审计修复记录.md) §1。上一级的 v1 文件一律不改。

| 文件 | 是什么 |
|---|---|
| `build_c1_sql_v2.py` | 调用 v1 的 `sql()`，做五处文本替换（每处断言命中次数）：池上成交后的状态＝本笔交易前＋本笔变动（买入用 `quote_amount_in_with_lp_fee`）；异常只按入场及之前判定（入场后才出现的记 flags 4096）；排序键加外层指令序号；持有期内已毕业但最后状态仍在曲线上的记 flags 8192 |
| `test_audit_c1_v2.py` | 永久测试：DuckDB 跑 v1 与 v2 的 SQL 片段，用 GPT 的合成样例复现 v1、核对 v2 的手算值 |
| `sql/` | 十周的 v2 SQL 与 `sha256.txt`（公开查询，查询号见台账）；`TIECHK_20250407.sql` 排序并列诊断 |
| `run_dune.py`、`run_weeks.py`、`dune_get.py`、`dune_get_stream.py` | 执行与下载（复制自 DQ-35，`dune_get.py` 只改 .env 的上溯层数） |
| `runs/dune_ledger.csv` | 费用：十周 286.36，第一次跑第一周 29.69（排序修正之前，结果在 `raw/dune/首跑_排序修正前/`，SQL 为不含排序替换的 v2，Dune 查询 8884573），诊断 4.63 |
| `analyze_c1_v2.py` | 原 `analyze_c1.py` 原样调用，只换输入输出 → `runs/c1_analysis.json`；新旧对照 → `runs/c1_v1_v2_compare.json` |
| `raw/dune/` | 逐币结果（入库，供复核） |

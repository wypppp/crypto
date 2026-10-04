# DQ-35 小样本（入库，供 GPT 独立复算）

- 10-04 起按总控第十五轮采纳的方案，小样本 CSV 入库，让审阅方能独立复算；正式切片只在 `raw/`（不入库）。
- 样本只用 DQ-37 开发周创建的池或币，只用于核对提取 SQL 的齐全、精度与一致性，不看价格或收益分布。

**v2.1 扩大样本（10-04 第十四轮）**：
- 全量对照报告是 `../runs/SMP21_*_compare.md`（`compare_sample_v21.py`、`compare_pre_v21.py`）。
- 全量逐笔原始文件太大（单组最大 58 MB），入库的是子集，由 `../过程/subset_sample.py` 生成：
  - 先剔除曲线创建在检验周的池或币；
  - 再按池（币）地址字典序纳入，逐笔累计约 5 万笔为止；
  - 各层 SQL 结果按同一批池过滤，文件名加 `_sub`。
- 子集上 M 层计数与 `'C'` 行不再相等（M 层是全量计数）；其余各项可在子集上复算。

| 组 | 逐笔原始（独立母体） | SQL 结果 | 生成 SQL |
|---|---|---|---|
| 新池、vq 非零：2026-09-23 建于 00:00～01:00 | `RAW21_GRAD_20260923_sub` | `SMP21_B_20260923_r1/r2_sub`、`SMP21_P_20260923_r1/r2_sub`、`SMP21_M_20260923_sub`（L 层 0 行，只有状态文件） | `../sql/RAW21_GRAD_20260923.sql`、`../sql/SMP21_{B,P,M,L}_20260923.sql` |
| 跨片合并、日桶：2025-10-07 建于 00:00～03:00，事件 10-07～10-20 | `RAW21_GRAD_20251007w_sub` | `SMP21_B_20251007wa_sub`、`SMP21_B_20251007wb_sub`（两片）、`SMP21_P_20251007w_sub`、`SMP21_L_20251007w_sub` | `../sql/RAW21_GRAD_20251007w.sql`、`../sql/SMP21_*_20251007w*.sql` |
| 老池：2025-10-07 建的池在 2026-02-09 | `RAW21_GRAD_20260209old_sub` | `SMP21_B_20260209old_sub`（无 P 层，对照时 P 写 `-`） | `../sql/*_20260209old.sql` |
| 封存边界：2026-07-13 建于 00:00～06:00 | `RAW21_GRAD_20260713_sub` | `SMP21_B_20260713_sub`、`SMP21_P_20260713_sub`、`SMP21_M_20260713_sub` | `../sql/*_20260713.sql` |
| 毕业前：2026-09-23 完成于 00:00～01:00 | `RAW21_PRE_20260923_sub` | `SMP21PRE_B_20260923s_r1/r2_sub`、`SMP21PRE_M_20260923s_sub`（修正 SOL 计价判断后的重跑） | `../sql/RAW21_PRE_20260923.sql`、`../sql/SMP21PRE_{B,M}_20260923.sql` |
| 毕业前：2026-07-13 完成于 00:00～06:00 | `RAW21_PRE_20260713_sub` | `SMP21PRE_B_20260713_sub`、`SMP21PRE_M_20260713_sub` | `../sql/*PRE*_20260713.sql` |
| 非 SOL：2026-09-24 建的非 SOL 池（全天） | `RAW21_GRAD_20260924ns_sub` | `SMP21_B_20260924ns_r1_sub`、`SMP21_P_20260924ns_r1_sub`、`SMP21_M_20260924ns_sub`（L 层 0 行） | `../sql/*_20260924ns.sql` |

**复算方法**：
- 把子集拷到 `raw/dune/` 并去掉 `_sub` 后缀，在实验目录运行（与全量对照所用参数相同）：
  - `python compare_sample_v21.py SMP21_B_20260923_r1 SMP21_P_20260923_r1 RAW21_GRAD_20260923 SMP21_B_20260923_r2 SMP21_P_20260923_r2 --m SMP21_M_20260923 --l SMP21_L_20260923 --raw-end 2026-09-23 --out SMP21_20260923`
  - `python compare_sample_v21.py SMP21_B_20251007wa,SMP21_B_20251007wb SMP21_P_20251007w RAW21_GRAD_20251007w --l SMP21_L_20251007w --raw-end 2025-10-20 --out SMP21_20251007w`
  - `python compare_sample_v21.py SMP21_B_20260209old - RAW21_GRAD_20260209old --raw-end 2026-02-09 --out SMP21_20260209old`
  - `python compare_sample_v21.py SMP21_B_20260713 SMP21_P_20260713 RAW21_GRAD_20260713 --m SMP21_M_20260713 --raw-end 2026-07-13 --out SMP21_20260713`
  - `python compare_sample_v21.py SMP21_B_20260924ns_r1 SMP21_P_20260924ns_r1 RAW21_GRAD_20260924ns --m SMP21_M_20260924ns --l SMP21_L_20260924ns --raw-end 2026-09-24 --out SMP21_20260924ns`
  - `python compare_pre_v21.py SMP21PRE_B_20260923s_r1 SMP21PRE_M_20260923s RAW21_PRE_20260923 SMP21PRE_B_20260923s_r2`
  - `python compare_pre_v21.py SMP21PRE_B_20260713 SMP21PRE_M_20260713 RAW21_PRE_20260713`
  - L 层 0 行的组没有 csv，只有状态文件；对照脚本按“文件不存在＝0 行”处理。
- 逐笔原始的列：`'C'` 行（每个纳入的池一行）借用列，q0＝quote_mint，b0＝quote decimals，q_amt＝mint，q_amt_lp＝base decimals，q_user＝曲线创建 epoch 秒；`'X'` 行的 pool 列是排除类别，q0 列是个数。
- `*_status.json` 是 Dune 执行状态（行数、字节、执行号、费用）。
- `SHA256SUMS` 是各文件的 sha256。

**首版 v2.1 样本**（`SMP21_*_20251007*`、`SMP2b_GRADRAW_20251007`）：列在 vq 修正之前，已从本目录移除，见提交 `35be912b`。

# DQ-35 小样本（入库，供 GPT 独立复算）

- 小样本 CSV 入库，让审阅方能独立复算；正式切片只在 `raw/`（不入库）。
- 样本只用 DQ-37 开发周创建的池或币，只用于核对提取 SQL 的齐全、精度与一致性，不看价格或收益分布。

**v2.2 扩大样本（10-05 第十五轮）**：
- 全量对照报告是 `../runs/SMP22_*_compare.md`（`compare_sample_v22.py`、`compare_pre_v22.py`）。
- 入库的是子集，由 `../过程/subset_sample_v22.py` 生成：
  - 先经 `dev_gate` 剔除检验周的池或币；
  - 再**强制纳入**有加撤池且单池不超过 5 万笔的池、全部有储备异常（无事件的储备变化）的池（07-13 组 3 个，GPT 点名）、有 boost 的池里事件最少的 2 个；
  - 07-14 组那个有加撤池的池一天有 20 万笔，没有纳入；非空加撤池的样本见跨片组（6 笔）；
  - 然后按池地址字典序补到约 5 万笔；
  - 各层 SQL 结果按同一批池过滤，文件名加 `_sub`。
- 子集上 M 层计数与 `'C'` 行不再相等（M 层是全量计数）；其余各项可在子集上复算。
- v2.1 的子集（`SMP21_*`、`RAW21_*`）已移除，见提交 `e729c5dd`。

| 组 | 逐笔原始（独立母体） | SQL 结果 | 生成 SQL |
|---|---|---|---|
| 新池、vq 非零、boost 多：2026-09-23 建于 00:00～01:00 | `RAW22_GRAD_20260923_sub` | `SMP22_{B,P}_20260923_r1/r2_sub`、`SMP22_{M,L}_20260923_sub` | `../sql/RAW22_GRAD_20260923.sql`、`../sql/SMP22_{B,P,M,L}_20260923.sql` |
| 跨 07-15 升级：2026-07-14 建于 00:00～02:00，事件 07-14～07-16 | `RAW22_GRAD_20260714x_sub` | `SMP22_{B,P}_20260714x_v2_sub`（修正“升级前布局”后重跑）、`SMP22_{M,L}_20260714x_sub` | `../sql/*_20260714x.sql` |
| 非 SOL：2026-09-24 建的非 SOL 池 | `RAW22_GRAD_20260924ns_sub` | `SMP22_{B,P,M,L}_20260924ns_sub` | `../sql/*_20260924ns.sql` |
| 跨片合并、日桶、非空 L：2025-10-07 建于 00:00～03:00，事件 10-07～10-20 | `RAW22_GRAD_20251007w_sub` | `SMP22_B_20251007wa_sub`、`SMP22_B_20251007wb_sub`、`SMP22_{P,M,L}_20251007w_sub` | `../sql/*_20251007w*.sql` |
| 老池：2025-10-07 建的池在 2026-02-09 | `RAW22_GRAD_20260209old_sub` | `SMP22_B_20260209old_sub`（无 P 层） | `../sql/*_20260209old.sql` |
| 封存边界、储备异常：2026-07-13 建于 00:00～06:00 | `RAW22_GRAD_20260713_sub` | `SMP22_{B,P,M}_20260713_sub` | `../sql/*_20260713.sql` |
| 毕业前：2026-09-23 完成于 00:00～01:00 | `RAW22_PRE_20260923_sub` | `SMP22PRE_B_20260923_r1/r2_sub`、`SMP22PRE_M_20260923_sub` | `../sql/*PRE*_20260923.sql` |
| 毕业前：2026-07-13 完成于 00:00～06:00 | `RAW22_PRE_20260713_sub` | `SMP22PRE_{B,M}_20260713_sub` | `../sql/*PRE*_20260713.sql` |

**复算方法**：
- 把子集拷到 `raw/dune/`，去掉 `_sub` 后缀，在实验目录运行与全量相同的命令（全量报告第一行是标签；参数见 `../README.md` §1d 与下列）：
  - `python compare_sample_v22.py SMP22_B_20260923_r1 SMP22_P_20260923_r1 RAW22_GRAD_20260923 --b2 SMP22_B_20260923_r2 --p2 SMP22_P_20260923_r2 --m SMP22_M_20260923 --l SMP22_L_20260923 --raw-end 2026-09-23 --out SMP22_20260923`
  - `python compare_sample_v22.py SMP22_B_20260714x_v2 SMP22_P_20260714x_v2 RAW22_GRAD_20260714x --m SMP22_M_20260714x --l SMP22_L_20260714x --raw-end 2026-07-16 --out SMP22_20260714x`
  - `python compare_sample_v22.py SMP22_B_20260924ns SMP22_P_20260924ns RAW22_GRAD_20260924ns --m SMP22_M_20260924ns --l SMP22_L_20260924ns --raw-end 2026-09-24 --out SMP22_20260924ns`
  - `python compare_sample_v22.py SMP22_B_20251007wa,SMP22_B_20251007wb SMP22_P_20251007w RAW22_GRAD_20251007w --m SMP22_M_20251007w --l SMP22_L_20251007w --raw-end 2025-10-20 --out SMP22_20251007w`
  - `python compare_sample_v22.py SMP22_B_20260209old - RAW22_GRAD_20260209old --raw-end 2026-02-09 --out SMP22_20260209old`
  - `python compare_sample_v22.py SMP22_B_20260713 SMP22_P_20260713 RAW22_GRAD_20260713 --m SMP22_M_20260713 --raw-end 2026-07-13 --out SMP22_20260713`
  - `python compare_pre_v22.py SMP22PRE_B_20260923_r1 SMP22PRE_M_20260923 RAW22_PRE_20260923 SMP22PRE_B_20260923_r2`
  - `python compare_pre_v22.py SMP22PRE_B_20260713 SMP22PRE_M_20260713 RAW22_PRE_20260713`
- 零行结果没有 csv，只有状态文件，对照脚本按“文件不存在＝0 行”处理。
- **逐笔原始的列**：
  - `'C'` 行借用列：q0＝quote_mint，b0＝quote decimals，q_amt＝mint，q_amt_lp＝base decimals，q_user＝曲线创建 epoch 秒，b_amt／f_lp＝建池后报价／代币储备，slot 等四列与 tx_id＝建池事件键；
  - `'X'` 行：pool 列是排除类别，q0 列是个数；
  - `'R'` 行：pool＝从字节解出的池，usr＝事件类别（B／S／I／U），q0＝十六进制字节尾段（买入从第 410 字节、卖出从第 369 字节、boost 从第 89 字节起），由 `../rawdecode_v22.py` 解析。
- `*_status.json` 是 Dune 执行状态（行数、字节、执行号、费用）；`SHA256SUMS` 是各文件的 sha256。

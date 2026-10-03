# DQ-35 v2 小样本对照 20251007L（compare_sample_v2.py 生成）

## 毕业后（GRAD v2）

- 两次运行逐行一致：**是**（不同的行 0 / 244）
- 逐笔 29064 笔（{'B': 15467, 'S': 13593, 'D': 2, 'W': 2}）；ord 越界 0、重复 0
- 储备连续性（本笔后＝下一笔前，误差 ≤1 原始单位），按事件类型：
  - B：quote 15466/15466，base 15466/15466
  - D：quote 2/2，base 2/2
  - S：quote 13591/13591，base 13591/13591
  - W：quote 2/2，base 2/2
  - 卖出 quote_amount_out − lp_fee ＝ quote_amount_out_without_lp_fee：13593/13593；cashback>0 的 0 笔，buyback_fee>0 的 0 笔
- 分桶对齐：两边都有 240，只在逐笔 0，只在 SQL 0
- 逐项一致：全部一致
- n_users（approx_distinct）与精确去重：相同 223/240，最大差 41
- 跨分片边界的桶 2 个，带用户名单 2 个
- 加撤池：SQL L 行 4，逐笔 D/W 4
  - L 行逐项一致 4/4（只在一边 0）
- SQL 输出 n_ord_overflow 合计 0

## 毕业前（GRADPRE v2）

- 本组没有毕业前样本

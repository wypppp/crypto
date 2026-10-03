# DQ-35 v2 小样本对照 20251007（compare_sample_v2.py 生成）

## 毕业后（GRAD v2）

- 两次运行逐行一致：**是**（不同的行 0 / 402）
- 逐笔 28397 笔（{'B': 16454, 'S': 11943}）；ord 越界 0、重复 0
- 储备连续性（本笔后＝下一笔前，误差 ≤1 原始单位），按事件类型：
  - B：quote 16453/16453，base 16453/16453
  - S：quote 11939/11939，base 11939/11939
  - 卖出 quote_amount_out − lp_fee ＝ quote_amount_out_without_lp_fee：11943/11943；cashback>0 的 0 笔，buyback_fee>0 的 0 笔
- 分桶对齐：两边都有 402，只在逐笔 0，只在 SQL 0
- 逐项一致：全部一致
- n_users（approx_distinct）与精确去重：相同 399/402，最大差 65
- 跨分片边界的桶 4 个，带用户名单 4 个
- 加撤池：SQL L 行 0，逐笔 D/W 0
- SQL 输出 n_ord_overflow 合计 0

## 毕业前（GRADPRE v2）

- 两次运行逐行一致：**是**（不同的行 0 / 171）
- 逐笔 1919 笔，币 5 个；ord 重复 0；quote_mint 分布 {'(空)': 1919}；mayhem 0 笔
- 曲线连续性（本笔前＝上一笔后）：x 1914/1914，y 1914/1914
  - 非 mayhem：x 1914/1914，y 1914/1914
- 分桶对齐：两边都有 171，只在逐笔 0，只在 SQL 0
- 逐项一致：全部一致
- n_users（approx_distinct）与精确去重：相同 171/171，最大差 0

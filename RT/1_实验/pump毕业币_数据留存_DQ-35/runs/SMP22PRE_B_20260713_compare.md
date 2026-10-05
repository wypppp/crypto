# DQ-35 v2.2 毕业前小样本对照：SMP22PRE_B_20260713 / SMP22PRE_M_20260713 对 RAW22_PRE_20260713

- 入口（dev_gate）：独立母体 88 个币，其中开发币 87 个、剔除 1 个；数值文件解析时丢弃 218 行
- M 层（字段 n_included、n_sealed、n_holdout_name、n_no_curve_create、n_no_symbol、identity_gap、n_included_sol）与独立候选：一致；纳入 88（SOL 88、USDC 0、其他 0）
- 有成交的币：逐笔 87，SQL 87，集合相同：True；不在独立母体里的 SQL 币：0
- 曲线逐笔连续（非 mayhem、SOL 计价）：10416 / 10416
- 事件键唯一：28001 个事件，28001 个不同键；B 层键重复 0
- 分桶数：SQL 3518，逐笔重算 3518，键集合相同：True
- 分桶逐字段（buy_first、buy_last、f_bb、f_cb、f_cr、f_pr、key_f、key_l、max_buy_sol、mayhem、n、n_bb_null、n_buy、n_cb_null、n_fee_null、pre_valid、qa_buy、qa_sell、sol_buy、sol_first、sol_sell、t_first、t_last、tok_buy、tok_first、tok_sell、tx_f、tx_l、x_last、x_post_first、x_pre_first、xr_last、y_last、y_post_first、y_pre_first）不一致：全部为 0
- n_users（approx_distinct）与精确去重不同的桶：0
- 越界计数合计：0；mayhem 桶 2287、pre_valid＝false 的桶 2287（x_pre_first 已置空）

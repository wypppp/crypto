# DQ-35 v2.2 小样本对照：SMP22_B_20260209old / - 对 RAW22_GRAD_20260209old

- 入口（dev_gate）：独立母体 73 个池，其中开发池 72 个、剔除 1 个（检验周或前向批次），数值文件解析时丢弃 3 行
- 事件键重复：成交 0，原始字节 'R' 行 0
- vq 来源（Python 解析 'R' 行）：{'layout0': 11830}
- 储备逐笔守恒：11822 / 11822（另 0 对之间夹着加撤池或 boost，不计）
- 建池后储备（C 行 pool_*_amount）＝首笔成交前储备：0 / 8 个有成交且无加撤池的池
- B 层：12 行（1 片，片内键重复 0），合并后 12（跨片合并 0），逐笔重算 12，键集合相同：True
- B 层逐字段（46 个字段：n、n_buy、n_fee_null、n_cb_null、n_bb_null、n_vq_null、n_vq_ovf、n_xchk、n_xchk_fail、n_xchk_skip、n_px_null、n_ord_overflow、q_buy_user、q_sell_user、q_buy_pool、q_sell_pool、b_buy、b_sell、f_lp、f_pr、f_cr、q0_open、b0_open、q1_close、b1_close、q_pool_last、b_amt_last、f_cb_buy、f_bb_buy、f_cb_sell、f_bb_sell、vq_open、vq_close、vq_min、vq_max、side_first、side_last、tx_f、tx_l、vq_src、t_first、t_last、px_high、px_low、key_f、key_l）不一致：全部为 0
- B 层跨片桶用户名单（逐成员）不一致：0；n_users（approx_distinct）与精确去重不同的桶：1
- B 层合计：越界 0、vq 缺失 0、vq 溢出 0、交叉核对越界 0（共核 5892 笔、未核 0 笔）、价格空 0

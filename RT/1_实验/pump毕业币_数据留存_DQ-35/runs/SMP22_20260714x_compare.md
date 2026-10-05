# DQ-35 v2.2 小样本对照：SMP22_B_20260714x_v2 / SMP22_P_20260714x_v2 对 RAW22_GRAD_20260714x

- 入口（dev_gate）：独立母体 47 个池，其中开发池 47 个、剔除 0 个（检验周或前向批次），数值文件解析时丢弃 0 行
- 母体：独立候选 47 个池，P 层 47 个，集合相同：True；P 层池键重复 0
- M 层（字段 n_included、n_sealed、n_holdout_name、n_no_curve_create、n_no_symbol、identity_gap）与独立候选：一致；类别合计 47＝候选 47：True；计价分层 SOL 47／USDC 0／其他 0
- 事件键重复：成交 0，原始字节 'R' 行 0
- vq 来源（Python 解析 'R' 行）：{'layout0': 177264, 'raw': 45031}
- 储备逐笔守恒：222234 / 222234（另 14 对之间夹着加撤池或 boost，不计）
- 建池后储备（C 行 pool_*_amount）＝首笔成交前储备：46 / 46 个有成交且无加撤池的池
- B 层：2860 行（1 片，片内键重复 0），合并后 2860（跨片合并 0），逐笔重算 2860，键集合相同：True
- B 层逐字段（46 个字段：n、n_buy、n_fee_null、n_cb_null、n_bb_null、n_vq_null、n_vq_ovf、n_xchk、n_xchk_fail、n_xchk_skip、n_px_null、n_ord_overflow、q_buy_user、q_sell_user、q_buy_pool、q_sell_pool、b_buy、b_sell、f_lp、f_pr、f_cr、q0_open、b0_open、q1_close、b1_close、q_pool_last、b_amt_last、f_cb_buy、f_bb_buy、f_cb_sell、f_bb_sell、vq_open、vq_close、vq_min、vq_max、side_first、side_last、tx_f、tx_l、vq_src、t_first、t_last、px_high、px_low、key_f、key_l）不一致：全部为 0
- B 层跨片桶用户名单（逐成员）不一致：0；n_users（approx_distinct）与精确去重不同的桶：57
- B 层合计：越界 0、vq 缺失 0、vq 溢出 0、交叉核对越界 0（共核 95114 笔、未核 0 笔）、价格空 0
- L 层（字段 kind、事件键、dq、db、q0、tx_id、q1_after、b1_after、vq）：SQL 14 行（键重复 0），逐笔 14（加撤池 14、boost 0），键集合相同：True，逐项不一致 0，越界 0
- P 层快照：比对 376 个（池×时点）；逐字段（created_t、c_q、c_b、target_time、state_time、known_at、coverage、gap_flag、vq、nboost、a_key、a_kind、a_tx、a_q1、a_b1、b_key、b_kind、b_tx、b_q0、b_b0）不一致：全部为 0；时点后第一个事件在覆盖期之后（b 侧与 coverage 不比）4
- P 层 coverage 分布（全部池×时点，SQL 值）：{'ok': 370, 'no_next': 6}
- P 层 7 天字段（n_7d、n_lp_7d、n_boost_7d、vq_min_7d、vq_max_7d）：比对 0 个池，不一致 0

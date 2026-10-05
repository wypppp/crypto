# DQ-35 v2.2 小样本对照：SMP22_B_20251007wa+SMP22_B_20251007wb / SMP22_P_20251007w 对 RAW22_GRAD_20251007w

- 入口（dev_gate）：独立母体 14 个池，其中开发池 14 个、剔除 0 个（检验周或前向批次），数值文件解析时丢弃 1 行
- 母体：独立候选 14 个池，P 层 14 个，集合相同：True；P 层池键重复 0
- M 层（字段 n_included、n_sealed、n_holdout_name、n_no_curve_create、n_no_symbol、identity_gap）与独立候选：一致；类别合计 15＝候选 15：True；计价分层 SOL 14／USDC 0／其他 0
- 事件键重复：成交 0，原始字节 'R' 行 0
- vq 来源（Python 解析 'R' 行）：{'layout0': 198862}
- 储备逐笔守恒：198842 / 198842（另 6 对之间夹着加撤池或 boost，不计）
- 建池后储备（C 行 pool_*_amount）＝首笔成交前储备：13 / 13 个有成交且无加撤池的池
- B 层：2695 行（2 片，片内键重复 0），合并后 2693（跨片合并 2），逐笔重算 2693，键集合相同：True
- B 层逐字段（46 个字段：n、n_buy、n_fee_null、n_cb_null、n_bb_null、n_vq_null、n_vq_ovf、n_xchk、n_xchk_fail、n_xchk_skip、n_px_null、n_ord_overflow、q_buy_user、q_sell_user、q_buy_pool、q_sell_pool、b_buy、b_sell、f_lp、f_pr、f_cr、q0_open、b0_open、q1_close、b1_close、q_pool_last、b_amt_last、f_cb_buy、f_bb_buy、f_cb_sell、f_bb_sell、vq_open、vq_close、vq_min、vq_max、side_first、side_last、tx_f、tx_l、vq_src、t_first、t_last、px_high、px_low、key_f、key_l）不一致：全部为 0
- B 层跨片桶用户名单（逐成员）不一致：0；n_users（approx_distinct）与精确去重不同的桶：41
- B 层合计：越界 0、vq 缺失 0、vq 溢出 0、交叉核对越界 0（共核 92450 笔、未核 0 笔）、价格空 0
- L 层（字段 kind、事件键、dq、db、q0、tx_id、q1_after、b1_after、vq）：SQL 6 行（键重复 0），逐笔 6（加撤池 6、boost 0），键集合相同：True，逐项不一致 0，越界 0
- P 层快照：比对 112 个（池×时点）；逐字段（created_t、c_q、c_b、target_time、state_time、known_at、coverage、gap_flag、vq、nboost、a_key、a_kind、a_tx、a_q1、a_b1、b_key、b_kind、b_tx、b_q0、b_b0）不一致：全部为 0；时点后第一个事件在覆盖期之后（b 侧与 coverage 不比）0
- P 层 coverage 分布（全部池×时点，SQL 值）：{'ok': 112}
- P 层 7 天字段（n_7d、n_lp_7d、n_boost_7d、vq_min_7d、vq_max_7d）：比对 14 个池，不一致 0

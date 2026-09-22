# DQ-8C 预注册 · 直接预测净期望（现有入场特征，非线性交互）

> 2026-09-17，运行前写定。0 credits，不碰封存周。A、B 两周都已被旧研究看过，本卡是开发性检验，不是确认。

## 只回答
用现有 18 个 +30 分钟入场特征，直接以"每个币的净回收"为目标训练非线性模型，按预测值挑出的前 10% 在另一周是否净回收 ≥1.03？

已测过、本卡不重复的：单特征阈值与两特征"且"组合按平均回收搜索（DQ-1F，3,227 种）；16 个特征的线性岭回归买入决策（DQ-8A）。本卡补的是多特征非线性交互。

## 数据与标签
- A 周：`dq7/raw/F2_dev.csv`，标签 `b50`（30 天封顶）；B 周：`dq1f/raw/F1_val.csv`，标签 `x50_24h`（60 天封顶，与 b50 在 99.8% 的币上相同）。
- 目标 y = 标签 − 0.004。赢家 = `ms_30d`（A）/`ms_60d`（B）≥10，只用于分解，不进模型。
- 特征（18 个）：entry_x_sol n_trades_pre n_buyers_pre trades_per_sol bot_share_pre net_sol_pre sell_share_pre secs_since_last pre_peak_pm dev_prior_launches dev_prior_grads dev_net_share dev_sold_sol top1_share top5_share slot0_buyers slot0_share early10_buyers。

## 模型（超参固定，不调）
- M0：全买。
- M1（描述）：岭回归 α=10，特征做 sign·log1p|x| 后按训练周标准化，缺失填训练周中位数。
- **M2（主模型）**：HistGradientBoostingRegressor(loss=squared_error, learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0, random_state=0)，原始特征，缺失原样。
- M2w（描述）：同 M2，但训练目标在训练周 99.5 分位处截顶（评估仍用原始回收）。

## 评估（在测试周）
- 按预测值排序，报告前 1%/5%/10%/20%/50% 的实际平均净回收、十分位表、十分位序与实际均值的 Spearman；
- 前 10% 内分解：赢家占比、赢家平均回收、非赢家平均回收；与测试周全体对照；
- 前 10% 均值的币级自助法（2,000 次，种子 20260917）10 分位。

## 判据（只对 M2）
同时满足才算"值得冻结一个直接期望模型去做封存周确认"：
1. A→B：前 10% 平均净回收 ≥ 1.03；
2. A→B：前 10% 自助法 10 分位 > 1.00；
3. B→A：前 10% 平均净回收 > 1.00。

1.03 来自 F84：所需每笔净优势约 3%（未计 MEV、失败交易）。前 1%、5% 样本太小，只作描述。

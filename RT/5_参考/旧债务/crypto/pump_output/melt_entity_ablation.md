# MELT entity 特征增量消融

- 样本：21,635（train 15,144 / test 6,491）
- 测试窗口：2025-01-30 至 2025-02-28
- 测试集 medium/low 比例：24.26%
- 注意：这是风险标签，不是 10x 或交易收益。

| 模型 | 特征 | AUPRC | log loss | top 10% precision |
|---|---|---:|---:|---:|
| logistic_l2 | BASE | 0.5293 | 0.5655 | 61.08% |
| logistic_l2 | ENTITY_ONLY | 0.5233 | 0.5439 | 60.77% |
| logistic_l2 | BASE_PLUS_ENTITY | 0.5416 | 0.5337 | 63.38% |

logistic_l2 增量：ΔAUPRC +0.0123；log-loss 改善 +0.0318；Δtop10 precision +2.31%。

按日 block bootstrap 95% 区间：ΔAUPRC [-0.0015, +0.0251]；log-loss 改善 [+0.0149, +0.0465]；Δtop10 precision [-1.14%, +4.09%]。

| hist_gradient_boosting | BASE | 0.5613 | 0.4913 | 64.46% |
| hist_gradient_boosting | ENTITY_ONLY | 0.5449 | 0.4697 | 65.23% |
| hist_gradient_boosting | BASE_PLUS_ENTITY | 0.5906 | 0.4596 | 68.15% |

hist_gradient_boosting 增量：ΔAUPRC +0.0293；log-loss 改善 +0.0317；Δtop10 precision +3.69%。

按日 block bootstrap 95% 区间：ΔAUPRC [+0.0174, +0.0418]；log-loss 改善 [+0.0242, +0.0396]；Δtop10 precision [+0.39%, +5.98%]。


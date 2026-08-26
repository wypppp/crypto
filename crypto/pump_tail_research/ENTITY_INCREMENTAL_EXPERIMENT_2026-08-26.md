# Pump entity graph 增量实验

> 状态：新特征实验；历史 2026-05-01 至 2026-07-24 结局已经被研究者看过，因此只是 development，不是最终确认。  
> 目的：用最低成本回答 entity reconstruction 是否提供现有钱包/价格/成交特征之外的增量，而不是启动完整图产品。

## 1. 需要纠正的事实

现有 T+5m 模型中的：

- `max_wallet_volume_share_5m`；
- `wallet_volume_hhi_5m`

是毕业后五分钟内的**逐钱包成交额集中度**，不是持币集中度，也没有共同资金源、Jito bundle、预迁移转账、creator 关联或跨币重复实体。

因此 entity graph 不是机械地“把现有 HHI 算准”。但它也不能因概念上不同就获得完整工程预算；必须先通过增量消融。

## 2. 单一经济问题

> 在保持既有 T+5m 入场、时间切分、基础特征和执行成本不变时，迁移前可实时取得的实体关系，能否提高右尾选择的容量加权、可执行净收益，而不只是更准确地预测事后 rug/风险标签？

主交易目标仍是 2026 研究中已冻结的 `remaining_max_5m >= 10`。MELT 的 high-risk 标签只可用于低成本信息消融，不能替代交易结局。

## 3. 分阶段预算

### E0：公开 MELT 数据消融，最多 2 天

使用作者发布的 `feature.pkl`、固定代码版本和时间留出，按原始特征名建立三组：

1. `BASE`：context、地址级 holding/market activity、价格量时间序列；
2. `ENTITY_ONLY`：bundle、共同资金源及聚类后集中度；
3. `BASE_PLUS_ENTITY`：前两者合并。

保持相同模型、同一时间边界和同一超参数，比较 `BASE_PLUS_ENTITY - BASE` 的 AUPRC、log loss、固定选择率 precision 及按日期 block bootstrap 区间。

E0 只回答“论文数据中是否存在增量信息”。若增量在大多数时间块为零/反向，或依赖无法点时取得的字段，停止，不建设 2026 图数据。

即使 E0 为正，也不能宣称可交易，只允许进入 E1。

### E1：2026 development 增量回放

在既有 26,496 个 T+5m 样本上新增一个冻结 entity 特征块。不得删除或重新调换既有 49 个基础特征，不用结果选择 entity 规则。

比较：

- `BASE`：既有冻结 HGB；
- `ENTITY_ONLY`：只用实体块；
- `BASE_PLUS_ENTITY`：相同 HGB 参数，增加实体块；
- L2 Logistic 作为低复杂度诊断。

沿用原三个时间前向 fold。由于其结局已被看过，E1 结果只能杀死方向或生成待确认假说；正结果不得授权实盘。

### E2：未来封存确认

只有 E1 经济闸门通过，才从冻结后的新毕业代币建立封存窗口。entity pipeline、阈值和执行规则原样运行，等 30 天结局成熟后解封。不得因 E1 结果增加 GNN、社交或名称特征。

## 4. 实体构建规则

为控制误合并，边分两层：

### 4.1 可用于 union-find 的高置信边

- 同一交易内由同一控制流程共同签名/购买；
- creator 向钱包直接提供启动资金或迁移前 token；
- 非 CEX、非公共路由地址作为同一直接资金源资助多个早期钱包；
- 可验证属于同一发起者的原子 bundle 关系。

### 4.2 只生成软特征、不得直接合并的边

- 仅同区块或相近时间交易；
- 仅使用相同 DEX/路由器；
- 共同 CEX 提现来源；
- 一跳以上、经过高扇出公共地址的资金关系；
- 单纯交易方向或金额相似。

每种边必须保存证据类型、首次可见区块及是否能在 T+5m 前完成计算。无法证明点时可得的边不得进入交易特征。

## 5. 冻结 entity 特征块

只允许以下事前定义的聚合；缺失保留缺失标记：

- 迁移时 `entity_count` 与 `wallet_to_entity_ratio`；
- top entity 持币占比及 entity holding HHI；
- creator-connected entity 持币占比；
- entity 买入成交额最大占比及 entity buy-volume HHI；
- 被高置信边覆盖的钱包/持币比例；
- bundle-linked、direct-funder-linked、creator-funded 比例分别统计；
- top entity 的未实现可售筹码相对迁移池基础储备；
- entity 在当前币之前的已知毕业次数和事后失败次数，只允许使用当前毕业前已经成熟的历史。

不得加入 test 结果启发的新图 motif。GNN、node embedding 和 LLM 图解释均不属于本实验。

## 6. 指标与裁决

### 6.1 信息增量

至少报告：

- pooled 与逐 fold 的 `ΔAUPRC`、`Δlog_loss`；
- 固定 validation 最高 10% 阈值下的 `Δprecision`；
- 容量加权 `Δprecision`；
- entity 覆盖率、组件大小分布和最大组件人工抽查；
- 按日期及 creator/entity 分组 bootstrap 的不确定区间。

仅 count precision 从 9.75% 略过 10% 不构成通过。既有模型的容量加权 precision 只有 4.04%，被选容量中位数只有 13.72 美元；增量必须作用到可部署样本。

### 6.2 经济闸门

`BASE_PLUS_ENTITY` 必须同时满足：

1. 相对 `BASE` 的容量加权 precision 增量在至少 2/3 fold 为正；
2. 选中集合的容量中位数不低于 100 美元；
3. 沿用双边池冲击、实际链上费率及双边各 100 bps 损耗后，预注册的固定退出规则平均净 ROI 大于 0，且按日期 block bootstrap 单侧 95% 下界大于 0；
4. 3 万元账户的日历顺序回放显示可部署金额而非仅有极浅池纸面倍数；
5. entity 特征可在 T+5m 决策截止前稳定生成。

固定退出规则在构建 entity 结果前另行冻结；历史 E1 即使通过，也只进入 E2。

若信息增量存在但经济闸门失败，结论是“entity 有风控/解释价值，但没有本目标所需的 trading edge”，本方向关闭，不改做安全产品来保留项目。

## 7. 防止复杂度升级

- E0/E1 失败后不得尝试 GNN、更多图 motif 或重新定义 Y；
- 不用钱包聚类后的完整未来实体历史回填早期特征；
- 不根据已知 10x 正例人工修正 cluster；
- 不把识别 rug 的表现替代右尾收益和容量；
- 不把历史 development 正结果写成前向能力；
- 不因第三方产品存在就直接否定增量，也不因第三方产品存在就假设其聚类可获得或优于本实验。


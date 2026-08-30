# 预测市场小本金钱包 cohort

> **状态：本方向已于 2026-08-28 关闭，不再推进。**
>
> `REVIEW_2026-08-26.md` 当时的状态是“候选保留，等待美国云服务器完成数据质量验证”，即挂起在基础设施上而非被裁决。2026-08-28 使用者裁决改为关闭，理由：该方向需要低延迟做市基础设施才能开始运行，正处于使用者已明确排除的速度竞争位置。
>
> 原有结论不变：本地先导的 −27.52% 是代理延迟造成的工程故障，不是策略收益估计；`+0.863%/周转额` 是按未来 90 天高活跃度选出的条件样本，不构成新人基线；$1,400 资本达到 10x/日周转的比例仅 2/34。完整裁决见 [阶段二决策日志](../roadmap/阶段二决策日志.md) 2026-08-28 条目。本目录保留为留档，**不作为可继续推进的方向**。

## 目标

直接估计小资金参与者从可部署风险资本出发实现 2x / 5x / 10x 的频率，而不是从排行榜或头部钱包反推。

## 冻结口径 v0.1（2026-08-25）

### 研究对象

- 主场所：Polymarket 国际版 Polygon CLOB；
- 身份单位：`proxy wallet`，不是自然人；
- 地址第一次出现在可确认的 Polymarket 成交中，定义为首次参与；
- 多钱包属于同一人的情况公开数据无法完全消除，因此同时报告钱包级结果和该限制。

### 时间窗

分三组，不用同一个不完整窗口混算：

1. 完整一年组：首次参与后有至少 365 天可观察期；
2. 当前制度组：首次参与后有至少 180 天可观察期；
3. 近期组：只报告 30/90 天，不外推一年成功率。

每组还要求地址第一次成交前有足够长的表覆盖历史；若无法证明“第一次”是真实首次，则改称 `首次可观察成交`。

### 收益

对已解决二元合约，每次 outcome token 转手都按最终结算值归因：

```text
买方 PnL = 数量 ×（结算值 - 成交价）- 费用
卖方 PnL = 数量 ×（成交价 - 结算值）- 费用
```

这个归因能处理同一 token 多次转手；创建完整 YES/NO 组合但从未交易本身为零 PnL。未解决头寸必须按当日可执行价格标记，不能用当前 API 的事后值代替历史值。

### 本金

不把成交量当本金。优先级如下：

1. 代理钱包的累计净外部入金峰值；
2. 若无法可靠区分外部转账，则用逐笔头寸的最小全额抵押资本；
3. 两者都无法完整重建时，只报告 PnL 分布，不报告 `1 万元变成多少`。

卖出 outcome token 不是零本金收入：若卖方通过拆分 $1 抵押物获得 token，卖价为 `p`，净占用资本近似为 `1-p`。研究代码必须计入隐含的全额抵押。

### 小资本层级

- 不超过 $500；
- 不超过 $1,500（最接近人民币 1 万元）；
- 不超过 $5,000。

分层以整个观察期的最大累计风险资本为准，不能只按第一笔仓位。

### 主输出

- 30/90/180/365 天的净收益与资本倍数；
- 达到 2x / 5x / 10x 的钱包数和比例；
- 亏损 50% / 90% / 近似归零比例；
- 前后半段 PnL，检验盈利是否持续；
- 收益是否由单笔事件、奖励、maker rebate 或异常结算驱动；
- 按类别、买入赔率、maker/taker、持有期和市场成熟度分解。

### 禁止项

- 不从排行榜抽取研究母体；
- 不把最高账户收益当个人成功率；
- 不把未结算仓位的浮盈当已实现收益；
- 不忽略 split / merge、卖方抵押、费用与奖励；
- 不把钱包当自然人，也不把外部对冲后的钱包 PnL当独立策略能力。

## 当前数据源

- Dune `prediction_markets.*` 目录在当前查询环境不可用，不作为本轮数据源；
- v1 历史排除：`polymarket_polygon.ctfexchange_evt_orderfilled` 与
  `polymarket_polygon.negriskctfexchange_evt_orderfilled`；
- v2 主成交：`polymarket_v2_polygon.ctfexchange_evt_orderfilled`；
- v3 只用于标记并排除触碰者，因为本轮元数据表尚不能映射其 token；
- 市场元数据：`polymarket_polygon.market_details`；
- 链上真实结算时间：`polymarket_polygon.ctf_evt_conditionresolution`；
- Polymarket Data API：单钱包活动和持仓交叉验证，不能单独产生全体钱包母体。

## 2026-08-25 已完成阶段

- 完成 2026-05-01 至 05-07 首次可观察 v2 钱包的完整 90 天 cohort，共
  31,503 个地址；主分析清洁队列 30,418 个。
- 可信主结果只使用
  `data/dune_v2_may01_07_cohort_90d_final.csv`。同名前两个不含 `final`
  的 CSV 是修复链上结算时序以前的排错产物，禁止引用。
- 已完成一次性长赔率分母、高频无资本筛选持续性、无前视持续性和
  resting-maker / aggregate-taker 分解。
- 阶段结论与下一步生死实验见 [FINDINGS_2026-08-25.md](./FINDINGS_2026-08-25.md)。

## 影子做市执行实验

完整预注册、手续费/返利口径和通过门见
[SHADOW_EXPERIMENT_2026-08-25.md](./SHADOW_EXPERIMENT_2026-08-25.md)。采集器只调用公开免认证接口，不包含下单代码。

```bash
PYTHONPATH=crypto/prediction_market_research .venv/bin/python -m shadow_mm stream \
  --config crypto/prediction_market_research/shadow_config.example.json \
  --duration-seconds 60

PYTHONPATH=crypto/prediction_market_research .venv/bin/python -m shadow_mm quality \
  --input crypto/prediction_market_research/data/shadow/raw_ws_FILE.jsonl.gz

PYTHONPATH=crypto/prediction_market_research .venv/bin/python -m shadow_mm replay \
  --input crypto/prediction_market_research/data/shadow/raw_ws_FILE.jsonl.gz

PYTHONPATH=crypto/prediction_market_research .venv/bin/python -m shadow_mm latency-probe \
  --duration-seconds 120
```

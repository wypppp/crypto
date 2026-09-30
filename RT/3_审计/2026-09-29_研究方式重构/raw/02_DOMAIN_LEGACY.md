# DOMAIN_LEGACY

> 状态：Legacy-aware Auditor 的导航索引
> GitHub snapshot：`37f1a295c639692fb9a7a98a392a6673d515f6a9`
> Repo：`wypppp/crypto`
> **本文件不是权威数据库。** Auditor 必须先读取 snapshot 下的 `RT/00_总入口.md`，对本文件做 completeness diff。若冲突，以 snapshot repo 中经过审计的记录为准。

## 0. 状态标签

本文件只使用：
- `FACT`：经过项目测量/审计支持的事实；
- `SCOPED_NEGATIVE`：局部负结果，只能在明确范围内使用；
- `ONGOING`：已开始但尚不能下经济结论；
- `UNTESTED`：尚未充分测试；
- `ASSET`：可复用数据/代码/holdout/基础设施。

## 1. 当前研究问题的演化

### FACT

项目逐渐把核心研究单位收敛为：

> `(token, time/state) → remaining executable net upside`

重点不再是“必须出生时预测最终赢家”，而是在某个真实可执行 state，利用当时可见信息，是否能在经济机会被消耗之前识别极端剩余右尾。

## 2. pump.fun / 类 pump 母体的右尾

### FACT

旧项目已确认：
- 母体存在巨大右尾；
- 极端赢家非常稀少；
- 全买经济结果不好；
- “存在百倍币”与“能事前识别百倍币”是不同问题；
- 单币真实容量可能明显限制财富路径。

DQ-1M 等已经建立：
- 较大历史母体；
- winner base rate；
- realizable multiple；
- transaction cost；
- capacity proxy；
- all-buy baseline。

这些数据、SQL、估值与生命周期实现属于可复用资产。

## 3. 静态市场状态 / +30m summary

### SCOPED_NEGATIVE

DQ-1F 等测试过：
- +30m 时点；
- 一组人工 market summary features；
- simple threshold / rule combinations；
- 多种 exit rules；
- development / validation 分离。

结果没有形成正经济期望。

正确解释：
> 这一组低维、人工压缩的 +30m summary feature / rule family 未找到优势。

不能解释为：
> 所有公开链上信息无效。

## 4. 动态退出

### SCOPED_NEGATIVE

DQ-7 测试过多条 post-entry 动态退出规则，包括 insider proxy、new buyers、buy/sell flow 等。

新增规则没有胜过既有 b50 基准。

这主要否定已测试的退出规则族，不能推出所有动态信息无效。

## 5. 动态 `token × state`

### SCOPED_NEGATIVE

DQ-8A 已经测试过动态 checkpoint/state，而不仅是静态入场特征。

结果没有达到预设经济改善门槛。

因此不能说“过去只测过静态特征”。

但仍受以下范围限制：
- universal model；
- fixed summary features；
- 非 raw event sequence；
- 非 rich wallet/entity graph。

## 6. summary-feature ML / volatility 与 EV

### SCOPED_NEGATIVE

DQ-8C、F93–F96 等显示：
- 某些摘要特征能一定程度区分大涨跌；
- 但高分未自动转化为 positive trading EV；
- 在已测特征轴上，选中“波动/赢家”与选中“高期望”不是同一件事。

不能扩展为所有高维链上信息只能预测波动。

## 7. H1 / ignition

### SCOPED_NEGATIVE

项目把某类观察压缩成“大额净流入/点火跟随”规则后进行历史测试，结果较差。

它主要否定该人工压缩规则，并没有否定所有 event-sequence information。

## 8. DQ-18：Later Leaders

### FACT

DQ-18 证明：
> 巨大剩余右尾并不只存在于 token 出生最早期。

达到更高价格/市值状态后：
- 仍存在少量巨大剩余右尾；
- perfect-pick upper bound 仍可能很大；
- all-buy 仍明显亏损。

因此“必须出生时预测”不是必要条件。

## 9. DQ-19：状态转变领先性 / 发现时间余地

### SCOPED_NEGATIVE + FACT

DQ-19 已经测试两个极端动态签名：
- T1：成交加速；
- T2：单位新买家净买入。

结果：
- T1 在 A/B 两周净回收均约 0.93，未通过；
- T2 在 A 周约 1.54，但 B 周约 0.92，未复现；
- 某些签名能显著富集 ≥10×/≥100× 币，但未形成稳定正期望。

同时形成新的时间事实：
> 典型赢家的剩余可兑现右尾在数小时内快速衰减；少数极端赢家在更晚 state 仍可能保留巨大空间。

因此：
- 已测过有限 public dynamic-state signatures；
- 仍没有充分测试 raw transaction/event sequence 本身。

## 10. DQ-20：钱包履历 / 买家构成

### SCOPED_NEGATIVE

DQ-20 测试了：
- 历史高活跃早买地址；
- 早期买家构成；
- 少数履历地址跟随；
- +30m 入场。

B 周主信号净回收约 0.933，与未触发币大体相当，未通过。

正确结论：
> “高历史早买活跃度 / 买家构成 + +30m 入场”这一具体定义没有形成优势。

不能推出：
- funding relation 无用；
- control relation 无用；
- creator relation 无用；
- 秒级跟随无用；
- 所有 wallet history 无用。

## 11. DQ-21 R0：资金关系可构造性

### FACT + ONGOING

R0 已完成一跳资金/关系变量的可构造性研究。

已知事实包括：
- 在定义的 K 个早买者与时点范围内，可在决策时点前构造一部分关系变量；
- service / exchange address 清理必要；
- 普通 transfer-table 会漏重要流入路径；
- durable nonce withdrawal 是重大语义边界；
- nonce authority 能证明提现控制，但不能自动等同于资金经济来源；
- 后续已把 `control` 与 `funding/source` 语义分离；
- R0 核心触发数量在删去 nonce control-as-source 后的本地敏感性中没有改变；
- “存在关系”在赢家压力样本与匹配失败压力样本间没有明显有利方向，但 R0 本身没有正式收益判定权。

成本方面还发现：
- 文档价格/credit 单价不能直接代替真实账户增量计费；
- 历史重建与在线持续索引成本需要账户级 smoke 校准。

## 12. DQ-21 S1：极早入场基础经济边界

### FACT

对第三个合格买家后极早入场进行了固定退出基础回收测量。

主要时点：
- `t3+5s`
- `t3+30s`
- `t3+120s`

单日 S1 中，多种固定退出基础回收均 <1：
- 保守口径 A 约 0.74–0.93；
- 乐观口径 B 约 0.76–0.98。

主要损失不只是费用：
> 开盘前几分钟本身存在明显价格下跌/漂移。

这产生一个重要经济要求：
> 新关系信号不能只有轻微预测力；若其他币表现不变，≥2× 赢家大致需要约 4–6 倍级别富集，才可能把策略推到有意义的正经济区间。

## 13. DQ-21 R1a v2：资金关系强度富集

### ONGOING

截至 snapshot，R1a v2 已获用户批准方向与“小样本先行”，但经济检验尚未完成。

当前开发设计区分：
- Zero：只看成交记录的近似关系；
- Light：普通转账的一页关系；
- Full：更完整资金归因；
- q = 5% / 10% / 20% 的关系强度分位；
- 主时点 `t3+30s`；
- A/B development；
- 不打开封存 confirmation 周。

当前问的是：
> 资金关系强度是否能把固定退出回收 ≥2× 的早期赢家显著富集，同时不让非赢家更差？

因此只能标记 `ONGOING`，不能提前写成正面或负面结论。

## 14. DQ-10M / MELT / entity

### FACT + SCOPED LIMITATION

研究过 same transaction、first transaction signer、Jito bundle、wallet funding、buyer entity relationships。

发现：
- 部分历史关系不可恢复；
- 部分关系技术可用；
- richer funding/entity graph 曾受数据成本/实现路径限制。

该路线过去主要因为数据获取方式成本或历史可得性受限而停止/降级，不等同于 entity information 已证明没有经济价值。

## 15. 链外传播 / attention

### SCOPED_NEGATIVE + UNTESTED

DQ-14/15 等检查过若干公开历史传播源。

在当时检查范围内：
- 可回放性不足；
- 失败样本缺失；
- mint 映射不足；
- 机器人/上涨战报问题明显；
- X 等并未完整覆盖。

因此只能说：
> 当时检查到的公开历史传播数据源不足以支持该实验。

不能推出所有现实世界注意力/社交信号无效。

## 16. DQ-17：优势来源搜索

### SCOPED_NEGATIVE

项目曾尝试从“更早 / 更深 / 更全”等信息位置寻找优势来源。

在当时严格证据要求下，没有找到合格来源。

但用户后来明确接受：
> 冻结统计 edge + true OOS，即使没有完整因果解释，也可研究。

因此 DQ-17 不能被用作“所有非当前信息位置已经被排除”。

## 17. T_sep

### ASSET / CONCEPT

项目逐渐形成：
> `T_sep = winner 与 non-winner 首次能够可靠分离的时点/state`

其经济价值依赖：
> remaining executable multiple × capacity × precision/recall − wrong-selection loss − execution cost

这是研究变量，不是已验证策略。

## 18. 尚未充分覆盖的信息空间

### UNTESTED / PARTIAL

至少包括：
- raw transaction/event sequence；
- richer wallet histories（DQ-20 只覆盖其中一个定义）；
- richer funding/control graph（DQ-21 正在推进，尚未完成经济确认）；
- creator / deployer / funding entity interactions；
- sequence × graph interactions；
- local mechanism-specific models；
- 部分现实注意力/外部信息；
- later-state conditional discovery；
- 其他加密市场中真正不同的信息位置。

“未充分测试”不等于“有价值”。

## 19. 工程与数据资产

### ASSET

项目已积累：
- pump.fun create/trade/complete/migration 数据经验；
- PumpSwap 边界处理；
- Dune SQL；
- public Solana RPC；
- Helius 使用经验；
- bulk historical ledger 调查；
- fees/slippage/capacity 测量；
- PIT 数据口径；
- replay/equity accounting；
- 多个 parser/tests；
- `rt_a_attribution` 等经过独立验收的工程资产；
- DQ-19/20/21 的缓存、分析脚本与结果。

未来首先考虑复用，而不是重写。

## 20. Holdout / validation assets

### ASSET

项目历史上存在尚未打开或可能仍保持有效隔离的时间窗口。

未来使用前必须：
1. repo-wide exposure audit；
2. 检查是否通过报告、图表、聊天、派生数据等间接暴露；
3. 确认后才称为 sealed holdout。

不得仅凭文件名认定 holdout 完好。

## 21. 信息/机制族状态矩阵

| 信息/机制族 | 已测范围 | 当前证据 | 仍未覆盖 |
|---|---|---|---|
| 静态市场状态 | +30m summaries | 多项局部负结果 | richer raw representations |
| 动态 public state | DQ-8A、DQ-19 | universal model / 两个有限签名未形成可复现 EV | raw event sequence、局部机制 |
| 动态退出 | DQ-7 | 11 条新规则不胜 b50 | 不同信息源驱动的退出 |
| wallet history | DQ-20 | 高活跃构成/+30m 跟随不通过 | funding/control/creator relation、秒级 |
| funding/control | DQ-21 R0/R1a | R0 可构造；R1a 正在测试经济富集 | full economic result、sealed confirmation |
| 链外传播 | DQ-14/15 | 当前公开可回放源不足 | X/其他完整历史档案 |
| later-state | DQ-18/19 | 仍有右尾；典型空间快速衰减 | later-state selection information |
| 其他场所/机制 | 多项筛查 | 尚无验证优势 | 真正不同信息位置/机制 |

## 22. 总体遗产状态

截至 snapshot，项目既没有证明 public/on-chain right-tail selection 不可行，也没有证明存在可交易 edge。

更准确的状态是：

> **右尾母体存在；多组 summary/state/exit/wallet-activity 规则未形成可验证优势；动态状态、钱包履历和资金关系已经比旧版 Legacy 测得更多，其中 funding/control 经济检验仍在进行；raw sequence、rich graph、部分外部信息和 later-state selection 尚未被充分排除。**

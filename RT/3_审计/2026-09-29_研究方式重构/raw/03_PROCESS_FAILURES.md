# PROCESS_FAILURES

> 状态：Legacy-aware Auditor 输入
> 目的：只记录“我们如何研究”层面的已观察问题。
> `OBSERVED` = 有实际项目案例。
> `SUSPECTED` = 有迹象但尚未充分确认。
> Auditor 必须回到冻结 snapshot 核验，不得把本摘要当权威事实。

## P01 — BUILD before broad resource discovery
**状态：OBSERVED**

多个任务较快进入 SQL / RPC / API / parser / 自研代码，之后才发现 bulk data、alternative provider、现成表或 repo。

典型案例：wallet funding/entity 路线先沿逐钱包 API 成本推进，之后才系统调查 bulk historical data。

核心问题：Search/Reuse 没有稳定成为 BUILD 前置步骤。

## P02 — 候选验证强，候选生成弱
**状态：OBSERVED**

项目逐渐形成较强 preregistration、OOS、fees/capacity、replay、falsification、audit，但很多候选来自人工猜测、少量 summary features、前一轮结果局部修改。

项目擅长证明给定规则不行，但不一定充分搜索真正不同的信息空间/机制。

## P03 — 过早压缩原始信息
**状态：OBSERVED / INTERPRETATION**

多个实验主要使用 fixed-time summaries、buyer count、reserve、concentration、flow aggregation、少量人工指标。

而原始信息还可能包含 sequence、timing、graph、identity/funding/control、interaction structure。

因此旧负结果容易超过实际信息范围。

## P04 — 实验数量与独立信息维度混淆
**状态：SUSPECTED，证据较强**

DQ/规则很多，但相当一部分使用高度相关的 public-state summaries。

“做过很多实验”不等于“搜索过很多独立机制”。

## P05 — acceptance criteria 曾与极重尾目标错位
**状态：OBSERVED**

历史上出现过多数周必须正、去掉最大赢家仍成立、较高 coverage、universal robustness 等倾向。

这些对稳定策略可能合理，但对低频、极重尾、少数赢家主导财富的目标可能过严。

## P06 — 局部失败容易扩大成上层结论
**状态：OBSERVED**

典型语言滑移：
> 某组 summary features 未产生 EV → public on-chain information 不行。

项目后期多次需要重新收窄这类结论。

## P07 — 工程早于研究语义稳定
**状态：OBSERVED**

出现过写代码后才发现数据边界、查询后才发现母体定义问题、parser 跑通后才重新解释变量、成本花掉后才改变路径。

## P08 — 用户成为模型人工通信总线
**状态：OBSERVED**

常见 A 长篇输出 → 用户复制给 B → B 长篇审核 → 再复制回来。

导致高人工负担、framing contamination、上下文膨胀和技术争议难以裁决。

## P09 — 双模型一致不能替代真实证据
**状态：OBSERVED / GENERAL RISK**

两个 frontier model 可能接受同一 framing、使用相似资料、共同遗漏外部工具，或对同一代码逻辑产生相似错误。

model agreement 不能代替 raw data、tests、primary sources、OOS。

## P10 — Decision Layer 与 Technical Layer 未充分分离
**状态：OBSERVED**

用户经常收到大量 SQL、parser、API schema 和技术争论，但真正需要决定的通常只是是否继续、是否花钱、是否打开 holdout、是否改变方向。

## P11 — 工具/数据能力发现是临时行为
**状态：OBSERVED**

没有稳定回答“外部世界已经有什么”的步骤，搜索常围绕已想到的实现。

## P12 — Holdout 很大程度依赖行为约束
**状态：OBSERVED**

大量使用“不要打开某周”。随着 agent 能自动搜索 repo、文件和报告，文字约束可能不够。

## P13 — AI 增大 researcher degrees of freedom
**状态：SUSPECTED**

AI 能快速产生更多 feature/state/model/mechanism，增强 discovery 的同时也增强 hindsight fitting / multiple discovery。

## P14 — “系统化”本身正在变成新目标
**状态：OBSERVED IN META-PROCESS**

项目最近从 crypto research 上升到 Research OS / Agent / Skill / MCP / governance，存在为避免重复造代码轮子而开始重复造研究系统的风险。

## P15 — API 成本不能只靠文档单位价格外推
**状态：OBSERVED**

DQ-21 期间先后出现不同 credits/call 假设，但用户控制台真实累计消耗与其中一次公开资料推算不一致。

更可靠顺序应是：
> 文档 → 小批 smoke → 控制台/账单增量 → 再外推

而不是：
> 文档 → 全量成本结论

## P16 — parser 技术正确不等于研究语义正确
**状态：OBSERVED**

DQ-21 中 durable nonce authority 一度同时被解释为 source/control。

后续审计指出 authority 能证明提现控制，不等于证明资金最初来自该实体或经济所有权属于它。

本地敏感性重算后核心 R0 触发数未改变，但术语和研究语义必须修正。

## P17 — 真实执行证据优先于静态假设
**状态：OBSERVED / GENERALIZED**

同类问题涉及 API cost、Dune credits、RPC timing、online latency、historical coverage。

能用真实账户/真实环境小规模测量校准时，不应只依赖网页规格推演最终经济或容量。

## P18 — Legacy 摘要会快速过时
**状态：OBSERVED IN CURRENT REVIEW**

`DOMAIN_LEGACY` 初版在 repo 新增 DQ-19/20/21 后已经落后。

因此人工 Legacy 摘要只能作为导航，不应成为第二套权威状态库。

改进：
- 以冻结 repo snapshot 为权威；
- Auditor 开始时做 `RT/00_总入口.md` vs Legacy completeness diff；
- 本轮开始后不追新 commit。

## 总结

最重要的流程问题不是“缺少复杂 OS”，而是若干具体故障：

- 搜索/复用晚于 BUILD；
- discovery breadth 不足；
- 低维压缩过早；
- claim scope 扩大；
- 用户成为通信总线；
- 技术层与决策层混合；
- holdout/研究自由度治理不足；
- 成本和语义有时用推演代替真实校准；
- Meta-system 本身开始吞噬注意力。

Forensic Auditor 的任务是核验这些问题是否真实、严重到什么程度，而不是默认全部成立。

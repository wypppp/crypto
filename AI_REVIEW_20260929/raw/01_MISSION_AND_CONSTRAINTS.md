# MISSION_AND_CONSTRAINTS

> 状态：Clean-room 输入
> 目的：只描述目标和硬约束，不描述旧项目历史，不暗示应该采用哪套 AI 架构。

## 1. 最终目标

核心目标：

> 从首笔真实资本部署开始计算，在 3 年内，仅通过交易活动，实现累计约人民币 100 万元或以上的交易净利润目标。

经济评价必须尽量使用真实可执行口径，至少考虑：
- 手续费；
- 滑点；
- funding；
- 无法成交；
- 容量限制；
- blocked opportunities；
- 真实资金占用。

不得用理论价格涨幅代替可执行收益。

税务如影响最终财富路径，应单独明确处理；不能用毛收益掩盖真实经济结果。

## 2. 资本路径

当前需要考虑三种资本情景：

### Path A
初始资本约人民币 1 万元，不追加外部资本。

### Path B
初始资本约人民币 1 万元；达到某个阶段性权益后，可追加约人民币 10 万元。

### Path C
初期直接投入约人民币 11 万元。

外部投入总上限约人民币 11 万元。

若 GitHub `背景.md` 中存在更新后的资金阶段规则，Legacy-aware 审计以冻结 snapshot 中 `背景.md` 为权威；Clean-room 不读取旧项目，因此这里只需要理解总体资本规模和约束。

## 3. 风险承受

用户可以接受：
- 初始资本全部亏损；
- 很高最大回撤；
- 较长无收益期；
- 大多数尝试失败；
- 收益高度集中于少数极端赢家。

因此不应因为胜率低、曲线不平滑、某些月份/周亏损，自动否定极重尾策略。

## 4. 收益形态偏好

研究重点是：

> **极端右尾。**

用户不主要寻找：
- 普通 10–30% 年化；
- 小 edge 高频积累；
- HFT；
- 需要极低延迟基础设施竞争的策略。

可以接受总体财富结果由少量巨大赢家决定。

## 5. 入场时间不预设

目标不是必须在 token 创建瞬间买入。

如果资产已经上涨 2×、3×、5×，但从该时点仍存在足够大的可执行、扣成本后的剩余右尾，则仍值得研究。

真正关心的是：

> 在机会被经济上消耗之前，能否识别它。

## 6. 研究领域

当前总领域：

> cryptocurrency / public on-chain and related observable information.

Clean-room 阶段不要预设：
- 必须是 Solana；
- 必须是 pump.fun；
- 必须是 wallet signal；
- 必须是 social；
- 必须是 machine learning；
- 必须是 causal mechanism。

## 7. 历史验证要求

核心策略原则上必须能够进行历史验证。

仅能从今天开始采集、完全无法恢复历史状态的信息，不适合作为主要 historical confirmation 依据。

必须重视：
- point-in-time correctness；
- look-ahead leakage；
- survivorship bias；
- historical availability；
- decision-time observability。

## 8. 数据与基础设施约束

大致约束：
- 数据预算优先控制在约 USD 100/月以内；
- 可以使用现有订阅和免费资源；
- 不做 HFT；
- 用户有计算机硕士背景；
- 可以运行 Linux / WSL / VPS；
- 每周可投入约 40 小时；
- 有自动化运维能力。

但用户不应该被迫逐行审查复杂 SQL、parser、统计代码，才能治理项目。

## 9. 当前工程环境

当前实际工程环境：

> VS Code → WSL/Linux → Git repository。

Claude Code 与 Codex 均可连接并在该 Linux 环境内工作。

现阶段不应为了流程改革而迁移或重建开发环境，除非有明确缺口。

## 10. AI 使用现实

用户已有多个强模型和 coding agent。

但：
- 模型额度是有限资源；
- 用户注意力也是有限资源；
- 长篇 A→B→A 审阅会显著消耗额度和时间；
- 不应默认每个任务都使用两个 frontier model。

未来模型品牌应视为可替换组件，而不是永久架构。

## 11. 用户希望承担的角色

用户主要负责：
- 最终目标；
- 资本与风险；
- 是否付费；
- 是否消耗重要 holdout；
- 是否进入 forward test；
- 是否真实部署资本；
- 战略方向选择。

用户不希望成为：
- 模型之间的人工通信总线；
- 每段代码的 reviewer；
- 每个 API/schema 的专家；
- 每个统计模型的人工 verifier。

## 12. 研究原则

允许：
- 纯统计发现；
- narrow mechanism；
- regime-dependent mechanism；
- 低 coverage；
- 极重尾；
- winner-first development exploration。

不要求：
- 必须先有漂亮因果故事；
- 必须高胜率；
- 必须每周盈利；
- 必须去掉最大赢家仍盈利；
- 必须全市场一个统一模型。

但必须明确区分 discovery 与 confirmation。

## 13. 硬安全边界

Research model / coding agent 不得获得：
- wallet seed phrase；
- private key；
- unrestricted signing authority；
- 不必要的 unrestricted exchange credentials。

真实资金执行必须与研究环境分层。

## 14. 当前要回答的元问题

不是：

> 下一只币怎么买？

而是：

> **如果今天从零设计这个研究项目，在充分利用当前 AI、数据、工具和开源资源的前提下，采用什么最低必要复杂度的工作方式，才能更高效、更可靠地接近最终财富目标？**

同时必须有停止条件：

> 什么时候应该停止研究“怎么研究”，回到真正的 crypto research？

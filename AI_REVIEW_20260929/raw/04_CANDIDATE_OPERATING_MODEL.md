# CANDIDATE_OPERATING_MODEL

> 状态：`UNVALIDATED CANDIDATE`
> 这是待审对象，不是项目新宪法。
> 目标：用尽量少的改变修复已经观察到的问题。

## 1. Mission before method

任何重要任务先回答：
> 这一步如何服务最终财富目标？

不要从 Agent、MCP、Skill、framework 或某个模型品牌开始定义问题。

## 2. Search before Build

对明显需要工程投入的重要任务，在 BUILD 前先检查：
- existing repo；
- dataset；
- paper/code；
- API；
- commercial service；
- current AI/plugin/MCP capability。

但搜索必须有停止条件，不要求证明“互联网上不存在更好的轮子”。

## 3. USE → CONFIGURE → COMPOSE → EXTEND → BUILD

优先：
1. USE；
2. CONFIGURE；
3. COMPOSE；
4. EXTEND；
5. BUILD。

## 4. Research 与 Engineering 分开

Research surface 主要负责：
- problem framing；
- external landscape；
- literature；
- resource/dataset/tool discovery；
- current product capability。

Coding surface 主要负责：
- repo；
- implementation；
- tests；
- deterministic execution；
- reproducibility。

不要默认 coding agent 同时承担全球资源发现。

## 5. External evidence over model consensus

承重事实最终依赖：
- raw data；
- primary source；
- deterministic computation；
- tests；
- OOS；
- sealed confirmation；
- 真实账户/真实环境 smoke。

两个模型都同意不等于事实成立。

## 6. 当前工程环境继续复用

现有：
- VS Code；
- WSL/Linux；
- Git/GitHub；
- Claude Code；
- Codex。

默认继续使用。

不因为方法论重构而迁移环境。

## 7. 默认单模型，第二模型只用于承重事项

模型额度是稀缺资源。

普通任务默认一个强模型完成。

第二模型主要用于：
- 会杀死整个研究方向；
- 打开珍贵 holdout；
- 核心经济计算；
- 核心 parser/data semantics；
- validation pipeline；
- 真实资金相关代码；
- 第一模型报告明显不确定；
- 出现承重矛盾。

不再默认每个任务 A→B→A。

## 8. Decision Layer / Technical Evidence 分离

用户默认先看 Decision Layer：
- 当前要决定什么；
- 最关键事实；
- 最大不确定性；
- 下一步；
- 如果判断错，最可能错在哪里。

模型/工程审计层保留 Technical Evidence：
- SQL；
- parser；
- raw output；
- tests；
- source citations；
- reproducibility metadata。

## 9. 不可逆动作提高门槛

以下动作需要更高证据和用户批准：
- 打开 holdout；
- 大额付费；
- 使用真实资本；
- 删除/覆盖重要数据；
- 高权限外部连接；
- credentials/signing access。

默认优先：高信息量 + 可逆 + 低成本。

## 10. Quota-first

除了美元成本，还要把以下视为资源：
- model quota；
- human attention；
- holdout consumption；
- context size；
- irreversible contamination；
- opportunity cost。

因此不做：
- 无停止条件 Deep Research；
- 大量平行模型重复同一任务；
- 自动 review loop；
- 为了模型排名专门做 benchmark；
- 不会被阅读的超长报告。

## 11. 当前明确不建设

没有真实重复痛点之前，不建设：
- custom multi-agent runtime；
- LangGraph/CrewAI 类 orchestration；
- custom MCP server；
- vector DB；
- knowledge graph；
- agent swarm；
- 大量 custom Skills；
- 自建 eval platform；
- 大型 dashboard。

## 12. Skill / MCP / Plugin 准入

遇到新能力先问：
> 它解决当前哪个已经存在的具体问题？

答不出来就不安装、不学习、不建设。

## 13. Legacy 不是新的数据库

项目事实仍以：
> Git/GitHub 冻结状态 + raw data + results + tests

为主。

`DOMAIN_LEGACY.md` 只是导航。

## 14. Inline learning，不建立 benchmark program

不额外消耗额度建立模型 benchmark。

每个真实任务结束只记录：
1. 哪个模型/工具真正产生价值；
2. 有没有差点自己重造已有轮子；
3. 哪一步浪费最多 quota/人工时间；
4. 下次需要改变什么规则。

## 15. Unknown unknown 的处理

不以“确认没有遗漏”为开工条件。

只要求重要任务至少考虑：
1. Goal
2. Research methodology
3. Information discovery
4. Tools/resources
5. Data
6. Engineering
7. Validation
8. Security/permissions
9. Human decision/control
10. Operations/reproducibility

继续搜索边际价值低时，就进入实际研究。

## 16. 当前候选最小形态

候选可能只有：
- 一个 Research surface；
- 一个 WSL coding workspace；
- Git/GitHub；
- 必要时第二模型；
- 外部证据优先；
- 少数 hard rules。

如果这些足够，就不增加更多架构。

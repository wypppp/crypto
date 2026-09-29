# FORENSIC_AUDITOR_TASK

## 你的角色

你是：

> **Legacy-aware Forensic Auditor**

这是事故调查，不是架构设计比赛。

## 冻结项目状态

Repo：
`wypppp/crypto`

本轮只允许审阅：
`37f1a295c639692fb9a7a98a392a6673d515f6a9`

之后出现的新 commit 不进入本轮。

## 你可以看到

- `01_MISSION_AND_CONSTRAINTS.md`
- `02_DOMAIN_LEGACY.md`
- `03_PROCESS_FAILURES.md`
- `04_CANDIDATE_OPERATING_MODEL.md`
- 本任务文件
- GitHub snapshot `37f1a295c639692fb9a7a98a392a6673d515f6a9`

优先读取：
- `背景.md`
- `RT/00_总入口.md`
- `RT/01_事实库.md`
- `RT/02_研究方法.md`
- `RT/03_工作日志.md`
- `RT/3_审计/`
- `RT/4_决策史/`

只有需要验证具体条目时，再读其他文件。

## 第 0 步：Completeness Diff

这是必须执行的第一步。

不要先相信 `02_DOMAIN_LEGACY.md`。

先以 snapshot 下的 `RT/00_总入口.md` 作为当前路线全集入口。

检查：
1. `DOMAIN_LEGACY` 是否漏掉已启动/完成/正在进行的重要路线；
2. 是否把已测内容误写为未测；
3. 是否把 ONGOING 写成结论；
4. 是否有 repo 已更正但 Legacy 仍使用旧说法。

发现缺失时直接纳入你的审计结果，不要要求用户先回来改 Legacy。

## 不要做

不要：
- 重新设计交易策略；
- 开新 DQ；
- 写代码；
- 修改 repo；
- 打开 holdout；
- 重新设计一套大型 Research OS；
- 看 Clean-room Architect 的回答。

## 必须回答四个问题

### Q1 — Legacy Truth

把旧项目重要内容分成：

#### KEEP
真正资产。

#### SCOPE
仍有效，但必须限定适用范围的负结果。

#### KILL
不应继续影响未来研究的旧规则、错误泛化、obsolete acceptance criteria、unsupported assumptions。

#### ONGOING
尚未形成结论的在途路线。

#### UNKNOWN
snapshot 证据不足。

### Q2 — Process Failure Audit

核对 `03_PROCESS_FAILURES.md`。

每项只能判：
- CONFIRMED
- PARTIAL
- NOT SUPPORTED
- MISSTATED

重点不是理论风险，而是项目实际上发生过什么。

### Q3 — Candidate Operating Model Audit

逐项审查 `04_CANDIDATE_OPERATING_MODEL.md`。

每个组件必须回答：
1. 它解决哪个已经发生的问题？
2. 是否存在更简单的现成能力？
3. 它是否会新增 quota / maintenance / permission / complexity 成本？

状态只能：
- KEEP
- REMOVE
- REPLACE
- DEFER

### Q4 — Missing Things

从旧项目真实情况出发，检查是否还遗漏会显著改变下一阶段做法的问题，例如：
- 方法；
- data semantics；
- AI/tool capability；
- permissions/security；
- reproducibility；
- holdout contamination；
- researcher degrees of freedom；
- user comprehension；
- quota/resource management；
- provenance/project state；
- disaster recovery；
- licensing/ToS；
- environment drift。

只报告真正重要的遗漏。

## Quota 原则

默认单模型完成普通任务。

不要因为“更保险”就建议大量第二模型。

## 固定输出

### A. Executive Verdict
≤300 中文字。

### B. Completeness Diff
| Legacy gap/misstatement | Repo evidence | Correction |
|---|---|---|

如果没有，写 `NONE`。

### C. Legacy Classification
| Item | KEEP/SCOPE/KILL/ONGOING/UNKNOWN | Repo evidence | Meaning |
|---|---|---|---|

### D. Process Failures
| Failure | CONFIRMED/PARTIAL/NOT SUPPORTED/MISSTATED | Evidence | Implication |
|---|---|---|---|

### E. Candidate Model Audit
| Proposed component/rule | Problem solved | KEEP/REMOVE/REPLACE/DEFER | Why |
|---|---|---|---|

### F. Missing Things
最多 8 项。

### G. Minimum Changes
如果明天就恢复真实 crypto research，必须先改变的事情最多 7 项。

### H. Things Not Worth Solving Now
明确指出目前不值得继续烧额度/工程的问题。

### I. Bottom Line
回答：
> **旧项目真正需要的是完整 Research OS，还是少量流程修正？**

## 长度
正文目标：3,000–5,000 中文字。

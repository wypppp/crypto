# AI Review Pack · 执行入口

> 版本：v1.0
> 冻结日期：2026-09-29
> GitHub repo：`wypppp/crypto`
> **本轮冻结 commit：`37f1a295c639692fb9a7a98a392a6673d515f6a9`**
> 状态：可直接执行

## 1. 本轮只解决一个问题

本轮不继续设计交易策略，也不继续扩展 Research OS。

只回答：

> 在充分利用当前已有 AI、Research、Coding Agent、GitHub、数据平台、论文、开源软件、MCP、Plugin、Skill 和其他现成基础设施的前提下，这个 crypto 研究项目最少需要采用什么工作方式？

目标不是“搭一个完整系统”，而是：

> **尽可能减少自研、减少模型额度消耗、减少用户人工搬运，同时提高研究质量和可审计性。**

## 2. 冻结规则

本轮所有涉及旧项目状态的审阅统一以 commit：

`37f1a295c639692fb9a7a98a392a6673d515f6a9`

为唯一 snapshot。

含义：

- A/B/C 审阅期间，即使 GitHub 出现新提交，也不追入本轮；
- `02_DOMAIN_LEGACY.md` 只是导航索引，不是权威数据库；
- Legacy-aware Auditor 必须先对 snapshot 下的 `RT/00_总入口.md` 做 completeness check；
- 若摘要与 snapshot repo 冲突，以 snapshot repo 中经过审计的记录为准；
- 本轮结束后再处理后续 commit，不在执行中漂移输入。

这里的“冻结”是**审阅输入冻结**，不是修改 GitHub、创建 tag 或 branch。

## 3. 只运行三次主要模型任务

### A — Clean-room Architect

只给：
- `01_MISSION_AND_CONSTRAINTS.md`
- `05_CLEANROOM_ARCHITECT_TASK.md`

不得给：
- GitHub；
- `02_DOMAIN_LEGACY.md`；
- `03_PROCESS_FAILURES.md`；
- `04_CANDIDATE_OPERATING_MODEL.md`；
- 另一个模型输出。

### B — Legacy-aware Forensic Auditor

给：
- `01_MISSION_AND_CONSTRAINTS.md`
- `02_DOMAIN_LEGACY.md`
- `03_PROCESS_FAILURES.md`
- `04_CANDIDATE_OPERATING_MODEL.md`
- `06_FORENSIC_AUDITOR_TASK.md`
- GitHub repo `wypppp/crypto`，但只审 snapshot `37f1a295c639692fb9a7a98a392a6673d515f6a9`

不得给：
- A 的输出。

### C — Difference Synthesizer

A/B 输出冻结后，新开独立会话。

给：
- `01`–`04`
- A 的冻结输出
- B 的冻结输出
- `07_SYNTHESIS_TASK.md`

默认不再做大规模 Research。只有 A/B 对一个会改变最终 operating model 的承重事实冲突时，C 才允许做一次针对性事实核验。

## 4. 模型额度纪律

模型额度是重要资源。

本轮明确不做：
- Claude vs GPT benchmark；
- Claude Code vs Codex benchmark；
- A→B→A 往返辩论；
- Reveal-and-Diff 第二轮；
- 第四个 Meta-review；
- 无停止条件 Deep Research；
- 自动 review loop。

默认：
1. A 一次；
2. B 一次；
3. C 一次；
4. 必要时最多增加一个 `BLOCKING FACT CHECK`。

## 5. 不再审核“审核流程”

本轮不再新增 Protocol Preflight、第四个 Meta-review 或新的 benchmark program。

如果源材料发现事实错误或 snapshot 遗漏，允许修事实；
但不因为“还能想出更漂亮的方法”重写流程。

## 6. 本轮禁止事项

在 C 完成前，不因本轮而启动：
- 新 Research OS 工程；
- custom multi-agent runtime；
- custom MCP server；
- vector DB / knowledge graph；
- 大量 custom Skills；
- repo 大重构；
- 新模型 benchmark；
- 新 holdout 开封；
- 新实盘授权。

旧项目已经批准、且与本轮无关的紧急资源动作是否继续，由用户单独裁决；本文件不自动撤销既有用户决定。

## 7. 成功标准

C 最后应尽量得到：
- `DELETE / REMOVE`
- `KEEP`
- `DEFER`
- `USER DECISION`
- 一套最小 operating model
- 最多 7 条 hard rules
- 是否应该停止讨论“怎么研究”，恢复 crypto research

如果没有 blocking flaw，本轮到此结束。

## 8. 文件清单

1. `00_README.md` — 唯一入口
2. `01_MISSION_AND_CONSTRAINTS.md` — Clean-room 公共目标与硬约束
3. `02_DOMAIN_LEGACY.md` — crypto/right-tail 遗产索引
4. `03_PROCESS_FAILURES.md` — 已观察研究流程问题
5. `04_CANDIDATE_OPERATING_MODEL.md` — 待审候选工作方式
6. `05_CLEANROOM_ARCHITECT_TASK.md` — 直接交给 A
7. `06_FORENSIC_AUDITOR_TASK.md` — 直接交给 B
8. `07_SYNTHESIS_TASK.md` — A/B 冻结后交给 C

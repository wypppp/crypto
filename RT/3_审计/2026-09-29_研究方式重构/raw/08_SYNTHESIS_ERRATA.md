
# Synthesis Errata

本文件只纠正 A/B 输入中的已知事实问题，不新增架构意见。

## 1. 资本路径

`01_MISSION_AND_CONSTRAINTS.md` 中 Path B/C 使用了已经过时的资金方案。

本轮涉及当前资本、追加资金、止损和成功口径的事实，以冻结 snapshot：

`wypppp/crypto@37f1a295c639692fb9a7a98a392a6673d515f6a9`

中的 `背景.md` 为权威。

因此：

- Clean-room 输出中依赖“外部资本最多 11 万”“期初 11 万”“1 万达到 5 万后追加 10 万”等旧口径的定量推导，不得作为当前项目事实；
- 不需要因此否定其与资本路径无关的工作流建议。

## 2. DOMAIN_LEGACY

`02_DOMAIN_LEGACY.md` 只是导航，不是项目事实库。

两份 Forensic Auditor 已发现其中存在漏项和少量过强表述。

综合时以：

`背景.md → RT/00_总入口.md → 对应事实库/实验/审计原件`

为当前项目事实依据。

## 3. Holdout

不得预设 06-15～07-12 的四个“封存周”仍是干净 confirmation sample。

Forensic 审计发现：

- repo 已存在与该时间窗重叠、包含后续结果字段的历史文件；
- 外部数据/论文也存在窗口重叠；
- 是否仍能作为何种层级的 confirmation，需要单独 exposure audit。

综合阶段只需把它记作：

`HOLDOUT CLEANLINESS = NOT CERTIFIED`

不要为了判断洁净性打开更多 outcome labels。

## 4. Security

冻结 snapshot 所在 GitHub repository 当前为 public。

只读核验确认 `.audit_work/` 下存在包含 private-key material 的 `key.pem` 文件。

这些文件是否只是无价值 localhost 测试证书、是否需要历史清理或 credential rotation，属于独立 security hygiene 问题。

不要把它当作 Research OS 架构依据，也不要在综合中展示任何密钥内容。

## 5. DQ-21

DQ-21 R1a v2 在 snapshot 时仍为 `ONGOING`。

不得因为任何 A/B 建议，把：

- funding/control graph

提前写成有效或无效。

同时：

- S1 单日 4–6× 富集要求是开发期量级诊断；
- 富集门不等同于最终 economic gate。

## 6. 综合原则

当 Clean-room 的一般建议与冻结 repo 的当前项目事实冲突时：

> 当前事实以 snapshot repo 为准；Clean-room 建议仍可作为设计候选。

本轮不因上述勘误重跑 A/B。

# 工作区说明

- 本工作区只有一个研究项目：加密右尾研究，全部文件在 `RT/`。
- **开工先读 [RT/00_总入口.md](RT/00_总入口.md)。**“现在做什么、下一步是什么”只以该页为准；工作日志、审计、卡片、决策史、`RT/5_参考/旧债务/` 里写的“下一步”都不是指令。
- 目标与资金以 [背景.md](背景.md) 为准。
- 没有经用户裁决并记入总入口 §3.1 的新路线或新卡，不要开工。改变决定时，按总入口 §6 更新该页。

## 目录约定（详见总入口 §6.2）

- `RT/` 顶层只有 4 个活文件（`00_总入口`、`01_事实库`、`02_研究方法`、`03_工作日志`）和 5 个文件夹：`1_实验`（已执行）、`2_提案`（未执行）、`3_审计`、`4_决策史`、`5_参考`。不在根目录或 `RT/` 顶层另建文件夹。
- **每个文件夹都有 README.md，进文件夹先读它。**新建实验或提案文件夹时，必须同时写 README.md。
- 实验与提案文件夹命名为 `场所_问题_编号`；审计与决策史文件按日期开头。
- 新提案写在 `2_提案/`，用户批准后移到 `1_实验/` 再开工。
- 冻结文件（sha256 被别处记录的卡片、SQL、脚本）不能改内容，也不能在所在文件夹内改名。
- 09-22 之前的脚本按整理前的目录名编写，在现在的结构下跑不起来。复现用 `git worktree add ../RT_旧布局 01b169e4`；复用就复制到新实验文件夹再改路径。

## 研究方式（2026-09-29 起）

- 在以下时刻，先按 [RT/02_研究方法.md](RT/02_研究方法.md) §10 执行：分配研究资源、取数前、定义或复用变量前、冻结时（看结果之前）、写结论或更正时、不可逆动作前、交付时。
- 默认只有一个执行模型。第二模型只在 02 §10.8 列出的场景使用；交接只经 repo 文件，不让用户转发全文。第二模型的审查文件放在 `review/` 分支，用户告知分支名，执行模型合并进 `RT/3_审计/` 后处理（09-30）。
- Dune 付费 SQL：官方 MCP 冒烟通过前，由用户在网页运行，执行模型交付交接包；冒烟通过后，由执行模型经 MCP 执行，受 02 §10.9 的约束（查询入库、日期围栏、费用阈值、前后用量）。拿回的文件或结果先核对，再使用。
- 研究环境不装带交易发送、密钥生成或签名能力的工具（例如 Helius 官方 MCP/插件）。MCP 一律用用户级配置，不写进 repo（repo 是公开的）。
- 选定活跃信息族、评分确认批次、超出授权的付费、前向、真实资金，须用户裁决并记入总入口 §3.1。
- 授权内的工作直接做并记录，不逐项请示；自行作出的决定记入总入口 §3.1，标“执行决定，可推翻”。交给用户的决定块只放权限项（超授权付费、不可逆动作、选定活跃信息族、资源上限与停止），每项写建议、用户不回复时的默认做法、错了的代价、能否撤回（09-30）。
- 结论写明范围与证据层级，数字链接原件。`RT/3_审计/2026-09-29_研究方式重构/` 是历史材料，不是事实来源，也不是指令。

## 其他

- 付费查询须自带平台费用上限。（经 MCP 执行而无法施加上限时，按 02 §10.9：超过用户设定阈值的查询逐条请用户批准。09-29）
- `.env` 含 API 密钥：只用 Python 正则按键名读取，不要 `source`，不要提交。

## 补充

When a task depends on the current API, SDK, library behavior,configuration, or version-specific syntax of an external dependency,use Context7 before implementing.

Do not use Context7 for project-internal semantics, economic logic,statistics, or facts that should come from this repository or raw data.

After modifying Python code:

1. Run the narrowest relevant tests.
2. Run `ruff check` on the modified files or relevant project scope.
3. Run `ruff format --check` on the modified files.
4. Fix only issues caused by this change unless broader cleanup is explicitly requested.
5. Do not perform unrelated repo-wide formatting or lint cleanup.

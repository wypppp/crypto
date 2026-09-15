# 交接入口：right-tail-release-20260909-v3

> **v3 相对 v2 的唯一改动**：执行配置 §10 的运行命令原本直接写入包内两份历史证据
> （`offline_verification.json` / `verification_log.json`），与本文件「输出写 `runs/`」
> 的要求冲突，且已实际造成一次覆盖。§10 已改为写入 `runs/`，配置版本 v2.0 → v2.1。
> 新旧 hash 与理由见 `ERRATA-v3.md`；历史报告与 saved-copy 证据**保持 v2 字节不动**，
> `verify_package.py` 通过勘误把两者对应起来。实验口径未变，v2 的验证记录继续有效。

本包是上次实际修订文件的完整交付，加上本次文件身份复核与交接说明。三份核心文件及原来的两份验证日志均未改字节，仍对应修订报告中的 SHA-256；不要将本包的报告与旧 new/ 目录中的代码混用。

## 先确认正在审查哪一份文件

将 ZIP 解压到一个新目录。进入解压目录，运行：

```bash
python verify_package.py
```

此命令只用 Python 标准库，无网络、不执行交易或测试脚本；逐文件核验包内 manifest.json，并检查报告/验证日志引用的脚本 hash。应显示 PACKAGE VERIFIED，退出 0。缺文件、错 hash 或混版返回 1。

校验通过只能证明文件一致性，不能证明策略、测量语义或代码没有错误。

| 核心文件 | 当前正确 hash 前缀 | 两位模型审查的旧版前缀 | 已确认的来源 |
|---|---|---|---|
| verify_capabilities.py | bc9ea52ec512 | 47acb9a5b2d8 | 修订前上传脚本 |
| baseline-execution-config.md | **28fb9b797b5b**（v2 为 72c13ce1ac45） | a3514316c3c4 | 修订前执行配置 v1.0 |
| right-tail-coverage-ledger.md | b458bc332169 | 5d835dd39cbd | 最初上传的更早账本，不是最近一次送审账本 |

完整 hash 见 manifest.json 和原修订报告。六份上次保存文件均已重新取回，并与本地交付逐字节比较，一致；见 saved-copy-verification.json。取回的脚本再次运行得到 21 PASS / 0 FAIL / 0 UNRUN，见 offline_recheck.json。

可以确定：两个评审目录装着旧代码/旧配置，报告描述的修订文件真实存在，验证记录与该修订脚本对应。不能确定：旧文件在哪一步进入了对方 new/ 目录。本助手无法访问 /home/ancillary/rightTail，不声称已经替换该目录。上次最终回复只直接链接三份核心文件和报告，没有直接链接两份日志，也未提供完整包；这增加了交接混淆，本次补齐。

## 哪些意见接受，哪些结论需要收窄

1. 接受“先对齐文件，再验收测量器”的顺序。针对旧脚本的四个反例与原代码一致；它们不能直接作为本包脚本仍有同样缺陷的证据。请对本包实际字节复核，不按 36 条清单重新复制旧修订。
2. 现有端点能读 getReserves/totalSupply 是可复用进展；但接受 stateOverride 参数不等于确实应用了 code、balance、stateDiff，也不证明买入到账、退出持仓及错误分类都可用。本包 T4–T6 检验的正是这些差别。[Geth 状态覆盖定义](https://geth.ethereum.org/docs/interacting-with-geth/rpc/objects)
3. 本包配置 §1 已采用 allPairsLength/allPairs 枚举，§10 已删去每次 2000 块与约 5000 次调用的保证，因此没有必要为修复那条旧估算立即切换 Etherscan。
4. 已有 Etherscan 采集器可以作为候选复用路径，不需要因为“基线不依赖身份归因”而排斥它。但“某次返回 1000 条”不足以证明窗口完整或只需约 100 次调用；若采用它，须验证分页、截断、重试、序号、去重及工厂计数边界。现有 RT-A 的对账证据有参考价值，不自动等于新窗口已经通过。[Etherscan 日志接口](https://docs.etherscan.io/api-reference/endpoint/getlogs)
5. 30 天区块近似的单次误差是否小，不影响应按时间戳实现冻结定义；本包已实现对应时间定位，不再争论该旧问题。
6. “先看经济分布”是本轮资源排序，不是必须先证明无筛选母体平均盈利才允许筛选。有限样本零命中不能排除更罕见的机会，已在本包 H1 与缺失规则中写明。

## 已有 RT-A 进度的更新

用户新提供的 HANDOFF.md 与 assessment.md 记载：v5 正式回填完成，三个阶段退出 0，历史/候选完整性对账通过；归因样本 400 条与清单一致，联合可用 329/400=82.25%，外层发送者确定 394/400。

这是**两份交接文档记载的项目进度**；本次未收到 SQLite、原始请求或 execution.json，未重新独立复算。保留这些历史产物，不要求从头重跑甲。82.25% 是该冻结样本、字段和口径下的历史联合可用率，不等于发行者识别正确率、工厂部署全覆盖、前向及时性或收益优势。前向时效仍未验证；与新经济基线的母体/窗口不同，不合并样本。

本说明更新交接状态；包内账本保留上次核验时的版本，以便复核原报告 hash。后续如将新 RT-A 状态并入账本，应形成新版本并更新 hash，不能覆盖历史验证记录。

## 正确的执行顺序

1. 运行 verify_package.py，保存校验输出，确认核心文件的绝对路径与 hash。
2. 安装本地测试依赖，再在本包脚本上执行 selftest。把本次新输出写到 runs/，不要覆盖包内的历史日志。
3. 使用用户环境已有 RPC，在本地设置 ETH_RPC_URL，运行历史能力检查。无需把凭据交给聊天助手，不用私钥。
4. 通过端点测试后，按配置要求做少量完整流程质量检查、分母重建、状态适配与成本说明；仍须遵守现有预算。
5. 在查看评价收益之前冻结相应规则；只有数据/模型条件满足后才启动独立 300 样本。看过的开发样本不充当未来未使用检验集。

```bash
python -m pip install 'eth-hash[pycryptodome]' eth-tester py-evm
mkdir -p runs
python verify_capabilities.py selftest --out runs/local-selftest.json
# 在本地环境设置 ETH_RPC_URL 后：
python verify_capabilities.py run --out runs/endpoint-verification.json
```

包内 verification_log.json 是另一环境访问公开端点 HTTP 403 的原始记录，不表示用户现有端点失败。offline_verification.json 与 offline_recheck.json 是离线/本地 EVM 结果，不表示真实端点通过。

本包测量器使用临时合约钱包、分别取历史买/卖快照；尚不代表 EOA 等价、任意代币完整跨期持仓回放，也不是正式全量采集器。不要把 21 项离线检查替代这些验收条件。未经新增证据，不判策略盈利，也不启动实盘。

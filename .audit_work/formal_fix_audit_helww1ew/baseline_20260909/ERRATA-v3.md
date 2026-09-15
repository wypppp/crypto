# 勘误与再版记录 · right-tail-release-20260909-v3

> 本包的规则是「改了就是新版本，更新 hash，不覆盖历史验证记录」。
> 因此 `revision-and-verification-report.md` 与 `saved-copy-verification.json`
> **保持 v2 时的字节不动**——它们记录的是当时验证过的那批文件。
> 本文件是 v2 → v3 的桥：列出被修订的文件及其新旧 hash，`verify_package.py`
> 用它把「历史记录里的 hash」和「当前文件的 hash」对应起来。没有在这里登记的
> 差异一律判为篡改。

## 修订项

### R1 · 执行配置 §10 的运行命令会破坏包完整性

| | |
|---|---|
| 文件 | `baseline-execution-config.md` |
| 版本 | 执行配置 v2.0 → **v2.1** |
| 旧 SHA-256 | `72c13ce1ac45865a631b845a097ebf7b08914ce468cd847db991ca65cd4f1d12` |
| 新 SHA-256 | `28fb9b797b5babf6668f97849a5f560d4b6d4238f7771106166f28cdeea3382f` |

**问题**：§10 的运行命令写的是

```bash
python verify_capabilities.py selftest --out offline_verification.json
python verify_capabilities.py run     --out verification_log.json
```

这两个路径正是包内**受 manifest 约束的历史证据文件**。照此执行会覆盖它们，
`verify_package.py` 随即失败，且原字节无法从本包恢复。而 `START_HERE.md` 要求
「把本次新输出写到 `runs/`，不要覆盖包内的历史日志」——两份文件互相矛盾，
且 §10 是「执行配置」、更可能被照抄。

**实际发生过**：2026-09-09 审查方按 §10 执行，覆盖了 `verification_log.json`
（原 `ebfbb4b1…`）。该文件由用户从原始 ZIP 重新解压恢复，经校验与原件逐字节一致。

**修改**：§10 的命令改为写入 `runs/`，并加一段说明指出包内那两个文件受 hash 约束。
配置标题版本号同步 v2.0 → v2.1。

**未改动**：母体、窗口、抽样、统计主张、成本口径、闸门条件均无变化。
本次只改运行命令与其说明，**不影响任何实验口径**，因此不需要重新执行 selftest
或端点验证；v2 的 21 PASS 与 8 PASS 记录继续有效。

## 未修订但已知的事项

- `verification_log.json` 记录的是**另一环境**访问公开端点的 HTTP 403，不代表用户端点的能力。
  用户端点的实际结果是 T1–T7 全过（8 PASS / 0 FAIL / 0 UNRUN），见 `runs/endpoint-verification.json`。
- `runs/` 目录不属于冻结包，不受 manifest 约束，可自由增删。

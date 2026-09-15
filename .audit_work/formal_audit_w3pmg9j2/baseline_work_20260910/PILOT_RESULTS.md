# 少量端到端验证 · 试跑结果（第 2 步）

> ⚠ **本文件的多项结论已被撤销或更正**，见 [PILOT_ERRATA_20260910.md](PILOT_ERRATA_20260910.md)。
> 尤其：`adequate_proven_by_execution` 已撤销；5 个 `measured_exit` 不再支持持仓充分或 M/Z 可判定；槽扫实为 35 次；均值为 75.04 秒。

> 开发样本**先冻结后测量**：`pilot/dev_sample.json`（seed 20260910，
> sha256 `0e37d131a3da408a…`），从 16,044 个 WETH 候选中无放回抽 8 个。
> 规格：`MEASUREMENT_SPEC.md` v1（草案）。EVM 原语复用 `verify_capabilities.py`
> （sha256 `bc9ea52ec51259d7…`），未重新实现。
> finalized 快照 25943342，hash `0x5f9fa40c4e531428…`
>
> **本轮不读收益、不抽正式 300 样本。** 下表只报测量机制与资源。

## 1. 状态分布（n=8）

| 状态 | 数 | 说明 |
|---|---:|---|
| `measured_exit` | 5 | 买入成功、槽位唯一命中、卖出成功且全部售出 |
| `execution_reverted_unknown` | 1 | 见 §3 |
| `no_mint_by_cutoff` | 1 | **已独立复核**：该池至今（到 finalized 快照）从未注入流动性 |
| `data_missing` | 1 | 瞬时网络错误，非脚本缺陷，见 §4 |

## 2. 逐样本资源

| idx | 状态 | RPC | 秒 | 槽扫 | slot |
|---|---|---:|---:|---:|---:|
| 477926 | `no_mint_by_cutoff` | 0 | 4.59 | — | — |
| 478595 | `measured_exit` | 60 | 100.07 | 34 | 0 |
| 479353 | `data_missing` | 15 | 26.35 | — | — |
| 480842 | `measured_exit` | 58 | 93.04 | 34 | 0 |
| 482755 | `measured_exit` | 59 | 93.91 | 34 | 0 |
| 488019 | `execution_reverted_unknown` | 60 | 95.81 | 34 | 1 |
| 491410 | `measured_exit` | 58 | 93.64 | 34 | 0 |
| 491473 | `measured_exit` | 59 | 92.92 | 34 | 3 |

合计 **370 次 RPC / 600.3 秒**。
完整路径样本（n=6）：平均 **59 次 / 94.9 秒**，离散度低。
槽位扫描固定占 34 次（57%）——唯一性判定必须扫完 32 个槽，不可缩短。

## 3. `execution_reverted_unknown` 的证据（SPEC §2 H3 在真实数据上兑现）

idx 488019，token `0x1756554146b5b934aa93bd2ffaca2ef084159910`：

- 槽位扫描唯一命中 slot 1，注入后 `balanceOf` 读数正确
- `identity_probe`：换 `CALLER` 注入，`balanceOf` 同样正确 → 槽映射无误
- 卖出 revert，`Error(string)` 解码为 **`TransferHelper: TRANSFER_FROM_FAILED`**
- `size_probe`：卖 1 个最小单位**同样 revert** → 不是与规模相关的限制

**判定维持 `execution_reverted_unknown`。** `balanceOf` 读得到而 `transferFrom` 失败，
分不清「代币侧限制」与「注入未覆盖 `transferFrom` 所用账本」——
这正是配置 §5「槽位找得到不证明状态充分」预警的情形。
**未被标为蜜罐或不可卖**，Z/M 均未知，样本保留在分母内。

## 4. `data_missing` 根因

idx 479353：`Remote end closed connection without response`。
买入已成功（stage 0），失败发生在退出块定位阶段的第 15 次调用。
包内 `RPC.request` 自带一次重试，仍未成功 → **瞬时网络错误，不是脚本缺陷、也不是链上失败**。
按 SPEC §3 记 `data_missing`，Z/M 未知，保留在分母。

> **对批量运行的要求**：8 个里出现 1 个瞬时失败。300 样本需要**断点续跑**能力
> （按候选记录完成状态、失败者单独重试），不能从零重跑。当前脚本尚无此能力。

## 5. 修掉的一个真缺陷

首轮全部 `data_missing`，根因是脚本用 `eth_blockNumber` 取链头，
而**它不在包的只读白名单**（`ALLOWED` 只有 6 个方法）。
已改为 `eth_getBlockByNumber(["finalized"])` 并冻结快照——
这反而符合配置 §1 的「运行开始固定 finalized 块号，不随 latest 漂移」。


# DQ-35 InitBoost 全量扫描（10-06；总控第二十轮第二节）

- 段：a、b、c（`sql/SCAN23_BOOST_*.sql`，生成 `过程/build_boostscan_sql.py`）；升级时刻取 2026-07-15 18:07:19～18:07:32 UTC。
- 只含计数、时刻与 vq 参数，没有成交价或收益。检验周、封存周、范围外建的老池只出计数。

## 1. 按建池时刻分组

| 组 | 有 boost 的池 | InitBoost 次数 | 有 InitBoost 的池 | BoostBuyAndBurn 次数 | 一个池多次 InitBoost |
|---|---|---|---|---|---|
| 升级前建池（老池） | 0 | 0 | 0 | 0 | 0 |
| 升级窗口内建池 | 0 | 0 | 0 | 0 | 0 |
| 升级后建池（新池） | 40980 | 40980 | 40980 | 1179251 | 0 |
| 查不到建池事件 | 0 | 0 | 0 | 0 | 0 |

## 2. 老池

**升级前建的池在扫描期内 InitBoost 0 次、BoostBuyAndBurn 0 次。**

## 3. 新池（核对）

- 首次 InitBoost 距建池（秒）：40980 个池，中位 0，p99 0，最大 0；同秒或之后 40980
- 同一个池各次 InitBoost 的 vq 相同：{True: 40980}
- 有 BoostBuyAndBurn 而没有 InitBoost 的新池：0（InitBoost 可能早于扫描起点，或在 d 段之后）
- vq 溢出（高 8 字节超 ±4e18）：0
- 新池的建池发起程序（前 8 位）：{'6EF8rrec': 37913, 'J7iAnje8': 1069, '5kZmvKba': 681, '4RoVsR9z': 434, 'AJHKxaUH': 334, '5LaRcUwH': 187}

## 4. 扫描期内全部事件类型

| 判别符 | 事件 | 次数 |
|---|---|---|
| `3e2f370aa503dc2a` | SellEvent | 670133268 |
| `67f4521f2cf57777` | BuyEvent | 666028840 |
| `929fbdac925838f4` | CloseUserVolumeAccumulatorEvent | 40422028 |
| `e2d6f62107f293e5` | ClaimCashbackEvent | 20369244 |
| `86240d48e86582d8` | InitUserVolumeAccumulatorEvent | 8038753 |
| `3f451c16305cc2b9` | BoostBuyAndBurnEvent | 1179251 |
| `e8f5c2eeeada3a59` | CollectCoinCreatorFeeEvent | 241589 |
| `b1310cd2a076a774` | CreatePoolEvent | 190075 |
| `6161d7905d92167c` | ExtendAccountEvent | 178791 |
| `1609851aa02c47c0` | WithdrawEvent | 160367 |
| `ae7c4af90451f611` | InitBoostEvent | 40980 |
| `78f83d531f8e6b90` | DepositEvent | 22603 |
| `aadd52c793a5f72e` | MigratePoolCoinCreatorEvent | 940 |
| `2ddc5d181961ac68` | AdminSetCoinCreatorEvent | 205 |
| `2f23a3f9969d937a` | **未知** | 65 |
| `98c67c7c6af67fbf` | **未知** | 2 |
| `5980f08d5bca4769` | **未知** | 1 |

- 未知判别符：5980f08d5bca4769、98c67c7c6af67fbf、2f23a3f9969d937a

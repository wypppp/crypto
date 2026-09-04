# PROBE 0B · 数据可得性门 · 可复核 manifest

> 采集时间(UTC):**2026-09-03T02:26:53Z**　执行环境:本机/沙箱　全部只读,未下单、未写入任何交易所

> 本文件的存在理由:0B 的第一版曾把 **GET 不被支持** 误记为 **API 不可达**,并据此建议改写候选卡母体。
> 没有 manifest 就无法区分「数据源变化」与「探测代码错误」。**引用 0B 结论必须引本文件,不引 probe.md 的摘要。**

## 一、端点探测(含全部失败)

| 方法 | 端点 | 状态 | 判读 |
|---|---|---|---|
| GET | `https://data.binance.vision/` | `200` | 归档站可达 |
| GET | `https://fapi.binance.com/fapi/v1/time` | `451` | **451 地域限制**,与 `AUDIT_12.md` 记录一致 |
| GET | `https://api.hyperliquid.xyz/info` | `405` | **405 = 不支持 GET,不是不可达** |
| POST | `https://api.hyperliquid.xyz/info` | `200` | **405 = 不支持 GET,不是不可达** |
| GET | `https://s3-ap-northeast-1.amazonaws.com/` | `200` | 归档站所用 S3 主机可达 |
| GET | `https://s3.us-east-1.amazonaws.com/` | `ERR:URLError` | **主机级超时** |
| GET | `https://hyperliquid-archive.s3.amazonaws.com/?list-type=2&max-keys=1` | `ERR:URLError` | 超时,但见下方判据 |

**关键判据(区分"桶不可得"与"沙箱网络策略")**:`s3-ap-northeast-1.amazonaws.com` 返回 200/307,
而 `s3.us-east-1.amazonaws.com` 与 `s3.amazonaws.com` **主机本身**超时,`aws.amazon.com` 返回 200。
⟹ 这是**本沙箱的网络主机限制**,**不是** HL 归档桶不可得。
**HL 历史归档在使用者本机上的可得性 = `UNIDENTIFIED`,必须在使用者本机重测,不得据此判死。**
另:本机无 `aws` cli、无 AWS 凭证、无 `boto3`,而 HL 归档为 requester-pays,**需凭证且产生费用**。

## 二、数据集清单(`data.binance.vision`)

| 前缀 | 子数据集 |
|---|---|
| `data/spot/daily/` | `aggTrades`, `klines`, `trades` |
| `data/futures/um/daily/` | `aggTrades`, `bookDepth`, `bookTicker`, `indexPriceKlines`, `klines`, `markPriceKlines`, `metrics`, `premiumIndexKlines`, `trades` |
| `data/futures/um/monthly/` | `aggTrades`, `bookTicker`, `fundingRate`, `indexPriceKlines`, `klines`, `markPriceKlines`, `premiumIndexKlines`, `trades` |

⚠ **现货三项只有 `aggTrades` / `klines` / `trades`——无 `bookTicker`、无 `bookDepth`。**

## 三、覆盖范围

| 数据集 | 对象数 | 列举截断 | 首 | 末 |
|---|---:|---|---|---|
| futures bookTicker/BTCUSDT | 320 | `false` | `BTCUSDT-bookTicker-2023-05-16.zip` | `BTCUSDT-bookTicker-2024-03-30.zip` |
| futures bookDepth/BTCUSDT | 500 | `true` | `BTCUSDT-bookDepth-2023-01-01.zip` | `BTCUSDT-bookDepth-2024-05-17.zip` |
| futures bookDepth/ALPACAUSDT(退市) | 271 | `false` | `ALPACAUSDT-bookDepth-2024-08-22.zip` | `ALPACAUSDT-bookDepth-2025-05-19.zip` |

**存在性点测**(`max-keys=1`,取该年首个对象):

| 查询 | 命中 |
|---|---|
| bookTicker 2025 | `（无）` |
| bookTicker 2026 | `（无）` |
| bookDepth 2026 | `BTCUSDT-bookDepth-2026-01-01.zip` |
| metrics 2026 | `BTCUSDT-metrics-2026-01-01.zip` |
| spot klines 2026 | `BTCUSDT-5m-2026-01-01.zip` |

⟹ `bookTicker` 在 **2024-03-30 后停更**(BTCUSDT 列举 `IsTruncated=false`,共 640 对象 = 320 日 + checksum);
`bookDepth` / `metrics` / `klines` **更新至今**;退市币 `ALPACAUSDT` 在 `bookDepth` 下有对象,**退市标的保留**。

## 四、抽样文件 schema 与 sha256

### bookDepth

- 文件:`BTCUSDT-bookDepth-2026-08-01.csv`
- **sha256**:`2201d1e8987d1a0cff818fd8c8ea2ca988ffabb5e3234a8968e7055d09a987ce`
- 数据行:34560　快照时点数:2880
- 表头:`timestamp,percentage,depth,notional`
- 首行:`2026-08-01 00:00:01,-5.00,10391.31400000,641498247.68100000`
- **档位**:`[-5.0, -4.0, -3.0, -2.0, -1.0, -0.2, 0.2, 1.0, 2.0, 3.0, 4.0, 5.0]` ⟹ **最细 ±0.2% = 20bp**,拿不到 bp 级半价差

### metrics

- 文件:`BTCUSDT-metrics-2026-08-01.csv`
- **sha256**:`1c0c8730c891e922a8eb3e838fc6aec4880ed15da9780a7e68e59460a03d4eec`
- 数据行:288　快照时点数:288
- 表头:`create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio`
- 首行:`2026-08-01 00:00:00,BTCUSDT,109489.8260000000000000,6890085260.3540000000000000,2.36265734,1.61198300,2.20090658,1.79177500`

## 五、复现命令

```bash
S3="https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
# 数据集清单
curl -s "$S3?delimiter=/&prefix=data/spot/daily/"      | grep -o '<Prefix>[^<]*</Prefix>'
curl -s "$S3?delimiter=/&prefix=data/futures/um/daily/" | grep -o '<Prefix>[^<]*</Prefix>'
# 覆盖范围(注意:XML 为单行,必须用 grep -o,grep -c 会数行数而非匹配数)
curl -s "$S3?delimiter=/&prefix=data/futures/um/daily/bookTicker/BTCUSDT/" | grep -o '<Key>[^<]*</Key>'
# HL:必须 POST,GET 返回 405
curl -sS -X POST https://api.hyperliquid.xyz/info -H 'Content-Type: application/json' -d '{"type":"meta"}'
```

## 六、本次采集暴露的探测缺陷(方法学,非数据)

1. **`grep -c '<Key>'` 在单行 XML 上数的是行数不是匹配数**,曾使退市币 `ALPACAUSDT` 被误判为"归档中不存在"。改用 `grep -o | wc -l`。
2. **批量 `curl` 循环中的超时被记成 `000`,而 `000` 与真实 HTTP 状态无法区分**。单独重测后:HL 为 `405`、fapi 为 `451`。
   ⟹ **任何"不可达"结论必须单独重测并记录 curl 错误码**,不得从批量循环的 `000` 直接下结论。
3. 主机级可达性与桶级可得性必须分开测,否则会把沙箱网络策略写成数据源缺失。

---

# 附录:`HL-0B` HL 历史数据通路(2026-09-03,同批采集)

全部经免费 POST API,**未使用 requester-pays S3、未产生费用**。

| 请求 | 结果 |
|---|---|
| `{"type":"meta"}` | 200;`isDelisted:true` 的资产 **56 个**(MATIC / RNDR / FTM / MKR / FXS / HPOS …) |
| `{"type":"metaAndAssetCtxs"}` | 200;`assetCtxs` 键 = `dayBaseVlm, dayNtlVlm, funding, impactPxs, markPx, midPx, openInterest, oraclePx, premium, prevDayPx`。**当前快照,无历史** |
| `{"type":"fundingHistory","coin":"BTC",...}` | ✅ 逐小时;回溯实测到 **2023-09-04**(≥3 年);键 = `coin, fundingRate, premium, time` |
| `candleSnapshot` `interval=1d` | ✅ 回溯实测到 **2023-03-06**(≥3.5 年);键 = `t,T,s,i,o,c,h,l,v,n` —— **含成交量 `v`** |
| `candleSnapshot` `interval=1h` | ⚠ 180 天前有数据、**365 天前返回空** ⟹ 小时级仅约 1 年 |
| 退市币 `MATIC` `candleSnapshot` | ✅ 2 年前窗口返回 73 根 |
| **历史 OI** | ❌ **API 无历史 OI 端点** |

**结论**:HL 免费 API 支撑「点时 top-20」与「资金费分位」,**缺历史 OI**、小时级仅约 1 年。

**对照 Binance**(同批实测):`metrics` **994 个标的**、5 分钟 `sum_open_interest`、回溯至 **2020-09-01**,
退市币保留且各自止于退市日(`ALPACAUSDT` 止 2026-01-15、`AGIXUSDT` 止 2024-07-11、`BNXUSDT` 止 2023-08-18)。

复现:
```bash
curl -sS -X POST https://api.hyperliquid.xyz/info -H 'Content-Type: application/json' \
  -d '{"type":"candleSnapshot","req":{"coin":"BTC","interval":"1d","startTime":START_MS,"endTime":END_MS}}'
curl -sS -X POST https://api.hyperliquid.xyz/info -H 'Content-Type: application/json' \
  -d '{"type":"fundingHistory","coin":"BTC","startTime":START_MS,"endTime":END_MS}'
```


---

# 复现包缺口(2026-09-03 自查,尚未补全)

本 manifest 比上一版可靠,但**还不是完整复现包**。以下已知缺口,补齐前引用相关数字须一并引用本节:

1. **HL 命令的 `START_MS/END_MS` 未给值** ⟹ 无法逐字复现;
2. **未给出两个抽样 CSV 的准确下载 URL、解压与 hash 命令**(仅给了 sha256 结果);
3. 「**994 个 metrics 标的**」「回溯 **2020-09**」「多个退市币终止日」**缺对应复现命令**;
4. 「**现货退市币保留**」**未展示一个退市现货样本**(仅展示了永续侧);
5. **`ALPACAUSDT bookDepth` 计数不一致**:本 manifest 记 271 个文件,`probe.md` 记 542 个对象
   ⟹ **542 = 271 文件 + 271 CHECKSUM**,两处口径不同,应统一为「文件数」;
6. **`BTCUSDT bookDepth` 的列举被 1000 键截断** ⟹ 现有证据只能证明**首段存在**与 **2026 点测存在**,
   **不能证明中间连续无缺口**。若 Probe 需要连续性,须逐月点测或分页列举。

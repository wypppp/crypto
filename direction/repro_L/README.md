# repro_L · Probe L 复现包(config v1.6)

**目录中的 .py 是实际运行的精确版本**;`SHA256SUMS.txt` 为完整 SHA-256,可用 `sha256sum -c` 校验。

## 流水线

| 顺序 | 脚本 | 作用 | 产物 |
|---|---|---|---|
| — | `L_00_bootstrap.py` | 载入唯一可执行来源 `L_config.json`,回显全文;**每阶段显式 `required_inputs`,缺失立即失败**;输入哈希在读取前记录,**输出哈希写完后单独记录** | — |
| 1 | `L_01_pull_ann.py` | 公告列表(`catalogId=48`) | `ann_raw.json`(2,244) |
| 2 | `L_02_crawl.py` | 公告正文。`expected_ids` 由窗口算出,**不依赖已存在文件**;自适应限流/`Retry-After`/抖动/失败轮转 | `ann_body/`、`crawl_report.json` |
| 3 | `L_03_classify.py` | 五桶分类与事件提取;**抓取完整性未通过时拒绝产出母表**(仅允许 `--dryrun`) | `L_mother_events.json` |
| 4 | `L_04_utrade.py` | `U_pair → U_trade`。官方 base/quote 优先 → 显式 fallback → 显式杠杆剔除表 | `u_trade_candidates.json` |
| 5 | `L_05b_meta.py` | 全体对最早 `daily/aggTrades` key(**仅元数据,含留出集**)。四态严格区分,缓存复用须重满足原判据 | `agg_earliest_day.json` |
| 6 | `L_06_manifest.py` | 由上两者 + config 重建下载清单,内建 reconciliation | `t0_manifest.json` |
| 7 | `L_07_download_t0.py` | **只读已冻结清单**,不重算母体/留出。逐文件校验 HTTP→官方 CHECKSUM→ZIP→CSV schema→文件名日期→时间戳单位;临时文件 + 原子改名 | `aggdl/` |
| B0 | `L_B0_perp_raw.py` | 永续原始合约表,**不剥前缀不做链接** | `perp_contracts_raw.json` |

## 关键口径

- **U_pair 3,695** → `REMOVED` 56 对(48 个确认杠杆 baseAsset)/ `SUSPECTED_LEVERAGED` 4 对(BEAR、BULL,**保留**)⟹ **参与扫描 3,639**
- `JUP`(4 对)、`SYRUP`(3 对)曾被后缀正则误删,**已恢复**
- 元数据扫描:**OK 3,626 / NO_ARCHIVE 13 / UNEXPECTED_RESPONSE 0 / FETCH_FAIL 0**
- 有 aggTrades 归档的 baseAsset **746**;窗口内 **359 = 主集 282 + 留出 77**
- **下载清单 880 个文件**;留出集 245 个**不下载**,`T0 = EMBARGOED`
- reconciliation:K线月份口径窗口内 356 **+3**(`JUP`/`SYRUP`/`币安人生`)**−0** = **359**;两口径共有 741 个 baseAsset,最早月份 **741/741 相同**
- 公告抓取完整性:`success = expected = 1453,missing = extra = 0` ✅

## 尚未执行

- `L_07` 全量下载(880 文件)**未运行**;须先通过 canary(覆盖 2024 毫秒 / 2025 微秒 / 2026 微秒 / CJK 路径)
- 联合母表(`U_trade ∪ U_announcement`)与 B 腿最终链接未生成
- **A 腿未启动**

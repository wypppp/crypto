# Probe L · 母表构建 · 进行中 · 2026-09-03(**v2 · config v1.3**)

> ⚠ **v1 的三处错误已更正**:①窗口内公告数是 **1,445** 不是 1,451;②爬虫有 P0 完整性缺陷(见 §三);
> ③"触发限流的是并发不是速率"**表述错误**——见 §三修正。

> 依据 [`L_config.json`](L_config.json) **v1.2**(sha256 `7a0fb019…`)。代码与哈希见 [`repro_L/`](repro_L/)。
> **未产出任何 λ 或收益。**本文件只记录母表构建的进度与已确立的事实。

## 一、已完成

| 项 | 结果 |
|---|---|
| 公告列表 | `catalogId=48` = "New Cryptocurrency Listing",**2,244 条全部取得**;窗口内(含 −7d 缓冲)**1,451 条** |
| 公告详情接口 | `.../cms/article/detail/query?articleCode={code}` 可用;正文为**嵌套 JSON 节点树**,取 `node=="text"` 拼接 |
| **`T_scheduled` 可提取** | 正文格式高度规整:`"Binance will list X (TICKER) and open trading for the following spot trading pairs at YYYY-MM-DD HH:MM (UTC)"` |
| **提取规则已验证** | 在已取得的 144 条正文上:命中 10 条现货上市;**2 条标题含 "Will List" 却未命中的,恰是 `Binance Futures Will List … Delivery Contracts`——正确排除** |
| **B 腿永续映射** | **700 个 USDⓈ-M 永续含 `onboardDate`**;去 `1000x` 前缀后 **654 个不同 baseAsset**;`onboardDate` 范围 **2019-09-08 ~ 2026-09-01**;status 分布 TRADING 569 / SETTLING 130 / PENDING 1 ⟹ [`repro_L/perp_linkage.json`](repro_L/perp_linkage.json) |

## 二、v1.1 的两条假设已被推翻(config 已升 v1.2)

1. ~~`T_scheduled` 来自公告正文,列表接口即可~~ ⟹ **列表接口只返回 `title`**,须走详情接口;
2. ~~`catalogId=48` 即现货上市母体~~ ⟹ **是混合流**。2,244 条中:永续 558、杠杆 302、"Will List" 247、"Will Add" 157、Earn 128、其它 835(bStocks、交易机器人、JPY 对等)。
   ⟹ v1.2 把**分类与提取规则显式冻结**(基于正文而非标题),并要求 `SPOT_LISTING + OTHER + PARSE_FAIL == 窗口内总数`。

## 三、当前阻塞:详情接口 IP 级限流

### 3a ⚠ P0:v1.2 爬虫永远到不了完整母体(已修)

`L_02c_slow.py` 的 `pending()` **只遍历已存在的 `ann_body/*.json`**。而当时只有 427 个文件,
另有约 **1,018 条公告根本没有文件** ⟹ 它会打印"全部完成",实际只代表**那 427 个文件内部**没有 `text=None`。

**已修**:`expected_ids` 由 `ann_raw.json` 按冻结窗口算出;`pending = 文件不存在 OR http != 200 OR text is None`;
完成断言 `success_ids == expected_ids` 且 `missing == extra == ∅`。修后 `pending` 立刻从 ~167 变为 **1,185**,证实该缺陷。

### 3b ⚠ 限流性质:我 v1 的表述错了

~~"触发限流的是并发,不是速率"~~ —— **不成立**。0.5s 连发 110 次零 429,**只证明存在突发额度**;
持续吞吐实测约 **5.4 条/分**,说明**同时存在突发桶与持续速率配额**。

**处置(稳吞吐,不强绕)**:突发额度用尽后自适应收敛到 **10–12 秒/请求**;读取 `Retry-After`;
随机抖动避免固定节拍;失败项**轮转队尾**避免单篇阻塞;**标题只用于优先级,绝不用于删减 `expected_ids`**。

⚠ 代理轮换 / 多 IP 可绕,但**损害可复现性**且可能触碰服务限制,**不采用**。

### 3c 已测过的替代路线(均不可用)

| 路线 | 结果 |
|---|---|
| 详情 `bapi`(当前) | 200,**唯一带正文** |
| 静态公告页 HTML(两种 URL) | **202,0 字节**(SPA 壳) |
| `apex` 详情 | 200,**80 字节,无正文** |
| 列表接口(任意 pageSize) | 只有 `title` |

⚠ **检查项 7 机制 3 在此处生效**:因为记录了 HTTP 状态,**一眼看出是 429 限流而非数据缺失**。
若沿用 `scan_d1.py` 那种"任何异常都写空数组"的写法,我会得出**"267 条公告没有正文"**这一错误结论。

## 四、发现的规则缺口(待 v1.3 补)

| 缺口 | 说明 |
|---|---|
| **多资产公告** | 实测存在 `"Binance Will List Genius Terminal (GENIUS) and OpenGradient (…)"` 这类一条公告含多个代号。config `extract.multi_asset_note` 要求**每个代号生成一个事件**,但当前正则**只捕获第一个** ⟹ 须改为全局扫描所有 `(TICKER)` |
| **乘数前缀解析** | `1000X` 之外还实测到 `1000000X`、以及少数以数字开头的异常 baseAsset(解析出乘数 `0/2/4`)⟹ 前缀规则需收紧 |

## 五、下一步

1. 慢速爬完成 1,451 条正文(后台运行中);
2. 按 v1.3 修正多资产与前缀规则后,运行 `L_03_classify.py`,产出 `SPOT_LISTING / OTHER / PARSE_FAIL` 三桶并跑桶和断言;
3. 链接 spot `T_first_trade` 与 perp `onboardDate`,产出**不可变母表**;
4. 母表落定后才跑 A 腿。**留出集数据全程不下载。**


---

## 六、B0:永续原始合约表(已完成)

[`repro_L/perp_contracts_raw.json`](repro_L/perp_contracts_raw.json) —— 快照 `2026-09-03T09:44:06Z`,
**原始响应 sha256** `8c4f1ce3c3f7b5fd9f84793f6ea7b05f1d59568f36c872e33588329763b8f2e7`。
保留 `symbol/pair/baseAsset/quoteAsset/marginAsset/contractType/status/onboardDate/deliveryDate`,**完全不剥数字前缀,不做任何链接**。

| 项 | 值 |
|---|---|
| 合约总数 | **892** |
| contractType | **`PERPETUAL` 700**｜**`TRADIFI_PERPETUAL` 188**｜`CURRENT_QUARTER` 2｜`NEXT_QUARTER` 2 |
| status | TRADING 761｜SETTLING 130｜PENDING_TRADING 1 |
| 永续的 onboardDate / deliveryDate | **700 / 700 全覆盖** |
| 永续 quoteAsset | USDT 656｜USDC 39｜USD1 2｜U 2｜BTC 1 |
| 原始 baseAsset 唯一数(永续) | 656 |

### 6a 数字前缀:原始表证实了 v1.2 映射确实坏了

以数字开头的原始 `baseAsset` 共 **23 个**:

```
0G  1000000BOB 1000000MOG 1000BONK 1000CAT 1000CHEEMS 1000FLOKI 1000LUNC
1000PEPE 1000RATS 1000SATS 1000SHIB 1000WHY 1000X 1000XEC 1INCH 1MBABYDOGE 2Z 4 42
```

其中 **`0G` / `1INCH` / `1MBABYDOGE` / `2Z` / `4` / `42` 的数字是币名本身**,只有 `1000*` / `1000000*` 是真乘数。
⟹ v1.2 的 `^(\d+)(.+)$` 剥离产生了 `2ZUSDT→Z`、`42USDT→2` 等错误映射,**该映射已作废**。
v1.3 规则:原始 `baseAsset` 完全相等优先 → 仅 `1000`/`1000000` 白名单 → 剥离后必须与真实现货 baseAsset 完全匹配 → 歧义与未匹配单列。

### 6b 顺带发现:`TRADIFI_PERPETUAL` 是股票永续的**规则性**标识

**188 个合约的 `contractType` 就是 `TRADIFI_PERPETUAL`。**
⟹ Probe F 中我那个按名单剔除股票永续的做法(已因错分 `FUSDT`→Ford、`TUSDT`→AT&T 而废弃),
**本可以直接用 `contractType` 字段完成**。已记入 `PROBE_F_lambda.md` 的可改进项。

### 6c 最终链接仍须等待

`perp_event_linkage.json` **不能现在生成**:v1.3 要求"剥离后必须与一个实际现货 baseAsset 完全匹配",
而完整参照系来自公告母表,母表未完成 ⟹ 现在生成的任何映射都缺少校验依据。

---

## 七、复现包已与运行版同步

[`repro_L/`](repro_L/) 中的 `.py` **就是后台实际运行的精确版本**(已逐个比对 sha256 一致),
含 `L_config.json` v1.3、`ann_raw.json`、`perp_contracts_raw.json` 与完整 `SHA256SUMS.txt`。
带 P0 缺陷的 `L_02c_slow.py`、并发过高的 `L_02_pull_bodies.py`、基于 v1.2 规则的 `L_03_classify.py` **已移出并在 README 中标注作废原因**。

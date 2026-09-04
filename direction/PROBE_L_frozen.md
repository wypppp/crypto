# PROBE L · 冻结 · **v1.1** · 2026-09-03

> ⚠ **[`L_config.json`](L_config.json) 是唯一可执行来源。**本 Markdown **只解释它,不被脚本解析**。
> 脚本必须:载入 config、**回显完整 config**、**回显 config 与代码的完整 SHA-256**、
> **遇未识别或缺失键即失败**、**回显全部断言的运行结果**。
> 否则只是把硬编码从 Python 搬到两个会漂移的文件里(检查项 7 机制 6)。
>
> `L_config.json` SHA-256(v1.1):`8ee801958a306be6624d6fffeb69c8b57850bde46a195f4fd8892a61a85ce4a7`

---

## 一、本 Probe 的性质:**`PARTIAL / PRICE-SIDE SCREEN`**

⚠ **v1.0 写的「完整服务 `GPT5-E1`」不成立,已撤回。**

只算条件 1+2、忽略提前退出、无 ask/bid、无容量 ⟹ 它测的是:

> **`GPT5-E1` 的价格侧放宽规则,及其 λ 上界。**

⚠ **`λ_filter12` 是事件数的上界,但其收益均值对完整四条件策略既不是上界也不是下界。**
放宽过滤会改变样本构成,方向未知 —— 不得当作"保守估计"。

| 卡 | 服务程度 |
|---|---|
| `GPT5-E1` | **`PARTIAL / PRICE-SIDE SCREEN`** |
| `OP5-E2` | 仅其「CEX 上市」子组(该卡含迁移与指数纳入,本 Probe 不取) |
| `#20` | 需永续侧,见 §八 B 腿 |

---

## 二、母体:**公告母体,不是成交母体**(v1.0 的最大缺陷)

⚠ **v1.0 把母体定义为「归档中出现过的标的」,会结构性漏掉四类事件**——
已公告但从未开盘｜开盘但从未成交｜归档缺失｜上市后立即停止。
**这些恰恰是原卡要求保留的失败样本。**

**已实测确认公告母体可取**(2026-09-03):

| 项 | 值 |
|---|---|
| 端点 | `www.binance.com/bapi/composite/v1/public/cms/article/list/query` |
| `catalogId` | **48**,`catalogName` = **"New Cryptocurrency Listing"** |
| 文章总数 | **2,244** |
| 字段 | `title`、`releaseDate`、`articleId` |

**正确拆法**:

| 层 | 定义 |
|---|---|
| **母体** | Binance 一手新币上市**公告** |
| `T_scheduled` | 公告正文中的**计划开盘时间** |
| `T_first_trade` | `aggTrades` 归档中的**第一笔成交** |
| 策略 `T0` | `T_first_trade` |
| **无成交的公告事件** | 保留为 **`no_T0`**,不得删除 |
| 事件 ID | **`{articleId}::{baseAsset}`** |

> **公告定义"应该发生什么";成交归档定义"实际何时开始"。**
> ⚠ 随机核对 20 个只能验证**解析**,不能替代**公告母体**。

**去重**:同一 `baseAsset` 的多个报价对只保留 `T_first_trade` 最早者;其余计入 `dup_dropped` 但**保留在母体计数中**
(`C1-BN` 的教训:cluster 规则并未替我合并 BTCUSDT/BTCUSDC/BTCBUSD)。

---

## 三、四个过滤条件:两个可算,两个不可算

| # | 条件 | 可算 | 冻结公式 |
|---|---|:---:|---|
| 1 | 30 分钟价格 > 首 30 分钟 VWAP | ✅ | 窗口 **`[T0, T0+30min)`**;`VWAP = Σ(price×qty)/Σ(qty)`,**qty 用 base quantity**;比较价 = **入场代理那一笔**(同一笔,不另取) |
| 2 | 最后 10 分钟主动买入占比 ≥60% | ✅ | 窗口 **`[T0+20min, T0+30min)`**;**主动买入 ⟺ `isBuyerMaker == false`**;占比按 **quote notional**(非 base qty) |
| 3 | 滑点 ≤1% | ❌ | 需订单簿,0B 已证现货无历史簿 |
| 4 | 交易/充值状态无异常 | ❌ | 归档无该字段 |

主口径 = 只施加 1+2 ⟹ `λ_filter12`。**不得声称"已按原卡四条件筛选"。**

---

## 四、价格代理与缺失处理

| 项 | 冻结值 |
|---|---|
| 入场 | `T0+30min` 后第一笔 `aggTrade` 成交价,**容差 ≤10 分钟** |
| 出场 | `T0+30min+7d` 后第一笔成交价,**容差 ≤24 小时** |
| **缺失命名** | **`price_proxy_missing`**(v1.0 的 `no_fill_proxy` 已改名 —— **没有公开成交不证明真实 IOC 一定无法成交**) |
| 缺失处理 | 保留在母体;**不填 0、不填 −100%、不删除** |
| 必报伴随量 | 入场/出场时点前后各 1 小时的成交笔数(稀疏度) |

### 估计量(必须分报,不得合并)

`n_universe` ｜ `n_price_observed` ｜ `price_proxy_missing` ｜ **observed-only** 的均值/中位/p10/p25/p75/p90。

⚠ **不计算全母体均值。**缺失值如何进入均值**未冻结**,**禁止运行后再决定**填 0 / −100% / 删除。
⟹ 第一项输出的正确名称是 **「未过滤、价格可观测样本的 `r_price_proxy` 分布」**,
**不得**称"完整无条件 cohort 均值"。

---

## 五、并发与 λ 层

| 项 | 冻结值 |
|---|---|
| `f_policy_cap` | **0.10**(政策帽,非实测成交) |
| 槽位数 | 10 |
| 占槽 | **严格 7 日,不提前释放** |
| **超额时的选择** | **按 `T0` 升序;完全相同则按 `baseAsset` 字典序升序** |
| 输出名 | **`λ_slot_admitted_upper`**(条件 3/4 与容量均未知 ⟹ 只能是上界) |

四层:`λ_listed` → `λ_filter12` → `λ_slot_admitted_upper` → **`λ_exec` = `UNIDENTIFIED`**。
并发触顶次数单独报为 `λ_concurrency_blocked`。

---

## 六、授权与禁止

| 允许 | 禁止 |
|---|---|
| 各层 λ、observed-only 的 `r_price_proxy` 分布 | `λ_exec`、`C_abs`、任何 P&L |
| A/B 两腿分别的结果 | 全母体均值(缺失处理未冻结) |
| 稀疏度、`price_proxy_missing` 占比、`T_first_trade − T_scheduled` 滞后分布 | 任何出口标签(`BUDGET-NO-GO` 等) |

**本 Probe 不产生任何出口标签。**

---

## 七、留出集:**开启条件已预注册**

| 项 | 值 |
|---|---|
| 规则 | `sha256(baseAsset)` 首字节 `mod 5 == 0`(≈20%) |
| 执行 | **留出集的数据文件根本不下载**(而非下载后不看)⟹ 可在文件系统层面验证 |
| **开启条件** | **仅当 A 腿全部规则完全锁定、且主分析集结果已产出后,作一次性确认;不满足则永不打开。上限 1 次。** |

⚠ v1.0 只写"主结果出具前不下载"是不够的 —— 本 Probe **没有出口线**,"主结果"因此不构成明确的开启条件。

⚠ **状态对照**:F 的符号留出**已被全量 census 消耗**;C1-BN 的时间留出**已被规格核验污染并作废**;**只有 L 的留出是干净的**。

---

## 八、B 腿(`#20` 反转):**映射可现在预处理**

**已实测确认**(2026-09-03):永续 `exchangeInfo` 的 **`onboardDate` 覆盖 892/892**(现货没有此字段)。
⟹ **现货↔永续的对应关系与上线时点,现在就能建,不需要等。**

| 现在可做(纯结构性链接,不含收益) | 仍禁止 |
|---|---|
| 建**不可变母表**(mother manifest):公告事件 → spot 标的 → perp 标的 → `onboardDate` → 可做空窗口存在性 | 任何反转收益 |
| 永续覆盖率(多少上市事件当时有永续可做空)——`#49` 在退市 cohort 上实测为 **51% 无永续**,本卡的同类数尚未测 | 任何 P&L |
| `spot T0` 与 `perp onboardDate` 的**滞后分布** | 用现货价格代替永续价格 |

**链接规则**(已冻结进 config):`spot baseAsset → perp symbol`,须处理 `1000X` 前缀等改名;
同一 `baseAsset` 有多个永续时取 `onboardDate` 最早者。

⚠ **B 腿的收益计算仍未冻结**,预处理只产出母表与链接统计。

---

## 九、预注册断言(全部必须通过,失败则不得出报告)

```
lambda_filter12            <= lambda_listed
lambda_slot_admitted_upper <= lambda_filter12
dup_dropped + lambda_listed == 去重前事件总数
n_price_observed + price_proxy_missing == n_universe
所有 T_first_trade > 2017-01-01 且 < window_end_utc
max(|T_first_trade - T_scheduled|) 必须打印;超过 6 小时的事件逐条列出
A_input_event_ids == shared_mother_event_ids
set(留出集 baseAsset) ∩ set(已下载文件对应 baseAsset) == ∅
```

**两处相对 v1.0 的修正**:

1. ⚠ **`2017 < T0 < 截止日` 不是时区哨兵** —— 它只抓秒/毫秒单位错,抓不住 8 小时偏移。
   真正的哨兵是 **`|T_first_trade − T_scheduled|` 的分布 + 最大值 + 异常清单**(需公告母体才成立,见 §二)。
2. ⚠ **`A腿事件集 == B腿事件集` 在 A 腿单跑时不可能满足**(B 腿明确禁止开跑)⟹
   改为 **`A_input_event_ids == shared_mother_event_ids`**;B 腿启用后再断言它读取**同一份不可变母表**。

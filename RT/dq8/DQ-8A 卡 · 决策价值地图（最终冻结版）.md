# DQ-8A 卡 · 决策价值地图（只用 6 月数据）

> **最终冻结版｜2026-09-17**
>
> 本版整合 DQ-8A 原卡及运行前最后审阅确认的 7 项修改；**r2（Gate 0 通过后）**：用户取消 credits 上限，第十三节预算只作估算；逐笔排序键加入 `outer_instruction_index`（F81，口径实现修复，不改研究内容）。**文字修订 r1（同日，冒烟前）**：冒烟上限 5→12 credits、阻断项分为 Gate 0 / Gate 1、冻结特征 2 定义、明确 Gate 1 前 A 周仅作工程调试、写明回归按持仓/空仓分状态估计。未扩大研究内容。  
> DQ-7 已停止，不运行其 4 个验证周；F78（止损后收复高点再买回）并入本卡；只用 6 月数据，P0 主判，P2 只做描述；5 月数据留作条件触发的 DQ-8B。
>
> **冻结原则：**
> - 本卡运行后不得新增模型、特征、检查点、止损比例或判据；
> - Gate 0 未通过，不得运行 A 周正式查询；Gate 1 未通过，不得做正式分析或运行 B 周；
> - 标记为“运行前必须冻结”的规则必须在 A 周正式查询前写入代码/配置并记录 sha256；
> - A 周用于调通分析管线；分析脚本冻结后，B 周才可运行；
> - 四个真正封存周在本卡中不得读取、运行或用于调参。

---

## 一、只回答一个问题

**在 pump 曲线创建后 30 分钟起，只使用当时及之前能够公开获得的链上状态，能否在预定义检查点上做出比 50% 移动止损 `b50` 更好的资本暴露决策？如果存在完美信息下的决策空间，当前公开信息能够捕获其中多少？**

本卡不是寻找“最优止损百分比”，也不是预测事后最高点。

核心 estimand 是：

> **当前可观察信息能否稳定提高相对于 `b50` 的机会归一净价值。**

---

## 二、数据

### 2.1 检查点面板

数据脚本：

- `sql/F3_smoke.sql`
- `sql/F3_devA.sql`
- `sql/F3_devB.sql`
- `sql/build_f3.py`

链上扫描、入场、AMM、毕业后交易和费用口径全部沿用 DQ-7 / F1。

### 2.2 检查点

自原始 30 分钟入场时刻起：

- 0 分钟
- 5 分钟
- 15 分钟
- 30 分钟
- 1 小时
- 2 小时
- 4 小时
- 8 小时
- 24 小时
- 3 天
- 7 天

持有期最长 30 天。

不得在看到 A/B 周结果后增加、删除或移动检查点。

### 2.3 每个检查点 / 区间至少输出

检查点状态：

- 当前储备；
- 当前交易场所；
- 当前费率；
- 当前可卖回收；
- 当前 0.5 SOL 买入/卖出的价格冲击或足以在 Python 中精确重建该冲击的储备状态；
- 第四节全部状态特征；
- 5 秒执行延迟后的成交状态。

每个相邻检查区间同时输出：

- 原始持仓在区间内首次触发 50% moving stop 的时点与成交状态；
- 原始持仓在区间内首次触发 70% moving stop 的时点与成交状态；
- 24 小时无成交触发时点；
- 重建任意检查点新开仓后逐笔 moving stop 所需要的完整路径信息，或预计算出的等价结果。

### 2.4 样本身份

- **A 周：2026-06-01～06-07**
  - Development A。
- **B 周：2026-06-08～06-14**
  - Cross-period generalization check；
  - 已在旧研究中打开过，**不得称为真正样本外**。
- **封存周：2026-06-15～07-12，共 4 周**
  - 本卡绝对不碰。

### 2.5 人群

**P0：**

- 活跃池全体；
- 本卡唯一正式主判人群。

**P2：**

```text
entry_x_sol ≥ 59.1866
AND dev_prior_launches ≤ 11
```

用途：

- 只做描述性评估；
- 不单独拟合主模型；
- 不以单周 P2 统计显著性决定路线生死。

入场特征按 mint 合并：

- A 周：`dq7/raw/F2_dev.csv`
- B 周：`dq1f/raw/F1_val.csv`

---

## 三、决策空间与估值

### 3.1 仓位空间

只允许：

```text
0 SOL
0.5 SOL
```

本卡**不单独测试部分仓位 / staged sizing**。

理由不是“已经证明中间仓位没有价值”，而是：

> 本卡有意把动作空间限制为二元资本暴露，优先回答“公开动态状态是否足以支持 0 ↔ 0.5 SOL 的决策变化”。

因此：

**本卡失败不能推出分阶段仓位无效。**

### 3.2 动作

每个检查点，若当前持仓 0.5 SOL：

```text
A0：立即卖出 / 转为空仓
A1：继续持有，并采用 50% moving stop
A2：继续持有，并采用 70% moving stop
```

若当前空仓：

```text
A0：继续空仓
A1：买入 0.5 SOL，并采用 50% moving stop
A2：买入 0.5 SOL，并采用 70% moving stop
```

### 3.3 【BLOCKING】所有新仓位必须获得完全相同的逐笔止损执行权

这是正式查询前的 blocking 条件。

任何检查点新买入的仓位：

1. 从该笔实际成交后重新定义本次持仓的 `running_peak`；
2. 在两个检查点之间逐笔更新 peak；
3. 逐笔检查其当前选择的 50% 或 70% moving stop；
4. 若未触发，`running_peak` 必须带入下一检查区间；
5. 再买回后的新持仓重新建立自己的 peak；
6. 不得用“只在下一检查点判断止损”代替。

策略状态至少必须包含：

```text
position
entry_time
entry_state
running_peak
stop_mode
```

**若当前 SQL / Python 管线不能对检查点新开仓实现上述逐笔重放，不得运行 A 周正式查询。**

### 3.4 【运行前必须冻结】24 小时沉寂

所有持仓模式共同执行：

```text
24 小时无成交 → 强制退出
```

因此：

```text
hold50 = 50% moving stop OR 24h inactivity OR 30d cap
hold70 = 70% moving stop OR 24h inactivity OR 30d cap
```

不得出现：

- `b50` 带 24h inactivity；
- 动态策略的 50%/70% 持仓却不带 inactivity。

### 3.5 成交时间

任何检查点：

- 决策信息只能使用截至检查点 `t` 的状态；
- 实际交易使用至少 5 秒后的可成交状态；
- 不得使用用于形成决策的同一笔成交价格立即成交。

区间止损继续沿用既有 5 秒执行假设。

### 3.6 卖出估值

沿用 F1：

- bonding curve：把我方仓位计入储备状态并按冻结公式估值；
- AMM pool：按常数乘积及冻结费用规则；
- 所有策略使用完全相同估值方法。

### 3.7 成本

每次完整 round trip：

```text
额外扣 0.004
```

口径继续与 DQ-7 一致。

所有重新进入都视为新的资本部署和新的 round trip，不得免费重置。

### 3.8 机会归一指标

原“wealth”更名为：

## `opportunity-normalized net value`

对每个候选币：

```text
value
= 1
+ Σ（每笔交易回收 − 本次部署本金 − 该笔额外成本）
```

完全不交易：

```text
value = 1
```

同时必须报告：

- round trips / opportunity；
- gross deployed notional；
- 总额外费用；
- 自身价格冲击；
- 首次入场检查点；
- re-entry 次数。

### 3.9 决策空间

#### S1｜持有 / 退出

检查点 0：

```text
必须买入 0.5 SOL
```

之后：

```text
卖出
或 hold50
或 hold70
```

对照：

```text
逐笔 b50 + 24h inactivity
```

#### S2｜自由进出

检查点 0：

```text
可以买，也可以不买
```

以后任意检查点：

```text
保持空仓
首次买入
卖出
重新买入
```

买入后选择：

```text
hold50
或 hold70
```

S2 包含：

- F78 re-entry；
- 延后首次入场；
- 多次进出。

---

## 四、信息受限策略

### 4.1 主方法

方法：

## 回归式逆向动态规划

不是把本卡称为标准 Longstaff–Schwartz。

从最后一个检查点向前递推。

在每个检查点，对可行动作估计：

> 在当前可观察状态下，选择该动作并在未来继续执行冻结策略的条件期望实现价值。

下游 target 使用**实现值**，不得用模型预测值替代真实 downstream realized value。

**分状态估计（r1 写明）**：持仓状态与空仓状态的 continuation 回归**分别拟合**，不混在同一个 ridge 中，因此不需要 `is_positioned` 特征：

- 持仓模型：按（检查点 k, 止损模式 50/70）拟合，样本为该检查点仍持有的仓位（原始仓位及此前各检查点新开仓位），target 为继续持有并按冻结策略执行的实现价值 ÷ 当前卖出价值；
- 空仓模型：按（检查点 k, 止损模式 50/70）拟合，样本为在 k 新买入 0.5 SOL 的假想仓位，target 为该仓位按冻结策略执行的实现价值（含买入冲击）÷ 0.5；
- 持仓时动作 = argmax{卖出, 持仓模型预测}；空仓时动作 = argmax{不买, 空仓模型预测 − 1 − 0.004 > 0}。

### 4.2 主模型

唯一正式主模型：

```text
Ridge regression
alpha = 10
不调参
```

所有连续特征按训练样本标准化。

### 4.3 【运行前必须冻结】mint-level 5-fold cross-fitting

A/B 周内部训练必须采用：

```text
K = 5
按 mint 固定分折
```

要求：

- 同一 mint 的所有 checkpoint 永远属于同一 fold；
- 禁止 checkpoint 行级随机分折；
- backward recursion 中，对 mint `i` 的 downstream action/value 必须来自**未见过 mint i 的模型**；
- OOF downstream realized value 再传递给前一个检查点；
- 不得用同一条路径既拟合 continuation function，又生成自己的训练 target。

完成 cross-fitting、确定正式策略逻辑后：

- A → B：可用完整 A 重拟合每个冻结 checkpoint 的模型参数，然后**一次性执行 B**；
- B 的任何结果不得反馈进入 A→B policy；
- B → A 同理，仅作稳定性检查。

### 4.4 主特征

正式特征冻结为以下 **16 个**：

1. `log(当前价 / 原始30分钟入场价)`
2. 回撤（r1 冻结）：**持仓状态** = `log(当前价 / 本次持仓买入后的 running peak)`；**空仓状态** = `log(当前价 / 原始 30 分钟入场以后的 global running peak)`。两种状态的回归分别拟合（见 4.1），同名特征不在同一模型中混用
3. `log1p(过去30分钟新买家数)`
4. `log1p(过去30分钟成交笔数)`
5. `log1p(前一个30分钟成交笔数)`
6. `过去30分钟买入额 / 买卖总额`
7. `log1p(过去30分钟买卖总额)`
8. `内部人累计卖出比例`，截到 `[-1, 2]`
9. `从未买过的钱包卖出占比`
10. `是否已毕业`
11. `log1p(距最后一笔成交秒数)`
12. `log(入场储备)`
13. `log1p(创建者前30天发币数)`
14. `log1p(max(入场前净流入, 0))`
15. `是否属于 P2`
16. **当前 0.5 SOL 交易冲击 / 当前流动性状态**
    - 优先直接使用 Python 按当前池状态算出的 0.5 SOL round-trip impact；
    - 若实现上必须使用储备代理，则冻结为 `log(current_x_sol)`，不得事后在两者之间选优。

若距上一笔成交 >30分钟：

- 特征 3–7、9 按冻结口径记 0。

### 4.5 P2 的解释限制

`P2` 只作为一个 indicator 进入主模型。

本卡**不加入 P2 × 其他特征的 interaction**。

因此 P2 的结果只能解释为：

> **P0-trained policy 在 P2 子集上的表现。**

不能解释为：

> “已经充分检验了 P2 自身最优的信息受限策略”。

### 4.6 非主模型

只做描述：

- 主模型；
- 加特征 1–3 的平方项和两两乘积。

非主模型：

- 不参与 GO/STOP；
- 不得替代主模型；
- 不得因结果更好而选择它去封存周。

### 4.7 尾部处理

目标：

```text
不 winsorize
不截断赢家收益
```

因为尾部是经济来源。

必须报告：

- 最大10个币对策略 Δ 的贡献；
- 去掉 top1 / top5 / top10 后的描述结果；
- 但这些敏感性分析不参与主判。

---

## 五、完美信息上界与报告指标

### 5.1 Perfect-information oracle

对 S1、S2 分别计算：

> 在相同动作空间、完全相同成本和执行条件下，事后知道整条未来路径时的逐币最优策略。

不得使用 S1/S2 动作空间之外的“最高点卖出”等 oracle 作为本卡正式 capture denominator。

### 5.2 三个核心值

每个决策空间必须报告：

```text
V_b50
V_oracle
V_policy
```

以及：

```text
oracle gap
= V_oracle − V_b50
```

```text
policy delta
= V_policy − V_b50
```

```text
capture ratio
= (V_policy − V_b50)
  /
  (V_oracle − V_b50)
```

### 5.3 Capture ratio 解释

Capture ratio：

- 只作为描述；
- 不参与 GO/STOP；
- 必须与绝对 `oracle gap`、`policy delta` 同时报告。

当：

```text
oracle gap 很小
```

不得单独用高 capture ratio 宣称策略有效。

---

## 六、判据

### 6.1 P0 正式主判

S1、S2 分别判定。

某一决策空间只有同时满足以下三条，才记为：

```text
PASS-DEVELOPMENT
```

#### 条件 1

A 周拟合 → B 周执行：

```text
paired mean delta
= policy − b50
≥ +0.03
```

#### 条件 2

B 周按 mint 做配对 bootstrap：

```text
2,000 次
paired delta 的 10 分位 > 0
```

#### 条件 3

B 周拟合 → A 周执行：

```text
paired mean delta > 0
```

该方向只作为稳定性条件，不构成真正 OOS。

### 6.2 P2

P2 不参与主 PASS/FAIL。

报告：

- `V_b50`
- `V_oracle`
- `V_policy`
- oracle gap
- policy delta
- capture ratio
- top-return contribution
- 动作分布

### 6.3 【运行前必须冻结】P2 anomaly 分支

若：

```text
P0 FAIL
```

但 P2 同时满足：

```text
paired delta ≥ +0.10
```

且：

```text
正增益并非由单个 mint 独占
```

则：

- **不得把 P2 判为通过；**
- **不得进入封存周；**
- 触发 DQ-8B 扩展开发数据 / P2 异质性调查。

该分支只是防止“P0 模型平均掉 P2 特有效应”。

若没有这种异常：

```text
P0 FAIL → 当前 pump +30m 动态决策路线 STOP
```

### 6.4 【运行前必须冻结】若 S1、S2 都通过，如何选择唯一 confirmatory primary

不得在封存周同时拿两个策略“谁过算谁”。

若 S1、S2 都满足开发判据：

1. 比较 A→B 的 paired mean delta；
2. 较高者成为唯一 `confirmatory_primary`；
3. 若两者差值 < 0.01：
   - 选择动作空间更简单的 **S1**。

冻结后：

- 四个封存周只允许 `confirmatory_primary` 作为正式主策略；
- 另一策略只允许描述性运行，不能救 primary。

---

## 七、必须报告的解释性结果

### 7.1 决策价值地图

对 S1、S2 分别输出：

| 决策空间 | b50 | Oracle | Policy | Oracle gap | Policy Δ | Capture |
|---|---:|---:|---:|---:|---:|---:|

P0 主表。

P2 另表。

### 7.2 行为分解

S1：

- 各 checkpoint 的：
  - exit；
  - hold50；
  - hold70；
- 每种动作对应的贡献。

S2 必须额外拆分：

- checkpoint 0 首次买入；
- 延后首次入场；
- never-buy；
- re-entry；
- 每币交易次数；
- 第1次 / 第2次 / 第3次及以上 re-entry 的贡献。

### 7.3 首次入场时点

必须输出 S2 的：

```text
first-entry checkpoint distribution
```

若 S2 的主要收益来自：

```text
3d / 7d 第一次入场
```

不得解释为：

> “动态退出有效”。

应解释为：

> “延后首次入场可能是独立的新方向”。

### 7.4 交易代价

必须报告：

- round trips / opportunity；
- gross deployed notional；
- 总额外费用；
- 自身 AMM impact；
- 持仓时间。

### 7.5 尾部贡献

输出：

- top1；
- top5；
- top10

分别贡献了多少 policy Δ。

---

## 八、面板与执行管线验收

### 8.1 【BLOCKING】冒烟

`F3_smoke.sql`

要求：

- 单日 cohort；
- 最多扫描3天；
- ≤12 credits（r1：自检含独立 b50 对照路径，需两次扫描）；
- 所有冻结 `bad_*` 必须为0；
- 新仓位逐笔50/70 trailing 重放自检必须通过；
- 24h inactivity 逻辑自检必须通过。

任一 blocking 自检失败：

```text
不得运行 A 周。
```

### 8.2 【BLOCKING】b50 复原验收

A 周面板重建 `b50` 必须与 DQ-7 `F2_dev.csv` 同一批 mint 对照。

必须同时满足：

#### A. 币级结果一致率

```text
≥ 99.8%
```

#### B. 平均回收绝对差

```text
≤ 0.001
```

#### C. Tail mismatch audit

所有不一致 mint 必须单独输出，并特别标记：

- 是否事后 ≥10×；
- 是否进入 top-return；
- 对均值差贡献。

如果有关键尾部币因管线差异导致结果不一致：

```text
即使总体一致率 ≥99.8%，也不得直接通过；
必须解释并修复或证明差异来自已冻结、可接受的口径变化。
```

---

## 九、执行顺序

### Step 1｜冒烟

运行：

```text
F3_smoke.sql
```

通过第八节 blocking 项。

### Step 2｜A 周

运行并下载：

```text
F3_devA.sql
```

执行端：

- 构造面板；
- 完成 b50 复原验收；
- 写完所有分析代码；
- 完成 cross-fitting；
- 完成 backward DP；
- 完成 oracle；
- 完成 S1/S2；
- 完成报告模板。

### Step 3｜冻结

在运行 B 周之前：

必须记录以下文件 sha256：

- SQL；
- panel builder；
- 主分析脚本；
- frozen config；
- feature list；
- fold assignment；
- decision-space definition；
- PASS/FAIL 判据；
- S1/S2 primary selection rule。

从此不得修改。

### Step 4｜B 周

用户运行并下载：

```text
F3_devB.sql
```

B 周：

- 只进入已经冻结的管线；
- 不允许据 B 周结果改模型、特征、checkpoint、止损比例、alpha 或判断规则。

### Step 5｜报告

输出：

- P0 正式判定；
- P2 描述；
- decision value map；
- capture ratio；
- tail contribution；
- actions；
- transaction count；
- costs；
- first-entry/re-entry decomposition；
- PASS / FAIL / DQ-8B trigger。

---

## 十、分支

| 结果 | 动作 |
|---|---|
| P0 PASS；P2 不确定 | 触发 **DQ-8B**：先对 05-18～31 做制度审计，再决定是否作为扩展开发数据 |
| P0 PASS；P2 同向且 Δ ≥ +0.03 | A+B 重拟合唯一 frozen primary，另写确认卡；四个封存周只正式验证一次 |
| S1、S2 都 PASS | 按 §6.4 冻结唯一 confirmatory primary |
| 临界：A→B Δ 在 +0.015～+0.03，或三条只满足两条 | 可触发 DQ-8B；封存周继续不碰；扩展后结果不得冒充确认 |
| P0 FAIL，但满足 P2 anomaly | DQ-8B / P2 异质性调查；不得进入封存周 |
| P0 FAIL，且无 P2 anomaly | **STOP 当前 pump +30m 动态决策路线；转 BSC G0** |

---

## 十一、DQ-8B 启动条件

DQ-8B 不自动运行。

只有以下情况允许：

1. P0 PASS，但 P2 样本不足；
2. P0 borderline；
3. P0 FAIL，但触发预注册的 P2 anomaly。

启动前必须先审计 05-18～31：

- 05-21 USDC pair 上线造成的制度断点；
- SOL-pair费用；
- migration机制；
- P0/P2比例；
- 成交活跃度；
- 特征分布；
- launch / graduation regime。

审计不过：

```text
五月不得直接与六月合并。
```

---

## 十二、路线停止与重开条件

若本卡正式判：

```text
STOP
```

停止的具体路线是：

> **使用本卡现有公开链上状态，在 pump.fun 创建后约30分钟开始，通过动态持仓/退出/再入决策改善 b50 的路线。**

不等于证明：

- pump.fun 永远没有 edge；
- 其他入场时点无效；
- 其他数据源无效；
- 其他母体无效。

### 重新打开必须满足

出现本卡中**不存在的新信息源**，例如：

- 高质量实体级钱包归因；
- 新的跨链/资金源信息；
- 可验证的链外注意力先导变量；
- 当前不存在的实时行为标签。

以下都**不构成重开理由**：

- 换模型；
- Ridge → XGBoost；
- 多几个检查点；
- 50%改45%；
- 新增更多阈值；
- 扩大参数搜索；
- 同一批特征重新组合。

---

## 十三、预算

### Dune

硬上限：

```text
220 credits
```

预估：

- 冒烟 ≤12；
- A 周执行约40–60；
- A 周下载约40–55；
- B 周同级。

冒烟后如果按实际行数估算会超过预算：

> **先报告，不自行删列、不降低检查点、不改变冻结特征。**

### 主动工时

```text
≤5小时
```

项目累计工时继续单独记账。

---

## 十四、不能推出

即使本卡 PASS，也不能推出：

- 实盘一定盈利；
- 已计入 MEV；
- 已计入失败交易；
- 当前零规模模拟可直接扩容；
- 其他入场时点有效；
- 其他场所有效；
- P2 已得到独立高功效验证；
- staged sizing 无效；
- 本卡之外的模型或新信息源无效。

即使本卡 FAIL，也只能推出：

> **在本卡冻结的信息集合、动作集合、模型族、检查点和执行口径下，没有得到足以继续投资研究资源的跨期动态决策增益。**

---

## 十五、运行前冻结清单

### Gate 0｜A 周查询前（BLOCKING）

冒烟必须全部满足，否则**不得运行 A 周正式查询**：

- [ ] `bad_k0 = 0`（新开仓通用逻辑在 k=0 与原始仓位逐区间一致：逐笔 trailing、running peak 跨区间延续）；
- [ ] `bad_early = 0`；
- [ ] `bad_state = 0`；
- [ ] `bad_b50_mismatch = 0`（面板重建 b50 含 24h inactivity，与独立路径逐币一致）。

### Gate 1｜A 周完成后、任何正式分析与 B 周之前（BLOCKING）

- [ ] A 周面板 b50 vs `dq7/raw/F2_dev.csv` 币级一致率 ≥99.8%；
- [ ] 平均回收绝对差 ≤0.001；
- [ ] tail mismatch audit 无未解释关键差异。

**Gate 1 通过之前，A 周数据只用于工程调试（面板解析、AMM 重放、复原验收）；不得读取或解释任何策略经济结果，不得据此修改特征、模型或设计。**只有 Gate 1 通过后，才允许用 A 周做正式 backward DP、冻结最终分析脚本并运行 B 周。

### A 周正式查询前必须冻结

- [ ] 检查点；
- [ ] 0 / 0.5 SOL 动作空间；
- [ ] 50% / 70% stop；
- [ ] 24h inactivity；
- [ ] 5秒延迟规则；
- [ ] 16个主特征；
- [ ] Ridge α=10；
- [ ] mint-level 5-fold cross-fitting；
- [ ] P2 anomaly 规则；
- [ ] S1/S2双通过时的唯一 primary 选择规则；
- [ ] opportunity-normalized net value 口径；
- [ ] oracle / capture 定义；
- [ ] PASS / FAIL / borderline 判据；
- [ ] DQ-8B触发条件；
- [ ] STOP 后重开条件。

### B 周运行前必须额外冻结

- [ ] 完整分析脚本；
- [ ] fold assignment；
- [ ] frozen config；
- [ ] 全部 sha256；
- [ ] 报告模板；
- [ ] confirmatory primary selection implementation。

---

**卡片状态：FROZEN（r1）— Gate 0 通过前不得运行 A 周；Gate 1 通过前不得做正式分析或运行 B 周。**
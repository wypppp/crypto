# Pump.fun 毕业代币右尾研究

> **状态（2026-09-22）**：已关闭。下文“保留一次终局检验”已被 08-28 的[终局裁决](../primary_issuance_research/NO_NEW_QUERY_TERMINAL_DECISION_2026-08-28.md)取代（预算关闭，不是负结果）。现况见 [总入口](../../RT/00_总入口.md) §2.2。

> **状态：T+5m 选币、首触发和 LP 方向已于 2026-08-28 按预注册判据关闭。**
>
> 触发 `REGIME_REPLICATION_2026_JANFEB.md` 第 4 节冻结的“结构性失败”判定：首触发主策略在 2026-05–07（3,401 入场，−7.28%，下界 −9.74%）与 2026-01–02（4,915 入场，−9.97%，下界 −11.51%）两个市场状态均为负；首触发 96 格两窗口合格 0/96；LP 主策略与八格同样全负。合计约 8,300 笔可执行入场、192 个首触发组合、18 个 LP 单元，无一正收益候选。
>
> 使用者保留一次、且仅一次终局检验：`PUMP_TERMINAL_EXPERIMENT_2026-08-28.md` 冻结 T+30s/T+60s、保守 entity 特征和真实首触发执行收益。它排在 CCA 与 MetaDAO 观察器部署之后；历史双状态失败或唯一未来确认失败后，整个普通公开数据 Pump 方向永久关闭，不再扩展延迟、退出参数或图特征。
>
> E0 在 MELT 风险标签上的增量只作为风控结论保留。除上述终局实验外，本目录仍是留档与方法资产，不授权重新优化已经关闭的 T+5m/LP 变体。

这套查询用于构造 2026-05-01 至 2026-07-24（UTC）真实迁移到 PumpSwap 的全量代币，并计算毕业后 30 天的存活、价格倍数和毕业时容量。

## 运行

1. 把只读权限的 Dune API key 放入进程环境的 `DUNE_API_KEY`（不要写入源码），然后运行原始 SQL；下载器会核对 Dune 报告的总行数，拒绝把截断结果当全集：

   ```bash
   .venv/bin/python crypto/pump_tail_research/run_dune.py
   ```

2. 在仓库根目录运行本地汇总：

   ```bash
   .venv/bin/python crypto/pump_tail_research/analyze.py \
     crypto/pump_tail_research/data/dune_token_metrics.csv \
     --out-dir crypto/pump_tail_research/output
   ```

输出包括逐币审计表、按周表、JSON 摘要和 Markdown 报告。

### 延迟入场复算

`08_delay_metrics.sql` 冻结 T+5m、T+15m、T+1h、T+4h、T+24h 五个入场点。入场价取截止时最后一个 canonical 池状态；储备状态同时纳入买、卖、加池和撤池事件，未来最高价只由截止后的真实买卖事件产生。

```bash
.venv/bin/python crypto/pump_tail_research/run_dune.py \
  --sql crypto/pump_tail_research/08_delay_metrics.sql \
  --out crypto/pump_tail_research/data/dune_delay_metrics.csv \
  --performance large

.venv/bin/python crypto/pump_tail_research/analyze_delays.py
```

延迟分析会输出峰值/首次触及时间分布、延迟—容量权衡表、固定止盈倍数曲线、逐币审计表和完整 Markdown 报告。`take_profit_curve.png` 的左图按币等权，右图按每个池的 5% 容量加权。

### T+5m 冻结时间前向检验

实验协议见 `T5M_EXPERIMENT.md`，其冻结哈希保存在 `T5M_EXPERIMENT.sha256`。特征 SQL 不含标签，也不读取 T+5m 之后的事件；本地脚本再按 mint 与延迟结局表一一合并。

```bash
.venv/bin/python crypto/pump_tail_research/run_dune.py \
  --sql crypto/pump_tail_research/09_t5m_features.sql \
  --out crypto/pump_tail_research/data/dune_t5m_features.csv \
  --performance large

MPLCONFIGDIR=/tmp/pump-tail-matplotlib \
  .venv/bin/python crypto/pump_tail_research/train_t5m_forward.py
```

三个测试窗口均晚于各自训练和验证窗口。主模型、参数、验证期最高10%阈值和五条通过条件已在特征结果返回前冻结；其他选择率及 Logistic 模型仅作诊断，不能替代主裁决。

### 首触发止盈/止损执行实验

`FIRST_PASSAGE_EXPERIMENT.md` 冻结了 T+5m15s 入场、固定美元仓位、双边池冲击、逐事件动态费率、额外执行损耗以及 TP/SL/超时首触发规则。哈希保存在 `FIRST_PASSAGE_EXPERIMENT.sha256`。

```bash
.venv/bin/python crypto/pump_tail_research/run_dune.py \
  --sql crypto/pump_tail_research/10_first_passage.sql \
  --out crypto/pump_tail_research/data/dune_first_passage.csv \
  --performance large

MPLCONFIGDIR=/tmp/pump-tail-matplotlib \
  .venv/bin/python crypto/pump_tail_research/analyze_first_passage.py
```

该实验不使用未来最高现货价直接结算，而是按每个事件后的池储备计算整仓可退出美元价值，再决定止盈、止损或超时谁先触发。

## 已冻结的口径

- N0 不是“出现过 migrate 指令”的数量，而是 Pump 作为外层程序实际触发、并成功发出 `CreatePoolEvent(index=0)` 的 canonical PumpSwap 池。`CompletePumpAmmMigrationEvent` 到 2026-05-21 才开始有数据，不能用它截断 5 月 1 日起的样本；建池事件本身则完整覆盖区间。
- 毕业价和初始储备直接解码 `create_pool` 参数，避免使用拉升后的池深。
- 只用毕业时创建的 canonical pool 两个 vault 的成交，不混入二级池。
- 价格先按池子的报价币计算，再用 `prices_external.hour` 转成 SOL；成交美元量由报价腿重新计算，不读取 `dex_solana.trades.amount_usd`。
- 第 7 天为 `[T+6d,T+7d)`，第 30 天为 `[T+29d,T+30d)`；目标日无成交时机械持有倍数记为 0，且保留 observed 标记。
- 主结果保留所有代币；另输出排除 Pump 官方 Mayhem 机器人钱包的诊断列，以及单笔报价额至少 0.01 SOL 的最大倍数诊断列。目标区间的 Dune `CreatePoolEvent.is_mayhem_mode` 历史值均未回填，因此报告将模式标记为“未知”，不会把空值伪装成 Standard。
- 5% 容量主口径是 `0.05 × 报价端初始储备`。它对应零费恒定乘积池约 5% 的**平均成交价**劣化；若要求买完后的末端现货价不超过 5%，系数应为 `sqrt(1.05)-1 ≈ 0.024695`，报告同时给出两者。
- 延迟分析的 5% 容量改用相应延迟时点的最后池储备，并按延迟时点所在小时的报价币美元价标记；不会沿用毕业时池深。

## 完整性闸门

在把结果当结论前，至少核对：

- CSV 的 mint 唯一且所有毕业时间均在冻结区间内；脚本会强制检查。
- 初始报价储备美元覆盖率应接近 100%；缺失通常意味着出现了 `prices_external.hour` 不覆盖的新报价币。
- 成交定价覆盖率应接近 100%。不能把缺失外部报价的成交静默当成零成交。
- Standard 与 Mayhem 必须分层检查；Mayhem 有官方自动随机交易，原始交易量和原始最高价不能直接视为用户需求。
- `事后右尾数 × 容量` 只是 oracle 上界。可执行资金必须用入场前信号实际选出的候选数来计算。

`collect_migrations.py` 是公共 RPC 审计/抽查工具，不适合直接爬取 85 天全集：迁移权限地址有大量失败交易和幂等空调用，免费公共 RPC 的历史吞吐也不足。

# 经济基线执行补充 v1 · 2026-09-10

本文件补充冻结交付包 ../baseline_20260909/ 的执行配置§1及当前状态。原v3包不改字节；其余研究设计继续以包内baseline-execution-config.md v2.1为依据。该补充不等于正式经济实验全部冻结。

## §1 已解析边界与完整分母

| 字段 | 本次真实复核 |
|---|---:|
| b_start（首个timestamp >= 2026-01-01T00:00:00Z） | 24136053 |
| b_end（首个timestamp >= 2026-04-01T00:00:00Z 的前一块） | 24781026 |
| allPairsLength(b_start−1) | 476626 |
| allPairsLength(b_end) | 493136 |
| 工厂索引区间，右端不含 | [476626,493136) |
| 全资产新池 N_all | 16510 |
| 恰一侧WETH的候选 N | 16044 |
| 已确认非WETH | 466 |
| 待识别 | 0 |

**16044 + 466 + 0 = 16510。** 全资产台账保存在universe_run/universe.csv，按零基工厂索引升序排列。事件中的序号是追加后的长度，即一基序号476627..493136；不能把它直接当allPairs下标。

本次明确改变枚举实现：复用RT-A的Etherscan PairCreated递归拆分采集（返回满1000条时拆分），由事件逐一重建索引、pair、token0、token1；全部事件与RPC历史工厂计数、序号连续性和边界对账。额外对10个等距分散索引逐一核对allPairs/token0/token1/getPair，40次调用全部一致。**不是对16510个索引逐一调用allPairs，也不是全体代币状态语义验证。** 工厂地址、代码hash及前后时间边界以collection_frozen.json为准。

开始固定finalized快照；四个窗口相邻边界、该finalized块及工厂代码结束时复读一致。原始请求持续写requests.jsonl，源码副本、资源、退出状态均在独立目录；不会覆盖v3历史证据或RT-A数据库。

仅本次分母采集规格已冻结，payload_sha256：`10c3c3810487f4905bc2921cfd9d01f837830dea8d795e3f1a09a1ac35362164`。完整经济实验config_frozen.json尚未产生；不得把collection_frozen.json当作它。没有读取目标代币收益、没有抽取300样本、没有模拟或广播交易。baseline_ready=false。

## 验收与资源
采集退出0，独立离线验收退出0。独立验收不导入采集器，直接从全部保存的HTTP响应重建事件，逐行核对CSV、索引、分类、链上计数与注册表抽查响应。两者一致。峰值采样RSS 145224 KiB（约141.8MiB），768MiB进程限制；总计50.755秒，RPC55次、Etherscan47次。请求次数不是供应商计算单位或账单金额。

7项离线测试覆盖分类/零基索引、缺失占位、相同/冲突重复、非法资产身份，以及成功/缺事件/预算耗尽的完整退出与产物。测试在临时目录，不覆盖真实运行。日志offline-tests.log。

## 下一道条件
1. 不必再为这段窗口重采母体；后续使用此台账hash，保持样本失败不替补和未知不删除。
2. 在候选收益查看前，将钱包/调用上下文、持仓状态适配范围、失败分类、成本情景、抽样与停止规则落实为可执行配置；需要更改原设计时另立版本。
3. 做少量端到端质量检查，明确开发样本的用途与进入正式统计的预设规则，不按成功与否选择或替补；已看收益资料不冒充未来未使用验证集。
4. 上述条件通过后，再按完整配置冻结300样本及分析；当前T1–T7通过和完整N仅关闭能力及分母两项，不替代持仓/成本/质量验收。

75小时前向观察不是此分母或经济基线的前置条件，本轮未启动。

## 实际命令与退出码
工作目录 /home/ancillary。

```bash
python3 -m unittest discover -s rightTail/baseline_work_20260910 -p 'test_*.py' -v
python3 -u rightTail/baseline_work_20260910/collect_universe.py --out rightTail/baseline_work_20260910/universe_run --max-http 400 --max-seconds 900
python3 rightTail/baseline_work_20260910/verify_universe.py --run rightTail/baseline_work_20260910/universe_run
```
三条均退出0。采集输出collection-stdout.log；验收结果universe_run/acceptance.json。历史v3包校验另存package-verification.log。

## 资源估算补充
正式300样本前增加真实候选分阶段调用/耗时计量条件。既有控制路径104次/181.86秒不等于候选预测；机械串行300次约15.2小时，不能承诺8小时完成。主动工时与运行墙钟分别核算。详见 [RESOURCE_SIZING.md](RESOURCE_SIZING.md) 和control_cost_profile.json。

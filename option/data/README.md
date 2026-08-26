# 公开污染源数据产物

本目录承载 `collect_ps_public.py` 生成的公开平台目录快照。`runs/` 中每次运行的原始响应和派生表默认不进入 Git；每次运行包含：

- `raw/`：行政区划、字典、启用企业和启用监测点的逐页原始 JSON；
- `manifest.json`：每个请求的 URL、查询时间、响应头、字节数与 SHA-256；
- `derived/enterprises.csv`、`ports.csv`：只做可复现连接与人工复核；
- `derived/candidate_discovery_hits.csv`：按 `06` 第 5 节检索词产生的发现命中；
- `derived/summary.json`、`SUMMARY.md`：计数与解释边界。

运行：

```bash
python3 option/scripts/collect_ps_public.py catalog
python3 option/scripts/collect_ps_public.py verify option/data/runs/<run-id>
python3 option/scripts/collect_ps_public.py rebuild option/data/runs/<run-id>
python3 option/scripts/collect_ps_public.py snapshot option/data/t026_public_points.csv
python3 option/scripts/collect_ps_public.py snapshot-rebuild option/data/t026/<run-id>
```

数据入口使用 IP 地址且当前需要显式关闭 TLS 证书校验；采集清单会记录这一事实。采集器默认请求间隔 1 秒、遇到 `429/5xx` 退避重试，并且只调用公开网页自身使用的目录接口。`catalog` 不下载监测小时值。

公开平台中的企业名称和 ID 原样保留，以便复核。它们属于 `U-PUB-OBS` 来源审计，不是内部目录。任何检索词命中都不证明产品—核心设备—排口拓扑，也不通过 `G2/G3`。

`u_pub_obs_v1.json` 是该公开来源宇宙的稳定控制记录，指向首个完整目录运行、成员计数、验证状态及限制。它不改变原 Round 0 v2 的 `source_scope_blocked` 状态。

`public_only_v1/` 是 2026-08-25 用户授权的新研究版本。它复用已验证的公开目录和三轮基线，但使用独立的 vintage、候选注册表、5 点选择表及后续 `polls/`；它不会回填原 v2。

`t026_public_points.csv` 是首批 `2-5` 个公开侧发现点。`snapshot` 每次新建不可覆盖目录，保存列定义、同日公开响应、查询时间和哈希。首次轮询的 `Tavailable_public` 必须保持 `unknown_single_poll`；只有连续轮询观察到同一测量窗口首次出现，才能计算公开端首次可见时点。

每轮快照后运行 `python3 option/scripts/summarize_t026_public.py`，生成 `t026_public_visibility.csv` 和 `t026_public_state.csv`。前者只在连续轮询之间出现新的最晚测量窗口时给出延迟上下界；首次轮询已经可见的窗口只有上界，不伪造精确发布时间。

接口会为整日预先返回 24 个时间模板行，未来小时也可能带工况文本。因此“响应含 24 行”不等于 24 个小时均已有监测值；汇总另外报告含数值字段的行数及其最晚测量时点，不用未来模板时间冒充数据可见时间。

## 休眠的内部数据交接骨架

2026-08-25 已确认当前没有独立内部系统。使用者不需要填写下列表格；它们只作为未来来源条件真实变化时的结构占位，不能用公开平台数据重复填充后冒充“双端”或内部证据。

下列空表把 `06` 的第一轮要求变成机器可查的交付格式：

- `t022_metadata_template.csv`：一行一个“监测点—生产设施”关系；
- `t022_capacity_template.csv`：独立的产品/规格/产能分母；
- `t022_field_dictionary_template.csv`：原始字段、单位、口径和缺失语义；
- `t022_status_dictionary_template.csv`：生产、治理、仪器和平台状态代码；
- `t026_crosswalk_template.csv`：历史上预填的 5 个公开点；因不存在内部端，全部保持 `enabled=0`，不再要求补表。

若未来确实获得独立内部来源，不要直接在模板中加入全年小时数值；填好后再运行：

```bash
python3 option/scripts/validate_t022.py metadata <metadata.csv>
python3 option/scripts/validate_t022.py capacity <capacity.csv>
python3 option/scripts/validate_t022.py field_dictionary <field_dictionary.csv>
python3 option/scripts/validate_t022.py status_dictionary <status_dictionary.csv>
```

校验器只做结构、必填值和枚举检查，不证明 ID 稳定、点位映射唯一、产能来源真实或授权合规；这些仍需数据提供方确认。

## Round 0 v2

`universe_v2/` 保存现行 `v2@2026-08-24T17:05:00+08:00` 的共同截止配置、九场所覆盖控制、四张 universe 表和排除日志。当前只是工作表，不是已经冻结的 Round 0；具体剩余缺口以 `universe_v2/venue_coverage_v2.csv` 为准。

每次修改后运行 `python3 option/scripts/validate_universe_v2.py`。该命令通过只代表表结构、共同截止、成员唯一性和场所计数一致；警告项仍是未闭合缺口，不代表获得 `W0/W1`。

`official_snapshots/` 保存交易所官方目录的不可覆盖原始响应、HTTP 头和清单。ICE 快照晚于 v2 共同截止 30 分 14 秒，只可生成发现行，不能单独证明截止时点成员资格；对应导入脚本会强制保留这一阻断。

# S0 单日冒烟的既有对账基准

> 在运行 S0 冒烟前，从 R0 已下载的 `Q_buyers.csv.gz` 计算；不是 S0 的结果。创建事件只有秒级时间戳，`t3_s=0` 表示同一秒，不代表同一 slot。

2026-06-01 创建、在 R0 样本中已有第 3 个合格买家的币共 13 个：

| mint | 既有 `t3_s` |
|---|---:|
| `9RWbXv3hCdmEpkqwb659JCvnVes6XLhvpXB7oYxjpump` | 0 |
| `2r9x15QN6obFdUPGKmv98x99N4PAYKsL7xg8Ug2Spump` | 0 |
| `D826xNm4gC9L97UjnFjpbsZoUXAKdEWXukyfdA4Apump` | 0 |
| `YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump` | 0 |
| `57L67vSKy6fkDNjwncNx6UX1BQnWCsc1a4hcWYyhpump` | 0 |
| `B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump` | 0 |
| `GB2t2Hs2Awo4YAafTL7PzYafQJ75CkPCLCEnWoD8pump` | 0 |
| `DEAVE9fyfQDk3fDLspnEv7y7dTGErezq2FFrp6B2pump` | 0 |
| `ARYoDE9aaS4u7N3xfRysHwSAbY3bVFGHq5eGi3NuyYM6` | 2 |
| `35Ki5P8TWL6VwhCXJ3RZMQb1HKV3xfSfiqjtYBBapump` | 2 |
| `2cgAW8un1eE2xN99PTs4NJyFYXA4pzqUEQTJbiuowgcn` | 3 |
| `E2sHHwpzeVjhV3DjAMP8kYBeG27qT66xS3V9EBYVpump` | 4 |
| `EYEyyarU2mpWCTjEU5j2ezk2QEvCcr6SFMukc7Vjpump` | 135 |

冒烟输出若包含这些币，`t3_s` 必须逐项一致；缺行须先区分“未被 2%/尾部/R0 规则导出”和真正漏算。由于 13 个币都在 R0 名单里，应全部导出。


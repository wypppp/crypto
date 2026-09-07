# 2026-09-07 TRADE_ONLY 证据快照

只补充身份与公告目录证据，不是新版正式研究母表。

- `qualification_evidence.json/csv`：42 条逐项证据与未完成要求。
- `baseline_manifest.json`：固定既有输入字节哈希。
- `identity_sources.json` 与 `source_observations.json`：一手来源链接及检索标题，不是完整网页快照。
- `ace_impact/`：隔离实验；配置仍继承基线版本标签，只能用于影响面，不是正式 v1.8.38。初次测试样本结构错误日志保留。

在原项目工作区运行：

```bash
python3 -B direction/review_2026-09-07/trade_only/build_evidence.py
python3 -B direction/review_2026-09-07/trade_only/run_ace_impact.py --out /tmp/ace_new_replay
```

`--out` 必须是新目录。两个脚本均可用 `--work` 指定同一批冻结上游输入。该快照依赖工作区或历史归档中的输入，不宣称自足复现包；缺输入会报错。本目录 SHA256SUMS 覆盖所有快照文件，除自身。

实测证据表重建逐字节一致，ACE 实验重放配置与母表逐字节一致，v1.8.37 原独立核验包 20/20 哈希仍一致。补证阶段没有新增行情下载，正式 42 条资格未改写。

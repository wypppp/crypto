# v1.8.37 · 独立 T0 核验快照

37 个非留出事件 / 130 个交易对，独立下载复算与原测量完整比较一致。核验配置 v1.8.37，上游测量配置 v1.8.36；两者通过输入哈希显式连接，禁止把原测量产物 config 哈希改为核验配置哈希。

在目录外副本中离线重放完整比较：

```bash
sha256sum --check SHA256SUMS.txt
python3 -B L_14_compare_t0.py
python3 -B L_14_test.py
```

如需再次联网下载，先复制到新目录，运行 `env -u L_CONFIG python3 -B L_13_verify_t0.py`，再运行 L14。L13 首轮下载与重算结果已保存；L14 补齐逐交易对候选成交行、行数、样本集合及依赖哈希的验证。不要只把 L13 的成功信息当作完整验收。

`L_t0_reference.json` 仅为原测量的比较参考，从 upstream/v1.8.36 的证据 tar 提取，未参与 L13 重算。tar 中是原测量摘要，不是完整 ZIP。独立 ZIP 经下载与官方 CHECKSUM 校验后逐笔重算，保留其哈希和每对摘要；本包不声称保存了全部原始 ZIP 或完全离线重放扫描。

根 SHA256SUMS.txt 覆盖本包所有文件，除自身。upstream 下的旧 SHA256SUMS 是历史来源记录，对应完整旧包，不是该子目录的运行清单。原完整 v1.8.36 归档不变。

见核验报告与 L_t0_verify_complete.json。本结果仅覆盖 37 条固定分层样本；另 168 条、NOT、历史覆盖风险及 TRADE_ONLY 42 条未决不由本次结论替代。

"""DQ-21 严格服务判定：样本中全部唯一可归因来源里，哪些在 Dune 的 Solana 交易所地址表中有标签。

python make_q_labels.py → Q_labels.sql（Dune 网页运行，平台单次上限 2 credits）
输入 results/all_inflows.csv.gz（build_r0.py all）。只传地址，不含任何收益信息。
"""
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent

if __name__ == "__main__":
    I = pd.read_csv(H / "results" / "all_inflows.csv.gz")
    addrs = sorted(set(I[I.status == "unique"].source))
    vals = ",\n        ".join(f"('{a}')" for a in addrs)
    sql = f"""/* DQ-21 严格服务判定（过程/R0b_预算与门槛.md §3）。生成：make_q_labels.py。平台单次费用上限：2 credits（请在 Dune 网页设置）。
   {len(addrs)} 个唯一可归因来源地址，查 Solana 交易所地址标签及其加入日期。 */
WITH v AS (
    SELECT address FROM (VALUES
        {vals}
    ) AS t(address)
)
SELECT v.address, c.cex_name, c.distinct_name, c.added_by, c.added_date
FROM v
JOIN cex_solana.addresses c ON c.address = v.address
"""
    (H / "Q_labels.sql").write_text(sql)
    print("addresses", len(addrs), "chars", len(sql))

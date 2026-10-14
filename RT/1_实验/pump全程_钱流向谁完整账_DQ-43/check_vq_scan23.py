#!/usr/bin/env python3
"""VQ 层与 DQ-35 InitBoost 全量扫描（SCAN23，独立实现）逐池核对（10-14，取数附录 v2 §3）。

python check_vq_scan23.py <VQ 结果标签>   例：WM2AGG_VQ_LIST_20260812
只读两边都有的池：先取 VQ 结果里的池（已过保护过滤的抽样币），再从 SCAN23 里只留这些池（先过滤、后比较）。
输出只有计数：两边都有 InitBoost 且 vq 相同、VQ 漏掉而 SCAN23 有、两边都没有、vq 不同。
"""

import sys
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
S35 = H.parents[0] / "pump毕业币_数据留存_DQ-35" / "raw" / "dune"


def main():
    label = sys.argv[1]
    vq = pd.read_csv(H / "raw" / "dune" / ("%s.csv.gz" % label), dtype=str)
    pools = set(vq["pool"])
    parts = []
    for seg in "abc":
        s = pd.read_csv(S35 / ("SCAN23_BOOST_%s.csv.gz" % seg), dtype=str)
        s = s[(s["rec"] == "P") & s["pool"].isin(pools)]
        parts.append(s[["pool", "n_init", "vq_init_min", "vq_init_max"]])
    sc = pd.concat(parts).drop_duplicates("pool").set_index("pool")
    sc.columns = ["n_init_35", "vq_35_min", "vq_35_max"]
    m = vq.set_index("pool").join(sc, how="left")
    ours = m["n_init"].astype(int) > 0
    theirs = m["n_init_35"].fillna("0").astype(int) > 0
    same = ours & theirs & (m["vq_min"] == m["vq_35_min"])
    print("池", len(m))
    print("两边都有 InitBoost 且 vq 相同", int(same.sum()))
    print("两边都有但 vq 不同", int((ours & theirs).sum() - same.sum()))
    print("VQ 层没有、SCAN23 有", int((~ours & theirs).sum()))
    print("VQ 层有、SCAN23 没有", int((ours & ~theirs).sum()))
    print("两边都没有", int((~ours & ~theirs).sum()))


if __name__ == "__main__":
    main()

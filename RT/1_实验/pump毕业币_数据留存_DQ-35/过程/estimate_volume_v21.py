#!/usr/bin/env python3
"""DQ-35 v2.1 重取的体量与费用外推（10-04）：用 2026-09-23 全天探针（runs/VOL21*_status.json，只执行不下载）
与 v1 各片实测费用、行数（runs/dune_ledger.csv、raw/dune/GRAD_*_status.json）外推全量。

python 过程/estimate_volume_v21.py  → 打印并写 runs/VOL21_估算.md

外推方法（按上沿报，总控第十八轮第三节）：
- 活跃度权重用 v1 各片的**行数**（≈ 桶数，随成交活跃度变化），不用 v1 费用：v1 费用含每条查询的固定开销，
  且同一 SQL 两次运行能差 5 倍，作权重会把体量抬高（初版这样算，B 层外推 671，已弃用）。
  某片权重＝v1 该片每日行数 ÷ v1 2026-09b 每日行数；2026-10a（4 天）v1 没有，权重按 1 计。
- B、PRE B：每片费用＝探针日费用 × 片长 × 权重。
- P：费用主要来自扫描的事件天数（片长＋8 天，探针日为 1＋8＝9 天），每片＝探针费用 × (片长＋8)／9 × 权重。
- L、M、PRE M：与体量关系小，每片按探针费用计（39 片）。
- 上沿：同一 SQL 两次运行的费用比，本轮实测最大约 5 倍（P 层 2.70 对 14.20，费用随执行耗时、即集群负载变化），
  “×2”是情景上沿（不是统计上界，10-05 更正措辞），另报“×5”的极端情景。
"""

import csv
import glob
import json
import re

from pathlib import Path

H = Path(__file__).resolve().parent.parent


def v1():
    cost = {"GRAD": {}, "GRADPRE": {}}
    with open(H / "runs" / "dune_ledger.csv") as f:
        for r in csv.DictReader(f):
            m = re.match(r"sql/(GRAD|GRADPRE)_(\d{6}[ab])\.sql", r["sql_file"])
            if m and r["state"] == "QUERY_STATE_COMPLETED":
                cost[m.group(1)][m.group(2)] = float(r["credits"])
    rows = {"GRAD": {}, "GRADPRE": {}}
    for fam in rows:
        for p in glob.glob(str(H / "raw" / "dune" / ("%s_2*_status.json" % fam))):
            ym = re.search(r"_(\d{6}[ab])_status", p).group(1)
            m = json.load(open(p))["result_metadata"]
            rows[fam][ym] = (m["total_row_count"], m.get("result_set_bytes", 0))
    return cost, rows


def probe(label):
    p = H / "runs" / ("%s_status.json" % label)
    if not p.exists():
        return None
    st = json.loads(p.read_text())
    m = st.get("result_metadata") or {}
    return dict(
        cost=float(st.get("execution_cost_credits") or 0),
        rows=m.get("total_row_count"),
        bytes=m.get("result_set_bytes"),
        secs=(m.get("execution_time_millis") or 0) / 1000,
    )


def weights(rows, fam):
    """每片活跃度权重（相对 v1 2026-09b 的每日行数）与片长；含 v1 没有的 2026-10a。"""
    import sys

    sys.path.insert(0, str(H))
    from run_all_v21 import halves

    base = rows[fam]["202609b"][0] / 15
    out = []
    for ym, s0, e0 in halves():
        days = (e0 - s0).days + 1
        if ym in rows[fam]:
            # v1 的片是 03-16 起；202503a（03-15 一天）与 202503b 合用 v1 的 202503b
            w = rows[fam][ym][0] / days / base
        elif ym == "202503a":
            w = rows[fam]["202503b"][0] / 16 / base
        else:
            w = 1.0
        out.append((ym, days, w))
    return out


def main():
    cost, rows = v1()
    lines = ["# DQ-35 v2.1 重取体量与费用外推（探针日 2026-09-23）", ""]
    lines.append(
        "| 层 | 探针日费用 | 探针日行数 | 探针日结果字节 | 外推全量费用（点） | 情景上沿（×2，非统计上界） | 极端情景（×5） | 外推行数 | 外推结果 GB |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    tot = 0.0
    for fam, layers, v1fam in (
        ("GRAD", ("B", "P", "L", "M"), "GRAD"),
        ("PRE", ("B", "M"), "GRADPRE"),
    ):
        ws = weights(rows, v1fam)
        for layer in layers:
            lab = (
                "VOL21_%s_20260923" if fam == "GRAD" else "VOL21PRE_%s_20260923"
            ) % layer
            pr = probe(lab)
            if pr is None:
                lines.append("| %s %s | 未跑 | | | | | | | |" % (fam, layer))
                continue
            n, b = pr["rows"] or 0, pr["bytes"] or 0
            if layer == "B":
                f = sum(d * w for _, d, w in ws)
                est, est_rows, est_gb = pr["cost"] * f, n * f, b * f / 1e9
            elif layer == "P":
                f = sum((d + 8) / 9 * w for _, d, w in ws)
                g = sum(d * w for _, d, w in ws)
                est, est_rows, est_gb = pr["cost"] * f, n * g, b * g / 1e9
            elif layer == "L":
                # 10-05 更正（GPT 批 1a-i）：L 层是逐笔，行数与字节随事件天数放大；费用每片按探针计
                f = sum(d * w for _, d, w in ws)
                est, est_rows, est_gb = pr["cost"] * len(ws), n * f, b * f / 1e9
            else:
                est, est_rows, est_gb = pr["cost"] * len(ws), len(ws), 0.0
            tot += est
            lines.append(
                "| %s %s | %.2f（%.0f 秒） | %s | %s | %.0f | %.0f | %.0f | %.2e | %.2f |"
                % (
                    fam,
                    layer,
                    pr["cost"],
                    pr["secs"],
                    n,
                    b,
                    est,
                    est * 2,
                    est * 5,
                    est_rows,
                    est_gb,
                )
            )
    lines += [
        "",
        "合计（点）%.0f credits；情景上沿（×2，非统计上界）%.0f；极端情景（×5）%.0f。"
        % (tot, tot * 2, tot * 5),
        "",
        "权重：v1 GRAD 2026-09b 每日 %.0f 行，全期 %d 行；v1 GRADPRE 2026-09b 每日 %.0f 行，全期 %d 行。"
        % (
            rows["GRAD"]["202609b"][0] / 15,
            sum(v[0] for v in rows["GRAD"].values()),
            rows["GRADPRE"]["202609b"][0] / 15,
            sum(v[0] for v in rows["GRADPRE"].values()),
        ),
    ]
    out = H / "runs" / "VOL21_估算.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""F132 受影响币的核对（10-06；总控第二十轮第二节）：老池在扫描期内没有 InitBoost（runs/SCAN23_BOOST_report.md），
但 07-15 之前创建的币可能在升级之后才毕业、建的是新池（vq 非零）。本脚本把各实验的币与扫描到的新池（base_mint）求交，
新池建立时刻早于该实验成交止日的币，记为“可能受影响、待逐笔重算”；其余记“已核，不受 F132 影响”。

python 过程/boostscan_affected.py a b c  → runs/SCAN23_BOOST_affected.md
止日取事实库 2026-10-05 补注记的各实验全局止日（保守：不按币逐个定窗口）。DQ-18 估值最晚约到 09-11（信号止于 03-15＋180 天）。
"""

import csv
import datetime as dt
import glob
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

H = Path(__file__).resolve().parent.parent
X = H.parent
E = dt.datetime(1970, 1, 1)
T_UP0 = (dt.datetime(2026, 7, 15, 18, 7, 19) - E).total_seconds()


def ep(y, m, d):
    return (dt.datetime(y, m, d) - E).total_seconds()


def csv_mints(*paths):
    out = set()
    for p in paths:
        op = gzip.open if p.endswith(".gz") else open
        with op(X / p, "rt", newline="") as f:
            out |= {r["mint"] for r in csv.DictReader(f)}
    return out


def dq18_mints():
    out = set()
    for p in glob.glob(str(X / "pump币_晚期龙头基础比率_DQ-18/raw/d/D_*.json")):
        if not p.endswith("_status.json"):
            with open(p) as f:
                out |= {r["mint"] for r in json.load(f)["rows"]}
    return out


EXPS = [
    (
        "DQ-1M（F55～F64）",
        lambda: csv_mints(
            "pump曲线_右尾测量_DQ-1M/raw/M1_full.csv",
            "pump曲线_右尾测量_DQ-1M/raw/M2_full.csv",
        ),
        ep(2026, 8, 8),
        "成交到 08-06／08-07",
    ),
    (
        "DQ-1F（F68～F70）",
        lambda: csv_mints(
            "pump曲线_入场筛选与动态退出_DQ-1F/raw/F1_dev.csv",
            "pump曲线_入场筛选与动态退出_DQ-1F/raw/F1_val.csv",
        ),
        ep(2026, 8, 15),
        "成交到 08-07／08-14",
    ),
    (
        "DQ-8A（F82、F84、F87）",
        lambda: csv_mints(
            "pump曲线_检查点动态决策_DQ-8A/raw/F3_devA.csv",
            "pump曲线_检查点动态决策_DQ-8A/raw/F3_devB.csv",
        ),
        ep(2026, 7, 16),
        "B 周成交止于 07-15",
    ),
    (
        "DQ-21 S1（F117、F120、F121）",
        lambda: csv_mints(
            "pump曲线_资金关系可构造性_DQ-21/raw/s1/S1_A_dual.csv.gz",
            "pump曲线_资金关系可构造性_DQ-21/raw/s1/S1_B_dual.csv.gz",
        ),
        ep(2026, 7, 16),
        "止于 07-15",
    ),
    ("DQ-18（F109～F111）", dq18_mints, ep(2026, 9, 12), "估值最晚约 09-11"),
]


def main():
    new = defaultdict(list)
    for tag in sys.argv[1:]:
        p = H / "raw" / "dune" / ("SCAN23_BOOST_%s.csv.gz" % tag)
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                if (
                    r["rec"] == "P"
                    and r["pool_created_t"]
                    and float(r["pool_created_t"]) >= T_UP0
                ):
                    t = (float(r["pool_created_t"]), r["pool"], r["creator_prog"])
                    if (
                        t not in new[r["base_mint"]]
                    ):  # 同一个池跨段出现（后一段只有 BoostBuyAndBurn）只记一次
                        new[r["base_mint"]].append(t)
    L = ["# F132 受影响币的核对（10-06；总控第二十轮第二节）", ""]
    L.append(
        "- 新池：扫描段 %s 里升级后建、有 InitBoost 的池 %d 个（base_mint %d 个）。老池的 InitBoost 为 0，见 `SCAN23_BOOST_report.md`。"
        % ("、".join(sys.argv[1:]), sum(map(len, new.values())), len(new))
    )
    L.append(
        "- 判定：币在升级后有了新池、且新池早于实验止日 → 可能受影响（待逐笔重算）；否则 → 已核，不受 F132 影响。止日按实验全局止日，偏保守。"
    )
    L.append("")
    L.append("| 实验 | 止日 | 币数 | 升级后有新池 | 新池早于止日（可能受影响） |")
    L.append("|---|---|---|---|---|")
    detail = []
    for lab, f, end, note in EXPS:
        ms = f()
        hit = [m for m in ms if m in new]
        aff = sorted(
            (min(t for t, _, _ in new[m]), m)
            for m in hit
            if min(t for t, _, _ in new[m]) < end
        )
        L.append(
            "| %s | %s | %d | %d | %d |" % (lab, note, len(ms), len(hit), len(aff))
        )
        for t, m in aff:
            pool = min(new[m])[1]
            detail.append(
                "| %s | `%s` | `%s` | %s |"
                % (
                    lab.split("（")[0],
                    m,
                    pool,
                    (E + dt.timedelta(seconds=t)).strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
    L.append("")
    L.append("## 可能受影响的币")
    L.append("")
    L.append("| 实验 | 币 | 新池 | 新池建立（UTC） |")
    L.append("|---|---|---|---|")
    L += detail
    out = H / "runs" / "SCAN23_BOOST_affected.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L[:12]))
    print("明细 %d 行" % len(detail))


if __name__ == "__main__":
    main()

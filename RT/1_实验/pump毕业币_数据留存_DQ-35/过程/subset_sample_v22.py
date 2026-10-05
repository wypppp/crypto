#!/usr/bin/env python3
"""DQ-35 v2.2 样本入库（10-05；GPT 批 1a-i 第 5 条“补入已有的非空 L 与储备异常样本”）。

python 过程/subset_sample_v22.py <逐笔原始标签> <上限事件数> <SQL 结果标签...>
- 入口经 dev_gate：先读 'C'／'X' 行定开发池，数值行解析时丢弃非开发池。
- 先强制纳入：有加撤池（D／W）且单池事件数不超过上限的开发池、全部有储备异常的开发池（相邻成交之间、中间没有加撤池与 boost，
  后一笔的成交前储备不等于前一笔的成交后储备）、有 boost（'R' 行的 I／U）的开发池里事件最少的 2 个；
  再按池地址字典序补到上限事件数。'X' 行原样保留。
- 各 SQL 结果按同一批池过滤（M 层单行原样），文件名加 _sub，放 samples/。
"""

import csv
import gzip
import sys
from collections import defaultdict
from pathlib import Path

H = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(H))
import dev_gate as g  # noqa: E402
from compare_sample_v21 import post_state  # noqa: E402

OUT = H / "samples"


def write(label, cols, rs):
    with gzip.open(OUT / ("%s_sub.csv.gz" % label), "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rs)


def header(label):
    with gzip.open(g.RAW / ("%s.csv.gz" % label), "rt", newline="") as f:
        return next(csv.reader(f))


def anomalies(rows, kind_col, id_col):
    """毕业后逐笔：无事件解释的储备断点所在的池。"""
    if kind_col != "ev":
        return set()
    by, other = defaultdict(list), defaultdict(list)
    for r in rows:
        k = (
            (
                int(float(r["slot"])),
                int(float(r["txi"])),
                int(float(r["oix"])),
                int(float(r["iix"])) if r["iix"] else -1,
            )
            if r["slot"]
            else None
        )
        if r["ev"] in ("B", "S"):
            q_amt, q_lp, lp = (
                int(r["q_amt"]),
                int(r["q_amt_lp"] or 0),
                int(r["f_lp"] or 0),
            )
            qp = q_lp if r["ev"] == "B" else q_amt - lp
            q0, b0 = int(r["q0"]), int(r["b0"])
            by[r[id_col]].append(
                (k, q0, b0, *post_state(r["ev"], q0, b0, qp, int(r["b_amt"])))
            )
        elif r["ev"] in ("D", "W") or (r["ev"] == "R" and r["usr"] in ("I", "U")):
            other[r[id_col]].append(
                k
            )  # 只有加撤池与 boost 算“中间事件”；买卖的原始字节行不算
    import bisect

    bad = set()
    for p, es in by.items():
        es.sort()
        ks = sorted(other.get(p, []))
        for a, b in zip(es, es[1:]):
            i = bisect.bisect_right(ks, a[0])
            if i < len(ks) and ks[i] < b[0]:
                continue
            if (b[1], b[2]) != (a[3], a[4]):
                bad.add(p)
    return bad


def main():
    rawlab, cap, labs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    cols = header(rawlab)
    kind_col = "ev" if "ev" in cols else "kind"
    id_col = "pool" if "pool" in cols else "mint"
    cre = "q_user" if kind_col == "ev" else "qa"
    c_all, x_rows = g.read_meta(rawlab, kind_col, id_col)
    keep, _ = g.dev_ids_from_meta(c_all, id_col, cre)
    rows, _ = g.stream(rawlab, id_col, keep, time_col="ts")
    n_ev = defaultdict(int)
    for r in rows:
        if r[kind_col] not in ("C", "X"):
            n_ev[r[id_col]] += 1
    # 有加撤池的池：单池事件数不超过上限才强制纳入（07-14 组那个池一天 20 万笔；非空加撤池已由跨片组覆盖）
    force = set(r[id_col] for r in rows if r[kind_col] in ("D", "W"))
    force = set(p for p in force if n_ev[p] <= cap)
    force |= anomalies(rows, kind_col, id_col)
    # boost 很常见（09-23 组每个有 vq 的池都有 InitBoost）：只取事件最少的 2 个，够独立复核 boost 的处理
    boosted = set(
        r[id_col] for r in rows if r[kind_col] == "R" and r["usr"] in ("I", "U")
    )
    force |= set(sorted(boosted - force, key=lambda p: (n_ev[p], p))[:2])
    sel, tot = set(force), sum(n_ev[p] for p in force)
    for p in sorted(keep - force):
        if sel and tot + n_ev[p] > cap:
            continue
        sel.add(p)
        tot += n_ev[p]
    write(rawlab, cols, x_rows + [r for r in rows if r[id_col] in sel])
    for lab in labs:
        c2 = header(lab)
        if id_col not in c2:  # M 层：单行计数
            with gzip.open(g.RAW / ("%s.csv.gz" % lab), "rt", newline="") as f:
                write(lab, c2, list(csv.DictReader(f)))
            continue
        write(lab, c2, g.stream(lab, id_col, sel)[0])
    print(
        "%s：强制纳入 %d 个（加撤池／boost／储备异常），共纳入 %d 个开发池、事件 %d"
        % (rawlab, len(force), len(sel), tot)
    )


if __name__ == "__main__":
    main()

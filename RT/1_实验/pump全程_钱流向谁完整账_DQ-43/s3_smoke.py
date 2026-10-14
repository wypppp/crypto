#!/usr/bin/env python3
"""S3 试跑的准备与核对（10-14，总控第七轮第三节第 2 步）。本脚本不访问 Dune，只读本机文件、写 SQL 与批准记录。

试跑范围：W＝08-11 创建的币，截点 08-12 00:00，W+1＝08-12 创建的币，数据止点 08-13 00:00；抽样 0.2%（全量是三对 × 两周 × 10%）。
08-11、08-12 都在开发周 08-10 内（第三对的 W）。

python s3_smoke.py prep   读 EDGE 下载（A7-03）→ 并查集 → 生成 S3 统计量与明细两条 SQL → 追加批准 A7-04～06（总控第七轮）→ 打印命令
python s3_smoke.py check  读两次统计量与一次明细 → 双跑一致、SQL 与参照逐项相等、入选确定、与冻结 a_riskset 对照 → runs/s3_smoke_check.json
只输出“是否相等”与结构计数，不输出得分、T 或任何按实体的结果（冻结卡 v4 §5 冒烟的输出边界）。
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys

import pandas as pd

import paid_guard as PG
import s3_ref as R
import s3_sql as S

H = PG.H
D = dt.date
W0, CUT, W1E, CAP = D(2026, 8, 11), D(2026, 8, 12), D(2026, 8, 13), D(2026, 8, 13)
P = 0.002
EDGE = "S3P_EDGE_SGT_0811_p002"
STATS, DETAIL = "S3P_STATS_0811_p002", "S3P_DETAIL_0811_p002"
CEX = H.parent / "pump曲线_资金关系可构造性_DQ-21" / "raw" / "dune" / "Q_cex_all.csv.gz"
SRC = "总控第七轮（RT/3_审计/2026-10-13_WM2取数_冒烟与SQL审阅/review原文_总控第七轮.md 第五节；用户 10-14 转发）"


def raw(label):
    return pd.read_csv(
        H / "raw" / "dune" / ("%s.csv.gz" % label), dtype=str, keep_default_na=False
    ).to_dict("records")


def prep():
    edges = raw(EDGE)
    cex = set(pd.read_csv(CEX).address)
    emap, n = R.entities(edges, cex)
    (H / "runs" / "s3_smoke_emap.json").write_text(
        json.dumps({"counts": n, "emap": emap}, ensure_ascii=False, indent=1)
    )
    files = {}
    for label, detail in ((STATS, False), (DETAIL, True)):
        sql = S.build_s3(
            W0, CUT, W1E, P, S.emap_values(emap), detail=detail, obs_cap=CAP
        )
        f = "sql/%s.sql" % label
        (H / f).write_text(sql)
        files[label] = f
    have = {r["编号"] for r in PG._rows(PG.APPROVALS)}
    new = [
        (
            "A7-04",
            files[STATS],
            "S3 统计量试跑第一次（0.2%、两天；实体映射来自 A7-03）",
        ),
        ("A7-05", files[STATS], "同上第二次（双跑核一致）"),
        ("A7-06", files[DETAIL], "S3 同一范围的逐笔明细：本机参照逐项核对"),
    ]
    with open(PG.APPROVALS, "a", newline="") as fh:
        w = csv.writer(fh)
        for k, f, note in new:
            if k not in have:
                w.writerow(
                    [k, "2026-10-14", SRC, f, PG.sha(H / f), "10", "2", note, "15"]
                )
    print(json.dumps(n, ensure_ascii=False))
    for k, label, run in (
        ("A7-04", STATS, "r1"),
        ("A7-05", STATS, "r2"),
        ("A7-06", DETAIL, ""),
    ):
        tag = "%s_%s" % (label, run) if run else label
        print("python run_dune.py %s %s --approve=%s" % (tag, files[label], k))


def check():
    emap = json.loads((H / "runs" / "s3_smoke_emap.json").read_text())["emap"]
    r1, r2 = raw(STATS + "_r1"), raw(STATS + "_r2")
    key = lambda rows: sorted(tuple(r[c] for c in S.OUT_COLS) for r in rows)  # noqa: E731
    sql = R.parse_out(r1)
    ref = R.reference(raw(DETAIL), emap, W0, CUT, W1E, CAP)
    fc = R.frozen_check(ref)
    out = {
        "double_run_identical": key(r1) == key(r2),
        "diff_sql_vs_reference": [list(map(str, d)) for d in R.compare(sql, ref)],
        "selection_certain": R.certain(sql["C"], sql["N"]["k_sel"]) == [],
        "frozen_select_set_same": fc["select_set_same"],
        # 冒烟只出结构核对（冻结卡 v4 §5）：T 只报两种算法是否相等，不报数值
        "T_from_G_equals_frozen": abs(float(R.t_stat(sql["G"])) - fc["T_frozen"])
        < 1e-9,
        "N_structure": {
            k: v
            for k, v in sql["N"].items()
            if k.startswith(
                (
                    "n_coins",
                    "n_rows",
                    "n_ent",
                    "n_el",
                    "k_sel",
                    "chk_",
                    "n_amm",
                    "n_mapped",
                    "n_events",
                )
            )
        },
        "n_C": len(sql["C"]),
        "n_G": len(sql["G"]),
    }
    (H / "runs" / "s3_smoke_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"prep": prep, "check": check}[sys.argv[1]]()

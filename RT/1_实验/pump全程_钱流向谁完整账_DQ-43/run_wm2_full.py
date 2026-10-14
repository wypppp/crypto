#!/usr/bin/env python3
"""WM2 全量取数驱动（10-14，取数附录 v2 §3、§4、§6；总控第五轮第六节：WM2 第一，每一步报实耗）。

python run_wm2_full.py --dry            → 列出全部任务与预计 credits，不执行
python run_wm2_full.py --gen            → 只生成全部 SQL（sql/<标签>.sql），供先入库
python run_wm2_full.py [--only=COIN,VQ] → 按顺序执行；已取回的（raw/dune/<标签>.csv.gz 存在）跳过

每条任务：SQL 必须已入库（git 跟踪且与生成器当前输出一致）→ run_dune.py（预算闸门、超时取消、台账）→ 下载。
闸门不放行（额度或硬停）时整个驱动停下，先报用户。抽样率 p＝10%（冻结卡 v4 §5）。
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import build_wm2_sql as B

H = Path(__file__).resolve().parent
D = dt.date
P = 0.10
PAIRS = [
    (D(2026, 5, 25), D(2026, 6, 1)),
    (D(2026, 7, 27), D(2026, 8, 3)),
    (D(2026, 8, 10), D(2026, 8, 17)),
]
# 每层每个创建周的分片数（单条导出预计 ≤ 约 80 credits；10-14 冒烟实测后定，见取数附录 v2 §6）
PARTS = {"CYCC": 4, "CYCA": 4}
EST = {
    "COIN": 15,
    "VQ": 10,
    "CYCCP": 10,
    "CYCAP": 10,
    "CYCC": 90,
    "CYCA": 90,
    "EDGE": 90,
    "COSTF": 90,
}


def week_range(w):
    c1 = w + dt.timedelta(days=6)
    return w, c1, w, min(c1 + dt.timedelta(days=B.HORIZON_DAYS), B.LAST_EVENT_DAY)


def jobs():
    """（层, 标签, build 的参数, build 的关键字参数）。顺序：母体与小表 → 周期 → 实体边 → 交易成本。"""
    out = []
    for w, w1 in PAIRS:
        for wk, is_w in ((w, True), (w1, False)):
            c0, c1, e0, e1 = week_range(wk)
            tag = wk.strftime("%m%d")
            out.append(("COIN", "WM2F_COIN_%s" % tag, (c0, c1, e0, e1), {}))
            if e1 >= B.VQ_FROM:
                out.append(("VQ", "WM2F_VQ_%s" % tag, (c0, c1, e0, e1), {}))
            for lay in ("CYCCP", "CYCAP"):
                out.append((lay, "WM2F_%s_%s" % (lay, tag), (c0, c1, e0, e1), {}))
            for lay in ("CYCC", "CYCA"):
                n = PARTS[lay]
                for i in range(n):
                    out.append(
                        (
                            lay,
                            "WM2F_%s_%s_p%dof%d" % (lay, tag, i, n),
                            (c0, c1, e0, e1),
                            {"part": (i, n), "with_pre": is_w},
                        )
                    )
    for w, w1 in PAIRS:
        c0, c1, e0, e1 = week_range(w)
        tag = w.strftime("%m%d")
        out.append(
            (
                "EDGE",
                "WM2F_EDGE_PRE_%s" % tag,
                (c0, c1, e0, e1, False, w - dt.timedelta(days=7), w1),
                {},
            )
        )
        out.append(("EDGE", "WM2F_EDGE_ALL_%s" % tag, (c0, c1, e0, e1), {}))
        c0, c1, e0, e1 = week_range(w1)
        out.append(
            ("EDGE", "WM2F_EDGE_ALL_%s" % w1.strftime("%m%d"), (c0, c1, e0, e1), {})
        )
    # 交易成本：一天一条；创建范围＝该组窗口周里不晚于当天的部分（组一 05-25～06-07，组二 07-27～08-23）
    for g0, g1 in ((D(2026, 5, 25), D(2026, 6, 7)), (D(2026, 7, 27), D(2026, 8, 23))):
        day = g0
        last = min(g1 + dt.timedelta(days=B.HORIZON_DAYS), B.LAST_EVENT_DAY)
        while day <= last:
            c1 = min(g1, day)
            out.append(
                (
                    "COSTF",
                    "WM2F_COSTF_%s" % day.strftime("%m%d"),
                    (g0, c1, day, day),
                    {},
                )
            )
            day += dt.timedelta(days=1)
    return out


def main():
    a = sys.argv[1:]
    dry = "--dry" in a
    gen = "--gen" in a
    only = next(
        (x.split("=")[1].split(",") for x in a if x.startswith("--only=")), None
    )
    js = [j for j in jobs() if only is None or j[0] in only]
    total = 0
    for lay, label, args, kw in js:
        done = (H / "raw" / "dune" / ("%s.csv.gz" % label)).exists()
        total += 0 if done else EST[lay]
        if dry:
            print(("已取 " if done else "待取 ") + label, EST[lay])
            continue
        sql = B.build(lay, *args, p=P, **kw)
        f = H / "sql" / ("%s.sql" % label)
        if gen:
            f.write_text(sql)
            continue
        if done:
            continue
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(f)], cwd=H, capture_output=True
        )
        if tracked.returncode != 0 or f.read_text() != sql:
            raise SystemExit("%s 未入库或与生成器不一致，先 --gen 并提交" % f.name)
        r = subprocess.run(
            [
                sys.executable,
                "run_dune.py",
                label,
                "sql/%s.sql" % label,
                "medium",
                "12",
                str(EST[lay]),
            ],
            cwd=H,
        )
        if r.returncode != 0:
            raise SystemExit("任务 %s 没有完成（闸门、超时或失败），驱动停下" % label)
    print("任务 %d 条；待取部分预计约 %d credits" % (len(js), total))


if __name__ == "__main__":
    main()

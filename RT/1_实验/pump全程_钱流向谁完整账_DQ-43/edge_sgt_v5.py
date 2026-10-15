"""第九轮最少 EDGE：整数、完整身份；母体和池采用确定性最小模板。"""

import datetime as dt

import wm2_deterministic as D  # isort: skip -- restore builder path before legacy imports

import edge_sgt_min_download as M

B = D.B


def build(c0, c1, event_end, edge_from, edge_cut, p=None):
    old = M.build(c0, c1, event_end, edge_from, edge_cut, p=p)
    f = B.fields("EDGE_v5", c0, c1, c0, event_end, False, p)
    # 只替换共用母体与池。整数 S/G/T 与压缩谓词原样保留。
    return (
        D.integer_time(
            D.population(f) + D.pools(f) + ",\nkc AS (" + old.split(",\nkc AS (", 1)[1]
        )
        + "\nORDER BY kind,a,b,x\n"
    )


def smoke():
    day = dt.date(2026, 8, 11)
    return build(day, day, day, day, day + dt.timedelta(days=1), p=0.002)

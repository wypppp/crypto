"""第十轮最少 EDGE：整数、完整身份；母体和池采用确定性最小模板。"""

import datetime as dt

import wm2_deterministic_v6 as D  # isort: skip -- restore builder path before legacy imports

import edge_sgt_min_download as M

B = D.B


def build(c0, c1, event_end, edge_from, edge_cut, p=None):
    old = M.build(c0, c1, event_end, edge_from, edge_cut, p=p)
    # 从完整S关系出发，保留非种子对手及其桥接；不只给裁剪后的边补度数。
    assert "FROM s_keep WHERE from_seed AND to_seed" in old
    old = old.replace("FROM s_keep WHERE from_seed AND to_seed", "FROM s_edges")
    f = B.fields("EDGE_v6", c0, c1, c0, event_end, False, p)
    # G仍只删冻结归并器必跳过的行，T仍保留完整关系。
    return (
        D.integer_time(
            D.population(f) + D.pools(f) + ",\nkc AS (" + old.split(",\nkc AS (", 1)[1]
        )
        + "\nORDER BY kind,a,b,x\n"
    )


def smoke():
    day = dt.date(2026, 8, 11)
    return build(day, day, day, day, day + dt.timedelta(days=1), p=0.002)

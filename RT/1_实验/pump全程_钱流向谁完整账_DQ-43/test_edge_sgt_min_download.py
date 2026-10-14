"""压缩不改变服务节点判定或归并：保留 S/T 度数，G 只删已判不可用的。"""

import edge_sgt_min_download as M
import s3_ref as R


def test_high_fanout_g_and_duplicate_t_do_not_change_entity_map():
    edges = [{"kind": "G", "a": "hub", "b": s, "x": 201} for s in ("a", "b")]
    edges += [{"kind": "G", "a": "ok", "b": s, "x": 200} for s in ("c", "d")]
    edges += [{"kind": "T", "a": "x", "b": "y", "x": None}] * 2
    short = M.compact_rows(edges)
    assert len(short) == 3
    assert (
        R.entities(short)[0]
        == R.entities(edges)[0]
        == {"c": "c", "d": "c", "x": "x", "y": "x"}
    )


def test_s_and_t_degree_stay_complete():
    edges = [{"kind": "S", "a": "h", "b": f"u{i}", "x": None} for i in range(201)]
    assert len(M.compact_rows(edges)) == 201
    assert R.entities(M.compact_rows(edges))[0] == R.entities(edges)[0] == {}

"""compare_sample_v22.expected_snapshots 的手算预期值测试（10-05）：快照五字段里 coverage 的六类都要能判出来，
包括样本里没有出现的 gap（无事件的储备变化，如直接转入金库）与撤池在时点前后的情形。"""

import compare_sample_v22 as c

END = c.END_MS  # 2026-10-05 00:00 UTC（毫秒）


def ev(kind, t, q0, b0, q1, b1, key, vq=None):
    return dict(
        kind=kind,
        t=t,
        q0=q0,
        b0=b0,
        q1=q1,
        b1=b1,
        key=(key, 0, 0, 0),
        tx="x%d" % key,
        vq=vq,
    )


def test_coverage_classes_hand():
    created = 1_000_000  # 毫秒
    C = ev("C", created, None, None, 100, 1000, 1)
    B1 = ev("B", created + 1_000, 100, 1000, 110, 910, 2, vq=5)
    W = ev("W", created + 5_000, 110, 910, 55, 455, 3)  # 撤池：事件后储备减半
    S1 = ev("S", created + 20_000, 55, 455, 50, 500, 4, vq=5)
    # T＝建池＋10 秒：之前最后一个是撤池（W），之后第一个是卖出，W 后＝S1 前 → ok；vq 取之前最后一笔带 vq 的成交
    x = c.expected_snapshots([C, B1, W, S1], created, 10, END)
    assert (x["a"]["kind"], x["b"]["kind"], x["cov"], x["vq"]) == ("W", "S", "ok", 5)
    # 无事件的变化：卖出前储备与撤池后不符 → gap
    S_gap = ev("S", created + 20_000, 56, 455, 51, 500, 4)
    assert c.expected_snapshots([C, B1, W, S_gap], created, 10, END)["cov"] == "gap"
    # 时点后再无事件 → no_next
    assert c.expected_snapshots([C, B1], created, 10, END)["cov"] == "no_next"
    # 时点前最后一个是 InitBoost（不给代币储备）→ partial
    IB = ev("I", created + 3_000, None, None, 120, None, 5, vq=17)
    assert c.expected_snapshots([C, B1, IB, S1], created, 10, END)["cov"] == "partial"
    # 时点后第一个是 boost（没有事件前储备）→ unverified
    U = ev("U", created + 15_000, None, None, 110, 910, 6, vq=17)
    x = c.expected_snapshots([C, B1, U], created, 10, END)
    assert x["cov"] == "unverified" and x["nboost"] == 0
    # 时点晚于事件止日 → immature
    assert c.expected_snapshots([C], END - 5_000, 10, END)["cov"] == "immature"


def test_same_second_counts_after_hand():
    # 同一秒（t＝时点）的事件算在时点之后
    created = 0
    C = ev("C", created, None, None, 100, 1000, 1)
    B = ev("B", 10_000, 100, 1000, 110, 910, 2)
    x = c.expected_snapshots([C, B], created, 10, END)
    assert x["a"]["kind"] == "C" and x["b"]["kind"] == "B" and x["cov"] == "ok"


def test_build_events_fails_on_duplicate_source_key():
    import pytest

    import compare_sample_v22 as C

    row = dict(
        ev="D",
        pool="p",
        slot="1",
        txi="2",
        oix="3",
        iix="",
        ts="2025-10-07 00:00:00.000 UTC",
        tx_id="t",
        q0="1",
        b0="1",
        q_amt="1",
        b_amt="1",
    )
    with pytest.raises(C.DuplicateKey):
        C.build_events([row, dict(row, ev="W")], [], {"p": 0})

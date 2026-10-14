"""首笔成熟钱包压缩足以恢复冻结风险集；构造与真实样本分开。"""

import pytest

import a_riskset as A
import s3_first_extract as F
import s3_first_local as L
import s3_ref as R
from test_s3_sql import CAP, CUT, EMAP, W0, W1E, detail, gen, hand, run


@pytest.mark.parametrize("seed", range(12))
def test_compact_sql_equals_full_detail_reference(seed):
    fx, emap = gen(seed)
    con = fx.con()
    raw = detail(con, emap)
    short = run(con, F.build(W0, CUT, W1E, None, obs_cap=CAP))
    assert len(short) <= len(raw)
    got = L.reference(short, emap, W0, CUT, W1E, CAP)
    want = R.reference(raw, emap, W0, CUT, W1E, CAP)
    assert R.compare(got, want) == []
    assert got["sel_exact"] == want["sel_exact"]
    assert got["frozen_check"]["select_set_same"]


def test_maturity_before_first_handles_nonmonotonic_timestamps():
    # 按链上键第一笔尚未成熟，第二笔时间戳较小且成熟。
    # 冻结函数先筛成熟再选首笔；“第一笔不成熟则之后都不成熟”需要额外单调性。
    bs = [
        A.Buy(0, "u", "m", 8300, (1, 0, 0, 0), "x", ("a",), 10000),
        A.Buy(1, "u", "m", 8100, (2, 0, 0, 0), "y", ("a",), 10000),
    ]
    assert [r["bid"] for r in A.collapse(A.label(bs, [], "grad"))] == [1]
    q = F.build(W0, CUT, W1E, None, obs_cap=CAP)
    assert "FROM tw WHERE is_buy AND to_unixtime(ts)+1800 < to_unixtime(obs_end)" in q


def test_detail_compression_preserves_multiwallet_stages_and_w1_isolation():
    con = hand().con()
    raw = detail(con, EMAP)
    short = L.compress_detail(raw, W0, CUT, W1E, CAP)
    want = R.reference(raw, EMAP, W0, CUT, W1E, CAP)
    got = L.reference(short, EMAP, W0, CUT, W1E, CAP)
    assert R.compare(got, want) == []
    w_coins = {
        r["mint"] for r in short if r["kind"] == "K" and int(r["t"]) < R.epoch(CUT)
    }
    only_w = L.reference(
        [r for r in short if r["mint"] in w_coins], EMAP, W0, CUT, W1E, CAP
    )
    assert got["sel_exact"] == only_w["sel_exact"]
    q = F.build(W0, CUT, W1E, None, obs_cap=CAP)
    assert "substr(tx_id" not in q and "tx_id AS tx" in q

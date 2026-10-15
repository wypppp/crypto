"""GPT 01/02 的源输入反例；旧版放行、新版拒绝；参照保持冻结。"""

import pytest

import s3_first_v5 as OLD
import s3_first_v6 as V
import s3_ref as R
import sql_determinism as SD
from test_s3_sql import (
    AB,
    CAP,
    CP,
    CR,
    CUT,
    EMAP,
    TR,
    W0,
    W1E,
    detail,
    gen,
    hand,
    run,
    t11,
)


def rows(fx, module=V):
    return run(fx.con(), module.build(W0, CUT, W1E, None, obs_cap=CAP))


def hidden_cross_phase():
    fx = hand()
    fx.pool("mA", t11(0, 1))
    fx.trade("mA", "x1", t11(4), True)
    curve = fx.t[TR][-1]
    fx.amm_buy("mA", "x1", t11(4))
    for name in (
        "evt_block_slot",
        "evt_tx_index",
        "evt_outer_instruction_index",
        "evt_inner_instruction_index",
    ):
        fx.t[AB][-1][name] = curve[name]
    return fx


def test_01_cross_phase_duplicate_hidden_by_first_compression():
    fx = hidden_cross_phase()
    OLD.validate(rows(fx, OLD))  # GPT反例：旧版看不见曲线第二笔。
    with pytest.raises(ValueError, match="K.q"):
        V.validate(rows(fx))


@pytest.mark.parametrize("field", ["user", "evt_tx_id"])
@pytest.mark.parametrize(
    "missing", [None, "", " \t  ", "\u00a0", "\u2003", "\x85", "\x1c"]
)
def test_01_missing_identity_on_unretained_trade_rejected(field, missing):
    fx = hand()
    fx.trade("mA", "x1", t11(4), True)
    fx.t[TR][-1][field] = missing
    with pytest.raises(ValueError, match="K.q"):
        V.validate(rows(fx))


def test_01_old_blank_unretained_tx_counterexample():
    fx = hand()
    fx.trade("mA", "x1", t11(4), True)
    fx.t[TR][-1]["evt_tx_id"] = ""
    OLD.validate(rows(fx, OLD))


@pytest.mark.parametrize("bad", ["quote", "mint", "duplicate", "outside_mother"])
def test_02_pool_anomaly_before_quote_and_mother_filter_rejects(bad):
    fx = hand()
    fx.pool("mA", t11(0, 1))
    extra = dict(fx.t[CP][-1])
    if bad == "quote":
        extra["quote_mint"] = "zzzz_non_sol"
    elif bad == "mint":
        extra["base_mint"] = "mB"
    elif bad == "outside_mother":
        extra["base_mint"] = "not_in_mother"
    fx.t[CP].append(extra)
    short = rows(fx)
    k = {r["mint"]: r["q"].split(";") for r in short if r["kind"] == "K"}
    assert int(k["mA"][7]) > 0
    if bad == "mint":
        assert int(k["mB"][7]) > 0
    with pytest.raises(ValueError, match="K.q"):
        V.validate(short)
    if bad == "quote":
        OLD.validate(rows(fx, OLD))  # max quote使整个异常池先消失。


def test_creator_whitespace_is_also_missing_identity():
    fx = hand()
    fx.t[CR][0]["creator"] = "  "
    with pytest.raises(ValueError, match="K.q"):
        V.validate(rows(fx))


@pytest.mark.parametrize("seed", range(12))
def test_v6_good_input_equals_complete_frozen_reference(seed):
    fx, emap = gen(seed)
    con = fx.con()
    short = run(con, V.build(W0, CUT, W1E, None, obs_cap=CAP))
    got = V.reference(short, emap, W0, CUT, W1E, CAP)
    assert R.compare(got, R.reference(detail(con, emap), emap, W0, CUT, W1E, CAP)) == []


def test_hand_w1_deletion_keeps_selection_and_static_integer_guard():
    short = rows(hand())
    got = V.reference(short, EMAP, W0, CUT, W1E, CAP)
    w = {r["mint"] for r in short if r["kind"] == "K" and int(r["t"]) < R.epoch(CUT)}
    changed = V.reference([r for r in short if r["mint"] in w], EMAP, W0, CUT, W1E, CAP)
    assert changed["sel_exact"] == got["sel_exact"]
    SD.check(V.build(W0, CUT, W1E, 0.002, obs_cap=CAP))

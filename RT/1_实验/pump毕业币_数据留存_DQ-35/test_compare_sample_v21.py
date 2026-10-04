"""compare_sample_v21.py 核心函数的手算预期值测试。"""

import compare_sample_v21 as c


def test_bucket_boundaries_hand():
    assert c.bucket(0) == ("S", 0)
    assert c.bucket(4_999) == ("S", 0)
    assert c.bucket(299_999) == ("S", 59)
    assert c.bucket(300_000) == ("M", 5)  # 第 5 分钟：[300 s, 360 s)
    assert c.bucket(3_599_999) == ("M", 59)
    assert c.bucket(3_600_000) == ("H", 1)  # 第 1 小时：[1 h, 2 h)
    assert c.bucket(604_799_999) == ("H", 167)
    assert c.bucket(604_800_000) == ("D", 7)


def test_post_state_integer_hand():
    # 买：报价储备 85,414,902,050 lamports，含 LP 费入池 1,002,000,000；代币出池 3,000,000,000,000
    assert c.post_state("B", 85_414_902_050, 10**15, 1_002_000_000, 3 * 10**12) == (
        86_416_902_050,
        10**15 - 3 * 10**12,
    )
    # 卖：报价出池（已扣 LP 费）998,000,000；代币入池 2,000,000
    assert c.post_state("S", 10**11, 10**15, 998_000_000, 2_000_000) == (
        10**11 - 998_000_000,
        10**15 + 2_000_000,
    )
    # 超过 2^53 的整数不丢位
    big = 2**53 + 1
    assert c.post_state("B", big, 10, 2, 1) == (big + 2, 9)


def test_expected_snapshot_hand():
    es = [dict(t=1_000), dict(t=2_000), dict(t=3_000)]
    # 建池 0 毫秒、时点 2 秒：之前最后一笔是 t=1000，之后第一笔是 t=2000（时点当秒的成交算“之后”）
    a, b = c.expected_snapshot(es, 0, 2)
    assert a["t"] == 1_000 and b["t"] == 2_000
    a, b = c.expected_snapshot(es, 0, 10)
    assert a["t"] == 3_000 and b is None


def test_same_rows_order_insensitive():
    r1 = [dict(a="1", b="x"), dict(a="2", b="y")]
    r2 = [dict(a="2", b="y"), dict(a="1", b="x")]
    assert c.same_rows(r1, r2)
    assert not c.same_rows(r1, [dict(a="2", b="y"), dict(a="1", b="z")])


def test_vq_interval_sell_hand():
    # q0=100、b0=1000、卖 10 个代币得 1：floor((100+vq)·10/1010)=1 ⇔ 100+vq ∈ [101, 202) ⇔ vq ∈ [1, 101]
    assert c.vq_interval_sell(100, 1000, 10, 1) == (1, 101)
    # q0=0、b0=90、卖 10 得 5：floor(Q·10/100)=5 ⇔ Q ∈ [50, 59]
    assert c.vq_interval_sell(0, 90, 10, 5) == (50, 59)
    # 真实量级：真值 17,584,505,288 必须落在区间内，且卖出占池 1% 时区间窄于 100 lamports
    q0, b0, vq, b_in = 85 * 10**9, 280 * 10**12, 17_584_505_288, 3 * 10**12
    q_out = (q0 + vq) * b_in // (b0 + b_in)
    lo, hi = c.vq_interval_sell(q0, b0, b_in, q_out)
    assert lo <= vq <= hi and hi - lo < 100


def _row(**kw):
    base = dict(
        kind="H",
        pool="P",
        bkey="10",
        straddle="true",
        n="0",
        n_buy="0",
        n_users="0",
        users_straddle="",
        n_fee_null="0",
        n_vq_obs="0",
        n_px_unknown="0",
        n_ord_overflow="0",
        f_cb_sell="",
        f_bb_sell="",
        vq_lo="",
        vq_hi="",
        px_high="",
        px_low="",
        t_first="0",
        t_last="0",
        q0_open="0",
        b0_open="0",
        side_first="B",
        q1_close="0",
        b1_close="0",
        side_last="B",
        q_pool_last="0",
        b_amt_last="0",
    )
    for f in c.NUM_FIELDS:
        base[f] = "0"
    base.update(kw)
    return base


def test_merge_buckets_hand():
    # 同一小时桶被片界切成两行：前片 3 笔（slot 100…105）、后片 2 笔（slot 200…201）
    r1 = _row(
        n="3",
        n_buy="2",
        users_straddle="u1,u2",
        q_buy_user="30",
        f_lp="3",
        f_cb_sell="",
        vq_lo="10",
        vq_hi="50",
        px_high="2.0",
        px_low="1.0",
        t_first="1000",
        t_last="1500",
        slot_f="100",
        txi_f="1",
        oix_f="0",
        iix_f="0",
        slot_l="105",
        txi_l="2",
        oix_l="1",
        iix_l="3",
        q0_open="111",
        b0_open="222",
        side_first="B",
        q1_close="333",
        b1_close="444",
        side_last="S",
    )
    r2 = _row(
        n="2",
        n_buy="1",
        users_straddle="u2,u3",
        q_buy_user="12",
        f_lp="2",
        f_cb_sell="7",
        vq_lo="20",
        vq_hi="40",
        px_high="1.5",
        px_low="0.5",
        t_first="2000",
        t_last="2600",
        slot_f="200",
        txi_f="0",
        oix_f="0",
        iix_f="0",
        slot_l="201",
        txi_l="5",
        oix_l="2",
        iix_l="1",
        q0_open="555",
        b0_open="666",
        side_first="S",
        q1_close="777",
        b1_close="888",
        side_last="B",
    )
    m = c.merge_buckets([r2, r1])[("H", "P", 10)]
    assert (m["n"], m["n_buy"], m["q_buy_user"], m["f_lp"], m["f_cb_sell"]) == (
        "5",
        "3",
        "42",
        "5",
        "7",
    )
    assert (m["q0_open"], m["side_first"], m["slot_f"]) == (
        "111",
        "B",
        "100",
    )  # 首笔取前片
    assert (m["q1_close"], m["side_last"], m["slot_l"]) == (
        "777",
        "B",
        "201",
    )  # 末笔取后片
    assert (m["vq_lo"], m["vq_hi"]) == ("20", "40")
    assert (m["px_high"], m["px_low"]) == ("2.0", "0.5")
    assert (m["t_first"], m["t_last"]) == ("1000.0", "2600.0")
    assert m["users_straddle"] == "u1,u2,u3" and m["n_users"] == "3"

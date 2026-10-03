"""compare_sample_v2.py 核心函数的手算预期值测试。"""

import pandas as pd

import compare_sample_v2 as c


def test_ord_key_hand():
    # slot 370,000,000、tx 1,234、外层 5、内层 12：
    # 370000000·1e10 = 3.7e18；1234·1e5 = 123,400,000；5·1e3 = 5,000；+12
    assert c.ord_key(370_000_000, 1234, 5, 12) == 3_700_000_000_123_405_012
    # 同一交易不同外层指令：外层大的排后，与内层编号无关
    assert c.ord_key(1, 1, 2, 0) > c.ord_key(1, 1, 1, 999)


def test_amm_post_hand():
    # 买：池子 quote 100 SOL（1e11 lamports）、base 1e15；quote_amount_in_with_lp_fee 1.002e9、base_amount_out 9.9e12
    q1, b1 = c.amm_post("B", 1e11, 1e15, 1e9, 1.002e9, 9.9e12, 2e6)
    assert q1 == 1e11 + 1.002e9 and b1 == 1e15 - 9.9e12
    # 卖：quote_amount_out 1e9、lp_fee 2e6 留在池里 → 池子付出 9.98e8
    q1, b1 = c.amm_post("S", 1e11, 1e15, 1e9, 9.98e8, 1e13, 2e6)
    assert q1 == 1e11 - 9.98e8 and b1 == 1e15 + 1e13
    # 加池、撤池
    assert c.amm_post("D", 10.0, 20.0, 1.0, None, 2.0, 0.0) == (11.0, 22.0)
    assert c.amm_post("W", 10.0, 20.0, 1.0, None, 2.0, 0.0) == (9.0, 18.0)


def test_curve_pre_hand():
    # 买 1 SOL 得 3e7 个代币，成交后 x=31、y=1.0e9 → 成交前 x=30、y=1.03e9
    assert c.curve_pre(True, 31.0, 1.0e9, 1.0, 3e7) == (30.0, 1.03e9)
    # 卖 3e7 个代币得 1 SOL，成交后 x=30、y=1.03e9 → 成交前 x=31、y=1.0e9
    assert c.curve_pre(False, 30.0, 1.03e9, 1.0, 3e7) == (31.0, 1.0e9)


def test_grad_bucket_hand():
    assert c.grad_bucket(0) == ("S", 0.0, 5)
    assert c.grad_bucket(299) == ("S", 59.0, 5)
    assert c.grad_bucket(300) == ("H", 0.0, 3600)  # 第 0 小时只含 300 秒之后
    assert c.grad_bucket(3600) == ("H", 1.0, 3600)
    assert c.grad_bucket(604799) == ("H", 167.0, 3600)
    assert c.grad_bucket(604800) == ("D", 7.0, 86400)


def test_same_rows_order_insensitive():
    a = pd.DataFrame({"k": [1, 2], "v": [0.1, 0.2]})
    b = pd.DataFrame({"k": [2, 1], "v": [0.2, 0.1]})
    assert c.same_rows(a, b, ["k"])[0]
    b2 = pd.DataFrame({"k": [2, 1], "v": [0.2, 0.10000001]})
    assert not c.same_rows(a, b2, ["k"])[0]


def test_close():
    assert c.close([1.0, float("nan")], [1.0 + 1e-12, float("nan")]).all()
    assert not c.close([1.0], [1.001]).any()


def test_exact_ord_catches_float_rounding():
    raw = pd.Series([3716842170007302006, 3716842170007302010])
    # Dune API 的浮点序列化把两者都写成 ...7302000；逐位比较必须判不一致
    rounded = pd.Series(["3716842170007302000", "3716842170007302000"])
    assert not c.exact_ord(raw, rounded).any()
    assert c.exact_ord(raw, raw.astype(str)).all()

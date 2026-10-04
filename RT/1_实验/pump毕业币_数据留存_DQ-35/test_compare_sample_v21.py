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

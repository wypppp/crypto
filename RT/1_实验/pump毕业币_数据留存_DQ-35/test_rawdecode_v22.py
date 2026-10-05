"""rawdecode_v22.parse 的手算预期值测试（10-05）：用 PROBE21b 的真实字节尾段与手工拼的字节。"""

import struct

import rawdecode_v22 as r

# PROBE21b 买入第 1 笔原始 data 的第 410 字节起（ix_name 'buy'，cashback 0，回购 bps 5000、回购费 52，
# vq 17,584,505,288，can_boost 1）：
BUY_TAIL = (
    "03000000"
    "627579"
    "0000000000000000"
    "0000000000000000"
    "8813000000000000"
    "3400000000000000"
    "C8411E1804000000"
    "0000000000000000"
    "01"
)


def test_buy_tail_hand():
    d = r.parse("B", BUY_TAIL)
    assert d["cb"] == 0 and d["bb"] == 52 and d["vq"] == 17_584_505_288


def test_negative_vq_hand():
    # 卖出尾段：cashback_bps 0、cashback 7、回购 bps 0、回购费 9、vq＝−5（i128 小端补码）
    tail = struct.pack("<QQQQ", 0, 7, 0, 9) + (-5).to_bytes(16, "little", signed=True)
    d = r.parse("S", tail.hex())
    assert (d["cb"], d["bb"], d["vq"]) == (7, 9, -5)
    # 超过 2^64 的正值也不丢位
    big = 2**70 + 3
    tail2 = struct.pack("<QQQQ", 0, 0, 0, 0) + big.to_bytes(16, "little", signed=True)
    assert r.parse("S", tail2.hex())["vq"] == big


def test_boost_hand():
    pool = bytes(range(32))
    i_tail = pool + (123).to_bytes(16, "little", signed=True) + struct.pack("<Q", 456)
    d = r.parse("I", i_tail.hex())
    assert (d["vq"], d["q1"], d["b1"], d["pool"]) == (123, 456, None, pool)
    u_tail = (
        pool
        + bytes(32)
        + struct.pack("<QQQ", 1, 2, 3)
        + (-7).to_bytes(16, "little", signed=True)
        + struct.pack("<QQQ", 88, 99, 0)
    )
    d = r.parse("U", u_tail.hex())
    assert (d["vq"], d["q1"], d["b1"]) == (-7, 88, 99)


def test_short_tail_gives_none():
    d = r.parse("S", (bytes(32)).hex())  # 只有费用字段，没有 vq
    assert d["cb"] == 0 and d["vq"] is None

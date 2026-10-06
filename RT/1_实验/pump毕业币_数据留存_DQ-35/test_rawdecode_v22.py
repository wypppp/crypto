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


# ---- 10-06 收口整改：旧布局白名单、溢出边界、u64 无符号
def test_layout_class_hand():
    import rawdecode_v22 as rd

    pre = rd.UPGRADE_END_MS - 1000
    post = rd.UPGRADE_END_MS + 1000
    old_sell = "00" * (
        400 - 368
    )  # 卖出尾段从第 369 字节起：总长 400 → 尾段 32 字节，没有 vq 字段
    assert rd.event_len("S", old_sell) == 400
    assert rd.layout_class("S", old_sell, pre) == "layout0"
    assert rd.layout_class("S", old_sell, post) == "unknown"  # 升级后缺 vq 字段
    odd = "00" * (401 - 368)  # 白名单外的旧长度
    assert rd.layout_class("S", odd, pre) == "unknown"
    new_sell = "00" * (425 - 368)  # 完整新布局
    assert rd.layout_class("S", new_sell, post) == "raw"


def test_hi_word_bounds_and_u64_hand():
    import struct

    import rawdecode_v22 as rd

    # 卖出尾段：cashback_bps(8) cashback(8) buyback_bps(8) buyback_fee(8) vq(16)
    cb = 2**63 + 1  # u64 按无符号读，不能变成负数
    vq_hi_min = struct.pack("<qq", 0, -(2**63))  # 高字 −2^63：越界记溢出
    tail = struct.pack("<QQQQ", 0, cb, 0, 5) + vq_hi_min
    d = rd.parse("S", tail.hex())
    assert d["cb"] == cb and d["bb"] == 5
    assert d["vq"] is None and d["vq_ovf"] == 1
    ok = struct.pack("<QQQQ", 0, 0, 0, 0) + (-17).to_bytes(16, "little", signed=True)
    d2 = rd.parse("S", ok.hex())
    assert d2["vq"] == -17 and d2["vq_ovf"] == 0

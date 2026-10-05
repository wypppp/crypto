"""curve_rawdecode_v1.parse 的手算预期值测试（10-06）：按 IDL 布局逐字段拼出字节，再解码。"""

import struct

import curve_rawdecode_v1 as C

PK = bytes(range(32))  # 0x00..0x1f：base58 首字节为 0 → 以 "1" 开头


def _fixed():
    b = PK  # mint
    b += struct.pack("<QQ", 1_000_000_000, 35_000_000)  # sol_amount 1 SOL，token_amount
    b += b"\x01" + PK  # is_buy、user
    b += struct.pack("<q", 1_760_000_000)  # timestamp
    b += struct.pack(
        "<QQQQ",
        31_000_000_000,
        1_038_000_000_000_000,
        1_000_000_000,
        758_000_000_000_000,
    )
    b += PK + struct.pack("<QQ", 95, 9_500_000)  # fee_recipient、fee_bps、fee
    b += PK + struct.pack("<QQ", 5, 500_000)  # creator、creator_fee_bps、creator_fee
    b += b"\x01" + struct.pack("<QQQq", 0, 0, 0, 0)  # track_volume … last_update_ts
    assert (
        len(b) == 250
    )  # 固定段 250 字节（SQL 里 ix_name 长度在第 267 字节＝16＋250＋1）
    return b


def test_layout_fixed_only_hand():
    o = C.parse(_fixed().hex())
    assert o["sol_amount"] == 1_000_000_000 and o["vsr"] == 31_000_000_000
    assert o["is_buy"] is True and o["fee"] == 9_500_000
    assert o["ix_name"] is None and o["vqr"] is None and o["layout"] == "fixed"


def test_layout_quote_and_holder_hand():
    name = b"buy_v2"  # n = 6
    sh = PK + struct.pack("<H", 10000)  # 1 个持股者，34 字节
    b = _fixed() + struct.pack("<I", 6) + name
    b += b"\x00" + struct.pack(
        "<QQQQ", 0, 0, 25, 2_500_000
    )  # mayhem、cashback_bps、cashback、buyback_bps、buyback_fee
    b += struct.pack("<I", 1) + sh
    b += PK + struct.pack(
        "<QQQ", 1_000_000_000, 30_000_000_000, 1_000_000_000
    )  # quote_mint、quote_amount、vqr、rqr
    o = C.parse(b.hex())
    assert o["ix_name"] == "buy_v2" and o["n_shareholders"] == 1
    assert o["buyback_fee"] == 2_500_000
    assert (
        o["quote_amount"] == 1_000_000_000
        and o["vqr"] == 30_000_000_000
        and o["rqr"] == 1_000_000_000
    )
    assert o["holder_rewards"] is None and o["layout"] == "quote"
    o2 = C.parse((b + struct.pack("<QQ", 50, 5_000_000)).hex())
    assert (
        o2["holder_rewards_bps"] == 50
        and o2["holder_rewards"] == 5_000_000
        and o2["layout"] == "holder"
    )
    # SQL 的偏移（1 起，含 16 字节前缀）：base = 308 + n + 34k = 308 + 6 + 34 = 348；vqr 在 base + 40 = 388
    full = bytes(16) + b
    assert struct.unpack("<Q", full[388 - 1 : 388 - 1 + 8])[0] == 30_000_000_000
    assert struct.unpack("<I", full[267 - 1 : 267 - 1 + 4])[0] == 6

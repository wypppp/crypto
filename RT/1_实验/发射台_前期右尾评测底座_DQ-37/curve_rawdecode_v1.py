#!/usr/bin/env python3
"""DQ-37 曲线阶段 v1：pump 曲线 TradeEvent 原始字节的解码（10-06；批 1a-ii，用于 RAWC 层的样本对照）。

输入是 RAWC 层的 hex_tail（原始数据从第 17 字节起，即去掉 8 字节事件前缀与 8 字节判别符）。布局按官方 IDL（pump.json）：
固定段 250 字节 → ix_name（u32 长度＋内容）→ mayhem(1)、cashback_bps、cashback、buyback_bps、buyback_fee（各 8）
→ shareholders（u32 个数＋每个 34 字节）→ quote_mint(32)、quote_amount、virtual_quote_reserves、real_quote_reserves、
holder_rewards_bps、holder_rewards（各 8）。较早版本的事件在某处结束，之后的字段返回 None（layout0）。
"""

import struct

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
FIXED = [
    ("mint", "pk"),
    ("sol_amount", "u64"),
    ("token_amount", "u64"),
    ("is_buy", "bool"),
    ("user", "pk"),
    ("timestamp", "i64"),
    ("vsr", "u64"),
    ("vtr", "u64"),
    ("rsr", "u64"),
    ("rtr", "u64"),
    ("fee_recipient", "pk"),
    ("fee_bps", "u64"),
    ("fee", "u64"),
    ("creator", "pk"),
    ("creator_fee_bps", "u64"),
    ("creator_fee", "u64"),
    ("track_volume", "bool"),
    ("total_unclaimed", "u64"),
    ("total_claimed", "u64"),
    ("current_sol_volume", "u64"),
    ("last_update_ts", "i64"),
]
TAIL1 = [
    ("mayhem", "bool"),
    ("cashback_bps", "u64"),
    ("cashback", "u64"),
    ("buyback_bps", "u64"),
    ("buyback_fee", "u64"),
]
TAIL2 = [
    ("quote_mint", "pk"),
    ("quote_amount", "u64"),
    ("vqr", "u64"),
    ("rqr", "u64"),
    ("holder_rewards_bps", "u64"),
    ("holder_rewards", "u64"),
]
SIZE = {"pk": 32, "u64": 8, "i64": 8, "bool": 1}


def b58(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def _read(b, off, kind):
    w = SIZE[kind]
    if off + w > len(b):
        return None, off
    x = b[off : off + w]
    if kind == "pk":
        v = b58(x)
    elif kind == "u64":
        v = struct.unpack("<Q", x)[0]
    elif kind == "i64":
        v = struct.unpack("<q", x)[0]
    else:
        v = x[0] != 0
    return v, off + w


def parse(hex_tail):
    """→ dict；缺失的字段为 None。另给 ix_name、n_shareholders 与 layout（最后一个完整读到的段）。"""
    b = bytes.fromhex(hex_tail[2:] if hex_tail.startswith("0x") else hex_tail)
    out, off = {}, 0
    for k, t in FIXED:
        out[k], off = _read(b, off, t)
    out["layout"] = "fixed"
    out["ix_name"] = out["n_shareholders"] = None
    for k, _ in TAIL1 + TAIL2:
        out[k] = None
    if off + 4 > len(b):
        return out
    n = struct.unpack("<I", b[off : off + 4])[0]
    out["ix_name"] = b[off + 4 : off + 4 + n].decode("utf-8", "replace")
    off += 4 + n
    for k, t in TAIL1:
        out[k], off = _read(b, off, t)
    if out["buyback_fee"] is None or off + 4 > len(b):
        return out
    out["layout"] = "tail1"
    k = struct.unpack("<I", b[off : off + 4])[0]
    out["n_shareholders"] = k
    off += 4 + 34 * k
    for name, t in TAIL2:
        out[name], off = _read(b, off, t)
    if out["rqr"] is not None:
        out["layout"] = "quote"
    if out["holder_rewards"] is not None:
        out["layout"] = "holder"
    return out

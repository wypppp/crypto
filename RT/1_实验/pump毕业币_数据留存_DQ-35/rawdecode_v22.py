#!/usr/bin/env python3
"""DQ-35 v2.2：PumpSwap 事件自调用原始字节尾段的 Python 解析（10-05）。供 compare_sample_v22.py 独立核对 SQL 的解码。

输入是 build_sample_raw_v22.py 的 'R' 行：十六进制尾段，买入从第 410 字节、卖出从第 369 字节、boost 两类从第 89 字节起
（1 起算；偏移按官方 IDL main，PROBE21b 逐字段核对）。与 SQL 的解码算术（build_grad_sql_v22.RAW）互不依赖。
"""

import struct


def i128(b):
    """16 字节小端有符号整数。"""
    return int.from_bytes(b, "little", signed=True)


def u64(b):
    return struct.unpack("<Q", b)[0]


def parse(kind, hex_tail):
    """返回 dict：vq（有符号）、以及按类别的 cashback／回购费或 boost 后储备；字节不够时对应字段为 None。"""
    b = bytes.fromhex(hex_tail)
    out = dict(vq=None, cb=None, bb=None, q1=None, b1=None, pool=None)
    if kind == "B":
        n = struct.unpack("<I", b[0:4])[0]
        p = 4 + n  # cashback_bps 起点（相对第 410 字节）
        if len(b) >= p + 32:
            out["cb"] = u64(b[p + 8 : p + 16])
            out["bb"] = u64(b[p + 24 : p + 32])
        if len(b) >= p + 48:
            out["vq"] = i128(b[p + 32 : p + 48])
    elif kind == "S":
        if len(b) >= 32:
            out["cb"] = u64(b[8:16])
            out["bb"] = u64(b[24:32])
        if len(b) >= 48:
            out["vq"] = i128(b[32:48])
    elif kind == "I":
        # pool(32) vq(16) real_quote_reserves_after(8)
        out["pool"] = b[0:32]
        out["vq"] = i128(b[32:48])
        out["q1"] = u64(b[48:56])
    elif kind == "U":
        # pool(32) authority(32) quote_in_requested(8) quote_in_used(8) base_burned(8) vq(16) real_quote_after(8) base_after(8)
        out["pool"] = b[0:32]
        out["vq"] = i128(b[88:104])
        out["q1"] = u64(b[104:112])
        out["b1"] = u64(b[112:120])
    return out

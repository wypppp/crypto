#!/usr/bin/env python3
"""DQ-35 v2.2：PumpSwap 事件自调用原始字节尾段的 Python 解析（10-05）。供 compare_sample_v22.py 独立核对 SQL 的解码。

输入是 build_sample_raw_v22.py 的 'R' 行：十六进制尾段，买入从第 410 字节、卖出从第 369 字节、boost 两类从第 89 字节起
（1 起算；偏移按官方 IDL main，PROBE21b 逐字段核对）。与 SQL 的解码算术（build_grad_sql_v22.RAW）互不依赖。
"""

import datetime as dt
import struct

# 10-06 收口整改：与 build_grad_sql_v22 相同的旧布局规则（IDL 固定于 e0687ae9／2c22246b，见 idl/）
UPGRADE_END_MS = int(
    (dt.datetime(2026, 7, 15, 18, 7, 32) - dt.datetime(1970, 1, 1)).total_seconds()
    * 1000
)
KNOWN_OLD = {
    "S": (320, 368, 384, 400),
    "B": (320, 368, 401, 416, 431, 432, 447, 448, 463),
}
TAIL_START = {"B": 410, "S": 369, "I": 89, "U": 89}  # 尾段起点（1 起算）
HI_BOUND = 4_000_000_000_000_000_000


def i128(b):
    """16 字节小端有符号整数。"""
    return int.from_bytes(b, "little", signed=True)


def u64(b):
    return struct.unpack("<Q", b)[0]


def _vq(b16):
    """i128；高 8 字节超出 ±4e18 时记溢出（与 SQL 一致），返回 (vq 或 None, 溢出 0/1)。"""
    if len(b16) < 16:
        return None, 0
    hi = int.from_bytes(b16[8:16], "little", signed=True)
    if not (-HI_BOUND < hi < HI_BOUND):
        return None, 1
    return i128(b16), 0


def event_len(kind, hex_tail):
    """尾段长度＋起点 → 事件 data 的总字节数。"""
    return len(hex_tail) // 2 + TAIL_START[kind] - 1


def layout_class(kind, hex_tail, t_ms):
    """raw＝带完整 vq 字段；layout0＝升级完成前、且（事件, 长度）在已核对白名单里；其余 unknown。"""
    d = parse(kind, hex_tail)
    if d["vq"] is not None or d["vq_ovf"]:
        return "raw"
    if t_ms < UPGRADE_END_MS and event_len(kind, hex_tail) in KNOWN_OLD.get(kind, ()):
        return "layout0"
    return "unknown"


def parse(kind, hex_tail):
    """返回 dict：vq（有符号）、vq_ovf、以及按类别的 cashback／回购费或 boost 后储备（u64 按无符号）；字节不够时为 None。"""
    b = bytes.fromhex(hex_tail)
    out = dict(vq=None, vq_ovf=0, cb=None, bb=None, q1=None, b1=None, pool=None)
    if kind == "B":
        if len(b) < 4:
            return out
        n = struct.unpack("<I", b[0:4])[0]
        p = 4 + n  # cashback_bps 起点（相对第 410 字节）
        if len(b) >= p + 32:
            out["cb"] = u64(b[p + 8 : p + 16])
            out["bb"] = u64(b[p + 24 : p + 32])
        if len(b) >= p + 48:
            out["vq"], out["vq_ovf"] = _vq(b[p + 32 : p + 48])
    elif kind == "S":
        if len(b) >= 32:
            out["cb"] = u64(b[8:16])
            out["bb"] = u64(b[24:32])
        if len(b) >= 48:
            out["vq"], out["vq_ovf"] = _vq(b[32:48])
    elif kind == "I":
        # pool(32) vq(16) real_quote_reserves_after(8)
        out["pool"] = b[0:32]
        out["vq"], out["vq_ovf"] = _vq(b[32:48])
        out["q1"] = u64(b[48:56]) if len(b) >= 56 else None
    elif kind == "U":
        # pool(32) authority(32) quote_in_requested(8) quote_in_used(8) base_burned(8) vq(16) real_quote_after(8) base_after(8)
        out["pool"] = b[0:32]
        out["vq"], out["vq_ovf"] = _vq(b[88:104])
        out["q1"] = u64(b[104:112]) if len(b) >= 112 else None
        out["b1"] = u64(b[112:120]) if len(b) >= 120 else None
    return out

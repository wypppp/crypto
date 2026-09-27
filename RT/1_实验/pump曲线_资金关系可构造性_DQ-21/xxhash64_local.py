#!/usr/bin/env python3
"""Minimal stdlib xxHash64 used to reproduce Dune's fixed mint sample."""

MASK64 = (1 << 64) - 1
SIGNLESS63 = (1 << 63) - 1
P1 = 11400714785074694791
P2 = 14029467366897019727
P3 = 1609587929392839161
P4 = 9650029242287828579
P5 = 2870177450012600261


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & MASK64


def _round(acc: int, lane: int) -> int:
    acc = (acc + lane * P2) & MASK64
    acc = _rotl(acc, 31)
    return (acc * P1) & MASK64


def _merge_round(acc: int, lane: int) -> int:
    acc ^= _round(0, lane)
    return (acc * P1 + P4) & MASK64


def xxh64(data: bytes, seed: int = 0) -> int:
    """Return the unsigned xxHash64 integer for *data*."""
    n = len(data)
    pos = 0
    if n >= 32:
        v1 = (seed + P1 + P2) & MASK64
        v2 = (seed + P2) & MASK64
        v3 = seed & MASK64
        v4 = (seed - P1) & MASK64
        limit = n - 32
        while pos <= limit:
            v1 = _round(v1, int.from_bytes(data[pos:pos + 8], "little")); pos += 8
            v2 = _round(v2, int.from_bytes(data[pos:pos + 8], "little")); pos += 8
            v3 = _round(v3, int.from_bytes(data[pos:pos + 8], "little")); pos += 8
            v4 = _round(v4, int.from_bytes(data[pos:pos + 8], "little")); pos += 8
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & MASK64
        h = _merge_round(h, v1)
        h = _merge_round(h, v2)
        h = _merge_round(h, v3)
        h = _merge_round(h, v4)
    else:
        h = (seed + P5) & MASK64

    h = (h + n) & MASK64
    while pos + 8 <= n:
        lane = int.from_bytes(data[pos:pos + 8], "little")
        h ^= _round(0, lane)
        h = (_rotl(h, 27) * P1 + P4) & MASK64
        pos += 8
    if pos + 4 <= n:
        h = (h ^ (int.from_bytes(data[pos:pos + 4], "little") * P1)) & MASK64
        h = (_rotl(h, 23) * P2 + P3) & MASK64
        pos += 4
    while pos < n:
        h = (h ^ (data[pos] * P5)) & MASK64
        h = (_rotl(h, 11) * P1) & MASK64
        pos += 1

    h ^= h >> 33
    h = (h * P2) & MASK64
    h ^= h >> 29
    h = (h * P3) & MASK64
    h ^= h >> 32
    return h & MASK64


def dune_mint_hash(mint: str) -> int:
    """Reproduce bitwise_and(from_big_endian_64(xxhash64(to_utf8(mint))), 2^63-1)."""
    return xxh64(mint.encode("utf-8")) & SIGNLESS63

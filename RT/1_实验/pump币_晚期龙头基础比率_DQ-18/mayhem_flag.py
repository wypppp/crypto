"""DQ-18 Mayhem 标记（README §6.2；Dune createevent 的 is_mayhem_mode 为空，改读链上 BondingCurve 账户）。

对样本中 2025-11-12 及以后创建的币：PDA = ["bonding-curve", mint] @ pump 程序 → getMultipleAccounts（Helius，按键名读 .env）
→ 布局 disc8 | virt_tok u64 | virt_sol u64 | real_tok u64 | real_sol u64 | total_supply u64 | complete u8 | creator 32 | is_mayhem_mode u8。
输出 raw/d/mayhem.json：{mint: {"mayhem": bool|None, "total_supply": int|None}}；更早创建的币一律非 Mayhem。
"""
import base64
import csv
import hashlib
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
P = 2 ** 255 - 19
D = -121665 * pow(121666, P - 2, P) % P


def b58d(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b


def b58e(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P:
        return False
    u, v = (y * y - 1) % P, (D * y * y + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    if x2 == 0:
        return True
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P == 0:
        return True
    return (x * x + x2) % P == 0 and True  # x*sqrt(-1) 也是根


def pda(seeds, program):
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + b58d(program) + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58e(h)
    raise ValueError


def main():
    cr = {r["mint"]: r["created_at"] for r in csv.DictReader(open(ROOT / "raw" / "census" / "first_crossings.csv"))}
    mints = [r["mint"] for r in csv.DictReader(open(ROOT / "raw" / "census" / "sample_D.csv"))
             if cr.get(r["mint"], "") >= "2025-11-12"]
    rpc = re.search(r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)", (ROOT.parents[2] / ".env").read_text(), re.M).group(1)
    out = {}
    for i in range(0, len(mints), 100):
        chunk = mints[i:i + 100]
        addrs = [pda([b"bonding-curve", b58d(m)], PUMP) for m in chunk]
        r = requests.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "getMultipleAccounts",
                                     "params": [addrs, {"encoding": "base64"}]}, timeout=60).json()
        for m, acc in zip(chunk, r["result"]["value"]):
            if not acc:
                out[m] = {"mayhem": None, "total_supply": None}
                continue
            d = base64.b64decode(acc["data"][0])
            out[m] = {"mayhem": bool(d[81]) if len(d) > 81 else None,
                      "total_supply": int.from_bytes(d[40:48], "little"), "len": len(d)}
    (ROOT / "raw" / "d" / "mayhem.json").write_text(json.dumps(out, indent=1))
    from collections import Counter
    print(len(mints), Counter((v["mayhem"], v["total_supply"]) for v in out.values()))


if __name__ == "__main__":
    main()

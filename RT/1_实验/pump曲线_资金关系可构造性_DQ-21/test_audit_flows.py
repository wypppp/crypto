"""代码审计 10-03 第 10 处的永久测试：GPT 的合成交易复现 flows.wallet_flows 的关闭账户重复计额，再核对 flows_v2 的手算值。

python -m pytest test_audit_flows.py
交易：OWNER 的 wSOL 账户 S（所有者 OWNER）初始 1.002 SOL；先用代币转账把 0.9 SOL 转到 W 的 wSOL 账户，再关闭 S、余额给 W。
W 的真实流入＝1.002 SOL；原版按交易开始时余额计关闭金额，得 0.9＋1.002＝1.902。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows as F  # noqa: E402
import flows_v2 as F2  # noqa: E402
from evt_decode import ALPH  # noqa: E402

OWNER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
S = "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T"
WA = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"
W = "2WDq7wSs9zYrpx2kbHDA4RUTRch2CCTP6ZWaH4GNfnQQ"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def b58e(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = ALPH[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + s


def tx() -> dict:
    sol = 1_000_000_000
    transfer = bytes([3]) + int(0.9 * sol).to_bytes(8, "little")
    close = bytes([9])
    return {
        "slot": 1,
        "blockTime": 1,
        "transaction": {
            "signatures": ["sig1"],
            "message": {
                "accountKeys": [OWNER, S, WA, W, TOKEN],
                "header": {"numRequiredSignatures": 1},
                "instructions": [
                    {
                        "programIdIndex": 4,
                        "accounts": [1, 2, 0],
                        "data": b58e(transfer),
                    },
                    {"programIdIndex": 4, "accounts": [1, 3, 0], "data": b58e(close)},
                ],
            },
        },
        "meta": {
            "fee": 5000,
            "preBalances": [10 * sol, 1_002_000_000, 2_039_280, 0, 1],
            "postBalances": [
                10 * sol - 5000,
                0,
                2_039_280 + 900_000_000,
                102_000_000,
                1,
            ],
            "preTokenBalances": [
                {"accountIndex": 1, "owner": OWNER, "mint": F.WSOL},
                {"accountIndex": 2, "owner": W, "mint": F.WSOL},
            ],
            "postTokenBalances": [{"accountIndex": 2, "owner": W, "mint": F.WSOL}],
            "innerInstructions": [],
        },
    }


def inflow_from(mod, src: str) -> int:
    inflows, _ = mod.wallet_flows(tx(), W)
    return sum(r["amount"] for r in inflows if r["source"] == src)


def test_10_old_reproduces_bug():
    assert inflow_from(F, OWNER) == 1_902_000_000


def test_10_fixed_hand_value():
    assert inflow_from(F2, OWNER) == pytest.approx(1_002_000_000)


def test_10_fixed_close_without_prior_transfer_unchanged():
    """没有先转出时，关闭金额＝交易开始时余额，新旧相同。"""
    v = F.tx_view(tx())
    x = tx()
    x["transaction"]["message"]["instructions"] = x["transaction"]["message"][
        "instructions"
    ][1:]
    old = [m for m in F.decode_moves(x, v) if m[0] == "close"]
    new = [m for m in F2.decode_moves(x, F.tx_view(x)) if m[0] == "close"]
    assert old[0][4] == new[0][4] == 1_002_000_000

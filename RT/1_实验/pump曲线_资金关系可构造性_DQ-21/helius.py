"""DQ-21 Helius 客户端（参照 DQ-16 helius.py）：按键名用正则读 .env 中的 helius_RPC_URL，不打印、不写出。
每次 getTransactionsForAddress 计 10 credits（F101 实测口径），记录耗时；超过上限就拒绝调用。"""
import json
import re
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # /home/ancillary
_m = re.search(r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)", (ROOT / ".env").read_text(), re.M)
URL = _m.group(1)
CREDITS_PER_CALL = 10
_lock = threading.Lock()
STATE = {"calls": 0, "credits": 0, "cap": 0, "lat": []}


class BudgetExceeded(RuntimeError):
    pass


def rpc(method, params, retries=5):
    with _lock:
        if STATE["credits"] + CREDITS_PER_CALL > STATE["cap"]:
            raise BudgetExceeded(f"credits {STATE['credits']} + {CREDITS_PER_CALL} > cap {STATE['cap']}")
        STATE["calls"] += 1
        STATE["credits"] += CREDITS_PER_CALL
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        t0 = time.time()
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=120))
            if "error" in d:
                raise RuntimeError(d["error"])
            with _lock:
                STATE["lat"].append(time.time() - t0)
            return d["result"]
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def gtfa(address, gte, lt, order, token=None, limit=100):
    """完整交易（json 编码、只要成功的），blockTime ∈ [gte, lt)，order = asc/desc。"""
    opts = {"transactionDetails": "full", "sortOrder": order, "limit": limit, "maxSupportedTransactionVersion": 0,
            "encoding": "json", "filters": {"blockTime": {"gte": int(gte), "lt": int(lt)}, "status": "succeeded"}}
    if token:
        opts["paginationToken"] = token
    return rpc("getTransactionsForAddress", [address, opts])

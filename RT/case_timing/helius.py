"""Minimal Helius RPC helper for case-timing work. Never prints the key."""
import json, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_env = {}
for line in open(ROOT / ".env"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        _env[k.strip()] = v.strip().strip('"').strip("'")
URL = _env["helius_RPC_URL"]
CALLS = {"gtfa_sig": 0, "gtfa_full": 0, "other": 0}

def rpc(method, params, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=90))
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))

def gtfa(address, details, gte, lt, limit, token=None):
    opts = {"transactionDetails": details, "sortOrder": "asc", "limit": limit,
            "filters": {"blockTime": {"gte": gte, "lt": lt}}}
    if details == "full":
        opts["maxSupportedTransactionVersion"] = 0
        opts["encoding"] = "jsonParsed"
    if token:
        opts["paginationToken"] = token
    CALLS["gtfa_full" if details == "full" else "gtfa_sig"] += 1
    return rpc("getTransactionsForAddress", [address, opts])

def all_in_window(address, details, gte, lt):
    limit = 100 if details == "full" else 1000
    out, token = [], None
    while True:
        r = gtfa(address, details, gte, lt, limit, token)
        out += r.get("data", [])
        token = r.get("paginationToken")
        if not token or not r.get("data"):
            return out

def all_full_ok(address, gte, lt):
    """Full transactions (succeeded only) in [gte, lt), ascending."""
    out, token = [], None
    while True:
        opts = {"transactionDetails": "full", "sortOrder": "asc", "limit": 100,
                "maxSupportedTransactionVersion": 0, "encoding": "json",
                "filters": {"blockTime": {"gte": gte, "lt": lt}, "status": "succeeded"}}
        if token:
            opts["paginationToken"] = token
        CALLS["gtfa_full"] += 1
        r = rpc("getTransactionsForAddress", [address, opts])
        out += r.get("data", [])
        token = r.get("paginationToken")
        if not token or not r.get("data"):
            return out

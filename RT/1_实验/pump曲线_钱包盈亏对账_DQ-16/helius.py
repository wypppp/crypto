"""Helius RPC helper for DQ-16 (copied from H1 helius.py; .env read by key name via regex). Never prints the key."""
import json, re, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # /home/ancillary
_m = re.search(r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)", (ROOT / ".env").read_text(), re.M)
URL = _m.group(1)
CALLS = {}

def rpc(method, params, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    CALLS[method] = CALLS.get(method, 0) + 1
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=120))
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))

def gtfa_page(address, gte, lt, details="full", limit=100, token=None, token_accounts=None, status=None):
    f = {"blockTime": {"gte": gte, "lt": lt}}
    if token_accounts:
        f["tokenAccounts"] = token_accounts
    if status:
        f["status"] = status
    opts = {"transactionDetails": details, "sortOrder": "asc", "limit": limit, "filters": f}
    if details == "full":
        opts["maxSupportedTransactionVersion"] = 0
        opts["encoding"] = "json"
    if token:
        opts["paginationToken"] = token
    return rpc("getTransactionsForAddress", [address, opts])

"""最小预检：链身份 + 当前 finalized 块。只输出公开链上数据，不输出凭据。"""
import os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2].parent / "baseline_20260909"))
import verify_capabilities as V
rpc = V.RPC(os.environ["ETH_RPC_URL"], max_calls=5, max_seconds=30, rps=2)
cid = int(rpc.request("eth_chainId", []), 16)
fin = rpc.request("eth_getBlockByNumber", ["finalized", False])
print(json.dumps({"chain_id": cid, "finalized_number": int(fin["number"], 16),
                  "finalized_hash": fin["hash"], "finalized_timestamp": int(fin["timestamp"], 16),
                  "rpc_calls": len(rpc.records)}))

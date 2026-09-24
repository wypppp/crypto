"""对 D 段输出的入场/退出成交 tx 取公共 RPC 原件，按交易前池状态估值（valuation.py）。

用法：python rpc_value_d.py raw/d/D_202410.json 入场 [抽样数]
原件缓存在 raw/d/rpc/<tx>.json；不查 Dune，不花额度。
"""
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

import valuation as V

ROOT = Path(__file__).resolve().parent
RPC = "https://api.mainnet-beta.solana.com"
CACHE = ROOT / "raw" / "d" / "rpc"
CACHE.mkdir(parents=True, exist_ok=True)


def get_tx(sig):
    p = CACHE / (sig + ".json")
    if p.exists():
        return json.loads(p.read_text())["result"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}
    for a in range(6):
        r = requests.post(RPC, json=body, timeout=30)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 + 3 * a)
            continue
        j = r.json()
        if j.get("result"):
            p.write_text(json.dumps(j))
            return j["result"]
        time.sleep(2)
    raise RuntimeError("rpc failed " + sig)


def value_row(row, tx_field, cap_field):
    tx = get_tx(row[tx_field])
    y, x, venue = V.pool_reserves(tx, row["mint"], row["pool"])
    when = datetime.utcfromtimestamp(tx["blockTime"])
    # SOL/USD：由该笔 Dune 打印价与池内 SOL/代币比反推（同一时刻），只用于把储备换成美元
    marg_sol_cap = x / y * 1e9
    sol_usd = row[cap_field] / marg_sol_cap if row[cap_field] else None
    f = V.fee_side(venue, when, marg_sol_cap)
    return {"venue": venue, "pool_sol": x, "pool_tok": y, "fee": f, "print_over_marginal": None,
            "sol_usd_implied": sol_usd, "cap5_buy_sol": V.cap5_buy_sol(x), "cap5_sell_sol": V.cap5_sell_sol(x)}


def main():
    rows = json.load(open(sys.argv[1]))["rows"]
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    ent = [r for r in rows if r["rt"] == "E"]
    known = [r for r in ent if r["mint"][:8] in ("CzLSujWB", "9BB6NFEc", "2qEHjDLD")]
    rnd = sorted(ent, key=lambda r: hashlib.md5((r["mint"] + str(r["tier"]) + ":dq18v").encode()).hexdigest())[:k]
    out = []
    for r in known + [x for x in rnd if x not in known]:
        v = value_row(r, "x_tx", "x_cap")
        tx = get_tx(r["x_tx"])
        y, x, _ = V.pool_reserves(tx, r["mint"], r["pool"])
        # 打印价（Dune）对池边际价：用 Coinbase 无关的比值检验——同一笔的 SOL/代币 数量
        out.append({"mint": r["mint"][:10], "tier": r["tier"], "signal": r["signal_time"][:16],
                    "entry_time": r["x_time"][:19], "venue": v["venue"], "pool_sol": round(x, 2),
                    "fee": v["fee"], "sol_usd_implied": round(v["sol_usd_implied"], 2),
                    "cap5_buy_usd": round(v["cap5_buy_sol"] * v["sol_usd_implied"]),
                    "marginal_cap_musd": round(x / y * 1e9 * v["sol_usd_implied"] / 1e6, 3)})
    (ROOT / "raw" / "d" / ("valuation_check_" + Path(sys.argv[1]).stem + ".json")).write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    for o in out:
        print(o)


if __name__ == "__main__":
    main()

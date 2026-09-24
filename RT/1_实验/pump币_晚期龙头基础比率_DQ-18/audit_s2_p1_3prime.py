"""DQ-18 P1 验收 3′：同一笔成交的执行价是否落在交易前后池状态区间内。

只用已下载的公共 RPC 原件（raw/s2/rpc_pool_last/）与池账户（raw/s2/rpc_pool_accounts/），
不发新请求、不查 Dune。执行价 = 池侧报价币变化 ÷ 池侧代币变化；P0/P1 = 交易前/后储备比。
f：PumpSwap 取 2025-09 后最高档单边 1.25%（宽），Raydium v4 取 0.25%。
Dune 同笔数量未在现有输出中，(a) 未核。不计算收益。
"""
import json
from decimal import Decimal
from pathlib import Path

import audit_s2_p1_pool_price as base

RAW = Path(__file__).resolve().parent / "raw" / "s2"
FEE = {"pumpswap": Decimal("0.0125"), "raydium": Decimal("0.0025")}
TOL = Decimal("0.005")


def main():
    rows = [r for r in json.loads((RAW / "P1_202512_pools.json").read_text())["rows"]
            if r["pool_rank"] == 1]
    sample = json.loads((RAW / "P1_202512_sample10.json").read_text())
    out = []
    for r in rows:
        mint, pool = r["mint"], r["pool_id"]
        bal = base.transaction_balances(r["last_tx_id"])
        if r["project"] == "raydium":
            ta, qa = base.raydium_vaults(pool, mint)
        else:
            ta = [a for a, v in bal.items() if v["mint"] == mint and v["owner"] == pool][0]
            qa = [a for a, v in bal.items() if v["mint"] == base.SOL and v["owner"] == pool][0]
        t, q = bal[ta], bal[qa]
        p0, p1 = q["pre"] / t["pre"], q["post"] / t["post"]
        ex = abs(q["delta"] / t["delta"]) if t["delta"] != 0 else None
        f = FEE[r["project"]]
        lo, hi = min(p0, p1) * (1 - f - TOL), max(p0, p1) * (1 + f + TOL)
        ok = ex is not None and lo <= ex <= hi
        out.append({"mint": mint, "project": r["project"], "tx": r["last_tx_id"],
                    "side": "buy" if q["delta"] > 0 else "sell",
                    "p0": str(p0), "p1": str(p1), "exec": str(ex),
                    "exec_over_p0": str(ex / p0) if ex else None,
                    "exec_over_p1": str(ex / p1) if ex else None,
                    "fee_assumed": str(f), "pass_b": ok, "a_checked": False})
    mints = {x["mint"] for x in out}
    (RAW / "P1_202512_3prime.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for x in out:
        print(x["mint"][:9], x["project"], x["side"], "exec/P0", x["exec_over_p0"][:8],
              "exec/P1", x["exec_over_p1"][:8], "PASS" if x["pass_b"] else "FAIL")
    print("n", len(out), "pass", sum(x["pass_b"] for x in out), "sample_file_type", type(sample).__name__)


if __name__ == "__main__":
    main()

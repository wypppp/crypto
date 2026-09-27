"""DQ-21 S0 结果复核：用 R0 已缓存的交易（0 credits）量早买交易的落地开销与 Helius 单次调用延迟。

python 落地成本与延迟.py → checks/落地成本与延迟.json
- 落地开销 = 交易手续费（含优先费）+ 外层指令里付款人转给“≥10 个不同付款人都转过”的地址的 SOL（Jito 与其他落地服务的小费）。
  通过自有路由程序在内层指令里付的小费、失败交易的手续费都不在内，所以是下界。
- 延迟 = R0 走查索引里只翻 1 页的走查耗时，是从本机（非同机房）发出的 getTransactionsForAddress 单次往返。
"""
import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
D21 = H.parents[1] / "1_实验" / "pump曲线_资金关系可构造性_DQ-21"
sys.path.insert(0, str(D21))
from evt_decode import b58d, account_keys  # noqa: E402

JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
CB = "ComputeBudget111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
Q = [0.1, 0.25, 0.5, 0.75, 0.9]


def q(s):
    return {str(k): round(float(v), 6) for k, v in s.quantile(Q).items()}


def main():
    B = pd.read_csv(D21 / "raw" / "dune" / "Q_buyers.csv.gz")
    tx = B[B.kind == "buy"].set_index(["mint", "usr"]).tx_id.to_dict()
    W = pd.read_csv(D21 / "results" / "all_wallets.csv").merge(
        pd.read_csv(D21 / "results" / "all_coins.csv")[["mint", "t0"]], on="mint")
    rows, payers = [], collections.defaultdict(set)
    for r in W.itertuples():
        sig = tx.get((r.mint, r.W))
        f = D21 / "raw" / "helius" / f"back__{r.W}__{r.t_buy}.jsonl.gz"
        if sig is None or not f.exists():
            continue
        x = next((y for y in (json.loads(l) for l in gzip.open(f, "rt") if sig in l)
                  if y["transaction"]["signatures"][0] == sig), None)
        if x is None:
            continue
        keys = account_keys(x)
        payer, outer = keys[0], []
        for i in x["transaction"]["message"]["instructions"]:
            d = b58d(i["data"]) if i.get("data") else b""
            if keys[i["programIdIndex"]] == SYS and len(d) >= 12 and d[:4] == b"\x02\x00\x00\x00" \
                    and keys[i["accounts"][0]] == payer:
                outer.append((keys[i["accounts"][1]], int.from_bytes(d[4:12], "little")))
        for dst, _ in outer:
            payers[dst].add(payer)
        rows.append(dict(sol=r.sol, dt=r.t_buy - r.t0, fee=x["meta"]["fee"] / 1e9, outer=outer))
    D = pd.DataFrame(rows)
    svc = {d for d, s in payers.items() if len(s) >= 10}
    D["jito"] = D.outer.map(lambda t: sum(l for d, l in t if d in JITO)) / 1e9
    D["tip"] = D.outer.map(lambda t: sum(l for d, l in t if d in svc)) / 1e9
    D["over"] = D.fee + D.tip
    out = {"n_buy_tx": len(D), "tip_destinations_ge10_payers": len(svc),
           "share_with_jito_tip": round(float((D.jito > 0).mean()), 3),
           "share_with_any_tip": round(float((D.tip > 0).mean()), 3),
           "fee_sol": q(D.fee), "overhead_sol_all": q(D.over)}
    for lab, g in D.groupby(D.dt <= 5):
        out["overhead_sol_" + ("buy_le5s" if lab else "buy_gt5s")] = {**q(g.over), "n": len(g)}
    idx = pd.read_csv(D21 / "raw" / "helius_index.csv")
    one = idx[idx.kind.isin(["back", "back_ext"]) & (idx.pages == 1)]
    out["helius_single_call_wall_s"] = {**q(one.wall_s), "n": len(one)}
    Wc = W[W.walk_complete.astype(str) == "True"]
    out["share_wallets_complete_within_1_page"] = round(float((Wc.walk_pages == 1).sum() / len(W)), 3)
    (H / "checks" / "落地成本与延迟.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

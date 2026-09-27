"""DQ-21 R0a 通过条件第 2 条：来源归因核验（README v1.2 §7）。

1. 从 results/{stage}_inflows.csv.gz 按（状态 × 证据）分层抽样：每层最多 10 笔，合计不足 50 时从 unique 各层补足；种子固定。
2. 每笔用 Helius getTransaction（jsonParsed，RPC 自带解析，与本项目的解码不共用代码）重取，独立判断：
   - 指令证据：解析后的系统转账/建账户/nonce 提款、SPL transfer/transferChecked、closeAccount 中，
     是否有目标为 W（或 W 名下代币账户）、来源 = 记录的来源（系统账户为转出方，带种子为 base，nonce 为授权人，
     SPL 与关闭账户为源/被关闭代币账户的资产所有者）、金额合计 >= 记录金额的指令；
   - 余额证据：按解析后的账户与代币余额所有者合并，来源的净减少是否 >= W 净增加的 95%，且没有第二个非 PDA 地址满足。
3. unique 必须 supported；非 unique 只检查是否本应能唯一归因（漏判不算错判，但记录）。
存 results/{stage}_audit{round}.csv 与原始交易 raw/helius/audit/，逐笔判读理由写在 过程/ 中。

python audit_sample.py r0a --round 1 --cap 1000
"""
import argparse
import gzip
import json
from pathlib import Path

import pandas as pd

import flows as F
import helius as HL

H = Path(__file__).resolve().parent
SEEDS = {1: 20260929, 2: 20260930, 3: 20261001}


def owners_parsed(tx):
    keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    own, mint = {}, {}
    for tb in (tx["meta"].get("preTokenBalances") or []) + (tx["meta"].get("postTokenBalances") or []):
        own[keys[tb["accountIndex"]]] = tb.get("owner")
        mint[keys[tb["accountIndex"]]] = tb.get("mint")
    return keys, own, mint


def parsed_ixs(tx):
    for ix in tx["transaction"]["message"]["instructions"]:
        yield ix
    for g in tx["meta"].get("innerInstructions") or []:
        for ix in g["instructions"]:
            yield ix


def check(tx, W, source, amount, evidence):
    keys, own, mint = owners_parsed(tx)
    ow = lambda a: own.get(a, a)
    if evidence != "balance":
        tot, seen = 0, []
        for ix in parsed_ixs(tx):
            p = ix.get("parsed")
            if not isinstance(p, dict):
                continue
            t, info = p.get("type"), p.get("info", {})
            if t in ("transfer", "transferWithSeed", "createAccount", "createAccountWithSeed", "withdrawFromNonce") and "lamports" in info:
                src = info.get("nonceAuthority") or info.get("sourceBase") or info.get("source")
                dst, amt = info.get("destination") or info.get("newAccount"), int(info["lamports"])
            elif t in ("transfer", "transferChecked") and ("amount" in info or "tokenAmount" in info):
                # 来源 = 源代币账户的资产所有者（09-27 复核后）；缺失时退回授权人
                src = own.get(info.get("source")) or info.get("authority") or info.get("multisigAuthority")
                dst = info.get("destination")
                amt = int(info.get("amount") or info["tokenAmount"]["amount"])
                if (info.get("mint") or mint.get(info.get("source")) or mint.get(dst)) != F.WSOL:
                    continue
            elif t == "closeAccount":
                src, dst = own.get(info.get("account")) or info.get("owner"), info.get("destination")
                amt = tx["meta"]["preBalances"][keys.index(info["account"])] if info.get("account") in keys else 0
            else:
                continue
            if ow(dst) == W and ow(src) == source:
                tot += amt
                seen.append(f"{t}:{amt / 1e9:.4f}")
        return tot >= amount * 0.999, ";".join(seen)
    agg = {}
    for i, k in enumerate(keys):
        d = tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i] + (tx["meta"]["fee"] if i == 0 else 0)
        agg[ow(k)] = agg.get(ow(k), 0) + d
    dW = agg.get(W, 0)
    full = [o for o, v in agg.items() if o != W and v <= -0.95 * dW and F.on_curve(o)]
    signers = {k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"] if k.get("signer")}
    return (dW > 0 and full == [source] and source in signers), f"dW={dW / 1e9:.4f};full_on={'|'.join(full)};signer={source in signers}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--cap", type=int, default=1000)
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    HL.STATE["cap"] = a.cap
    inf = pd.read_csv(H / "results" / f"{a.stage}_inflows.csv.gz")
    inf = inf[inf.role == "buyer"]
    prev = set()
    for r in range(1, a.round):
        f = H / "results" / f"{a.stage}_audit{r}.csv"
        if f.exists():
            prev |= set(pd.read_csv(f).sig + "|" + pd.read_csv(f).W)
    inf = inf[~(inf.sig + "|" + inf.W).isin(prev)]
    inf["layer"] = inf.status + "/" + inf.evidence
    seed = SEEDS[a.round]
    parts = [g.sample(min(len(g), 10), random_state=seed) for _, g in inf.groupby("layer")]
    samp = pd.concat(parts)
    if len(samp) < a.n:
        rest = inf[(inf.status == "unique") & ~inf.index.isin(samp.index)]
        samp = pd.concat([samp, rest.sample(min(len(rest), a.n - len(samp)), random_state=seed)])
    out_raw = H / "raw" / "helius" / "audit"
    out_raw.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in samp.itertuples():
        f = out_raw / f"{r.sig}.json.gz"
        if f.exists():
            tx = json.load(gzip.open(f, "rt"))
        else:
            tx = HL.rpc("getTransaction", [r.sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            json.dump(tx, gzip.open(f, "wt"))
        ok, detail = check(tx, r.W, r.source, r.amount, r.evidence)
        rows.append({"layer": r.layer, "sig": r.sig, "W": r.W, "source": r.source, "amount_sol": r.amount / 1e9,
                     "status": r.status, "evidence": r.evidence, "payer": r.payer, "w_signed": r.w_signed,
                     "independent_supported": ok, "detail": detail})
    R = pd.DataFrame(rows)
    R.to_csv(H / "results" / f"{a.stage}_audit{a.round}.csv", index=False)
    u = R[R.status == "unique"]
    print("sampled", len(R), "layers", R.layer.value_counts().to_dict())
    print("unique supported", int(u.independent_supported.sum()), "/", len(u), "credits(10/call)", HL.STATE["credits"])
    print(R[R.status == "unique"][~R.independent_supported].to_string() if (~u.independent_supported).any() else "no unsupported unique")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DQ-26 第一步·G1b SOL 闭合（卡片_v1.md §4）：Helius `getTransaction` 逐笔核对抽样交易。

python g1b.py fetch → raw/helius/g1b/<tx>.json（不入库），runs/g1b_calls.json（请求计数，上限 5,000）
python g1b.py score → runs/g1b.json、runs/g1b_tx.csv

每笔：
  实际变动＝签名者账户＋其拥有的代币账户（含 WSOL 与租金）的 lamports 变动之和（pre/post balances）；
  记账口径＝事件现金（Dune 抽样：曲线用事件实际费用，dex 非曲线成交的 SOL 金额）− 网络费（meta.fee，签名者付）
           − 小费与附加转出（转入 Jito 小费账户或 step1 认定的服务方收款地址的 System 转账，任意层级）；
  差＝实际 − 记账；|差| ≤ max(0.001 SOL, 该笔事件现金的 1%) 为闭合。
  （卡片写“租金按 0.00203928 SOL 的整数倍单列”；这里把签名者自有代币账户的 lamports 一并计入实际变动，
    租金在签名者与其代币账户之间相互抵消，效果相同且不依赖租金常数——token-2022 账户的租金不是该常数。）
只算钱包自己签名（且付网络费）的交易；签名者不是该钱包的单列。
RPC 地址按键名 helius_RPC_URL 从工作区 .env 正则读取，不打印、不写出。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "helius" / "g1b"
RUNS = H / "runs"
CAP = 5000
_m = re.search(
    r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)",
    (H.parents[2] / ".env").read_text(),
    re.M,
)
if _m is None:
    raise RuntimeError("helius_RPC_URL not found")
URL = _m.group(1)
JITO = set(
    json.loads((H / "raw" / "jito_tip_accounts_20261001.json").read_text())["result"]
)


def rpc(method: str, params: list) -> dict:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    for attempt in range(6):
        try:
            req = urllib.request.Request(
                URL, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            if "error" in d and d["error"].get("code") in (-32429, 429):
                time.sleep(2 + 2 * attempt)
                continue
            return d
        except OSError:
            time.sleep(2 + 2 * attempt)
    raise RuntimeError("rpc failed")


def fetch() -> None:
    s = pd.read_csv(H / "raw" / "dune" / "SAMPLE_G1B_R.csv.gz")
    RAW.mkdir(parents=True, exist_ok=True)
    todo = [t for t in s.tx_id.unique() if not (RAW / f"{t}.json").exists()]
    calls_f = RUNS / "g1b_calls.json"
    used = json.loads(calls_f.read_text())["calls"] if calls_f.exists() else 0
    assert used + len(todo) <= CAP, (used, len(todo))

    def one(t: str) -> int:
        d = rpc(
            "getTransaction",
            [
                t,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        )
        (RAW / f"{t}.json").write_text(json.dumps(d))
        return 1

    with ThreadPoolExecutor(5) as ex:
        n = sum(ex.map(one, todo))
    calls_f.write_text(json.dumps({"calls": used + n, "cap": CAP}))
    print("fetched", n, "total calls", used + n)


def instrs(tx: dict):
    msg = tx["transaction"]["message"]
    for ins in msg.get("instructions", []):
        yield ins
    for grp in (tx.get("meta") or {}).get("innerInstructions") or []:
        for ins in grp.get("instructions", []):
            yield ins


def score() -> None:
    s = pd.read_csv(H / "raw" / "dune" / "SAMPLE_G1B_R.csv.gz")
    service = set(pd.read_csv(RUNS / "service_recipients.csv").cp)
    rows = []
    for r in s.itertuples(index=False):
        f = RAW / f"{r.tx_id}.json"
        d = json.loads(f.read_text()).get("result") if f.exists() else None
        if not d:
            rows.append({"tx_id": r.tx_id, "entity": r.entity, "status": "missing"})
            continue
        keys = [k["pubkey"] for k in d["transaction"]["message"]["accountKeys"]]
        meta = d["meta"]
        if keys[0] != r.usr:
            rows.append({"tx_id": r.tx_id, "entity": r.entity, "status": "not_signer"})
            continue
        owned = {0}
        for tb in (meta.get("preTokenBalances") or []) + (
            meta.get("postTokenBalances") or []
        ):
            if tb.get("owner") == r.usr:
                owned.add(tb["accountIndex"])
        actual = (
            sum(meta["postBalances"][i] - meta["preBalances"][i] for i in owned) / 1e9
        )
        tips = 0.0
        for ins in instrs(d):
            p = ins.get("parsed")
            if (
                ins.get("program") == "system"
                and isinstance(p, dict)
                and p.get("type") == "transfer"
            ):
                info = p["info"]
                if info.get("source") == r.usr and (
                    info.get("destination") in JITO
                    or info.get("destination") in service
                ):
                    tips += info["lamports"] / 1e9
        fee = meta["fee"] / 1e9
        recon = r.sol_cash - fee - tips
        resid = actual - recon
        tol = max(0.001, 0.01 * abs(r.sol_cash))
        rows.append(
            {
                "tx_id": r.tx_id,
                "entity": r.entity,
                "status": "ok" if meta.get("err") is None else "failed_tx",
                "srcs": r.srcs,
                "sol_cash": r.sol_cash,
                "fee": fee,
                "tips": tips,
                "actual": actual,
                "resid": resid,
                "closed": abs(resid) <= tol,
            }
        )
    t = pd.DataFrame(rows)
    t.to_csv(RUNS / "g1b_tx.csv", index=False)
    ok = t[t.status == "ok"].copy()
    ok["closed"] = ok.closed.astype(bool)
    res = {
        "sampled": int(len(t)),
        "status": t.status.value_counts().to_dict(),
        "closed_share": round(float(ok.closed.mean()), 4) if len(ok) else None,
        "pass": bool(len(ok) and ok.closed.mean() >= 0.95),
        "resid_quantiles": ok.resid.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        .round(5)
        .to_dict(),
        "unclosed_by_src": ok[~ok.closed].srcs.value_counts().to_dict(),
        "unclosed_resid_sum": round(float(ok.loc[~ok.closed, "resid"].sum()), 4),
        "entities_all_closed": int(ok.groupby("entity").closed.all().sum()),
        "fee_median": float(np.median(ok.fee)) if len(ok) else None,
    }
    (RUNS / "g1b.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    {"fetch": fetch, "score": score}[sys.argv[1]]()

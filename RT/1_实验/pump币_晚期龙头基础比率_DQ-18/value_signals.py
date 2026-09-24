"""DQ-18 第二层估值：每个信号的入场/退出成交 → RPC 交易前池状态 → 我方仓位的净倍数与模型容量。

先 python value_signals.py fetch   # 并发取 raw/d/need_tx.txt 的原件（缓存 raw/d/rpc/）
再 python value_signals.py value   # 输出 raw/d/valued.csv
倍数以美元计。SOL/USD 用独立源（Coinbase 小时收盘，取决策时刻前最后一根已收盘的 K 线，raw/d/coinbase_sol_usd_1h.json）；
09-24 独立复核后改：旧版由同一笔的打印价与池内比值反推，池配对出错时会反推出荒谬的 SOL 价。
打印价反推值只作诊断（sol_dev = 反推 ÷ 独立 − 1），不进估值。费率见 valuation.fee_side。
链上固定成本不在此扣，留给账户模拟（0.002/0.005/0.01 SOL 三档）。
"""
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

import valuation as V

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "raw" / "d" / "rpc"
RPC = "https://api.mainnet-beta.solana.com"
if os.environ.get("DQ18_RPC") == "helius":  # 用户 09-24 同意改用 Helius；按键名读取，不打印
    RPC = re.search(r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)", (ROOT.parents[2] / ".env").read_text(), re.M).group(1)


def fetch_one(sig):
    p = CACHE / (sig + ".json")
    if p.exists():
        return "cached"
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}
    for a in range(8):
        try:
            r = requests.post(RPC, json=body, timeout=30)
        except requests.RequestException:
            time.sleep(3 + 3 * a)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 + 4 * a)
            continue
        j = r.json()
        if j.get("result"):
            p.write_text(json.dumps(j))
            return "ok"
        if j.get("error"):
            time.sleep(2 + 2 * a)
            continue
        return "null"
    return "fail"


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    sigs = [s for s in (ROOT / "raw" / "d" / "need_tx.txt").read_text().split() if s]
    todo = [s for s in sigs if not (CACHE / (s + ".json")).exists()]
    print("need", len(sigs), "todo", len(todo), flush=True)
    stats = {}
    with ThreadPoolExecutor(8 if os.environ.get("DQ18_RPC") == "helius" else 4) as ex:
        for i, res in enumerate(ex.map(fetch_one, todo)):
            stats[res] = stats.get(res, 0) + 1
            if i % 200 == 0:
                print(i, stats, flush=True)
    print("done", stats, flush=True)


SOL_1H = {int(k): v for k, v in json.loads((ROOT / "raw" / "d" / "coinbase_sol_usd_1h.json").read_text()).items()}


def sol_usd(when):
    """when（UTC naive）之前最后一根已收盘小时 K 线的收盘价。"""
    t = int((when - datetime(1970, 1, 1)).total_seconds()) // 3600 * 3600 - 3600
    for back in range(0, 48 * 3600, 3600):
        if t - back in SOL_1H:
            return SOL_1H[t - back]
    raise KeyError(when)


def state(sig, mint, pool):
    p = CACHE / (sig + ".json")
    if not sig or not p.exists():
        return None
    tx = json.loads(p.read_text())["result"]
    try:
        y, x, venue = V.pool_reserves(tx, mint, pool)
    except ValueError:
        return None
    return {"y": y, "x": x, "venue": venue, "when": datetime.utcfromtimestamp(tx["blockTime"])}


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def value():
    rows = list(csv.DictReader(open(ROOT / "raw" / "d" / "signals.csv")))
    out = []
    for r in rows:
        o = {k: r.get(k, "") for k in ("mint", "tier", "signal_time", "stratum", "weight", "validation", "exit_time",
                               "entry_time", "entry_cap_print", "e5_cap_print", "e60_cap_print", "exit_proxy_c",
                               "exit_kind", "b50_triggered", "max_cap", "c_D1", "c_D7", "c_D30", "c_D90", "c_D180",
                               "cross_hour_vwap")}
        e = state(r.get("entry_tx"), r["mint"], r.get("entry_pool"))
        x = state(r.get("exit_tx"), r["mint"], r.get("exit_pool"))
        o["entry_known"] = bool(e)
        o["exit_known"] = bool(x)
        ecp, xcp = fnum(r.get("entry_cap_print")), fnum(r.get("exit_cap_print"))
        if e:
            fe = V.fee_side(e["venue"], e["when"], e["x"] / e["y"] * 1e9)
            sol_e = sol_usd(e["when"])
            o.update({"entry_x": e["x"], "entry_y": e["y"], "entry_when": e["when"].isoformat(),
                      "entry_venue": e["venue"], "entry_fee": fe, "entry_sol_usd": sol_e,
                      "entry_sol_dev": ecp / (e["x"] / e["y"] * 1e9) / sol_e - 1 if ecp else "",
                      "entry_marg_cap": e["x"] / e["y"] * 1e9 * sol_e,
                      "cap5_buy_usd": V.cap5_buy_sol(e["x"]) * sol_e})
        if x:
            fx = V.fee_side(x["venue"], x["when"], x["x"] / x["y"] * 1e9)
            sol_x = sol_usd(x["when"])
            o.update({"exit_x": x["x"], "exit_y": x["y"], "exit_when": x["when"].isoformat(),
                      "exit_venue": x["venue"], "exit_fee": fx, "exit_sol_usd": sol_x,
                      "exit_sol_dev": xcp / (x["x"] / x["y"] * 1e9) / sol_x - 1 if xcp else "",
                      "exit_marg_cap": x["x"] / x["y"] * 1e9 * sol_x,
                      "cap5_sell_usd": V.cap5_sell_sol(x["x"]) * sol_x})
        if e and x:
            # 零规模倍数（美元）：边际价比 × 两次费率
            o["mult_marginal"] = (o["exit_marg_cap"] / o["entry_marg_cap"]) * (1 - fe) * (1 - fx)
            # $1,400 仓位：按入场池状态买入，按退出池状态卖出
            q = 1400 / sol_e
            tok = V.buy(e["x"], e["y"], q, fe)
            proceeds_sol = V.sell(x["x"], x["y"], tok, fx)
            o["mult_1400"] = proceeds_sol * sol_x / 1400
            o["tok_1400"] = tok
        elif e and r.get("exit_proxy_c"):
            # 退出成交缺失：用下一条路径小时 VWAP 作代理（第一层性质），单独标记
            o["mult_marginal"] = fnum(r["exit_proxy_c"]) / o["entry_marg_cap"] * (1 - fe) ** 2
            o["exit_is_proxy"] = True
        out.append(o)
    keys = sorted({k for o in out for k in o})
    with open(ROOT / "raw" / "d" / "valued.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print("valued", len(out), "both known", sum(1 for o in out if o.get("mult_1400") is not None))


if __name__ == "__main__":
    {"fetch": fetch, "value": value}[sys.argv[1]]()

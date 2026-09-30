#!/usr/bin/env python3
"""DQ-22 卡片 v2：样本外——币安 U 本位新上永续（不在币安现货首发全集中的币）。0 credits。

python oos_replicate.py → runs/oos_events.csv、runs/oos_analysis.json（及 exchangeInfo 快照）
事件构造为新代码；取数、爆仓、资金费与统计量调用 v1 的 perp_replicate.py（冻结，不改）。
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import perp_replicate as P

HERE = Path(__file__).resolve().parent
L_MASTER = (
    HERE.parents[1] / "5_参考" / "旧债务" / "direction" / "v1.8.40" / "L_u_master.json"
)
INFO = P.RUNS / "fapi_exchangeInfo_20260930.json"
T0_MIN, T0_MAX = dt.date(2023, 1, 1), dt.date(2026, 8, 26)
PREFIXES = ("1000000", "1000")


def prefixes(prefix: str) -> list[str]:
    out, marker = [], ""
    while True:
        q = urllib.parse.urlencode(
            {"delimiter": "/", "prefix": prefix, "marker": marker}
        )
        with urllib.request.urlopen(f"{P.S3}?{q}", timeout=60) as r:
            body = r.read().decode()
        page = re.findall(r"<Prefix>" + re.escape(prefix) + r"([^/<]+)/</Prefix>", body)
        out += page
        if "<IsTruncated>true</IsTruncated>" not in body or not page:
            return out
        marker = prefix + page[-1] + "/"


def exchange_info() -> dict[str, dict]:
    if not INFO.exists():
        raw = json.loads(P.get("https://www.binance.com/fapi/v1/exchangeInfo"))
        keep = [
            {k: s.get(k) for k in ("symbol", "underlyingType", "onboardDate", "status")}
            for s in raw["symbols"]
        ]
        P.RUNS.mkdir(exist_ok=True)
        INFO.write_text(json.dumps({"serverTime": raw["serverTime"], "symbols": keep}))
    return {s["symbol"]: s for s in json.loads(INFO.read_text())["symbols"]}


def base_of(sym: str, names: set[str]) -> str:
    b = sym[:-4]
    for p in PREFIXES:
        if b.startswith(p) and b[len(p) :] in names:
            return b[len(p) :]
    return b


def one(sym: str, t0: dt.date) -> dict:
    d = t0 + P.DAY
    out = {"perp": sym, "t0": t0.isoformat(), "entry_day": d.isoformat()}
    hmax = max(P.HOLDS)
    kl = P.daily("klines", sym, d, d + hmax * P.DAY)
    mk = P.daily("markPriceKlines", sym, d, d + hmax * P.DAY)
    for h in P.HOLDS:
        tag = f"H{h}"
        days = [d + k * P.DAY for k in range(h + 1)]
        out[f"{tag}_r_spot"] = np.nan
        if any(x not in kl or x not in mk for x in days):
            out[f"{tag}_status"] = "window_missing"
            continue
        t1 = dt.datetime.combine(d + P.DAY, dt.time(), P.UTC)
        t2 = dt.datetime.combine(d + (h + 1) * P.DAY, dt.time(), P.UTC)
        fr = P.funding(sym, t1, t2)
        if fr is None:
            out[f"{tag}_status"] = "window_missing"
            continue
        p0, p1 = kl[d]["c"], kl[days[-1]]["c"]
        liq = max(mk[x]["h"] for x in days[1:]) >= p0 * (1 + 0.9 / P.LEV)
        fund = P.LEV * sum(
            rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk
        )
        px = P.LEV * (1 - p1 / p0) - P.FEE * P.LEV
        out[f"{tag}_status"] = "ok"
        out[f"{tag}_liq"] = bool(liq)
        out[f"{tag}_funding"] = fund
        out[f"{tag}_n_funding"] = len(fr)
        out[f"{tag}_r_px"] = -1.0 if liq else px
        out[f"{tag}_r"] = -1.0 if liq else px + fund
    return out


def main() -> None:
    names = {r["base_asset"] for r in json.loads(L_MASTER.read_text())["u_master"]}
    assert len(names) == 746
    info = exchange_info()
    syms = [
        s
        for s in prefixes("data/futures/um/monthly/klines/")
        if s.endswith("USDT") and "_" not in s
    ]
    cand = [s for s in syms if base_of(s, names) not in names]
    typ = {s: (info[s]["underlyingType"] if s in info else "NOT_IN_INFO") for s in cand}
    cand = [s for s in cand if typ[s] in ("COIN", "NOT_IN_INFO")]
    with ThreadPoolExecutor(8) as ex:
        t0s = dict(zip(cand, ex.map(P.first_day, cand)))
    rows = [
        {"perp": s, "base": base_of(s, names), "type": typ[s], "t0": t0s[s]}
        for s in cand
        if t0s[s] is not None and T0_MIN <= t0s[s] <= T0_MAX
    ]
    U = pd.DataFrame(rows).sort_values(["base", "t0"]).drop_duplicates("base")
    assert not set(U.base) & names
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, U.perp, U.t0))
    E = U.drop(columns="t0").merge(pd.DataFrame(res), on="perp")
    E.to_csv(P.RUNS / "oos_events.csv", index=False)
    out: dict = {
        "card": "卡片_样本外_v2.md",
        "n_symbols_um_usdt": len(syms),
        "n_not_in_L": int(sum(1 for s in syms if base_of(s, names) not in names)),
        "n_events": int(len(E)),
        "type_counts": U.type.value_counts().to_dict(),
        "events_by_year": E.t0.str[:4].value_counts().sort_index().to_dict(),
        "cells": {},
    }
    for h in P.HOLDS:
        s = E[E[f"H{h}_status"] == "ok"]
        out[f"H{h}_status"] = E[f"H{h}_status"].value_counts().to_dict()
        c = P.cell(s, h) if len(s) >= 2 else {"n": int(len(s))}
        if len(s) >= 2:
            c["perp_price_no_funding_mean"] = float(s[f"H{h}_r_px"].mean())
            c.pop("decomposition_same_events", None)
        out["cells"][f"H{h}_L1"] = c
    p = out["cells"]["H30_L1"]
    if p["n"] < 30:
        reading = "样本不足"
    elif p["ci95_block_month"][0] > 0:
        reading = "1_样本外支持"
    elif p["mean"] <= 0:
        reading = "2_样本外不支持"
    else:
        reading = "3_描述"
    out["reading"] = reading
    (P.RUNS / "oos_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(
        json.dumps(
            {k: out[k] for k in ("n_events", "events_by_year", "reading")},
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()

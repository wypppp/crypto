#!/usr/bin/env python3
"""DQ-25 卡片 v1：大额解锁前做空——事后日程上界版。0 credits。

python unlock_short.py map  → runs/mapping.csv（只做映射与身份核对：每个币只取 2026-09-29 一天的日线）
python unlock_short.py      → runs/events.csv、runs/analysis.json
日程：raw/emissionsIndex.json（DefiLlama 静态数据集快照，sha256 见卡片）。
价格：调用冻结的 DQ-22 perp_replicate.py（data.binance.vision，逐文件核对 CHECKSUM，缓存共用 DQ-22 raw/）。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DQ22 = HERE.parent / "币安新币_上线后做空_DQ-22"
sys.path.insert(0, str(DQ22))
import perp_replicate as P  # noqa: E402

RAW = HERE / "raw"
RUNS = HERE / "runs"
IDX = RAW / "emissionsIndex.json"
IDX_SHA = "5ff6193b0fd0c041f0a5ba4aa7d252fb6183c9cffd5eadeadf293ce6dc5571c1"
PERPS = RAW / "um_usdt_perps.json"
T_MIN, T_MAX = dt.date(2023, 2, 1), dt.date(2026, 8, 31)
CHECK_DAY = dt.date(2026, 9, 29)
PRICE_FROM, PRICE_TO = dt.date(2022, 12, 1), dt.date(2026, 9, 30)
MAIN_CATS = {"insiders", "privateSale"}
EMISSION_CATS = {"farming", "staking", "liquidity", "noncirculating", "burned"}
DAY = P.DAY
FEE = 0.001
TOUCHED: set[str] = set()


def holdout(base: str) -> bool:
    return hashlib.sha256(base.encode()).digest()[0] % 5 == 0


def load_index() -> list[dict]:
    raw = IDX.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == IDX_SHA
    return json.loads(raw)["data"]


def mapping() -> pd.DataFrame:
    perps = set(json.loads(PERPS.read_text()))
    rows = []
    for x in load_index():
        tp = x.get("tokenPrice") or []
        sym = ((tp[0].get("symbol") if tp else "") or "").upper()
        price = tp[0].get("price") if tp else None
        row = {
            "name": x["name"],
            "slug": x.get("protocolSlug"),
            "sym": sym,
            "price": price,
        }
        cand = [
            (p, p + sym + "USDT")
            for p in ("", "1000", "1000000")
            if p + sym + "USDT" in perps
        ]
        if not sym or not cand:
            rows.append({**row, "status": "no_perp"})
            continue
        pre, perp = cand[0]
        row.update(perp=perp, mult=float(pre) if pre else 1.0)
        if holdout(sym):
            rows.append({**row, "status": "holdout_hash"})
            continue
        rows.append({**row, "status": "check"})
    M = pd.DataFrame(rows)
    M.loc[
        M.perp.notna() & M.perp.duplicated(keep=False) & (M.status == "check"), "status"
    ] = "dup_perp"
    chk = M[M.status == "check"]

    def close_on(perp: str) -> float | None:
        TOUCHED.add(perp)
        k = P.daily("klines", perp, CHECK_DAY, CHECK_DAY)
        return k[CHECK_DAY]["c"] if CHECK_DAY in k else None

    with ThreadPoolExecutor(8) as ex:
        cl = list(ex.map(close_on, chk.perp))
    M.loc[chk.index, "close_check"] = cl
    ratio = M.price / (M.close_check / M.mult)
    M["ratio"] = ratio
    m = M.status == "check"
    M.loc[m & M.close_check.isna(), "status"] = "unverifiable"
    M.loc[m & M.close_check.notna() & ((ratio < 0.8) | (ratio > 1.25)), "status"] = (
        "mismatch"
    )
    M.loc[M.status == "check", "status"] = "ok"
    RUNS.mkdir(exist_ok=True)
    M.to_csv(RUNS / "mapping.csv", index=False)
    return M


def unlock_days(x: dict, cats: set[str] | None) -> dict[dt.date, float]:
    by: dict[dt.date, float] = defaultdict(float)
    for e in x.get("events") or []:
        if e.get("unlockType") != "cliff":
            continue
        cat = e.get("category")
        if cats is not None and cat not in cats:
            continue
        if cats is None and cat in EMISSION_CATS:
            continue
        n = sum(v for v in (e.get("noOfTokens") or []) if v)
        if n > 0:
            by[dt.datetime.fromtimestamp(e["timestamp"], P.UTC).date()] += n
    return by


def events_of(x: dict, cats: set[str] | None, thr: float) -> tuple[list, list]:
    """（事件日，全部合格日）：合格日＝当日解锁量 ≥ thr × 最大供应量；事件＝前 30 天内无合格日的合格日，落在 [T_MIN, T_MAX]。"""
    ms = x.get("maxSupply")
    if not ms:
        return [], []
    q = sorted(d for d, v in unlock_days(x, cats).items() if v / ms >= thr)
    ev = [d for i, d in enumerate(q) if all((d - p).days > 30 for p in q[:i])]
    return [d for d in ev if T_MIN <= d <= T_MAX], q


def series(perp: str) -> dict[dt.date, dict]:
    TOUCHED.add(perp)
    fd = P.first_day(perp)
    if fd is None:
        return {}
    return P.daily("klines", perp, max(fd, PRICE_FROM), PRICE_TO)


def short_leg(perp: str, d0: dt.date, d1: dt.date) -> dict:
    TOUCHED.add(perp)
    days = [d0 + k * DAY for k in range((d1 - d0).days + 1)]
    kl = P.daily("klines", perp, d0, d1)
    mk = P.daily("markPriceKlines", perp, d0, d1)
    if any(x not in kl or x not in mk for x in days):
        return {"status": "window_missing"}
    fr = P.funding(
        perp,
        dt.datetime.combine(d0 + DAY, dt.time(), P.UTC),
        dt.datetime.combine(d1 + DAY, dt.time(), P.UTC),
    )
    if fr is None:
        return {"status": "window_missing"}
    p0, p1 = kl[d0]["c"], kl[d1]["c"]
    mk_hi = max(mk[x]["h"] for x in days[1:]) / p0
    last_hi = max(kl[x]["h"] for x in days[1:]) / p0
    liq = mk_hi >= 1.9
    fund = sum(rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk)
    px = 1 - p1 / p0 - FEE
    return {
        "status": "ok",
        "liq": bool(liq),
        "mark_high": mk_hi,
        "last_high": last_hi,
        "funding": fund,
        "r_px": -1.0 if liq else px,
        "r": -1.0 if liq else px + fund,
        "token_ret": p1 / p0 - 1,
    }


def basket(closes: dict, d0: dt.date, d1: dt.date, excl: set[str]) -> tuple[float, int]:
    rs = [
        c[d1]["c"] / c[d0]["c"] - 1
        for s, c in closes.items()
        if s not in excl and d0 in c and d1 in c
    ]
    return (float(np.mean(rs)) - FEE if rs else np.nan), len(rs)


def cell(s: pd.DataFrame, col: str) -> dict:
    r = s[col].values.astype(float)
    blocks = pd.to_datetime(s.entry_day).dt.to_period("M").astype(str).values
    yrs = s["T"].str[:4].values
    srt = np.sort(r)[::-1]
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "ci95_block_month": P.block_ci(r, blocks),
        "ci95_iid": P.iid_ci(r),
        "median": float(np.median(r)),
        "share_pos": float((r > 0).mean()),
        "mean_drop_top3": float(srt[3:].mean()) if len(r) > 3 else None,
        "by_year": {
            y: {"n": int((yrs == y).sum()), "mean": float(r[yrs == y].mean())}
            for y in sorted(set(yrs))
        },
    }


def main() -> None:
    M = mapping()
    ok = M[M.status == "ok"]
    idx = {x["name"]: x for x in load_index()}
    with ThreadPoolExecutor(8) as ex:
        closes = dict(zip(ok.perp, ex.map(series, ok.perp)))
    btc = series("BTCUSDT")
    main_days = {
        r.perp: events_of(idx[r.name], MAIN_CATS, 0.01)[1] for r in ok.itertuples()
    }

    def excl_for(d0: dt.date, d1: dt.date, perp: str) -> set[str]:
        hi = d1 + 30 * DAY
        return {perp} | {
            p for p, q in main_days.items() if any(d0 <= d <= hi for d in q)
        }

    defs = {
        "M": (MAIN_CATS, 0.01, 31, -1),
        "S3_allcats": (None, 0.01, 31, -1),
        "S4_thr5": (MAIN_CATS, 0.05, 31, -1),
        "S5_14d": (MAIN_CATS, 0.01, 15, -1),
        "S6_post": (MAIN_CATS, 0.01, 1, 29),
    }
    jobs = []
    for r in ok.itertuples():
        x = idx[r.name]
        for tag, (cats, thr, back, fwd) in defs.items():
            for T in events_of(x, cats, thr)[0]:
                d0 = T - back * DAY
                d1 = T + fwd * DAY
                jobs.append(
                    {
                        "cell": tag,
                        "sym": r.sym,
                        "perp": r.perp,
                        "T": T,
                        "d0": d0,
                        "d1": d1,
                    }
                )

    def run(j: dict) -> dict:
        out = {**j, "T": j["T"].isoformat(), "entry_day": j["d0"].isoformat()}
        c = closes[j["perp"]]
        if j["d0"] not in c:
            return {
                **out,
                "status": "perp_later"
                if not c or min(c) > j["d0"]
                else "window_missing",
            }
        leg = short_leg(j["perp"], j["d0"], j["d1"])
        out.update(leg)
        if leg["status"] != "ok":
            return out
        b, nb = basket(closes, j["d0"], j["d1"], excl_for(j["d0"], j["d1"], j["perp"]))
        out.update(basket_r=b, basket_n=nb, H30_r=leg["r"] + b)
        if j["d0"] in btc and j["d1"] in btc:
            out["btc_hedged"] = (
                leg["r"] + btc[j["d1"]]["c"] / btc[j["d0"]]["c"] - 1 - FEE
            )
        return out

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(run, jobs))
    E = pd.DataFrame(res).drop(columns=["d0", "d1"])
    E.to_csv(RUNS / "events.csv", index=False)
    bases = {s for s in M[M.perp.isin(TOUCHED)].sym} | {"BTC"}
    assert not any(holdout(b) for b in bases)
    out: dict = {
        "card": "卡片_v1.md",
        "mapping": M.status.value_counts().to_dict(),
        "status": {t: g.status.value_counts().to_dict() for t, g in E.groupby("cell")},
        "cells": {},
    }
    for tag in defs:
        s = E[(E.cell == tag) & (E.status == "ok") & E.H30_r.notna()]
        if len(s) < 2:
            out["cells"][tag] = {"n": int(len(s))}
            continue
        out["cells"][tag] = cell(s, "H30_r")
        out["cells"][tag]["share_liquidated"] = float(s.liq.mean())
        out["cells"][tag]["liq_by_last_price"] = int((s.last_high >= 1.9).sum())
        out["cells"][tag]["liq_by_mark_price"] = int(s.liq.sum())
        out["cells"][tag]["basket_n_median"] = float(s.basket_n.median())
        if tag == "M":
            out["cells"]["S1_short_only"] = cell(s, "r")
            out["cells"]["S2_btc_hedged"] = cell(s[s.btc_hedged.notna()], "btc_hedged")
            out["cells"]["M"]["growth"] = P.growth(s, 30)
            out["cells"]["M"]["mean_short_leg"] = float(s.r.mean())
            out["cells"]["M"]["mean_basket_leg"] = float(s.basket_r.mean())
            out["cells"]["M"]["mean_funding_not_liq"] = float(
                s.loc[~s.liq.astype(bool), "funding"].mean()
            )
    p = out["cells"]["M"]
    if p["n"] < 30:
        reading = "样本不足"
    elif p["ci95_block_month"][0] > 0:
        reading = "1_上界够"
    else:
        reading = "2_上界不够_收口"
    out["reading"] = reading
    (RUNS / "analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(
        json.dumps({"mapping": out["mapping"], "reading": reading}, ensure_ascii=False)
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "map":
        m = mapping()
        print(m.status.value_counts().to_dict())
    else:
        main()

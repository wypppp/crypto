#!/usr/bin/env python3
"""探针：币安首发上市后做空的现货代理（探针_做空代理_2026-09-30.md）。0 credits。

python probe_short_proxy.py → runs/probe_short_proxy.json
只读 DQ-2 正式运行的 206 条；日线来自本地缓存（缺失时从 data.binance.vision 补）。不碰留出样本。
"""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

import dq2_listing_tail as D

RESULTS = D.HERE / "runs" / "20260915T013907Z-full" / "results.csv"
OUT = D.HERE / "runs" / "probe_short_proxy.json"
ENTRY_LAG = (1, 3)  # T0 日后第几日收盘入场；1 为主
HOLD = (7, 30, 90)  # 30 为主
LEV = (1, 2, 3)  # 1 为主
FEE = 0.001
SEED = 20260930


def paths() -> tuple[dict[str, dict], int]:
    ev = pd.read_csv(RESULTS, usecols=["symbol", "T0_day"])
    assert len(ev) == D.N_EXPECTED
    out = {}
    for sym, t0 in zip(ev.symbol, ev.T0_day):
        day0 = dt.date.fromisoformat(t0)
        rows = D.daily_rows(
            sym, day0, day0 + dt.timedelta(days=max(ENTRY_LAG) + max(HOLD))
        )
        out[sym] = {"t0": day0, "rows": rows}
    return out, len(ev)


def one(p: dict, lag: int, hold: int, lev: int) -> float | None:
    rows, d0 = p["rows"], p["t0"] + dt.timedelta(days=lag)
    days = [d0 + dt.timedelta(days=k) for k in range(hold + 1)]
    if any(d not in rows for d in days):
        return None
    entry = rows[d0]["c"]
    if entry <= 0:
        return None
    high = max(rows[d]["h"] for d in days[1:])
    if high >= entry * (1 + 0.9 / lev):
        return -1.0
    return lev * (1 - rows[days[-1]]["c"] / entry) - FEE * lev


def stats(r: np.ndarray, years: np.ndarray) -> dict:
    rng = np.random.default_rng(SEED)
    boot = rng.choice(r, size=(10_000, len(r)), replace=True).mean(axis=1)
    worst = np.sort(r)[: max(1, len(r) // 10)]
    by_year = {
        str(y): {"n": int((years == y).sum()), "mean": float(r[years == y].mean())}
        for y in sorted(set(years))
    }
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "median": float(np.median(r)),
        "share_pos": float((r > 0).mean()),
        "share_liquidated": float((r == -1.0).mean()),
        "worst10pct_mean": float(worst.mean()),
        "mean_drop_worst1": float(np.sort(r)[1:].mean()),
        "by_year": by_year,
    }


def main() -> None:
    ps, n_all = paths()
    out: dict = {"card": "探针_做空代理_2026-09-30.md", "n_events": n_all, "cells": {}}
    for lag in ENTRY_LAG:
        for hold in HOLD:
            for lev in LEV:
                vals, yrs = [], []
                for p in ps.values():
                    x = one(p, lag, hold, lev)
                    if x is not None:
                        vals.append(x)
                        yrs.append(p["t0"].year)
                key = f"lag{lag}_H{hold}_L{lev}"
                out["cells"][key] = stats(np.array(vals), np.array(yrs))
                out["cells"][key]["n_missing"] = n_all - len(vals)
    pm = out["cells"]["lag1_H30_L1"]
    yrs_pos = [v["mean"] > 0 for v in pm["by_year"].values()]
    lam = n_all / ((dt.date(2026, 9, 13) - dt.date(2021, 1, 1)).days / 365.25)
    out["primary"] = pm
    out["lambda_per_year"] = lam
    out["reading"] = (
        "1_先解决再说"
        if pm["ci95"][0] > 0 and sum(yrs_pos) >= 0.75 * len(yrs_pos)
        else ("2_现货代理不支持" if pm["mean"] <= 0 or pm["ci95"][0] <= 0 else "3_描述")
    )
    out["required_r_times_L"] = {"第一阶段": np.log(10) / 12, "第二阶段": 1.075 / 12}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(
        json.dumps(
            {k: out[k] for k in ("n_events", "primary", "reading", "lambda_per_year")},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DQ-23 卡片 v1：币安新上永续做多（轧空右尾）——开发筛查与“先上永续、后上现货”描述。0 credits。

python long_squeeze.py → runs/events.csv、runs/analysis.json、runs/perp_first_path.csv
取数与缓存调用冻结的 DQ-22 perp_replicate.py；公告标题规则调用冻结的 DQ-22 t1_forward.py。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DQ22 = HERE.parent / "币安新币_上线后做空_DQ-22"
sys.path.insert(0, str(DQ22))
import perp_replicate as P  # noqa: E402
import t1_forward as T  # noqa: E402

RUNS = HERE / "runs"
RAW = HERE / "raw"
V1 = DQ22 / "runs" / "events.csv"
V2 = DQ22 / "runs" / "oos_events.csv"
T0_MIN, T0_MAX = dt.date(2023, 1, 1), dt.date(2026, 8, 26)
FRONT = dt.date(2026, 11, 1)
HOLDS = (30, 7)
TPS = {"TP100": 1.0, "TP50": 0.5}
DAY = P.DAY
TOUCHED: set[str] = set()


def universe() -> pd.DataFrame:
    v2 = pd.read_csv(V2, usecols=["perp", "base", "t0"]).assign(part="perp_only")
    v1 = pd.read_csv(V1)
    pf = v1[(v1.perp_lag_days < 0) & v1.perp.notna()].copy()
    pf = pd.DataFrame(
        {
            "perp": pf.perp,
            "base": pf.base,
            "t0": pf.perp_first_day,
            "spot_t0": pf.t0,
            "part": "perp_first",
        }
    )
    U = pd.concat([v2, pf], ignore_index=True)
    U = U[(U.t0 >= T0_MIN.isoformat()) & (U.t0 <= T0_MAX.isoformat())]
    U = U.sort_values(["base", "t0"]).drop_duplicates("base")
    U["holdout_hash"] = U.base.map(T.holdout)
    return U


def long_event(rec: dict) -> dict:
    sym, base = rec["perp"], rec["base"]
    assert not T.holdout(base)
    TOUCHED.add(base)
    t0 = dt.date.fromisoformat(rec["t0"])
    d = t0 + DAY
    out = {"perp": sym, "base": base, "t0": rec["t0"], "entry_day": d.isoformat()}
    kl = P.daily("klines", sym, d, d + 30 * DAY)
    mk = P.daily("markPriceKlines", sym, d, d + 30 * DAY)
    if d not in kl:
        out["status"] = "no_entry_bar"
        return out
    p0 = kl[d]["c"]
    out["status"] = "ok"

    def fund(last: dt.date) -> float | None:
        t1 = dt.datetime.combine(d + DAY, dt.time(), P.UTC)
        t2 = dt.datetime.combine(last + DAY, dt.time(), P.UTC)
        fr = P.funding(sym, t1, t2)
        if fr is None:
            return None
        return -P.LEV * sum(
            rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk
        )

    for h in HOLDS:
        tag = f"H{h}"
        days = [d + k * DAY for k in range(h + 1)]
        if any(x not in kl or x not in mk for x in days):
            out[f"{tag}_status"] = "window_missing"
            continue
        f = fund(days[-1])
        if f is None:
            out[f"{tag}_status"] = "window_missing"
            continue
        liq = min(mk[x]["l"] for x in days[1:]) <= p0 * (1 - 0.9 / P.LEV)
        px = P.LEV * (kl[days[-1]]["c"] / p0 - 1) - P.FEE * P.LEV
        out[f"{tag}_status"] = "ok"
        out[f"{tag}_liq"] = bool(liq)
        out[f"{tag}_funding"] = f
        out[f"{tag}_r_px"] = -1.0 if liq else px
        out[f"{tag}_r"] = -1.0 if liq else px + f
        out[f"{tag}_max_high"] = max(kl[x]["h"] for x in days[1:]) / p0
    if out.get("H30_status") != "ok":
        return out
    days = [d + k * DAY for k in range(31)]
    for tag, k in TPS.items():
        hit = next((x for x in days[1:] if kl[x]["h"] >= p0 * (1 + k)), None)
        if hit is None:
            out[f"{tag}_r"], out[f"{tag}_liq"] = out["H30_r"], out["H30_liq"]
            out[f"{tag}_hit_day"] = None
            continue
        upto = [x for x in days[1:] if x <= hit]
        liq = min(mk[x]["l"] for x in upto) <= p0 * (1 - 0.9 / P.LEV)
        f = fund(hit)
        out[f"{tag}_liq"] = bool(liq)
        out[f"{tag}_hit_day"] = (hit - d).days
        out[f"{tag}_r"] = -1.0 if liq else P.LEV * k - P.FEE * P.LEV + f
    return out


def cell(s: pd.DataFrame, col: str) -> dict:
    r = s[col].values.astype(float)
    blocks = pd.to_datetime(s.entry_day).dt.to_period("M").astype(str).values
    yrs = s.t0.str[:4].values
    srt = np.sort(r)[::-1]
    liq = s[col.replace("_r", "_liq")].astype(bool)
    out = {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "ci95_block_month": P.block_ci(r, blocks),
        "ci95_iid": P.iid_ci(r),
        "sd": float(r.std(ddof=1)),
        "median": float(np.median(r)),
        "share_pos": float((r > 0).mean()),
        "share_liquidated": float(liq.mean()),
        "max": float(srt[0]),
        "mean_drop_top1": float(srt[1:].mean()),
        "mean_drop_top3": float(srt[3:].mean()),
        "by_year": {
            y: {"n": int((yrs == y).sum()), "mean": float(r[yrs == y].mean())}
            for y in sorted(set(yrs))
        },
    }
    fcol = col.replace("_r", "_funding")
    if fcol in s:
        out["funding_mean_not_liquidated"] = float(s.loc[~liq, fcol].mean())
        out["price_only_mean"] = float(s[col.replace("_r", "_r_px")].mean())
    return out


def ann_days() -> dict[str, str]:
    """公告目录 48：每个币名最早一篇宣布现货上市的公告日。快照存 raw/。"""
    arts = T.cms_articles(dt.date(2022, 10, 1))
    RAW.mkdir(exist_ok=True)
    (RAW / "cms48_articles.json").write_text(json.dumps(arts, ensure_ascii=False))
    first: dict[str, str] = {}
    for a in sorted(arts, key=lambda a: a["day"]):
        for t in T.listing_tickers(a["title"]):
            first.setdefault(t.strip().upper(), a["day"])
    return first


def perp_first_path(U: pd.DataFrame) -> pd.DataFrame:
    pf = U[(U.part == "perp_first") & ~U.holdout_hash]
    first = ann_days()
    rows = []
    for r in pf.itertuples():
        assert not T.holdout(r.base)
        TOUCHED.add(r.base)
        a = first.get(r.base.upper())
        row = {"base": r.base, "perp": r.perp, "perp_t0": r.t0, "spot_t0": r.spot_t0}
        row["ann_day"] = a
        if a is None:
            rows.append(row)
            continue
        A = dt.date.fromisoformat(a)
        S = dt.date.fromisoformat(r.spot_t0)
        P0 = dt.date.fromisoformat(r.t0)
        assert S < FRONT
        kl = P.daily("klines", r.perp, max(P0, A - 8 * DAY), S + 31 * DAY)
        c = {k: v["c"] for k, v in kl.items()}

        def ratio(x: dt.date, y: dt.date) -> float:
            return c[y] / c[x] if x in c and y in c else np.nan

        row.update(
            days_perp_to_ann=(A - P0).days,
            days_ann_to_spot=(S - A).days,
            pre_week=ratio(A - 8 * DAY, A - DAY),
            ann_day=a,
            ann_jump=ratio(A - DAY, A),
            ann_to_spot=ratio(A, S),
            spot_to_d1=ratio(S, S + DAY),
            d1_to_d31=ratio(S + DAY, S + 31 * DAY),
        )
        rows.append(row)
    return pd.DataFrame(rows)


def describe(x: pd.Series) -> dict:
    x = x.dropna()
    return {
        "n": int(len(x)),
        "mean": float(x.mean()) if len(x) else None,
        "median": float(x.median()) if len(x) else None,
        "share_up": float((x > 1).mean()) if len(x) else None,
    }


def main() -> None:
    U = universe()
    assert (U.t0 < FRONT.isoformat()).all()
    UH = U[~U.holdout_hash]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(long_event, UH.to_dict("records")))
    E = UH.merge(pd.DataFrame(res).drop(columns=["base", "t0"]), on="perp")
    RUNS.mkdir(exist_ok=True)
    E.to_csv(RUNS / "events.csv", index=False)
    ok30 = E[E.get("H30_status") == "ok"]
    ok7 = E[E.get("H7_status") == "ok"]
    out: dict = {
        "card": "卡片_v1.md",
        "universe": {
            "n_before_hash": int(len(U)),
            "n_after_hash": int(len(UH)),
            "by_part": UH.part.value_counts().to_dict(),
            "by_year": UH.t0.str[:4].value_counts().sort_index().to_dict(),
        },
        "H30_status": E.get("H30_status").value_counts(dropna=False).to_dict(),
        "cells": {
            "M_H30": cell(ok30, "H30_r"),
            "S1_H7": cell(ok7, "H7_r"),
            "S2_H30_TP100": cell(ok30, "TP100_r"),
            "S3_H30_TP50": cell(ok30, "TP50_r"),
            "S4_perp_only_199": cell(ok30[ok30.part == "perp_only"], "H30_r"),
            "S5_perp_first": cell(ok30[ok30.part == "perp_first"], "H30_r"),
        },
    }
    out["cells"]["M_H30"]["growth"] = P.growth(ok30, 30)
    p = out["cells"]["M_H30"]
    if p["n"] < 30:
        reading = "样本不足"
    elif p["ci95_block_month"][0] > 0:
        reading = "1_开发正结果"
    elif p["mean"] <= 0:
        reading = "2_停止该实现"
    else:
        reading = "3_描述"
    out["reading"] = reading
    path = perp_first_path(U)
    path.to_csv(RUNS / "perp_first_path.csv", index=False)
    yr = UH.assign(y=UH.t0.str[:4]).groupby("y")
    out["perp_first_describe"] = {
        "n": int(len(path)),
        "n_with_ann": int(path.ann_day.notna().sum()),
        "segments": {
            k: describe(path[k])
            for k in ("pre_week", "ann_jump", "ann_to_spot", "spot_to_d1", "d1_to_d31")
            if k in path
        },
        "days_perp_to_ann": path.get("days_perp_to_ann", pd.Series(dtype=float))
        .describe()
        .to_dict(),
        "days_ann_to_spot": path.get("days_ann_to_spot", pd.Series(dtype=float))
        .describe()
        .to_dict(),
        "base_rate_later_spot_by_perp_year": {
            y: {"n": int(len(g)), "later_spot": int((g.part == "perp_first").sum())}
            for y, g in yr
        },
    }
    assert not any(T.holdout(b) for b in TOUCHED)
    (RUNS / "analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(
        json.dumps(
            {"universe": out["universe"], "reading": reading}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()

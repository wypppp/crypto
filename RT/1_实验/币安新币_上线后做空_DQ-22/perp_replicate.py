#!/usr/bin/env python3
"""DQ-22 卡片 v1：币安首发上线满一天后做空 U 本位永续——同批事件的永续复现。0 credits。

python perp_replicate.py → runs/events.csv、runs/analysis.json
数据：data.binance.vision 的 U 本位永续日线、标记价格日线、资金费月文件（逐文件核对 CHECKSUM，缓存在 raw/）；
现货沿用 DQ-2 缓存。只为 DQ-2 正式运行的 206 个币名构造地址，断言不触及留出样本。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DQ2 = HERE.parent / "币安上市_上市后价格右尾_DQ-2"
sys.path.insert(0, str(DQ2))
import dq2_listing_tail as D  # noqa: E402

RESULTS = DQ2 / "runs" / "20260915T013907Z-full" / "results.csv"
RAW = HERE / "raw"
RUNS = HERE / "runs"
BASE = "https://data.binance.vision/data/futures/um"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
HOLDS = (30, 7)  # 30 为主
LEV = 1
FEE = 0.001
SEED = 20260930
DAY = dt.timedelta(days=1)
UTC = dt.timezone.utc
TOUCHED: set[str] = set()
SYMS: set[str] = set()


def get(url: str) -> bytes | None:
    """404 返回 None；其他错误重试。"""
    url = urllib.parse.quote(url, safe=":/.-_?=&")
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rt-dq22"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == 4:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if i == 4:
                raise
        time.sleep(2 * (i + 1))
    return None


def fetch(rel: str) -> bytes | None:
    """取归档文件并核对 CHECKSUM；不存在返回 None。缓存于 raw/。"""
    dest = RAW / rel
    miss = dest.with_name(dest.name + ".ABSENT")
    if miss.exists():
        return None
    if dest.exists():
        return dest.read_bytes()
    data = get(f"{BASE}/{rel}")
    if data is None:
        miss.parent.mkdir(parents=True, exist_ok=True)
        miss.write_text("404\n")
        return None
    chk = get(f"{BASE}/{rel}.CHECKSUM")
    if chk is None or hashlib.sha256(data).hexdigest() != chk.decode().split()[0]:
        raise RuntimeError(f"CHECKSUM {rel}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data


def s3_keys(prefix: str) -> list[str]:
    keys, marker = [], ""
    while True:
        q = f"{S3}?delimiter=/&prefix=data/futures/um/{prefix}&marker={marker}"
        body = get(q)
        if body is None:
            return keys
        txt = body.decode()
        page = re.findall(r"<Key>([^<]+)</Key>", txt)
        keys += [k for k in page if k.endswith(".zip")]
        if "<IsTruncated>true</IsTruncated>" not in txt or not page:
            return keys
        marker = page[-1]


def first_day(sym: str) -> dt.date | None:
    """该永续在归档中的第一根日线日期。"""
    SYMS.add(sym)
    mon = s3_keys(f"monthly/klines/{sym}/1d/")
    if mon:
        ym = min(re.search(r"-(\d{4})-(\d{2})\.zip$", k).groups() for k in mon)
        rows = D.parse_klines(
            fetch(f"monthly/klines/{sym}/1d/{sym}-1d-{ym[0]}-{ym[1]}.zip")
        )
        return min(D.us_date(r["t"]) for r in rows)
    day = s3_keys(f"daily/klines/{sym}/1d/")
    if day:
        return min(
            dt.date.fromisoformat(re.search(r"-(\d{4}-\d{2}-\d{2})\.zip$", k).group(1))
            for k in day
        )
    return None


def daily(kind: str, sym: str, d1: dt.date, d2: dt.date) -> dict[dt.date, dict]:
    """kind ∈ {klines, markPriceKlines}；月文件缺时逐日补。"""
    out: dict[dt.date, dict] = {}
    y, m = d1.year, d1.month
    while (y, m) <= (d2.year, d2.month):
        data = fetch(f"monthly/{kind}/{sym}/1d/{sym}-1d-{y:04d}-{m:02d}.zip")
        if data is not None:
            rows = D.parse_klines(data)
        else:
            rows, day = [], max(d1, dt.date(y, m, 1))
            while day <= min(d2, D.month_last_day(y, m)):
                x = fetch(f"daily/{kind}/{sym}/1d/{sym}-1d-{day.isoformat()}.zip")
                if x is not None:
                    rows += D.parse_klines(x)
                day += DAY
        for r in rows:
            d = D.us_date(r["t"])
            if d1 <= d <= d2:
                out[d] = r
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def funding(sym: str, t1: dt.datetime, t2: dt.datetime) -> list[tuple] | None:
    """[t1, t2) 内的结算 (时刻, 费率)；任一所需月文件缺失返回 None。"""
    out = []
    y, m = t1.year, t1.month
    while (y, m) <= (t2.year, t2.month):
        data = fetch(f"monthly/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip")
        if data is None:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt = z.read(z.namelist()[0]).decode()
        for row in csv.reader(io.StringIO(txt)):
            if not row or not row[0].isdigit():
                continue
            t = dt.datetime.fromtimestamp(int(row[0]) / 1000, UTC)
            if t1 <= t < t2:
                out.append((t, float(row[2])))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def event(rec: dict) -> dict:
    base, spot, t0 = rec["base"], rec["symbol"], dt.date.fromisoformat(rec["T0_day"])
    TOUCHED.add(base)
    d = t0 + DAY
    out = {"base": base, "spot": spot, "t0": t0.isoformat(), "entry_day": d.isoformat()}
    firsts = {}
    for sym in (f"{base}USDT", f"1000{base}USDT", f"1000000{base}USDT"):
        fd = first_day(sym)
        if fd is not None:
            firsts[sym] = fd
    if not firsts:
        out["status"] = "no_perp"
        return out
    earliest = min(firsts.values())
    cands = [s for s, fd in firsts.items() if fd == earliest]
    if len(cands) > 1:
        out["status"] = "ambiguous"
        return out
    sym = cands[0]
    out.update(
        perp=sym,
        perp_first_day=earliest.isoformat(),
        perp_lag_days=(earliest - t0).days,
    )
    if earliest > d:
        out["status"] = "perp_later"
        return out
    out["status"] = "perp_at_entry"
    hmax = max(HOLDS)
    kl = daily("klines", sym, d, d + hmax * DAY)
    mk = daily("markPriceKlines", sym, d, d + hmax * DAY)
    sp = D.daily_rows(spot, d, d + hmax * DAY)
    for h in HOLDS:
        days = [d + k * DAY for k in range(h + 1)]
        tag = f"H{h}"
        if any(x not in kl or x not in mk for x in days):
            out[f"{tag}_status"] = "window_missing"
            continue
        t1 = dt.datetime.combine(d + DAY, dt.time(), UTC)
        t2 = dt.datetime.combine(d + (h + 1) * DAY, dt.time(), UTC)
        fr = funding(sym, t1, t2)
        if fr is None:
            out[f"{tag}_status"] = "window_missing"
            continue
        p0, p1 = kl[d]["c"], kl[days[-1]]["c"]
        liq = max(mk[x]["h"] for x in days[1:]) >= p0 * (1 + 0.9 / LEV)
        fund = LEV * sum(
            rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk
        )
        px = LEV * (1 - p1 / p0) - FEE * LEV
        out[f"{tag}_status"] = "ok"
        out[f"{tag}_liq"] = bool(liq)
        out[f"{tag}_funding"] = fund
        out[f"{tag}_n_funding"] = len(fr)
        out[f"{tag}_r_px"] = -1.0 if liq else px
        out[f"{tag}_r"] = -1.0 if liq else px + fund
        if all(x in sp for x in days) and sp[d]["c"] > 0:
            s0 = sp[d]["c"]
            sliq = max(sp[x]["h"] for x in days[1:]) >= s0 * (1 + 0.9 / LEV)
            out[f"{tag}_r_spot"] = (
                -1.0 if sliq else LEV * (1 - sp[days[-1]]["c"] / s0) - FEE * LEV
            )
    return out


def block_ci(r: np.ndarray, blocks: np.ndarray, n: int = 10_000) -> list[float]:
    rng = np.random.default_rng(SEED)
    ub = np.unique(blocks)
    groups = [r[blocks == b] for b in ub]
    means = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        x = np.concatenate([groups[j] for j in pick])
        means[i] = x.mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def iid_ci(r: np.ndarray, n: int = 10_000) -> list[float]:
    rng = np.random.default_rng(SEED)
    m = rng.choice(r, size=(n, len(r)), replace=True).mean(axis=1)
    return [float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))]


def growth(s: pd.DataFrame, h: int) -> dict:
    """同一入场月（H30）或 ISO 周（H7）的事件等分资金；空期回收 0。"""
    day = pd.to_datetime(s.entry_day)
    fq = "M" if h == 30 else "W"
    per = day.dt.to_period(fq)
    grp = s.assign(per=per).groupby("per")[f"H{h}_r"].mean()
    full = pd.period_range(per.min(), per.max(), freq=fq)
    R = grp.reindex(full, fill_value=0.0)
    k = 12 if h == 30 else 52
    fs = np.round(np.arange(0.01, 1.0001, 0.01), 2)
    G = [float(np.mean(np.log(np.maximum(1 + f * R.values, 1e-12)))) for f in fs]
    i = int(np.argmax(G))
    by_year = {}
    for y in sorted(set(p.year for p in R.index)):
        v = R[[p.year == y for p in R.index]].values
        by_year[str(y)] = float(np.mean(np.log(np.maximum(1 + fs[i] * v, 1e-12))) * k)
    return {
        "n_periods": int(len(R)),
        "n_periods_with_events": int((grp.index.size)),
        "f_star": float(fs[i]),
        "g_star_per_year": G[i] * k,
        "g_f1_per_year": G[-1] * k,
        "g_by_year_at_f_star": by_year,
    }


def cell(s: pd.DataFrame, h: int) -> dict:
    t = f"H{h}"
    r = s[f"{t}_r"].values.astype(float)
    blocks = pd.to_datetime(s.entry_day).dt.to_period("M").astype(str).values
    yrs = s.t0.str[:4].values
    sub = s[s[f"{t}_r_spot"].notna()]
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "ci95_block_month": block_ci(r, blocks),
        "ci95_iid": iid_ci(r),
        "sd": float(r.std(ddof=1)),
        "median": float(np.median(r)),
        "share_pos": float((r > 0).mean()),
        "share_liquidated": float(s[f"{t}_liq"].mean()),
        "funding_contrib_mean": float(s[f"{t}_funding"].mean()),
        "n_funding_settlements_median": float(s[f"{t}_n_funding"].median()),
        "by_year": {
            y: {"n": int((yrs == y).sum()), "mean": float(r[yrs == y].mean())}
            for y in sorted(set(yrs))
        },
        "decomposition_same_events": {
            "n": int(len(sub)),
            "spot_proxy": float(sub[f"{t}_r_spot"].mean()),
            "perp_price_no_funding": float(sub[f"{t}_r_px"].mean()),
            "perp_full": float(sub[f"{t}_r"].mean()),
        },
        "growth": growth(s, h),
    }


def main() -> None:
    ev = pd.read_csv(RESULTS, usecols=["base", "symbol", "T0_day"])
    assert len(ev) == D.N_EXPECTED
    allowed = set(ev.base)
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(event, ev.to_dict("records")))
    assert TOUCHED == allowed
    # 访问过的合约代码都能映射回这 206 个币名；且没有一个币名命中 Probe L 的留出哈希规则
    ok_syms = {f"{p}{b}USDT" for b in allowed for p in ("", "1000", "1000000")}
    assert SYMS <= ok_syms
    assert not any(hashlib.sha256(b.encode()).digest()[0] % 5 == 0 for b in TOUCHED)
    E = pd.DataFrame(rows)
    RUNS.mkdir(exist_ok=True)
    E.to_csv(RUNS / "events.csv", index=False)
    years = (dt.date(2026, 9, 13) - dt.date(2021, 1, 1)).days / 365.25
    out: dict = {
        "card": "卡片_永续复现_v1.md",
        "n_frame": int(len(E)),
        "status": E.status.value_counts().to_dict(),
        "perp_lag_days_later": E.loc[E.status == "perp_later", "perp_lag_days"]
        .describe()
        .to_dict(),
        "lambda_exec_per_year": float((E.status == "perp_at_entry").sum() / years),
        "exec_by_year": {
            y: {"n": int(len(g)), "exec": int((g.status == "perp_at_entry").sum())}
            for y, g in E.assign(y=E.t0.str[:4]).groupby("y")
        },
        "cells": {},
    }
    for h in HOLDS:
        st = E.get(f"H{h}_status")
        s = E[st == "ok"] if st is not None else E.iloc[0:0]
        out[f"H{h}_status"] = (
            E.loc[E.status == "perp_at_entry", f"H{h}_status"].value_counts().to_dict()
        )
        out["cells"][f"H{h}_L1"] = cell(s, h) if len(s) >= 2 else {"n": int(len(s))}
    p = out["cells"]["H30_L1"]
    if p["n"] < 30:
        reading = "样本不足"
    elif p["ci95_block_month"][0] > 0:
        reading = "1_继续"
    elif p["mean"] <= 0:
        reading = "2_停止该实现"
    else:
        reading = "3_描述"
    out["reading"] = reading
    if p["n"] >= 2 and p["mean"] > 0:
        se55 = p["sd"] / np.sqrt(55)
        z = p["mean"] / se55 - 1.6449
        out["holdout55_power"] = float(0.5 * (1 + math.erf(z / math.sqrt(2))))
    out["stage_thresholds"] = {"第一阶段_g": 2.3026, "第二阶段_g": 1.075}
    (RUNS / "analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(
        json.dumps(
            {k: out[k] for k in ("status", "lambda_exec_per_year", "reading")},
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()

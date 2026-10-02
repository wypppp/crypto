"""K1 路径的修正版（代码审计 10-03 第 14 处）。原 k1_paths.py 不改；F108 的 K1 只是描述量，按总控第十轮第 6 条只修代码、不重跑。

第 14 处：原版把“该秒最后一笔成交价”与“1 秒 K 线收盘价”挂在该秒的起点，于是“t 秒时的最新成交价”可能用到 t 到 t＋1 秒之间的成交，
最多约 1 秒的未来信息（审计反例：5.000 秒价 1、5.900 秒价 2，请求第 5 秒应得 1，原版得 2）。
v2：逐笔成交（币安 aggTrades、Bybit）按毫秒时间戳保留每一笔；1 秒 K 线的收盘挂在该秒的终点（开盘＋1000 毫秒）。
px_at(t) 取时间戳 ≤ t×1000 毫秒的最后一点。成交额按点的时间戳落在 (t0＋L, t0＋X] 内求和。
"""

import bisect
import csv
import gzip

import k1_paths as K


def series(r):
    """返回 (毫秒时间戳列表, {毫秒: (价格, 成交额)}, 来源)；只保留 [t0−120 s, t0+660 s]。"""
    s = r["_sym"]
    t0 = int(r["_t0"].timestamp())
    lo, hi = t0 - 120, t0 + 660
    pts = {}
    src = None
    for d in K.days(r["_t0"]):
        sp = K.CACHE / "spot" / s / f"{s}-1s-{d}.zip"
        um = K.CACHE / "um" / s / f"{s}-aggTrades-{d}.zip"
        by = K.CACHE / "bybit" / s / f"{s}{d}.csv.gz"
        if sp.exists() and sp.stat().st_size:
            src = "binance_spot_1s"
            for x in K.rows_of(sp, lo, hi, 0):
                if float(x[5]) > 0:  # 只取有成交的秒；收盘挂在该秒终点
                    pts[K.ms(x[0]) + 1000] = (float(x[4]), float(x[7]))
        elif um.exists() and um.stat().st_size:
            src = "binance_um_aggTrades"
            for x in K.rows_of(um, lo, hi, 5):
                t, p, q = K.ms(x[5]), float(x[1]), float(x[2])
                last, vol = pts.get(t, (p, 0.0))
                pts[t] = (p, vol + p * q)  # 同一毫秒多笔：价取文件顺序最后一笔，额相加
        elif by.exists() and by.stat().st_size:
            src = "bybit_trades"
            with gzip.open(by, "rt") as g:
                tr = sorted(
                    (
                        float(x["timestamp"]),
                        float(x["price"]),
                        float(x["foreignNotional"]),
                    )
                    for x in csv.DictReader(g)
                    if lo <= float(x["timestamp"]) <= hi + 1
                )
            for t, p, qv in tr:
                k = int(round(t * 1000))
                last, vol = pts.get(k, (p, 0.0))
                pts[k] = (p, vol + qv)
    return sorted(pts), pts, src


def px_at(ts, pts, sec):
    """sec 秒（含 sec.000）及之前的最后一笔成交价。"""
    i = bisect.bisect_right(ts, sec * 1000) - 1
    return pts[ts[i]][0] if i >= 0 else None


def calc():
    """同 K.calc，换用毫秒序列；输出 results/K1_paths_v2.csv。"""
    K.OUT.mkdir(exist_ok=True)
    res = []
    for r in K.events():
        t0 = int(r["_t0"].timestamp())
        ts, pts, src = series(r)
        row = {
            k: r.get(k, "")
            for k in (
                "exchange",
                "ticker",
                "published_utc",
                "ts_precision",
                "prior_korean_krw_listing",
                "binance_spot_usdt",
                "binance_usdm_perp",
                "bybit_usdt_perp",
            )
        }
        g = r.get("prior_korean_krw_listing")
        row["group"] = "first" if g == "no" else ("repeat" if g == "yes" else "unknown")
        row["src"] = src or "none"
        if not ts:
            res.append(row)
            continue
        ref = px_at(ts, pts, t0 - 60)
        p0 = px_at(ts, pts, t0)
        row["pre60"] = (p0 / ref - 1) if ref and p0 else ""
        first_move = ""
        if ref:
            a, b = (
                bisect.bisect_left(ts, (t0 - 60) * 1000),
                bisect.bisect_right(ts, (t0 + 600) * 1000),
            )
            for k in ts[a:b]:
                if abs(pts[k][0] / ref - 1) >= 0.01:
                    first_move = k / 1000 - t0
                    break
        row["first_move_s"] = first_move
        for L in K.LAGS:
            e = px_at(ts, pts, t0 + L)
            for X in K.EXITS:
                x = px_at(ts, pts, t0 + X)
                row[f"r_L{L}_X{X}"] = (x / e - 1) if e and x else ""
                if L == 5:
                    row[f"qvol_L5_X{X}"] = sum(
                        v[1]
                        for k, v in pts.items()
                        if (t0 + L) * 1000 < k <= (t0 + X) * 1000
                    )
        res.append(row)
    keys = []
    for x in res:
        for k in x:
            if k not in keys:
                keys.append(k)
    with open(K.OUT / "K1_paths_v2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(res)

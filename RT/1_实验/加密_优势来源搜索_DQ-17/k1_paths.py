"""K1：韩国所韩元上币公告 → 币安同币的秒级价格路径（S2_筛选.md §3 K1，判据已先写定）。

只用免费公开归档：币安现货 1 秒 K 线（优先）；没有现货时用币安 U 本位永续逐笔成交（aggTrades）；两者都没有时用 Bybit 永续逐笔成交（public.bybit.com）。都聚合到秒。
入场价 = t0+L 秒时的最新成交价（L = 2、5、10）；退出价 = t0+60/300/600 秒时的最新成交价；不取事后最高。
另记 t0 前 60 秒到 t0 的涨幅（查有无更早渠道）和价格首次偏离 t0−60 s 水平 ≥1% 的时刻。
用法：python3 k1_paths.py fetch → 下载缓存；python3 k1_paths.py calc → 写 results/K1_paths.csv
"""
import csv, sys, zipfile, gzip, io, datetime as dt, urllib.request, bisect
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE / "raw" / "K1_events.csv"
CACHE = HERE / "raw" / "prices_k1"
OUT = HERE / "results"
SPOT = "https://data.binance.vision/data/spot/daily/klines"
UM = "https://data.binance.vision/data/futures/um/daily/aggTrades"
BYBIT = "https://public.bybit.com/trading"
LAGS = (2, 5, 10)
EXITS = (60, 300, 600)
COST = 0.003
UTC = dt.timezone.utc


def get(url, dest):
    if dest.exists():
        return dest if dest.stat().st_size > 0 else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
    except Exception as e:
        dest.write_bytes(b"")
        print("miss", url, getattr(e, "code", e))
        return None
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return dest


def parse_utc(v):
    v = (v or "").strip().replace("Z", "").replace("+00:00", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(v, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    return None


def events():
    out = []
    for r in csv.DictReader(open(EV, encoding="utf-8")):
        t0 = parse_utc(r.get("published_utc"))
        if t0 is None or "KRW" not in (r.get("markets") or "KRW"):
            continue
        r["_t0"] = t0
        r["_sym"] = r["ticker"].strip().upper() + "USDT"
        out.append(r)
    return out


def days(t0):
    d = t0.date()
    ds = {d}
    if t0.hour == 23:
        ds.add(d + dt.timedelta(days=1))
    if t0.hour == 0:
        ds.add(d - dt.timedelta(days=1))
    return sorted(ds)


def fetch():
    from concurrent.futures import ThreadPoolExecutor
    jobs = []
    for r in events():
        s = r["_sym"]
        for d in days(r["_t0"]):
            if r.get("binance_spot_usdt") == "yes":
                f = f"{s}-1s-{d}.zip"
                jobs.append((f"{SPOT}/{s}/1s/{f}", CACHE / "spot" / s / f))
            elif r.get("binance_usdm_perp") == "yes":
                f = f"{s}-aggTrades-{d}.zip"
                jobs.append((f"{UM}/{s}/{f}", CACHE / "um" / s / f))
            elif r.get("bybit_usdt_perp") == "yes":
                f = f"{s}{d}.csv.gz"
                jobs.append((f"{BYBIT}/{s}/{f}", CACHE / "bybit" / s / f))
    print("jobs", len(jobs), flush=True)
    with ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(lambda j: get(*j), jobs), 1):
            if i % 20 == 0:
                print("done", i, flush=True)
    print("fetch finished", flush=True)


def rows_of(p, lo=None, hi=None, tcol=0):
    """逐行读取 zip 内 CSV；给定 lo/hi（秒）时只保留该时间窗内的行，避免整份读入内存。"""
    if not p.exists() or p.stat().st_size == 0:
        return
    with zipfile.ZipFile(p) as z, z.open(z.namelist()[0]) as fh:
        for line in io.TextIOWrapper(fh, encoding="utf-8"):
            x = line.rstrip("\n").split(",")
            if not x[0].lstrip("-").isdigit():
                continue  # 表头
            if lo is not None:
                sec = ms(x[tcol]) // 1000
                if sec < lo or sec > hi:
                    continue
            yield x


def ms(t):
    t = int(t)
    return t // 1000 if t > 10**14 else t


def series(r):
    """返回 (秒级时间戳列表, 该秒最后成交价, 该秒成交额) 与数据来源；只保留 [t0−120 s, t0+660 s]。"""
    s = r["_sym"]
    t0 = int(r["_t0"].timestamp())
    lo, hi = t0 - 120, t0 + 660
    pts = {}
    src = None
    for d in days(r["_t0"]):
        sp = CACHE / "spot" / s / f"{s}-1s-{d}.zip"
        um = CACHE / "um" / s / f"{s}-aggTrades-{d}.zip"
        by = CACHE / "bybit" / s / f"{s}{d}.csv.gz"
        if sp.exists() and sp.stat().st_size:
            src = "binance_spot_1s"
            for x in rows_of(sp, lo, hi, 0):
                if float(x[5]) > 0:  # 只取有成交的秒
                    pts[ms(x[0]) // 1000] = (float(x[4]), float(x[7]))
        elif um.exists() and um.stat().st_size:
            src = "binance_um_aggTrades"
            for x in rows_of(um, lo, hi, 5):
                sec = ms(x[5]) // 1000
                p, q = float(x[1]), float(x[2])
                last, vol = pts.get(sec, (p, 0.0))
                pts[sec] = (p, vol + p * q)  # 文件按时间排序，最后一笔即该秒收盘
        elif by.exists() and by.stat().st_size:
            src = "bybit_trades"
            with gzip.open(by, "rt") as g:
                tr = sorted((float(x["timestamp"]), float(x["price"]), float(x["foreignNotional"]))
                            for x in csv.DictReader(g) if lo <= float(x["timestamp"]) <= hi + 1)
            for t, p, qv in tr:
                sec = int(t)
                last, vol = pts.get(sec, (p, 0.0))
                pts[sec] = (p, vol + qv)
    ts = sorted(pts)
    return ts, pts, src


def px_at(ts, pts, sec):
    """sec 时刻（含）之前最后一笔成交价。"""
    i = bisect.bisect_right(ts, sec) - 1
    return pts[ts[i]][0] if i >= 0 else None


def calc():
    OUT.mkdir(exist_ok=True)
    res = []
    for r in events():
        t0 = int(r["_t0"].timestamp())
        ts, pts, src = series(r)
        row = {k: r.get(k, "") for k in ("exchange", "ticker", "published_utc", "ts_precision",
                                          "prior_korean_krw_listing", "binance_spot_usdt", "binance_usdm_perp", "bybit_usdt_perp")}
        row["group"] = "first" if r.get("prior_korean_krw_listing") == "no" else ("repeat" if r.get("prior_korean_krw_listing") == "yes" else "unknown")
        row["src"] = src or "none"
        if not ts:
            res.append(row)
            continue
        ref = px_at(ts, pts, t0 - 60)
        p0 = px_at(ts, pts, t0)
        row["pre60"] = (p0 / ref - 1) if ref and p0 else ""
        first_move = ""
        if ref:
            for sec in ts[bisect.bisect_left(ts, t0 - 60): bisect.bisect_right(ts, t0 + 600)]:
                if abs(pts[sec][0] / ref - 1) >= 0.01:
                    first_move = sec - t0
                    break
        row["first_move_s"] = first_move
        for L in LAGS:
            e = px_at(ts, pts, t0 + L)
            for X in EXITS:
                x = px_at(ts, pts, t0 + X)
                row[f"r_L{L}_X{X}"] = (x / e - 1) if e and x else ""
                if L == 5:
                    row[f"qvol_L5_X{X}"] = sum(v[1] for s2, v in pts.items() if t0 + L < s2 <= t0 + X)
        res.append(row)
    keys = []
    for x in res:
        for k in x:
            if k not in keys:
                keys.append(k)
    with open(OUT / "K1_paths.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(res)
    print(f"写入 {OUT / 'K1_paths.csv'}，{len(res)} 行")


if __name__ == "__main__":
    {"fetch": fetch, "calc": calc}[sys.argv[1]]()

"""K2：DeFi 黑客告警后做空的价格路径（S2_筛选.md §3 K2，判据已先写定）。

只用 data.binance.vision 的免费文件：U 本位永续 1 分钟 K 线（日文件）与资金费率（月文件）。
入场 = 告警时刻 +5 分钟后第一根整分钟 K 线的开盘价；退出 = 入场后 3 h、9 h 那根 K 线的收盘价。
做空收益 = −(退出/入场 − 1)；扣 0.2% 往返成本；资金费按入场到退出之间的结算点累加（费率为正时空头收取）。
容量代理 = 入场后 9 h 永续成交额（quote）的 1%。
用法：python3 k2_paths.py fetch  → 下载缓存；python3 k2_paths.py calc → 计算并写 results/K2_paths.csv
"""
import csv, io, sys, zipfile, datetime as dt, urllib.request, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE / "raw" / "K2_events.csv"
CACHE = HERE / "raw" / "prices"
OUT = HERE / "results"
BASE = "https://data.binance.vision/data/futures/um"
COST = 0.002
UTC = dt.timezone.utc


def get(url, dest):
    if dest.exists():
        return dest if dest.stat().st_size > 0 else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except Exception as e:  # 404 = 当日无文件
        dest.write_bytes(b"")
        print("miss", url, getattr(e, "code", e))
        return None
    dest.write_bytes(data)
    return dest


def events():
    rows = list(csv.DictReader(open(EV, encoding="utf-8")))
    return [r for r in rows if r["binance_usdm_perp"] == "yes"]


def sym(r):
    return r["token_symbol"].strip().upper() + "USDT"


def days_for(r):
    d = dt.date.fromisoformat(r["date"])
    return [d + dt.timedelta(days=k) for k in (-1, 0, 1, 2)]


def fetch():
    for r in events():
        s = sym(r)
        months = set()
        for d in days_for(r):
            f = f"{s}-1m-{d}.zip"
            get(f"{BASE}/daily/klines/{s}/1m/{f}", CACHE / s / f)
            g = f"BTCUSDT-1m-{d}.zip"
            get(f"{BASE}/daily/klines/BTCUSDT/1m/{g}", CACHE / "BTCUSDT" / g)
            months.add(f"{d:%Y-%m}")
        for m in months:
            f = f"{s}-fundingRate-{m}.zip"
            get(f"{BASE}/monthly/fundingRate/{s}/{f}", CACHE / s / f)


def read_zip_csv(p):
    if p is None or not p.exists() or p.stat().st_size == 0:
        return []
    with zipfile.ZipFile(p) as z:
        name = z.namelist()[0]
        text = z.read(name).decode()
    rows = [l.split(",") for l in text.strip().splitlines()]
    if rows and not rows[0][0].lstrip("-").isdigit():
        rows = rows[1:]  # 新文件带表头
    return rows


def klines(s, days):
    out = {}
    for d in days:
        for x in read_zip_csv(CACHE / s / f"{s}-1m-{d}.zip"):
            t = int(x[0])
            if t > 10**14:  # 微秒时间戳（2025 起部分文件）
                t //= 1000
            out[t] = (float(x[1]), float(x[4]), float(x[7]))  # open, close, quote volume
    return out


def funding(s, months):
    out = []
    for m in months:
        for x in read_zip_csv(CACHE / s / f"{s}-fundingRate-{m}.zip"):
            t = int(x[0])
            if t > 10**14:
                t //= 1000
            out.append((t, float(x[2])))
    return sorted(out)


def parse_utc(v):
    v = v.strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(v.replace("+00:00", ""), fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    return None


def path_from(t0, kl, fr, btc, horizons=(3, 9)):
    """t0 之后第一根整分钟 K 线开盘入场。返回各持有期的做空结果。"""
    ms = int(t0.timestamp() * 1000)
    start = (ms // 60000 + (1 if ms % 60000 else 0)) * 60000
    if start not in kl:
        return None
    entry = kl[start][0]
    res = {"entry_utc": dt.datetime.fromtimestamp(start / 1000, UTC).strftime("%Y-%m-%d %H:%M"), "entry": entry}
    for h in horizons:
        end = start + h * 3600_000 - 60000  # 最后一根 K 线的开盘时刻
        if end not in kl:
            res[f"short_{h}h"] = None
            continue
        px = kl[end][1]
        ret = -(px / entry - 1)
        fsum = sum(rate for t, rate in fr if start < t <= end + 60000)
        vol = sum(v[2] for t, v in kl.items() if start <= t <= end)
        b = None
        if start in btc and end in btc:
            b = btc[end][1] / btc[start][0] - 1
        res[f"short_{h}h"] = ret
        res[f"net_{h}h"] = ret - COST + fsum
        res[f"funding_{h}h"] = fsum
        res[f"qvol_{h}h"] = vol
        res[f"btc_{h}h"] = b
        lo = min(kl[t][1] for t in kl if start <= t <= end)
        hi = max(kl[t][1] for t in kl if start <= t <= end)
        res[f"mae_{h}h"] = -(hi / entry - 1)  # 期间最不利（做空）
        res[f"mfe_{h}h"] = -(lo / entry - 1)
    return res


def calc():
    OUT.mkdir(exist_ok=True)
    rows = []
    for r in events():
        s = sym(r)
        days = days_for(r)
        kl = klines(s, days)
        btc = klines("BTCUSDT", days)
        fr = funding(s, sorted({f"{d:%Y-%m}" for d in days}))
        base = {"date": r["date"], "name": r["name"], "symbol": s, "amount_usd": r["amount_usd"],
                "n_bars": len(kl), "alert_utc": r["first_alert_utc"], "hack_tx_utc": r["hack_tx_time_utc"]}
        for tag, col in (("alert", "first_alert_utc"), ("hack", "hack_tx_time_utc")):
            t = parse_utc(r[col])
            if t is None:
                continue
            anchor = t + dt.timedelta(minutes=5) if tag == "alert" else t
            p = path_from(anchor, kl, fr, btc)
            if p:
                rows.append({**base, "anchor": tag, **p})
            else:
                rows.append({**base, "anchor": tag, "entry_utc": "no-bar"})
        if not parse_utc(r["first_alert_utc"]) and not parse_utc(r["hack_tx_time_utc"]):
            rows.append({**base, "anchor": "none"})
    keys = []
    for x in rows:
        for k in x:
            if k not in keys:
                keys.append(k)
    with open(OUT / "K2_paths.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"写入 {OUT / 'K2_paths.csv'}，{len(rows)} 行")


if __name__ == "__main__":
    {"fetch": fetch, "calc": calc}[sys.argv[1]]()

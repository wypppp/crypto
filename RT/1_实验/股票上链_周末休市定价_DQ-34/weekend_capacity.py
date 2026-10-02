"""写卡前三问之②：HIP-3 各市场每个周末的美元成交额（只读成交额，不读收益）。

成交额 = Σ v × (o+h+l+c)/4（1 小时 K 线；价格只用来把张数换成美元，不计算任何涨跌）。
周末窗口：周五美股收盘 → 周日 CME 股指期货开盘。美国夏令时为周五 20:00 → 周日 22:00 UTC，
冬令时为周五 21:00 → 周日 23:00 UTC（2026 年夏令时 3-08 起、11-01 止）。节假日不单独处理。
输出：runs/weekend_capacity_by_market_week.csv（市场 × 周末）与 runs/weekend_capacity_summary.csv。
"""

import csv
import datetime as dt
import glob
import gzip
import json
import os
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "hl" / "candles" / "1h"
RUNS = HERE / "runs"
UTC = dt.timezone.utc
DST = (dt.datetime(2026, 3, 8, 7, tzinfo=UTC), dt.datetime(2026, 11, 1, 6, tzinfo=UTC))

# 资产类别（按代码人工归类；不认识的记“未分类”，单报）
US_INDEX = {
    "SP500",
    "XYZ100",
    "USA500",
    "US500",
    "USTECH",
    "USA100",
    "SMALL2000",
    "MAG7",
}
US_ETF = {
    "EWY",
    "EWJ",
    "EWT",
    "EWZ",
    "SOXL",
    "SMH",
    "XLE",
    "URNM",
    "XBI",
    "KORU",
    "KWEB",
    "MAGS",
    "TLT",
    "IGV",
}
US_STOCK = {
    "NVDA",
    "TSLA",
    "GOOGL",
    "META",
    "AMD",
    "MSTR",
    "AAPL",
    "MSFT",
    "NBIS",
    "HOOD",
    "INTC",
    "ORCL",
    "PLTR",
    "AMZN",
    "COIN",
    "CRWV",
    "LITE",
    "TSM",
    "RKLB",
    "ARM",
    "BABA",
    "MRNA",
    "HIMS",
    "BE",
    "DELL",
    "AVGO",
    "NFLX",
    "WDC",
    "IBM",
    "LLY",
    "USAR",
    "STRC",
    "RIVN",
    "GME",
    "NOK",
    "QCOM",
    "AMAT",
    "NOW",
    "ASML",
    "COST",
    "DKNG",
    "ZM",
    "IREN",
    "CRWD",
    "AAOI",
    "BX",
    "EBAY",
    "CRCL",
    "SNDK",
    "MU",
    "MRVL",
    "BMNR",
    "CRDO",
    "COHR",
    "VST",
    "STX",
    "CAR",
    "LRCX",
    "GLW",
    "GEV",
    "RDDT",
    "NET",
    "IONQ",
    "TER",
    "TTWO",
    "SMCI",
    "CIFR",
    "CIEN",
    "RTX",
    "SOFI",
    "MELI",
    "CVX",
    "GPRO",
    "BB",
    "BIRD",
    "LYTE",
}
NON_US_EQ = {
    "SKHX",
    "SMSN",
    "SKHY",
    "HYUNDAI",
    "KIOXIA",
    "SOFTBANK",
    "TENCENT",
    "XIAOMI",
    "KR200",
    "JP225",
    "JPN225",
    "NIFTY",
    "IBOV",
    "UNITREE",
    "ZHIPU",
    "MINIMAX",
    "CAMBRICON",
    "INNOLIGHT",
    "NAVER",
    "IBIDEN",
    "UMC",
    "GIGADEV",
    "CXMT",
    "YMTC",
}
COMMOD = {
    "CL",
    "BRENTOIL",
    "SILVER",
    "GOLD",
    "NATGAS",
    "COPPER",
    "PLATINUM",
    "PALLADIUM",
    "OIL",
    "WTI",
    "USOIL",
    "GAS",
    "WHEAT",
    "SOY",
    "CORN",
    "ALUMINIUM",
    "URANIUM",
    "TTF",
    "HO",
    "GOLDJM",
    "SILVERJM",
    "USENERGY",
    "GLDMINE",
}
FX_RATES = {"JPY", "EUR", "GBP", "KRW", "DXY", "USBOND", "10Y", "2Y", "30Y", "USDE"}
CRYPTO = {
    "BTC",
    "ETH",
    "HYPE",
    "SOL",
    "ZEC",
    "1000PEPE",
    "BNB",
    "FARTCOIN",
    "XRP",
    "LINK",
    "XPL",
    "PUMP",
    "SUI",
    "IP",
    "DOGE",
    "ENA",
    "BASED",
    "LIGHTER",
    "XMR",
    "BCH",
    "ADA",
    "LTC",
    "LIT",
    "TOTAL2",
    "OTHERS",
    "BTCD",
    "PURRDAT",
    "BVIV",
}
PRIVATE = {
    "SPCX",
    "SPACEX",
    "OPENAI",
    "OAI",
    "ANTHROPIC",
    "ANTH",
    "CBRS",
    "SHEIN",
    "OURA",
}


def klass(sym: str) -> str:
    for name, s in (
        ("美股指数", US_INDEX),
        ("美股ETF", US_ETF),
        ("美股个股", US_STOCK),
        ("非美股票与指数", NON_US_EQ),
        ("商品", COMMOD),
        ("外汇与利率", FX_RATES),
        ("加密", CRYPTO),
        ("未上市公司", PRIVATE),
    ):
        if sym in s:
            return name
    return "未分类"


def weekend_start(t: dt.datetime) -> "dt.datetime | None":
    """t 所在小时若落在某个周末窗口内，返回该窗口的周五起点，否则 None。"""
    dst = DST[0] <= t < DST[1]
    off = 0 if dst else 1
    fri = (t - dt.timedelta(days=(t.weekday() - 4) % 7)).replace(
        hour=20 + off, minute=0, second=0, microsecond=0
    )
    if t < fri:
        fri -= dt.timedelta(days=7)
    end = fri + dt.timedelta(days=2, hours=2)
    return fri if fri <= t < end else None


def main() -> None:
    RUNS.mkdir(exist_ok=True)
    by = {}  # (market, 周末起点) -> 美元成交额
    total = {}  # market -> 全部小时的美元成交额
    span = {}  # market -> (首根, 末根)
    for p in sorted(glob.glob(str(RAW / "*.json.gz"))):
        mkt = os.path.basename(p)[: -len(".json.gz")]
        with gzip.open(p, "rt") as f:
            cs = json.load(f)["candles"]
        if not cs:
            continue
        span[mkt] = (cs[0]["t"], cs[-1]["t"])
        for c in cs:
            usd = float(c["v"]) * sum(float(c[k]) for k in "ohlc") / 4
            total[mkt] = total.get(mkt, 0.0) + usd
            ws = weekend_start(dt.datetime.fromtimestamp(c["t"] / 1000, UTC))
            if ws is not None:
                by[(mkt, ws)] = by.get((mkt, ws), 0.0) + usd
    # 只统计窗口完整覆盖的周末（首根之后开始、末根之前结束）
    weeks = sorted({w for _, w in by})
    rows = []
    for mkt, (t0, t1) in sorted(span.items()):
        first = dt.datetime.fromtimestamp(t0 / 1000, UTC)
        last = dt.datetime.fromtimestamp(t1 / 1000, UTC)
        for w in weeks:
            if w < first or w + dt.timedelta(days=2, hours=2) > last:
                continue
            rows.append((mkt, klass(mkt.split("_", 1)[1]), w, by.get((mkt, w), 0.0)))
    with open(RUNS / "weekend_capacity_by_market_week.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market", "class", "weekend_start_utc", "usd_volume"])
        for mkt, k, ws, usd in rows:
            w.writerow([mkt, k, ws.strftime("%Y-%m-%dT%H:%MZ"), round(usd, 2)])
    # 汇总：按类别，每个周末加总后取中位数与最大值；各市场周末中位数
    summ = []
    for k in sorted({r[1] for r in rows}):
        per_w = {}
        per_m = {}
        for mkt, kk, ws, usd in rows:
            if kk != k:
                continue
            per_w[ws] = per_w.get(ws, 0.0) + usd
            per_m.setdefault(mkt, []).append(usd)
        tot_all = sum(total[m] for m in per_m)
        wk_all = sum(per_w.values())
        summ.append(
            [
                k,
                len(per_m),
                len(per_w),
                round(statistics.median(per_w.values())),
                round(max(per_w.values())),
                round(wk_all / tot_all, 4) if tot_all else "",
                sum(1 for v in per_m.values() if statistics.median(v) >= 1e6),
                sum(1 for v in per_m.values() if statistics.median(v) >= 1e5),
            ]
        )
    with open(RUNS / "weekend_capacity_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "class",
                "n_markets",
                "n_weekends",
                "median_weekend_usd_class_total",
                "max_weekend_usd_class_total",
                "weekend_share_of_all_hours",
                "n_markets_median_weekend_ge_1m",
                "n_markets_median_weekend_ge_100k",
            ]
        )
        w.writerows(summ)


if __name__ == "__main__":
    main()

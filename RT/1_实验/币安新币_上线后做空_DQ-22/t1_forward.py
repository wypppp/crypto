#!/usr/bin/env python3
"""DQ-22 卡片 v3：做空窄类的前向 T1 窗口——事件构造与评分。0 credits。

python t1_forward.py validate  → runs/t1_validate.json（历史 2025-01～2026-08 对账 Probe L；只查元数据与开发事件）
python t1_forward.py replay    → runs/t1_replay.json（开发事件上与 v1 逐位一致性）
python t1_forward.py rate      → runs/t1_rate.json（按公告标题数月度事件，只看元数据）
python t1_forward.py plan      → runs/t1_plan.json（事件率与检验力推出窗口长度）
python t1_forward.py score     → runs/t1_score.json（只在窗口期满且用户触发后运行）

事件：币安公告目录 48（New Cryptocurrency Listing）中标题宣布现货上市的币；T0＝该币在币安现货归档中的第一根日线日期，
须落在最早一篇公告日前 1 天至后 30 天内（首次上市），且在窗口内。回收沿用 v1 主格：T0＋1 日永续收盘做空、1 倍、30 天、
标记价判爆仓、实际资金费；取数与计算调用冻结的 perp_replicate.py。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
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
CMS = (
    "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    "?type=1&catalogId=48&pageNo={page}&pageSize=50"
)
SPOT_S3 = "data/spot/"
QUOTES = ("USDT", "USDC", "FDUSD", "BNB", "TRY", "BTC")
WINDOW = (dt.date(2026, 11, 1), dt.date(2029, 6, 30))
HOLD = 30
SCORE_EARLIEST = dt.date(2029, 8, 15)
ALPHA = 0.05
LIST_RE = re.compile(r"\bWill List\b")
INTRO_RE = re.compile(
    r"^Introducing .*? on Binance (HODLer Airdrops|Launchpool|Megadrop)"
)
BAD_RE = re.compile(
    r"Pre-Market|Binance Futures|Perpetual|Margin|Binance Alpha|bStocks|Delivery", re.I
)
NAME_RE = re.compile(r"Will List ([A-Z0-9]+)(?:\s|$)")


def holdout(base: str) -> bool:
    return hashlib.sha256(base.encode()).digest()[0] % 5 == 0


def cms_articles(since: dt.date) -> list[dict]:
    """公告目录 48，按发布时间倒序翻页到 since 之前。"""
    out, page = [], 1
    while True:
        req = urllib.request.Request(
            CMS.format(page=page), headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            arts = json.loads(r.read())["data"]["catalogs"][0]["articles"]
        if not arts:
            return out
        for a in arts:
            day = dt.datetime.fromtimestamp(a["releaseDate"] / 1000, P.UTC).date()
            out.append({"id": a["id"], "day": day.isoformat(), "title": a["title"]})
        if day < since:
            return out
        page += 1
        time.sleep(0.7)


def listing_tickers(title: str) -> list[str]:
    """标题宣布现货上市时返回币名；否则空。"""
    if BAD_RE.search(title):
        return []
    if INTRO_RE.search(title):
        m = re.findall(r"\(([^()]+)\)", title)
        return m[:1]
    if LIST_RE.search(title):
        tail = title[LIST_RE.search(title).end() :]
        m = re.findall(r"\(([^()]+)\)", tail)
        if m:
            return m
        n = NAME_RE.search(title)
        return [n.group(1)] if n else []
    return []


def s3_keys(prefix: str) -> list[str]:
    keys, marker = [], ""
    while True:
        q = f"{P.S3}?delimiter=/&prefix={prefix}&marker={marker}"
        body = P.get(q)
        if body is None:
            return keys
        txt = body.decode()
        page = re.findall(r"<Key>([^<]+)</Key>", txt)
        keys += [k for k in page if k.endswith(".zip")]
        if "<IsTruncated>true</IsTruncated>" not in txt or not page:
            return keys
        marker = page[-1]


def spot_first_day(sym: str) -> dt.date | None:
    """现货归档中该交易对的第一根日线日期，只读文件列表（不下载行情）。"""
    mon = s3_keys(f"{SPOT_S3}monthly/klines/{sym}/1d/")
    pre = f"{SPOT_S3}daily/klines/{sym}/1d/{sym}-1d-"
    if mon:
        ym = min(re.search(r"-(\d{4}-\d{2})\.zip$", k).group(1) for k in mon)
        day = s3_keys(pre + ym)
        if day:
            return min(
                dt.date.fromisoformat(
                    re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", k).group(1)
                )
                for k in day
            )
        return dt.date.fromisoformat(ym + "-01")
    day = s3_keys(pre)
    if day:
        return min(
            dt.date.fromisoformat(re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", k).group(1))
            for k in day
        )
    return None


def t0_of(ticker: str) -> dt.date | None:
    days = [spot_first_day(f"{ticker}{q}") for q in QUOTES]
    days = [d for d in days if d is not None]
    return min(days) if days else None


def candidates(arts: list[dict], d1: dt.date, d2: dt.date) -> dict[str, dict]:
    """公告日在 [d1−30, d2] 内、标题宣布现货上市的币名（同名取最早公告）。"""
    out: dict[str, dict] = {}
    for a in sorted(arts, key=lambda a: a["day"]):
        day = dt.date.fromisoformat(a["day"])
        if not (d1 - 30 * P.DAY <= day <= d2):
            continue
        for t in listing_tickers(a["title"]):
            t = t.strip().upper()
            if t and t not in out:
                out[t] = {"ticker": t, "ann_day": a["day"], "article_id": a["id"]}
    return out


def build_events(
    arts: list[dict], d1: dt.date, d2: dt.date, skip=lambda t: False
) -> list[dict]:
    cand = [c for c in candidates(arts, d1, d2).values() if not skip(c["ticker"])]
    with ThreadPoolExecutor(8) as ex:
        t0s = list(ex.map(lambda c: t0_of(c["ticker"]), cand))
    out = []
    for c, t0 in zip(cand, t0s):
        ann = dt.date.fromisoformat(c["ann_day"])
        if t0 is None:
            st = "no_spot"
        elif not (ann - P.DAY <= t0 <= ann + 30 * P.DAY):
            st = "not_first_listing"
        elif not (d1 <= t0 <= d2):
            st = "outside_window"
        else:
            st = "event"
        out.append({**c, "T0_day": t0.isoformat() if t0 else None, "status": st})
    return out


def event_fwd(base: str, t0: dt.date) -> dict:
    """v1 event() 去掉现货代理；映射、可执行性、回收与 v1 相同。"""
    d = t0 + P.DAY
    out = {"base": base, "t0": t0.isoformat(), "entry_day": d.isoformat()}
    firsts = {}
    for sym in (f"{base}USDT", f"1000{base}USDT", f"1000000{base}USDT"):
        fd = P.first_day(sym)
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
    out.update(perp=sym, perp_first_day=earliest.isoformat())
    if earliest > d:
        out["status"] = "perp_later"
        return out
    out["status"] = "perp_at_entry"
    days = [d + k * P.DAY for k in range(HOLD + 1)]
    kl = P.daily("klines", sym, d, days[-1])
    mk = P.daily("markPriceKlines", sym, d, days[-1])
    if any(x not in kl or x not in mk for x in days):
        out["H30_status"] = "window_missing"
        return out
    t1 = dt.datetime.combine(d + P.DAY, dt.time(), P.UTC)
    t2 = dt.datetime.combine(d + (HOLD + 1) * P.DAY, dt.time(), P.UTC)
    fr = P.funding(sym, t1, t2)
    if fr is None:
        out["H30_status"] = "window_missing"
        return out
    p0, p1 = kl[d]["c"], kl[days[-1]]["c"]
    liq = max(mk[x]["h"] for x in days[1:]) >= p0 * (1 + 0.9 / P.LEV)
    fund = P.LEV * sum(
        rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk
    )
    px = P.LEV * (1 - p1 / p0) - P.FEE * P.LEV
    out.update(
        H30_status="ok",
        H30_liq=bool(liq),
        H30_funding=fund,
        H30_r_px=-1.0 if liq else px,
        H30_r=-1.0 if liq else px + fund,
    )
    return out


def block_lower(r: np.ndarray, blocks: np.ndarray, n: int = 10_000) -> float:
    """按入场月分块自助法，均值的单侧 5% 分位。"""
    rng = np.random.default_rng(P.SEED)
    groups = [r[blocks == b] for b in np.unique(blocks)]
    means = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        means[i] = np.concatenate([groups[j] for j in pick]).mean()
    return float(np.quantile(means, ALPHA))


def power(mean: float, sd: float, n: float, deff: float) -> float:
    z = mean / (sd * math.sqrt(deff / n)) - 1.6449
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def n_needed(mean: float, sd: float, deff: float, target: float = 0.8) -> float:
    return ((1.6449 + 0.8416) * sd / mean) ** 2 * deff


def validate() -> dict:
    """2025-01～2026-08：标题规则＋现货首日 vs Probe L 母表（MATCHED 首次现货上市）。留出哈希命中的币名只比对名单，不查归档。"""
    d1, d2 = dt.date(2025, 1, 1), dt.date(2026, 8, 31)
    arts = cms_articles(d1 - 30 * P.DAY)
    L = json.loads(L_MASTER.read_text())
    Lw = {
        r["base_asset"].upper(): r["T0_day"]
        for r in L["u_master"]
        if r["join_class"] == "MATCHED"
        and r["kind"] == "FIRST_SPOT_LISTING"
        and d1.isoformat() <= r["T0_day"] <= d2.isoformat()
    }
    cand = candidates(arts, d1, d2)
    ev = build_events(arts, d1, d2, skip=holdout)
    evd = {e["ticker"]: e for e in ev}
    rows = []
    for t in sorted(set(Lw) | set(cand)):
        e = evd.get(t)
        rows.append(
            {
                "ticker": t,
                "in_L": t in Lw,
                "L_T0": Lw.get(t),
                "title_hit": t in cand,
                "holdout_name": holdout(t),
                "status": e["status"] if e else None,
                "T0": e["T0_day"] if e else None,
            }
        )
    R = pd.DataFrame(rows)
    nh = R[~R.holdout_name]
    both = nh[nh.in_L & (nh.status == "event")]
    out = {
        "window": [d1.isoformat(), d2.isoformat()],
        "n_L": int(R.in_L.sum()),
        "n_L_title_hit": int((R.in_L & R.title_hit).sum()),
        "L_missed_by_title": R.loc[R.in_L & ~R.title_hit, "ticker"].tolist(),
        "title_hits_not_in_L": R.loc[
            ~R.in_L & R.title_hit, ["ticker", "status"]
        ].to_dict("records"),
        "non_holdout": {
            "n_L": int(nh.in_L.sum()),
            "n_event_and_in_L": int(len(both)),
            "T0_equal": int((both.T0 == both.L_T0).sum()),
            "T0_diff": both.loc[both.T0 != both.L_T0, ["ticker", "L_T0", "T0"]].to_dict(
                "records"
            ),
            "in_L_not_event": nh.loc[
                nh.in_L & (nh.status != "event"), ["ticker", "status", "L_T0", "T0"]
            ].to_dict("records"),
            "event_not_in_L": nh.loc[
                ~nh.in_L & (nh.status == "event"), ["ticker", "T0"]
            ].to_dict("records"),
        },
    }
    (P.RUNS / "t1_validate.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    )
    return out


def replay() -> dict:
    """v1 已算过的开发事件：event_fwd 与 v1 events.csv 的 H30 回收逐位一致。"""
    v1 = pd.read_csv(P.RUNS / "events.csv")
    s = v1[v1.H30_status == "ok"]
    with ThreadPoolExecutor(8) as ex:
        res = list(
            ex.map(
                lambda r: event_fwd(r.base, dt.date.fromisoformat(r.t0)), s.itertuples()
            )
        )
    got = pd.DataFrame(res).set_index("base")
    ref = s.set_index("base")
    diff = (got.H30_r - ref.H30_r).abs()
    out = {
        "n": int(len(s)),
        "max_abs_diff": float(diff.max()),
        "n_diff": int((diff > 0).sum()),
    }
    (P.RUNS / "t1_replay.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def rate() -> dict:
    """公告标题数出的首次现货上市（只看元数据，不查归档），按公告月计。"""
    arts = cms_articles(dt.date(2024, 12, 1))
    cand = candidates(arts, dt.date(2025, 1, 1), dt.date(2026, 9, 30))
    by = (
        pd.Series([c["ann_day"][:7] for c in cand.values()]).value_counts().sort_index()
    )
    out = {"by_month": by.to_dict(), "tickers": sorted(cand)}
    (P.RUNS / "t1_rate.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    )
    return out


def plan() -> dict:
    """窗口长度：v1 主格的均值与标准差、分块设计效应、公告标题数出的事件率、v1 的可执行比例。"""
    v1 = json.loads((P.RUNS / "analysis.json").read_text())
    c = v1["cells"]["H30_L1"]
    wb = c["ci95_block_month"][1] - c["ci95_block_month"][0]
    wi = c["ci95_iid"][1] - c["ci95_iid"][0]
    deff = (wb / wi) ** 2
    by = json.loads((P.RUNS / "t1_rate.json").read_text())["by_month"]
    months = pd.period_range("2025-10", "2026-09", freq="M").astype(str)
    last12 = sum(by.get(m, 0) for m in months)
    last6 = sum(by.get(m, 0) for m in months[6:]) * 2
    ex = v1["exec_by_year"]
    share = sum(ex[y]["exec"] for y in ("2025", "2026")) / sum(
        ex[y]["n"] for y in ("2025", "2026")
    )
    need = n_needed(c["mean"], c["sd"], deff)
    lam = {"trailing12": last12 * share, "last6_annualized": last6 * share}
    yrs = (WINDOW[1] - WINDOW[0]).days / 365.25
    out = {
        "mean": c["mean"],
        "sd": c["sd"],
        "deff_block_month": deff,
        "exec_share_2025_2026": share,
        "listings_trailing12": last12,
        "listings_last6_x2": last6,
        "lambda_exec_per_year": lam,
        "n_needed_power80_one_sided5": need,
        "years_needed": {k: need / v for k, v in lam.items()},
        "window_years": yrs,
        "expected_n": {k: v * yrs for k, v in lam.items()},
        "power_at_window": {
            k: power(c["mean"], c["sd"], v * yrs, deff) for k, v in lam.items()
        },
        "power_if_effect_half": {
            k: power(c["mean"] / 2, c["sd"], v * yrs, deff) for k, v in lam.items()
        },
    }
    (P.RUNS / "t1_plan.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def score() -> dict:
    today = dt.datetime.now(P.UTC).date()
    assert today >= SCORE_EARLIEST, "窗口未期满，不取窗口内数据"
    arts = cms_articles(WINDOW[0] - 30 * P.DAY)
    ev = build_events(arts, *WINDOW)
    E0 = [e for e in ev if e["status"] == "event"]
    with ThreadPoolExecutor(8) as ex:
        res = list(
            ex.map(
                lambda e: event_fwd(e["ticker"], dt.date.fromisoformat(e["T0_day"])), E0
            )
        )
    E = pd.DataFrame(res)
    E.to_csv(P.RUNS / "t1_events.csv", index=False)
    s = E[E.get("H30_status") == "ok"] if "H30_status" in E else E.iloc[0:0]
    r = s.H30_r.values.astype(float)
    blocks = pd.to_datetime(s.entry_day).dt.to_period("M").astype(str).values
    out = {
        "window": [WINDOW[0].isoformat(), WINDOW[1].isoformat()],
        "n_candidates": len(ev),
        "candidate_status": pd.Series([e["status"] for e in ev])
        .value_counts()
        .to_dict(),
        "event_status": E.status.value_counts().to_dict() if len(E) else {},
        "n": int(len(r)),
    }
    if len(r) >= 2:
        lo = block_lower(r, blocks)
        out.update(
            mean=float(r.mean()),
            block_lower_5pct=lo,
            sd=float(r.std(ddof=1)),
            median=float(np.median(r)),
            share_liquidated=float(s.H30_liq.mean()),
            describe_perp_price_no_funding=float(s.H30_r_px.mean()),
        )
    btc = P.daily("klines", "BTCUSDT", WINDOW[0], WINDOW[1])
    if btc:
        out["describe_btc_window_return"] = btc[max(btc)]["c"] / btc[min(btc)]["c"] - 1
    if len(r) < 20:
        reading = "样本不足"
    elif out["block_lower_5pct"] > 0:
        reading = "1_确认"
    elif out["mean"] <= 0:
        reading = "2_不确认"
    else:
        reading = "3_未判定"
    out["reading"] = reading
    (P.RUNS / "t1_score.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {
        "validate": validate,
        "replay": replay,
        "rate": rate,
        "plan": plan,
        "score": score,
    }[mode]
    print(json.dumps(fn(), ensure_ascii=False, default=str)[:3000])

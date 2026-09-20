#!/usr/bin/env python3
"""DQ-2 · 币安首发上市（已验收公告匹配子集 206 条）上市后价格机会描述。

规格：同目录 DQ2_卡.md（运行时记录其 sha256）。
只读 direction 精确 T0 产物；只下载这 206 个 baseAsset 的 {BASE}USDT 公开 K 线；
留出集按 Probe L 冻结规则断言，且不下载。输出是零规模价格代理倍数，不是可执行收益。

用法（在仓库根目录）：
  .venv/bin/python RT/dq2/dq2_listing_tail.py --canary 4   # 最早 2 条 + 最晚 2 条
  .venv/bin/python RT/dq2/dq2_listing_tail.py --full
退出码：0 完成且无下载错误；1 有下载错误（结果仍写出，相关事件记 download_error）；2 前置断言失败。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import io
import json
import os
import platform
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CARD = HERE / "DQ2_卡.md"
SRC = Path("/home/ancillary/direction/archive/v1.8.40/L_t0_exact_v2.json")
SRC_SHA256 = "e4b58bdd8165513d1792f99142b786b39b469c29a17798cca4ebfbc75384ced7"
BASE_URL = "https://data.binance.vision/data/spot"
RAW = HERE / "raw"
DATA_END = dt.date(2026, 9, 13)
DAILY_FALLBACK_FROM = (2026, 8)  # 这之后的月份缺月文件时改用日文件
HORIZONS = (7, 30, 90, 180)
THRESHOLDS = (2, 5, 10, 50, 100)
ANCHORS = ("a30", "a0")
MIN_US = 60_000_000
ENTRY_DELAY_US = 30 * MIN_US
ENTRY_TOL_US = 10 * MIN_US
N_EXPECTED = 206
UTC = dt.timezone.utc


class Absent(Exception):
    """官方归档不存在该文件（HTTP 404）。"""


_lock = threading.Lock()
STATS = {"downloaded": 0, "cached": 0, "absent": 0}
SYMBOLS_TOUCHED: set[str] = set()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(url: str) -> bytes:
    # 代币名可能含非 ASCII 字符（如"币安人生"），路径须百分号编码
    url = urllib.parse.quote(url, safe=":/.-_")
    req = urllib.request.Request(url, headers={"User-Agent": "rt-dq2-research"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch(rel: str, symbol: str) -> bytes:
    """取官方文件并核对 CHECKSUM；404 抛 Absent；其他失败重试后抛 RuntimeError。"""
    with _lock:
        SYMBOLS_TOUCHED.add(symbol)
    dest = RAW / rel
    chk_path = dest.with_name(dest.name + ".CHECKSUM")
    absent_path = dest.with_name(dest.name + ".ABSENT")
    if absent_path.exists():
        with _lock:
            STATS["absent"] += 1
        raise Absent(rel)
    if dest.exists() and chk_path.exists():
        data = dest.read_bytes()
        if sha256_bytes(data) == chk_path.read_text().split()[0]:
            with _lock:
                STATS["cached"] += 1
            return data
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            try:
                data = _get(f"{BASE_URL}/{rel}")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    absent_path.parent.mkdir(parents=True, exist_ok=True)
                    absent_path.write_text(dt.datetime.now(UTC).isoformat() + "\n")
                    with _lock:
                        STATS["absent"] += 1
                    raise Absent(rel) from None
                raise
            expected = _get(f"{BASE_URL}/{rel}.CHECKSUM").decode().split()[0]
            if sha256_bytes(data) != expected:
                raise RuntimeError("CHECKSUM_MISMATCH")
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            chk_path.write_text(expected + "\n")
            with _lock:
                STATS["downloaded"] += 1
            return data
        except Absent:
            raise
        except Exception as exc:  # 网络/校验错误：重试
            last_err = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DOWNLOAD_FAILED {rel}: {type(last_err).__name__}: {last_err}")


def norm_us(value: int) -> int:
    digits = len(str(value))
    if digits == 13:
        return value * 1000
    if digits == 16:
        return value
    raise RuntimeError(f"TIMESTAMP_UNIT {value}")


def parse_klines(data: bytes) -> list[dict]:
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise RuntimeError(f"ZIP_MEMBERS {names}")
        with zf.open(names[0]) as fh:
            for line in io.TextIOWrapper(fh, encoding="utf-8"):
                line = line.strip()
                if not line or not line[0].isdigit():  # 空行或表头
                    continue
                c = line.split(",")
                if len(c) != 12:
                    raise RuntimeError(f"SCHEMA {len(c)} columns")
                rows.append({
                    "t": norm_us(int(c[0])), "o": float(c[1]), "h": float(c[2]),
                    "l": float(c[3]), "c": float(c[4]), "v": float(c[5]),
                    "qv": float(c[7]), "n": int(c[8]),
                })
    return rows


def us_date(us: int) -> dt.date:
    return dt.datetime.fromtimestamp(us / 1e6, UTC).date()


def us_iso(us: int) -> str:
    return dt.datetime.fromtimestamp(us / 1e6, UTC).isoformat()


def day_start_us(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) * 1_000_000


def month_last_day(year: int, month: int) -> dt.date:
    nxt = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return nxt - dt.timedelta(days=1)


def minute_rows(sym: str, day: dt.date) -> list[dict] | None:
    """某 UTC 日的 1m K 线；日文件和月文件都不存在时返回 None。"""
    try:
        rows = parse_klines(fetch(f"daily/klines/{sym}/1m/{sym}-1m-{day.isoformat()}.zip", sym))
        if any(us_date(r["t"]) != day for r in rows):
            raise RuntimeError(f"ROW_DAY_MISMATCH {sym} {day}")
    except Absent:
        try:
            data = fetch(f"monthly/klines/{sym}/1m/{sym}-1m-{day:%Y-%m}.zip", sym)
        except Absent:
            return None
        rows = [r for r in parse_klines(data) if us_date(r["t"]) == day]
    rows.sort(key=lambda r: r["t"])
    return rows


def daily_rows(sym: str, d1: dt.date, d2: dt.date) -> dict[dt.date, dict]:
    out: dict[dt.date, dict] = {}
    if d1 > d2:
        return out
    year, month = d1.year, d1.month
    while (year, month) <= (d2.year, d2.month):
        try:
            rows = parse_klines(fetch(f"monthly/klines/{sym}/1d/{sym}-1d-{year:04d}-{month:02d}.zip", sym))
        except Absent:
            rows = []
            if (year, month) >= DAILY_FALLBACK_FROM:
                day = max(d1, dt.date(year, month, 1))
                last = min(d2, month_last_day(year, month))
                while day <= last:
                    try:
                        rows += parse_klines(fetch(f"daily/klines/{sym}/1d/{sym}-1d-{day.isoformat()}.zip", sym))
                    except Absent:
                        pass
                    day += dt.timedelta(days=1)
        for r in rows:
            d = us_date(r["t"])
            if (d.year, d.month) != (year, month):
                raise RuntimeError(f"ROW_MONTH_MISMATCH {sym} {year}-{month:02d} {d}")
            if d1 <= d <= d2:
                out[d] = r
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def measure_event(rec: dict) -> dict:
    base = rec["base_asset"]
    sym = base + "USDT"
    t0 = rec["T0_exact_us"]
    day0 = dt.date.fromisoformat(rec["T0_day"])
    out: dict = {"base": base, "symbol": sym, "T0_utc": us_iso(t0), "T0_day": day0.isoformat(),
                 "lag_seconds": rec.get("lag_seconds"), "error": ""}
    try:
        mins_day0 = minute_rows(sym, day0)
        mins = list(mins_day0 or [])
        next_day = day0 + dt.timedelta(days=1)
        if t0 + ENTRY_DELAY_US + ENTRY_TOL_US >= day_start_us(next_day):
            mins += minute_rows(sym, next_day) or []
        last_needed = min(day0 + dt.timedelta(days=max(HORIZONS)), DATA_END)
        daily = daily_rows(sym, day0, last_needed)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
        for a in ANCHORS:
            out[f"{a}_status"] = "download_error"
            for h in HORIZONS:
                out[f"{a}_H{h}_status"] = "download_error"
        return out

    out["minute_file"] = "absent" if mins_day0 is None else "ok"
    last_avail = max(daily) if daily else None
    out["last_daily_day"] = last_avail.isoformat() if last_avail else ""

    anchors: dict[str, tuple[float, dict]] = {}
    row30 = next((r for r in mins
                  if t0 + ENTRY_DELAY_US <= r["t"] <= t0 + ENTRY_DELAY_US + ENTRY_TOL_US and r["n"] > 0), None)
    if row30:
        anchors["a30"] = (row30["o"], row30)
    row0 = next((r for r in mins if r["t"] <= t0 < r["t"] + MIN_US and r["v"] > 0), None)
    if row0:
        anchors["a0"] = (row0["qv"] / row0["v"], row0)

    for a in ANCHORS:
        if a not in anchors:
            status = "minute_file_absent" if mins_day0 is None else "entry_missing"
            out[f"{a}_status"] = status
            for h in HORIZONS:
                out[f"{a}_H{h}_status"] = status
            continue
        price, row = anchors[a]
        out[f"{a}_status"] = "ok"
        out[f"{a}_price"] = price
        out[f"{a}_time_utc"] = us_iso(row["t"])
        out[f"{a}_minute_trades"] = row["n"]
        if a == "a30":
            out["a30_offset_seconds"] = (row["t"] - (t0 + ENTRY_DELAY_US)) / 1e6
            out["a30_pm1h_trades_seen"] = sum(r["n"] for r in mins if abs(r["t"] - row["t"]) < 60 * MIN_US)
        entry_day = us_date(row["t"])
        intraday = [r for r in mins if r["t"] > row["t"] and us_date(r["t"]) == entry_day]
        for h in HORIZONS:
            end_day = day0 + dt.timedelta(days=h)
            days = [entry_day + dt.timedelta(days=i) for i in range(1, (end_day - entry_day).days + 1)]
            observable = [d for d in days if d <= DATA_END]
            present = [(d, daily[d]) for d in observable if d in daily]
            highs = [(r["h"], entry_day) for r in intraday] + [(r["h"], d) for d, r in present]
            closes = ([intraday[-1]["c"]] if intraday else []) + [r["c"] for _, r in present]
            missing = [d for d in observable if d not in daily]
            if end_day > DATA_END:
                status = "immature"
            elif not missing:
                status = "complete"
            elif last_avail is None or last_avail < end_day:
                status = "data_ended"
            else:
                status = "gaps"
            key = f"{a}_H{h}"
            out[f"{key}_status"] = status
            if highs:
                max_h, max_day = max(highs, key=lambda x: x[0])
                out[f"{key}_mstar"] = max_h / price
                out[f"{key}_max_day"] = max_day.isoformat()
            if closes:
                out[f"{key}_mstar_close"] = max(closes) / price
            if end_day in daily:
                out[f"{key}_mpi"] = daily[end_day]["c"] / price
            out[f"{key}_missing_days"] = len(missing)
    return out


def classify(row: dict, a: str, h: int, k: float, field: str) -> str:
    value = row.get(f"{a}_H{h}_{field}")
    if value is not None and value >= k:
        return "yes"
    if row.get(f"{a}_H{h}_status") == "complete":
        return "no"
    return "unknown"


def quantiles(values: list[float]) -> dict:
    s = sorted(values)
    if not s:
        return {"n": 0}
    def q(p: float) -> float:
        return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]
    return {"n": len(s), "p10": q(.10), "p25": q(.25), "p50": q(.50), "p75": q(.75),
            "p90": q(.90), "p95": q(.95), "max": s[-1]}


def summarize(results: list[dict]) -> dict:
    n = len(results)
    summary: dict = {"n_events": n, "anchors": {}}
    for a in ANCHORS:
        entry_counts: dict[str, int] = {}
        for r in results:
            entry_counts[r.get(f"{a}_status", "?")] = entry_counts.get(r.get(f"{a}_status", "?"), 0) + 1
        per_h = {}
        for h in HORIZONS:
            status_counts: dict[str, int] = {}
            for r in results:
                st = r.get(f"{a}_H{h}_status", "?")
                status_counts[st] = status_counts.get(st, 0) + 1
            hits = {}
            for field in ("mstar", "mstar_close"):
                hits[field] = {}
                for k in THRESHOLDS:
                    c = {"yes": 0, "no": 0, "unknown": 0}
                    for r in results:
                        c[classify(r, a, h, k, field)] += 1
                    c["interval"] = [c["yes"] / n, (c["yes"] + c["unknown"]) / n] if n else None
                    hits[field][str(k)] = c
            complete = [r for r in results if r.get(f"{a}_H{h}_status") == "complete"]
            dist = {f: quantiles([r[f"{a}_H{h}_{f}"] for r in complete if r.get(f"{a}_H{h}_{f}") is not None])
                    for f in ("mstar", "mstar_close", "mpi")}
            per_h[str(h)] = {"status_counts": status_counts, "hits": hits, "observed_only_complete": dist}
        summary["anchors"][a] = {"entry_status_counts": entry_counts, "horizons": per_h}
    return summary


def fmt(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def summary_markdown(summary: dict, results: list[dict], manifest: dict) -> str:
    n = summary["n_events"]
    lines = [f"# DQ-2 结果摘要（脚本生成）", "",
             f"run `{manifest['run_id']}`｜事件 {n}｜数据截止 {manifest['data_end']}｜"
             f"卡片 sha256 `{manifest['card_sha256'][:12]}…`｜下载错误 {manifest['events_with_download_error']}", "",
             "价格代理，零规模；不是可执行收益。命中区间 = [是/N, (是+未知)/N]。", ""]
    for a in ANCHORS:
        block = summary["anchors"][a]
        lines += [f"## 基准 {a}", "", f"入场状态：{block['entry_status_counts']}", ""]
        for field, label in (("mstar", "M*（最高价）"), ("mstar_close", "M*close（最高收盘）")):
            lines += [f"### {label} 命中", "", "| H | " + " | ".join(f"≥{k}×" for k in THRESHOLDS) + " |",
                      "|---|" + "---|" * len(THRESHOLDS)]
            for h in HORIZONS:
                cells = []
                for k in THRESHOLDS:
                    c = block["horizons"][str(h)]["hits"][field][str(k)]
                    cells.append(f"{c['yes']} 是 / {c['unknown']} 未知 [{c['interval'][0]:.1%}, {c['interval'][1]:.1%}]")
                lines.append(f"| {h}d | " + " | ".join(cells) + " |")
            lines.append("")
        lines += ["### 状态与 observed-only 分布（仅 complete）", "",
                  "| H | 状态计数 | M* p50 / p90 / max | M*close p50 / p90 / max | Mπ p10 / p50 / p90 |", "|---|---|---|---|---|"]
        for h in HORIZONS:
            hb = block["horizons"][str(h)]
            d = hb["observed_only_complete"]
            ms, mc, mp = d["mstar"], d["mstar_close"], d["mpi"]
            lines.append(f"| {h}d | {hb['status_counts']} | {fmt(ms.get('p50'))} / {fmt(ms.get('p90'))} / {fmt(ms.get('max'))} "
                         f"| {fmt(mc.get('p50'))} / {fmt(mc.get('p90'))} / {fmt(mc.get('max'))} "
                         f"| {fmt(mp.get('p10'))} / {fmt(mp.get('p50'))} / {fmt(mp.get('p90'))} |")
        lines.append("")
    lines += ["## a30 · H180 M* 最高的 15 条（含未成熟/中断，M* 为观测值或下界）", "",
              "| base | T0 | 入场价 | M* | M*close | 最高点日期 | 状态 | Mπ180 |", "|---|---|---|---|---|---|---|---|"]
    ranked = sorted((r for r in results if r.get("a30_H180_mstar") is not None),
                    key=lambda r: r["a30_H180_mstar"], reverse=True)[:15]
    for r in ranked:
        lines.append(f"| {r['base']} | {r['T0_day']} | {r['a30_price']:.8g} | {fmt(r['a30_H180_mstar'])} | "
                     f"{fmt(r.get('a30_H180_mstar_close'))} | {r.get('a30_H180_max_day', '')} | "
                     f"{r['a30_H180_status']} | {fmt(r.get('a30_H180_mpi'))} |")
    errors = [r for r in results if r.get("error")]
    if errors:
        lines += ["", "## 下载错误", ""] + [f"- {r['base']}: {r['error']}" for r in errors]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--canary", type=int)
    grp.add_argument("--full", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    started = dt.datetime.now(UTC)

    problems = []
    src_bytes = SRC.read_bytes()
    if sha256_bytes(src_bytes) != SRC_SHA256:
        problems.append("SRC_SHA256_MISMATCH")
    records = [r for r in json.loads(src_bytes)["records"] if r.get("status") == "VERIFIED_COMPLETE"]
    if len(records) != N_EXPECTED:
        problems.append(f"N_RECORDS {len(records)} != {N_EXPECTED}")
    if any(r.get("embargo") != "FETCHABLE" for r in records):
        problems.append("NON_FETCHABLE_RECORD")
    holdout_hits = [r["base_asset"] for r in records
                    if hashlib.sha256(r["base_asset"].encode()).digest()[0] % 5 == 0]
    if holdout_hits:
        problems.append(f"HOLDOUT_RULE_HIT {holdout_hits}")
    if any(r["base_asset"] + "USDT" not in r["pairs_verified"] for r in records):
        problems.append("USDT_PAIR_NOT_IN_VERIFIED_PAIRS")
    if not CARD.exists():
        problems.append("CARD_MISSING")
    if problems:
        print("前置断言失败：", problems, file=sys.stderr)
        return 2

    records.sort(key=lambda r: (r["T0_exact_us"], r["base_asset"]))
    if args.canary:
        half = args.canary // 2
        todo = records[:args.canary - half] + (records[-half:] if half else [])
    else:
        todo = records
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + ("-canary" if args.canary else "-full")
    out_dir = HERE / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(measure_event, todo))

    allowed = {r["base_asset"] + "USDT" for r in records}
    on_disk = set()
    for kind in ("daily", "monthly"):
        kdir = RAW / kind / "klines"
        if kdir.exists():
            on_disk |= {p.name for p in kdir.iterdir() if p.is_dir()}
    post_problems = []
    if SYMBOLS_TOUCHED - allowed:
        post_problems.append(f"SYMBOL_OUTSIDE_SUBSET {sorted(SYMBOLS_TOUCHED - allowed)}")
    if on_disk - allowed:
        post_problems.append(f"RAW_DIR_OUTSIDE_SUBSET {sorted(on_disk - allowed)}")

    fields: list[str] = []
    for r in results:
        for key in r:
            if key not in fields:
                fields.append(key)
    with (out_dir / "results.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    summary = summarize(results)
    n_err = sum(1 for r in results if r.get("error"))
    manifest = {
        "run_id": run_id, "mode": "canary" if args.canary else "full",
        "started_at": started.isoformat(), "finished_at": dt.datetime.now(UTC).isoformat(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "card_sha256": sha256_bytes(CARD.read_bytes()),
        "source": str(SRC), "source_sha256": SRC_SHA256,
        "data_end": DATA_END.isoformat(), "horizons": HORIZONS, "thresholds": THRESHOLDS,
        "events_measured": len(results), "events_in_subset": len(records),
        "events_with_download_error": n_err,
        "downloads": dict(STATS), "symbols_touched": len(SYMBOLS_TOUCHED),
        "assertions": {"pre": "pass", "post": post_problems or "pass"},
        "python": platform.python_version(),
        "claims_not_supported": ["可执行收益或容量", "全部 CEX 首发上市发生率", "选币能力", "下架残值"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    md = summary_markdown(summary, results, manifest)
    (out_dir / "summary.md").write_text(md)
    print(md)
    print(f"输出目录：{out_dir}")
    if post_problems:
        print("后置断言失败：", post_problems, file=sys.stderr)
        return 2
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())

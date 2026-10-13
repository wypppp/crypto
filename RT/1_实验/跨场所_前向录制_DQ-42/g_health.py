#!/usr/bin/env python3
"""DQ-42 健康检查（G v2 §3 白名单，10-13）。

python g_health.py [--hours 24]

只输出：计数、成功率、缺口时长、字段结构摘要（指纹个数，不含键名与值）、清单核对、通过或失败。
不输出标题、币的标识、价格或任何正文。输出先过 `whitelist()`，不在白名单里的键或字符串值一律丢弃并计数。
读取时只取每行的元数据字段（kind、时刻、状态码、指纹、条目数），不取响应体与条目内容。
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
from pathlib import Path

import hashlib

from g_store import MANIFESTS, RAW, utc_day

NS_PER_S = 1_000_000_000

ALLOWED_KEYS = {
    "windows",
    "missed_windows",
    "recorders",
    "alive",
    "beat_age_s",
    "limit_s",
    "gap",
    "window_h",
    "generated_utc_day",
    "overall",
    "http",
    "chain",
    "heartbeat",
    "manifests",
    "dropped",
    "requests",
    "ok",
    "fail",
    "success_rate",
    "status_counts",
    "max_gap_s",
    "expected_every_s",
    "struct_fps",
    "events",
    "connects",
    "closes",
    "errors",
    "stalls",
    "rpc_errors",
    "max_silent_s",
    "procs",
    "beats",
    "checked",
    "mismatch",
    "missing_days",
    "result",
    "first_utc_day",
    "last_utc_day",
    "item_events",
}
ALLOWED_STR = {"pass", "fail", "no_data"}
META_HTTP = ("kind", "src", "tag", "t_req_utc_ns", "status", "struct_fp")


def whitelist(obj, names: set[str], dropped: list) -> object:
    """递归过滤：字典键须在 ALLOWED_KEYS 或配置里的来源名、端点名、进程名中；
    值只许数字、布尔、None、ALLOWED_STR 里的字符串，或形如 YYYY-MM-DD 的日期、状态码字符串。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if (
                k in ALLOWED_KEYS
                or k in names
                or (isinstance(k, str) and k.isdigit())
                or k == "none"
            ):
                out[k] = whitelist(v, names, dropped)
            else:
                dropped.append(1)
        return out
    if isinstance(obj, list):
        return [whitelist(v, names, dropped) for v in obj]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str) and (obj in ALLOWED_STR or _is_day(obj)):
        return obj
    dropped.append(1)
    return None


def _is_day(s: str) -> bool:
    return len(s) == 10 and s[4] == "-" and s[7] == "-" and s.replace("-", "").isdigit()


def rows(path: Path, keep: tuple):
    """逐行读，只保留 keep 里的字段。"""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            yield {k: d.get(k) for k in keep}


def files_in_window(stream_dir: Path, since_ns: int):
    first = utc_day(since_ns)
    return sorted(p for p in stream_dir.glob("*.jsonl.gz") if p.name[:10] >= first)


def max_gap_s(times_ns: list[int], start_ns: int, end_ns: int) -> float:
    """时刻序列在 [start, end] 内的最大间隔（含两端到首末时刻），单位秒。"""
    ts = sorted(t for t in times_ns if start_ns <= t <= end_ns)
    if not ts:
        return (end_ns - start_ns) / 1e9
    pts = [start_ns] + ts + [end_ns]
    return max(b - a for a, b in zip(pts, pts[1:])) / 1e9


def check_http(raw: Path, since: int, until: int, expected: dict) -> dict:
    out = {}
    for d in sorted((raw / "http").glob("*")):
        src = d.name
        req = [
            r for p in files_in_window(d, since) for r in rows(p, META_HTTP + ("kind",))
        ]
        main = [
            r
            for r in req
            if r["kind"] == "request"
            and r["tag"] is None
            and since <= r["t_req_utc_ns"] <= until
        ]
        items = sum(1 for r in req if r["kind"] == "item")
        ok_t = [
            r["t_req_utc_ns"] for r in main if r["status"] in (200, 304)
        ]  # 304＝ETag 未变
        codes: dict = {}
        for r in main:
            k = str(r["status"]) if r["status"] is not None else "none"
            codes[k] = codes.get(k, 0) + 1
        n = len(main)
        exp = expected.get(src)
        gap = max_gap_s(ok_t, since, until) if n else None
        sr = len(ok_t) / n if n else None
        good = n > 0 and sr >= 0.9 and (exp is None or gap <= 3 * exp + 120)
        out[src] = {
            "requests": n,
            "ok": len(ok_t),
            "fail": n - len(ok_t),
            "success_rate": sr,
            "status_counts": codes,
            "max_gap_s": gap,
            "expected_every_s": exp,
            "struct_fps": len({r["struct_fp"] for r in main if r["struct_fp"]}),
            "item_events": items,
            "result": "pass" if good else ("no_data" if n == 0 else "fail"),
        }
    return out


def check_chain(raw: Path, since: int, until: int) -> dict:
    """按时间表抽样之后，只在录制窗内量“沉默”；连续录制时段按整段量。
    missed_windows：抽样开始之后、完整落在检查期内、却没有 window_open 记录的窗数（进程不在的迹象）。"""
    import g_chain

    out = {}
    for d in sorted((raw / "chain").glob("*")):
        keep = ("kind", "what", "t_utc_ns", "start", "end")
        rs = [
            r
            for p in files_in_window(d, since)
            for r in rows(p, keep)
            if since <= (r["t_utc_ns"] or 0) <= until
        ]
        ev = [r["t_utc_ns"] for r in rs if r["kind"] == "event"]
        conn = [r["what"] for r in rs if r["kind"] == "conn"]
        opened = sorted(
            (r["start"], r["end"])
            for r in rs
            if r["kind"] == "conn" and r["what"] == "window_open"
        )
        if opened:
            first = opened[0][0] * NS_PER_S
            # 抽样之前若有连续录制的事件，那一段按整段量；没有就不算
            pre = [t for t in ev if t < first]
            spans = [(max(since, min(pre)), min(first, until))] if pre else []
            spans += [
                (max(a * NS_PER_S, since), min(b * NS_PER_S, until)) for a, b in opened
            ]
            sched, h = [], (first // NS_PER_S) // 3600 * 3600
            while h * NS_PER_S < until:
                a, b = g_chain.window_for_hour(h)
                if a * NS_PER_S >= first and b * NS_PER_S <= until:
                    sched.append((a, b))
                h += 3600
            missed = len(set(sched) - set(opened))
        else:
            spans, missed = [(since, until)], 0
        gaps = [
            max_gap_s([t for t in ev if a <= t <= b], a, b) for a, b in spans if b > a
        ]
        gap = max(gaps) if gaps else None
        good = bool(ev) and gap is not None and gap <= 300 and missed == 0
        out[d.name] = {
            "events": len(ev),
            "connects": conn.count("open"),
            "closes": conn.count("close"),
            "errors": conn.count("error"),
            "stalls": conn.count("stall"),
            "rpc_errors": conn.count("rpc_error"),
            "windows": len(opened),
            "missed_windows": missed,
            "max_silent_s": gap,
            "result": "pass" if good else ("no_data" if not ev else "fail"),
        }
    return out


def check_heartbeat(raw: Path, since: int, until: int) -> dict:
    out = {}
    for d in sorted((raw / "heartbeat").glob("*")):
        ts = [
            r["t_utc_ns"]
            for p in files_in_window(d, since)
            for r in rows(p, ("t_utc_ns",))
            if r["t_utc_ns"]
        ]
        ts = [t for t in ts if since <= t <= until]
        gap = max_gap_s(ts, since, until)
        out[d.name] = {
            "beats": len(ts),
            "max_gap_s": gap,
            "result": "pass" if ts and gap <= 180 else "fail",
        }
    return out


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifests(raw: Path, mdir: Path) -> dict:
    checked = mismatch = 0
    for m in sorted(mdir.glob("*.json")):
        doc = json.loads(m.read_text())
        for f in doc["files"]:
            p = raw / f["path"]
            checked += 1
            if not p.exists() or _sha(p) != f["sha256"]:
                mismatch += 1
    return {
        "checked": checked,
        "mismatch": mismatch,
        "result": "pass" if mismatch == 0 else "fail",
    }


def _recorders() -> dict:
    """断档检查（g_gaps）：进程是否在、最近心跳距今秒数、门槛、是否断档。"""
    import g_gaps

    return {
        s["name"]: {k: s[k] for k in ("alive", "beat_age_s", "limit_s", "gap")}
        for s in g_gaps.status()
    }


def report(
    hours: float = 24,
    raw: Path = RAW,
    mdir: Path = MANIFESTS / "rec",
    config: Path | None = None,
    now_ns: int | None = None,
) -> dict:
    until = time.time_ns() if now_ns is None else now_ns
    since = until - int(hours * 3600 * 1e9)
    expected, names = {}, set()
    cfg = config or Path(__file__).with_name("sources.json")
    if cfg.exists():
        for s in json.loads(cfg.read_text())["sources"]:
            if s.get("decision", "录") == "录" and "every_s" in s:
                expected[s["key"]] = s["every_s"]
                names.add(s["key"])
    names |= {
        p.name for sub in ("http", "chain", "heartbeat") for p in (raw / sub).glob("*")
    }
    names |= {"dq34_trades", "dq34_recorder"}  # g_gaps 的记录器名
    r = {
        "window_h": hours,
        "generated_utc_day": utc_day(until),
        "http": check_http(raw, since, until, expected),
        "chain": check_chain(raw, since, until),
        "heartbeat": check_heartbeat(raw, since, until),
        "manifests": check_manifests(raw, mdir),
        "recorders": _recorders() if raw == RAW else {},
    }
    parts = [
        v["result"] for sec in ("http", "chain", "heartbeat") for v in r[sec].values()
    ]
    parts.append(r["manifests"]["result"])
    parts += ["fail" if v["gap"] else "pass" for v in r["recorders"].values()]
    r["overall"] = "pass" if parts and all(x == "pass" for x in parts) else "fail"
    dropped: list = []
    safe = whitelist(r, names, dropped)
    safe["dropped"] = len(dropped)
    return safe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    print(json.dumps(report(a.hours), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

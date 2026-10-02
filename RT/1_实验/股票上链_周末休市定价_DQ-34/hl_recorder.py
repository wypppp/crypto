#!/usr/bin/env python3
"""DQ-34 数据保全：前向记录 Hyperliquid HIP-3 各 dex 的 metaAndAssetCtxs（10-02；只存不分析）。

python hl_recorder.py → raw/recorder/YYYY-MM-DD.jsonl（UTC 日；隔日压缩为 .jsonl.gz）、raw/recorder/heartbeat.txt
记录预言机价、标记价、中间价、资金费、溢价、持仓量、日成交额——都是“当时可见”的数据，过后无法重建。
频率（UTC）：平时每小时整点一次；周五 19:30 至周一 01:00（覆盖美股周五收盘到周日晚上，冬夏令时都含）
与周一 13:00～15:00（美股开盘前后）每 5 分钟一次。
只调用公开读接口，不涉及密钥。只用标准库。用 raw/recorder/recorder.pid 防止重复运行（看门狗见 README）。
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
OUT = H / "raw" / "recorder"
URL = "https://api.hyperliquid.xyz/info"
UTC = dt.timezone.utc


def info(body: dict) -> object:
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "rt-dq34-rec"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def dense(t: dt.datetime) -> bool:
    """周五 19:30～周一 01:00、周一 13:00～15:00（UTC）为 5 分钟一次。"""
    wd, hm = t.weekday(), t.hour * 60 + t.minute
    if wd == 4 and hm >= 19 * 60 + 30:
        return True
    if wd in (5, 6):
        return True
    if wd == 0 and (hm < 60 or 13 * 60 <= hm < 15 * 60):
        return True
    return False


def next_tick(now: dt.datetime) -> dt.datetime:
    t = now.replace(second=0, microsecond=0)
    while True:
        t += (
            dt.timedelta(minutes=5 - t.minute % 5)
            if t.minute % 5
            else dt.timedelta(minutes=5)
        )
        if dense(t) or t.minute == 0:
            return t


def log(msg: str) -> None:
    with open(OUT / "recorder.log", "a") as f:
        f.write(dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + " " + msg + "\n")


def compress_old(today: str) -> None:
    for p in OUT.glob("*.jsonl"):
        if p.stem < today:
            with open(p, "rb") as src:
                with gzip.open(p.with_suffix(".jsonl.gz"), "wb") as dst:
                    shutil.copyfileobj(src, dst)
            p.unlink()


def snapshot(dexes: list[str]) -> int:
    t0 = dt.datetime.now(UTC)
    ok = 0
    path = OUT / f"{t0.strftime('%Y-%m-%d')}.jsonl"
    with open(path, "a") as f:
        for dex in dexes:
            rec = {"t_ms": int(t0.timestamp() * 1000), "dex": dex}
            for i in range(3):
                try:
                    rec["data"] = info({"type": "metaAndAssetCtxs", "dex": dex})
                    rec["t_resp_ms"] = int(time.time() * 1000)
                    ok += 1
                    break
                except Exception as e:  # noqa: BLE001 —— 记录后继续
                    rec["error"] = repr(e)[:200]
                    time.sleep(2 * (i + 1))
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    (OUT / "heartbeat.txt").write_text(f"{t0.isoformat()} ok={ok}/{len(dexes)}\n")
    return ok


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pid = OUT / "recorder.pid"
    if pid.exists():
        try:
            os.kill(int(pid.read_text()), 0)
            sys.exit("already running")
        except (ProcessLookupError, ValueError):
            pass
    pid.write_text(str(os.getpid()))
    log("start")
    dexes, refreshed = ["xyz"], None
    while True:
        now = dt.datetime.now(UTC)
        if refreshed != now.date():
            try:
                dexes = [d["name"] for d in info({"type": "perpDexs"}) if d]
                refreshed = now.date()
                compress_old(now.strftime("%Y-%m-%d"))
            except Exception as e:  # noqa: BLE001
                log(f"perpDexs error {e!r}"[:200])
        ok = snapshot(dexes)
        if ok < len(dexes):
            log(f"partial {ok}/{len(dexes)}")
        nt = next_tick(dt.datetime.now(UTC))
        # 分段睡、按墙钟判断：主机睡眠时单调钟停走，一次睡到底会错过醒来后的整点
        while dt.datetime.now(UTC) < nt:
            time.sleep(min(30.0, max(1.0, (nt - dt.datetime.now(UTC)).total_seconds())))


if __name__ == "__main__":
    main()

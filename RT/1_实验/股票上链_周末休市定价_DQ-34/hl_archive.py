#!/usr/bin/env python3
"""DQ-34 数据保全：Hyperliquid HIP-3 历史 K 线与资金费存档（10-02；只存不分析）。

python hl_archive.py [--dex xyz] [--intervals 5m,15m,1h] [--funding]
→ raw/hl/candles/{interval}/{coin}.json.gz、raw/hl/funding/{coin}.json.gz、raw/hl/meta_{dex}_{UTC}.json.gz
只调用公开读接口 POST https://api.hyperliquid.xyz/info（candleSnapshot 只返回最近 5,000 根，更早的取不回）。
已存在的文件跳过（可续跑）；遇 429 退避重试。只用标准库，便于搬到服务器。
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
OUT = H / "raw" / "hl"
URL = "https://api.hyperliquid.xyz/info"
MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "1d": 86_400_000}
GAP = 1.0  # 两次请求的最小间隔（秒）
_last = [0.0]


def info(body: dict) -> object:
    for i in range(8):
        wait = GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(
                URL,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "rt-dq34"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(min(5 * 2**i, 120))
    raise RuntimeError(f"failed {body}")


def save(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f)
    tmp.rename(path)


def fname(coin: str) -> str:
    return coin.replace(":", "_").replace("/", "_")


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "archive.log", "a") as f:
        f.write(line + "\n")


def coins(dex: str) -> list[str]:
    meta, ctx = info({"type": "metaAndAssetCtxs", "dex": dex})
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    save(OUT / f"meta_{dex}_{stamp}.json.gz", [meta, ctx])
    return [a["name"] for a in meta["universe"]]


def candles(coin: str, iv: str) -> None:
    p = OUT / "candles" / iv / f"{fname(coin)}.json.gz"
    if p.exists():
        return
    now = int(time.time() * 1000)
    body = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": iv,
            "startTime": now - 5000 * MS[iv],
            "endTime": now,
        },
    }
    rows = info(body)
    save(p, {"fetched_ms": now, "request": body, "candles": rows})
    log(f"candles {iv} {coin} {len(rows)}")


def funding(coin: str) -> None:
    p = OUT / "funding" / f"{fname(coin)}.json.gz"
    if p.exists():
        return
    now = int(time.time() * 1000)
    out, start = [], 0
    while True:
        page = info({"type": "fundingHistory", "coin": coin, "startTime": start})
        if not page:
            break
        out += page
        nxt = max(int(x["time"]) for x in page) + 1
        if nxt <= start or len(page) < 500:
            break
        start = nxt
    save(p, {"fetched_ms": now, "coin": coin, "funding": out})
    log(f"funding {coin} {len(out)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dex", default="xyz")
    ap.add_argument("--intervals", default="5m,15m,1h")
    ap.add_argument("--funding", action="store_true")
    a = ap.parse_args()
    dexes = (
        [d["name"] for d in info({"type": "perpDexs"}) if d]
        if a.dex == "all"
        else a.dex.split(",")
    )
    for dex in dexes:
        cs = coins(dex)
        log(f"dex {dex} {len(cs)} coins")
        for iv in [x for x in a.intervals.split(",") if x]:
            for c in cs:
                candles(c, iv)
        if a.funding:
            for c in cs:
                funding(c)
    log("done")


if __name__ == "__main__":
    main()

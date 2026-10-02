#!/usr/bin/env python3
"""DQ-34 数据保全：Kraken 代币化股票（xStocks 等）的 OHLC 存档（10-02；只存不分析）。

python kraken_archive.py → raw/kraken/pairs_{UTC}.json.gz、raw/kraken/ohlc/{interval}/{pair}.json.gz
Kraken 公开 OHLC 接口每个周期只返回最近 720 根（1 小时约 30 天、5 分钟约 2.5 天），更早的取不回；
逐笔成交接口可回取全部历史，不在本脚本内。已存在的文件跳过；只用标准库。
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
OUT = H / "raw" / "kraken"
API = "https://api.kraken.com/0/public"
INTERVALS = (5, 15, 60, 240, 1440)
GAP = 1.1
_last = [0.0]


def get(path: str) -> dict:
    for i in range(8):
        wait = GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(
                f"{API}/{path}", headers={"User-Agent": "rt-dq34"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            if not d.get("error"):
                return d
            if not any("Too many" in e or "Rate" in e for e in d["error"]):
                return d
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(min(5 * 2**i, 120))
    raise RuntimeError(path)


def save(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f)
    tmp.rename(path)


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    with open(OUT / "archive.log", "a") as f:
        f.write(line + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ap = get("AssetPairs?aclass_base=tokenized_asset")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    save(OUT / f"pairs_{stamp}.json.gz", ap)
    pairs = sorted(ap["result"])
    log(f"pairs {len(pairs)}")
    for iv in INTERVALS:
        for p in pairs:
            dest = OUT / "ohlc" / str(iv) / f"{p}.json.gz"
            if dest.exists():
                continue
            now = int(time.time())
            d = get(f"OHLC?pair={p}&interval={iv}&asset_class=tokenized_asset")
            save(dest, {"fetched_s": now, "pair": p, "interval_min": iv, "response": d})
            rows = [v for k, v in d.get("result", {}).items() if k != "last"]
            log(f"ohlc {iv} {p} {len(rows[0]) if rows else d.get('error')}")
    log("done")


if __name__ == "__main__":
    main()

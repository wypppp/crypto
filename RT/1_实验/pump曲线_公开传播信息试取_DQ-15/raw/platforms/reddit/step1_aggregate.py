"""DQ-15 平台可得性检查：Reddit (Arctic Shift) 第一步——按日聚合统计。
只查可得性，不做收益分析。请求节流 1/秒。
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://arctic-shift.photon-reddit.com/api"
SUBS = ["solana", "SolanaMemeCoins", "memecoins", "CryptoMoonShots", "pumpfun"]
LOG = []

def get(path, params, outname):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-availability-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        body = e.read()
        code = e.code
    (HERE / outname).write_bytes(body)
    LOG.append({"url": url, "http": code, "size": len(body), "out": outname})
    print(code, len(body), outname)
    time.sleep(1)
    return code, body

for kind in ["posts", "comments"]:
    for sub in SUBS:
        get(f"/{kind}/search/aggregate",
            {"subreddit": sub, "after": "2026-06-01", "before": "2026-06-08",
             "aggregate": "created_utc", "frequency": "day"},
            f"agg_{kind}_{sub}_daily.json")

(HERE / "step1_请求日志.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=2))
print("done", len(LOG), "requests")

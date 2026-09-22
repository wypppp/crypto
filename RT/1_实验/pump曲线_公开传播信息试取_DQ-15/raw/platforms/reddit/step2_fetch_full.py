"""DQ-15 平台可得性检查：Reddit (Arctic Shift) 第二步——按 mint 游标翻页，取 A 周（2026-06-01T00:00Z ~ 2026-06-08T00:00Z）
全部 posts / comments 原始数据。只查可得性，不做收益分析。请求节流 1/秒，每次 limit=100。
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
BASE = "https://arctic-shift.photon-reddit.com/api"
SUBS = ["solana", "SolanaMemeCoins", "memecoins", "CryptoMoonShots", "pumpfun"]
START = "2026-06-01T00:00:00"
END_TS = int(datetime(2026, 6, 8, 0, 0, 0, tzinfo=timezone.utc).timestamp())
LOG = []
REQ_COUNT = 0

def get(kind, sub, after_str):
    global REQ_COUNT
    params = {"subreddit": sub, "after": after_str, "before": "2026-06-08T00:00:00",
              "limit": 100, "sort": "asc"}
    url = f"{BASE}/{kind}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-availability-check/1.0"})
    REQ_COUNT += 1
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        body = e.read()
        code = e.code
    LOG.append({"url": url, "http": code, "size": len(body)})
    time.sleep(1)
    if code != 200:
        print("ERROR", code, url)
        return code, []
    d = json.loads(body)
    return code, d.get("data", [])

for kind in ["posts", "comments"]:
    for sub in SUBS:
        all_items = []
        after_str = START
        page = 0
        while True:
            page += 1
            code, items = get(kind, sub, after_str)
            print(f"{kind}/{sub} page{page}: {len(items)} items, http={code}")
            if not items:
                break
            all_items.extend(items)
            last_ts = items[-1]["created_utc"]
            if last_ts >= END_TS - 1:
                break
            after_str = datetime.fromtimestamp(last_ts + 1, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            if page > 30:
                print("!! too many pages, stopping to respect budget", sub, kind)
                break
        out = HERE / f"{kind}_{sub}_A周_full.json"
        out.write_text(json.dumps(all_items, ensure_ascii=False))
        print(f"=== {kind}/{sub}: total {len(all_items)} saved to {out.name} ===")

(HERE / "step2_请求日志.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=2))
print("TOTAL REQUESTS:", REQ_COUNT)

#!/usr/bin/env python3
"""DQ-41 第 4 天 O3 来源审计：取微博热搜存档在开发周 A 周的全部提交（10-06）。

python o3_weibo_fetch.py → raw/weibo/commits.json、raw/weibo/<日>/<提交号>.json
来源：GitHub justjavac/weibo-trending-hot-search，文件 raw/<北京日期>.json。只取源记录，不读任何价格。
入口过滤：提交时刻（UTC）须过 screen_gate.date_ok（开发周、早于止日）；不过的提交不下载内容。
"""

import json
import time
import urllib.request
from pathlib import Path

import screen_gate as G

REPO = "justjavac/weibo-trending-hot-search"
DAYS = ["2026-06-0%d" % i for i in range(1, 8)]  # A 周（开发周）的北京日期文件
OUT = Path(__file__).resolve().parent / "raw" / "weibo"


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rt-dq41-audit"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:  # noqa: BLE001 网络抖动重试
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    for d in DAYS:
        api = (
            "https://api.github.com/repos/%s/commits?path=raw/%s.json&per_page=100"
            % (REPO, d)
        )
        cs = json.loads(get(api))
        for c in cs:
            t = c["commit"]["committer"]["date"]
            rec = {
                "day": d,
                "sha": c["sha"],
                "committer_date": t,
                "author_date": c["commit"]["author"]["date"],
                "author": c["commit"]["author"]["name"],
                "message": c["commit"]["message"],
                "gate_ok": G.date_ok(t),
            }
            if rec["gate_ok"]:
                p = OUT / d / ("%s.json" % c["sha"])
                if not p.exists():
                    p.parent.mkdir(exist_ok=True)
                    raw = "https://raw.githubusercontent.com/%s/%s/raw/%s.json" % (
                        REPO,
                        c["sha"],
                        d,
                    )
                    p.write_bytes(get(raw))
            log.append(rec)
        print(d, "提交", len(cs), flush=True)
    (OUT / "commits.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

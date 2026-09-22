"""DQ-15 平台可得性检查：Reddit 数据分析——正则抽取 pump 合约地址，与 A 周清单/H1 触发比对。
只做可得性统计，不做收益分析。"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

HERE = Path(__file__).parent
EXP = HERE.parent.parent  # .../pump曲线_公开传播信息试取_DQ-15/raw
MINT_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}pump")

a_week_mints = set(l.strip() for l in (EXP / "inputs/a_week_mints.txt").read_text().splitlines() if l.strip())
h1_triggers = {}
with open(EXP / "inputs/h1_triggers_blind.csv") as f:
    next(f)
    for line in f:
        parts = line.strip().split(",")
        if len(parts) >= 2:
            h1_triggers[parts[0]] = parts[1]

SUBS = ["solana", "SolanaMemeCoins", "memecoins", "CryptoMoonShots", "pumpfun"]

summary = {}
all_addr_hits = []  # list of dicts for sample extraction

for sub in SUBS:
    posts = json.loads((HERE / f"posts_{sub}_A周_full.json").read_text())
    comments = json.loads((HERE / f"comments_{sub}_A周_full.json").read_text())

    daily_posts = defaultdict(int)
    daily_comments = defaultdict(int)
    addr_post_count = 0
    addr_comment_count = 0
    addrs_found = set()
    edited_posts = 0
    removed_posts = 0
    deleted_selftext = 0
    edited_comments = 0
    removed_comments = 0

    for p in posts:
        day = datetime.fromtimestamp(p["created_utc"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily_posts[day] += 1
        text = " ".join(str(p.get(k, "")) for k in ["title", "selftext", "url"])
        found = set(MINT_RE.findall(text))
        if found:
            addr_post_count += 1
            addrs_found |= found
            for a in found:
                all_addr_hits.append({
                    "platform": "reddit", "sub": sub, "type": "post",
                    "id": p.get("id"), "author": p.get("author"),
                    "created_utc": p.get("created_utc"),
                    "created_iso": datetime.fromtimestamp(p["created_utc"], tz=timezone.utc).isoformat(),
                    "text": (p.get("title", "") + " | " + p.get("selftext", ""))[:400],
                    "url": f"https://reddit.com{p.get('permalink','')}",
                    "addr": a,
                    "in_a_week": a in a_week_mints,
                    "in_h1": a in h1_triggers,
                    "edited": p.get("edited"),
                    "removed_by_category": p.get("removed_by_category"),
                })
        if p.get("edited"):
            edited_posts += 1
        if p.get("removed_by_category"):
            removed_posts += 1
        if p.get("selftext") in ("[removed]", "[deleted]"):
            deleted_selftext += 1

    for c in comments:
        day = datetime.fromtimestamp(c["created_utc"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily_comments[day] += 1
        text = str(c.get("body", ""))
        found = set(MINT_RE.findall(text))
        if found:
            addr_comment_count += 1
            addrs_found |= found
            for a in found:
                all_addr_hits.append({
                    "platform": "reddit", "sub": sub, "type": "comment",
                    "id": c.get("id"), "author": c.get("author"),
                    "created_utc": c.get("created_utc"),
                    "created_iso": datetime.fromtimestamp(c["created_utc"], tz=timezone.utc).isoformat(),
                    "text": text[:400],
                    "url": f"https://reddit.com{c.get('permalink','')}" if c.get('permalink') else f"https://reddit.com/comments/{c.get('link_id','').replace('t3_','')}/_/{c.get('id')}",
                    "addr": a,
                    "in_a_week": a in a_week_mints,
                    "in_h1": a in h1_triggers,
                    "edited": c.get("edited"),
                    "removed_by_category": c.get("removed_by_category"),
                })
        if c.get("edited"):
            edited_comments += 1
        if c.get("removed_by_category"):
            removed_comments += 1
        if c.get("body") in ("[removed]", "[deleted]"):
            removed_comments += 0  # already counted via removed_by_category typically; note separately

    in_a_week_addrs = addrs_found & a_week_mints
    in_h1_addrs = addrs_found & set(h1_triggers.keys())

    summary[sub] = {
        "posts_total": len(posts),
        "comments_total": len(comments),
        "daily_posts": dict(sorted(daily_posts.items())),
        "daily_comments": dict(sorted(daily_comments.items())),
        "posts_with_addr": addr_post_count,
        "comments_with_addr": addr_comment_count,
        "distinct_addrs_found": len(addrs_found),
        "distinct_addrs_in_a_week_list": len(in_a_week_addrs),
        "distinct_addrs_in_h1_triggers": len(in_h1_addrs),
        "addrs_in_a_week_list": sorted(in_a_week_addrs),
        "addrs_not_in_a_week_list": sorted(addrs_found - a_week_mints),
        "edited_posts": edited_posts,
        "removed_posts_by_category": removed_posts,
        "deleted_or_removed_selftext": deleted_selftext,
        "edited_comments": edited_comments,
        "removed_comments_by_category": removed_comments,
    }

(HERE / "reddit_分析结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
(HERE / "reddit_合约地址命中样本.json").write_text(json.dumps(all_addr_hits, ensure_ascii=False, indent=2))

print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("daily_posts", "daily_comments", "addrs_in_a_week_list", "addrs_not_in_a_week_list")} for k, v in summary.items()}, ensure_ascii=False, indent=2))
print("\n总命中地址样本数:", len(all_addr_hits))

"""DQ-15：把 Reddit 命中样本规范化为 raw/normalized/reddit.csv
列：source,msg_id,ts_utc,url,text,author_kind,edited
去重：同一条消息（sub+type+id）只保留一行（消息可能命中多个合约地址）。
author_kind 判定（启发式，不代表已验证）：
  - 用户名含 bot/auto（不区分大小写）或 author 为 AutoModerator/[deleted] → bot
  - 其余 → human（Reddit 未提供"机器人"官方标记，这是基于用户名的粗判）
"""
import json
import csv
import re
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
OUT = HERE.parent.parent / "normalized" / "reddit.csv"

hits = json.loads((HERE / "reddit_合约地址命中样本.json").read_text())

BOT_RE = re.compile(r"bot|auto", re.IGNORECASE)

def author_kind(author):
    if not author or author in ("[deleted]", "[removed]"):
        return "unknown"
    if author == "AutoModerator":
        return "bot"
    if BOT_RE.search(author):
        return "bot"
    return "human"

seen = {}
for h in hits:
    key = (h["sub"], h["type"], h["id"])
    if key in seen:
        continue  # 同一消息多次命中不同地址，只留一行
    seen[key] = h

rows = []
for h in seen.values():
    msg_id = f"reddit_{h['sub']}_{h['type']}_{h['id']}"
    edited = h.get("edited")
    edited_str = "" if edited in (False, None) else str(edited)
    rows.append({
        "source": f"reddit/r_{h['sub']}",
        "msg_id": msg_id,
        "ts_utc": h["created_iso"],
        "url": h["url"],
        "text": h["text"].replace("\n", " ").strip(),
        "author_kind": author_kind(h.get("author")),
        "edited": edited_str,
    })

rows.sort(key=lambda r: r["ts_utc"])

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["source", "msg_id", "ts_utc", "url", "text", "author_kind", "edited"])
    w.writeheader()
    w.writerows(rows)

print(f"wrote {len(rows)} rows to {OUT}")
from collections import Counter
print(Counter(r["author_kind"] for r in rows))

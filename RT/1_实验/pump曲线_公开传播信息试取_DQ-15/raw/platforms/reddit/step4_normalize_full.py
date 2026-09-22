"""Re-normalize all A-week Reddit posts+comments (untruncated title/selftext/body/url) into raw/normalized/reddit.csv.
Replaces the step-3 output, which cut text at 400 chars and kept only CA-bearing rows."""
import glob, json
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
rows = []
for f in sorted(glob.glob(str(HERE / "*_A周_full.json"))):
    d = json.load(open(f)); d = d.get("data", d) if isinstance(d, dict) else d
    for x in d:
        kind = "post" if "title" in x else "comment"
        text = " | ".join(str(x.get(k) or "") for k in ("title", "selftext", "body", "url") if x.get(k))
        link = f"https://www.reddit.com{x['permalink']}" if x.get("permalink") else ""
        rows.append(dict(source="reddit", msg_id=f"{x.get('subreddit')}/{kind}/{x['id']}", ts_utc=x["created_utc"], url=link,
                         text=text, author_kind="bot" if str(x.get("author", "")).lower() in ("automoderator",) else "human",
                         edited=bool(x.get("edited")), removed=x.get("removed_by_category") or ""))
pd.DataFrame(rows).drop_duplicates("msg_id").to_csv(HERE.parent.parent / "normalized" / "reddit.csv", index=False)
print(len(rows))

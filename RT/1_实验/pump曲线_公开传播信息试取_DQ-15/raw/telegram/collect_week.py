import sys, os, json
sys.path.insert(0, "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad")
from screen import fetch, BASE
from parse_full import parse_messages
from datetime import datetime, timezone

def dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

A_START = dt("2026-06-01T00:00:00+00:00")
A_END = dt("2026-06-08T00:00:00+00:00")

def collect(name, start_before_id, max_pages=400):
    """Walk backward from start_before_id, collect all messages with A_START <= t < A_END.
    Stop when a full page's max time < A_START (gone past window)."""
    all_msgs = {}
    before = start_before_id
    pages = 0
    seen_before = set()
    while pages < max_pages:
        if before in seen_before:
            print(f"  loop detected at before={before}, stop", file=sys.stderr)
            break
        seen_before.add(before)
        url = f"https://t.me/s/{name}?before={before}"
        save_path = f"{BASE}/{name}/before_{before}.html"
        code, text = fetch(url, save_path)
        pages += 1
        if not text:
            print(f"  [{pages}] before={before}: fetch failed", file=sys.stderr)
            break
        msgs = parse_messages(text)
        if not msgs:
            print(f"  [{pages}] before={before}: no messages, stop", file=sys.stderr)
            break
        ids = [m["id"] for m in msgs]
        times = [dt(m["time"]) for m in msgs if m["time"]]
        for m in msgs:
            all_msgs[m["id"]] = m
        min_id = min(ids)
        min_t = min(times) if times else None
        max_t = max(times) if times else None
        print(f"  [{pages}] before={before}: ids {min_id}-{max(ids)} times {min_t} ~ {max_t} (collected so far: {len(all_msgs)})", file=sys.stderr)
        if min_t and min_t < A_START:
            print(f"  page min time {min_t} < A_START, stopping walk-back", file=sys.stderr)
            break
        before = min_id
    # filter to A week window
    in_week = {k: v for k, v in all_msgs.items() if v["time"] and A_START <= dt(v["time"]) < A_END}
    return all_msgs, in_week, pages

if __name__ == "__main__":
    name = sys.argv[1]
    start_before = int(sys.argv[2])
    all_msgs, in_week, pages = collect(name, start_before)
    print(f"=== {name}: {pages} pages fetched, {len(all_msgs)} total msgs collected, {len(in_week)} in A week ===", file=sys.stderr)
    out_dir = "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad"
    with open(f"{out_dir}/{name}_week.json", "w") as f:
        json.dump(sorted(in_week.values(), key=lambda m: m["id"]), f, ensure_ascii=False, indent=1)
    print(json.dumps({"name": name, "pages": pages, "total_collected": len(all_msgs), "in_week": len(in_week)}))

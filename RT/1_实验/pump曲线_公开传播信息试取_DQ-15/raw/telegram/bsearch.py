import sys, re, json
from datetime import datetime, timezone
sys.path.insert(0, "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad")
from screen import fetch, parse_posts, BASE

def dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

A_START = dt("2026-06-01T00:00:00+00:00")
A_END = dt("2026-06-08T00:00:00+00:00")

def fetch_before(name, before_id, save=True):
    if before_id is None:
        url = f"https://t.me/s/{name}"
        save_path = f"{BASE}/{name}/latest.html" if save else None
    else:
        url = f"https://t.me/s/{name}?before={before_id}"
        save_path = f"{BASE}/{name}/before_{before_id}.html" if save else None
    code, text = fetch(url, save_path)
    ids, times = parse_posts(text) if text else ([], [])
    parsed_times = [dt(t) for t in times]
    return code, ids, parsed_times, text

def binary_search_id(name, lo_id, hi_id, target_dt, max_iter=20):
    """Find approx message id whose time is close to target_dt, via binary search on before= param."""
    lo, hi = lo_id, hi_id
    best = None
    for i in range(max_iter):
        mid = (lo + hi) // 2
        code, ids, times, text = fetch_before(name, mid, save=False)
        if not ids:
            print(f"  [{i}] before={mid}: EMPTY page", file=sys.stderr)
            # try nudging
            hi = mid
            continue
        page_min_t, page_max_t = min(times), max(times)
        print(f"  [{i}] before={mid}: ids {min(ids)}-{max(ids)} times {page_min_t.isoformat()} ~ {page_max_t.isoformat()}", file=sys.stderr)
        best = (mid, ids, times)
        if page_max_t < target_dt:
            lo = mid
        elif page_min_t > target_dt:
            hi = mid
        else:
            # target within this page's range
            return mid, ids, times
        if hi - lo <= 25:
            break
    return best[0] if best else None, best[1] if best else [], best[2] if best else []

if __name__ == "__main__":
    name = sys.argv[1]
    latest_id = int(sys.argv[2])
    print(f"=== binary search for {name}, latest_id={latest_id} ===", file=sys.stderr)
    print("--- searching for A_START (2026-06-01) ---", file=sys.stderr)
    mid1, ids1, times1 = binary_search_id(name, 1, latest_id+20, A_START)
    print(f"RESULT near A_START: id~{mid1}", file=sys.stderr)
    print("--- searching for A_END (2026-06-08) ---", file=sys.stderr)
    mid2, ids2, times2 = binary_search_id(name, 1, latest_id+20, A_END)
    print(f"RESULT near A_END: id~{mid2}", file=sys.stderr)
    print(json.dumps({"name": name, "id_near_start": mid1, "id_near_end": mid2}))

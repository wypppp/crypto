import urllib.request, re, time, sys, os, json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
BASE = "/home/ancillary/RT/1_实验/pump曲线_公开传播信息试取_DQ-15/raw/telegram"

req_count = 0
LOG_PATH = "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad/req_count.txt"

def load_count():
    global req_count
    if os.path.exists(LOG_PATH):
        req_count = int(open(LOG_PATH).read().strip() or 0)

def save_count():
    with open(LOG_PATH, "w") as f:
        f.write(str(req_count))

def fetch(url, save_path=None, retries=2):
    global req_count
    load_count()
    if req_count >= 1500:
        raise RuntimeError("hit 1500 request cap")
    for attempt in range(retries+1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            data = e.read()
            code = e.code
        except Exception as e:
            print(f"ERROR fetching {url}: {e}", file=sys.stderr)
            time.sleep(1)
            continue
        req_count += 1
        save_count()
        time.sleep(1.1)
        if code == 429:
            print(f"RATE LIMITED at {url}, stopping", file=sys.stderr)
            raise RuntimeError("429 rate limited")
        text = data.decode("utf-8", errors="replace")
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w") as f:
                f.write(text)
        return code, text
    return None, None

def parse_posts(html):
    """Return list of (msg_id, datetime_str) sorted by id, plus subscriber count if present."""
    posts = re.findall(r'data-post="[^/]+/(\d+)"', html)
    times = re.findall(r'<time datetime="([^"]+)"', html)
    ids = [int(x) for x in posts]
    return ids, times

def get_sub_count(html):
    m = re.search(r'([\d,\. ]+[KM]?)\s*subscribers', html)
    if m:
        return m.group(1)
    return None

def screen_channel(name):
    url = f"https://t.me/s/{name}"
    save_path = f"{BASE}/{name}/latest.html"
    try:
        code, text = fetch(url, save_path)
    except RuntimeError as e:
        return {"name": name, "error": str(e)}
    if code != 200:
        return {"name": name, "http": code, "accessible": False}
    if "tgme_channel_info" not in text and "tgme_widget_message" not in text:
        return {"name": name, "http": code, "accessible": False, "note": "no channel content markers"}
    ids, times = parse_posts(text)
    subs = get_sub_count(text)
    title_m = re.search(r'<div class="tgme_channel_info_header_title"[^>]*>\s*<span[^>]*>([^<]*)</span>', text)
    title = title_m.group(1) if title_m else None
    result = {
        "name": name,
        "http": code,
        "accessible": True,
        "subs": subs,
        "title": title,
        "latest_id": max(ids) if ids else None,
        "latest_time": max(times) if times else None,
        "earliest_id_on_page": min(ids) if ids else None,
        "earliest_time_on_page": min(times) if times else None,
        "n_posts_on_page": len(ids),
    }
    return result

if __name__ == "__main__":
    names = sys.argv[1:]
    results = []
    for name in names:
        r = screen_channel(name)
        print(json.dumps(r, ensure_ascii=False))
        results.append(r)
    out_path = "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad/screen_results.jsonl"
    with open(out_path, "a") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

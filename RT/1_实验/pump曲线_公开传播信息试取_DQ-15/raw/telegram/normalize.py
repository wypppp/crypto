import json, csv, sys

CHANNELS = {
    "solana100xcall": "bot",
    "pfultimate": "bot",
    "memecoin_finder": "human",
    "memecoin_daily": "human",
    "devcabal": "human",
}

OUT_DIR = "/home/ancillary/RT/1_实验/pump曲线_公开传播信息试取_DQ-15/raw/normalized"
SCRATCH = "/tmp/claude-1000/-home-ancillary/cb9b2558-fc70-472b-b4a2-ffe63c926c03/scratchpad"

for name, kind in CHANNELS.items():
    data = json.load(open(f"{SCRATCH}/{name}_week.json"))
    data.sort(key=lambda m: m["id"])
    out_path = f"{OUT_DIR}/tg_{name}.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "msg_id", "ts_utc", "url", "text", "author_kind", "edited"])
        for m in data:
            url = f"https://t.me/{name}/{m['id']}"
            w.writerow([name, m["id"], m["time"], url, m["text"], kind, m["edited"]])
    print(f"{out_path}: {len(data)} rows")

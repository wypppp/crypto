"""Download a finished Dune execution as CSV, refusing results larger than a size cap (exports are billed per MB).

usage: python3 dune_get.py <execution_id> <Q1|Q2> [--max-mb 1.5]
Reads DUNE_API_KEY from /home/ancillary/.env by key name (never printed). Writes raw/dune/<name>.csv and
raw/dune/<name>_status.json (state, row count, bytes, execution cost if reported).
"""
import json, re, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
KEY = re.search(r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)", (HERE.parents[2] / ".env").read_text(), re.M).group(1)
API = "https://api.dune.com/api/v1"

def get(path, raw=False):
    req = urllib.request.Request(API + path, headers={"X-Dune-API-Key": KEY})
    with urllib.request.urlopen(req, timeout=300) as r:
        b = r.read()
    return b if raw else json.loads(b)

def main():
    eid, name = sys.argv[1], sys.argv[2]
    cap = float(sys.argv[sys.argv.index("--max-mb") + 1]) if "--max-mb" in sys.argv else 1.5
    st = get(f"/execution/{eid}/status")
    out = HERE / "raw" / "dune"; out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}_status.json").write_text(json.dumps(st, indent=1))
    meta = st.get("result_metadata") or {}
    rows, size = meta.get("total_row_count"), meta.get("result_set_bytes")
    print("state", st.get("state"), "rows", rows, "bytes", size, "cost", st.get("execution_cost_credits"))
    if st.get("state") != "QUERY_STATE_COMPLETED":
        sys.exit("not completed")
    if size is None or size > cap * 1e6:
        sys.exit(f"result size {size} bytes exceeds cap {cap} MB (or unknown): not downloading")
    parts, off, page = [], 0, 30000
    while off < rows:
        b = get(f"/execution/{eid}/results/csv?limit={page}&offset={off}", raw=True).decode()
        parts.append(b if off == 0 else b.split("\n", 1)[1])
        off += page
    (out / f"{name}.csv").write_text("".join(parts))
    print("saved", out / f"{name}.csv")

if __name__ == "__main__":
    main()

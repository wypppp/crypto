"""Save one finished Dune execution after checking result size.

Usage: python get_s2_dune.py EXECUTION_ID LABEL [MAX_MB]
Reads DUNE_API_KEY by name from workspace .env, never prints or writes it.
The JSON results endpoint can consume export credits; default cap is 1 MB.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API = "https://api.dune.com/api/v1"
KEY_MATCH = re.search(
    r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)",
    (ROOT.parents[2] / ".env").read_text(),
    re.M,
)
if KEY_MATCH is None:
    raise RuntimeError("DUNE_API_KEY not found")
KEY = KEY_MATCH.group(1)


def get(path: str) -> dict:
    req = urllib.request.Request(
        API + path, headers={"X-Dune-API-Key": KEY}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except (ConnectionError, TimeoutError) as exc:
            if attempt == 3:
                raise
            time.sleep(1 + attempt * 2)


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: python get_s2_dune.py EXECUTION_ID LABEL [MAX_MB]")
    execution_id, label = sys.argv[1:3]
    if re.fullmatch(r"[A-Za-z0-9_-]+", label) is None:
        raise ValueError("LABEL must contain only letters, digits, _ or -")
    max_mb = float(sys.argv[3]) if len(sys.argv) == 4 else 1.0
    raw = ROOT / "raw" / "s2"
    raw.mkdir(parents=True, exist_ok=True)
    status = get(f"/execution/{execution_id}/status")
    (raw / f"{label}_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2)
    )
    meta = status.get("result_metadata") or {}
    row_count = meta.get("total_row_count")
    result_bytes = meta.get("result_set_bytes")
    print(
        "state", status.get("state"),
        "rows", row_count,
        "bytes", result_bytes,
        "execution_cost_credits", status.get("execution_cost_credits"),
    )
    if status.get("state") != "QUERY_STATE_COMPLETED":
        return
    if row_count is None or result_bytes is None or result_bytes > max_mb * 1e6:
        print("result not downloaded: size unknown or above cap")
        return
    rows = []
    offset = 0
    # Free-tier response limits apply to cells as well as bytes. The A-stage
    # result has 17 columns, so 500 rows returns HTTP 402; 40 rows is small.
    page_size = 40
    page_dir = raw / f"{label}_pages"
    page_dir.mkdir(exist_ok=True)
    while offset < row_count:
        page_path = page_dir / f"{offset:07d}.json"
        if page_path.exists():
            page = json.loads(page_path.read_text())
        else:
            page = get(f"/execution/{execution_id}/results?limit={page_size}&offset={offset}")
            page_path.write_text(json.dumps(page))
        batch = page["result"]["rows"]
        if not batch:
            raise RuntimeError(f"empty page before expected row count at {offset}")
        rows.extend(batch)
        offset += len(batch)
    if len(rows) != row_count:
        raise RuntimeError(f"expected {row_count} rows; got {len(rows)}")
    (raw / f"{label}.json").write_text(
        json.dumps({"execution_id": execution_id, "rows": rows},
                   ensure_ascii=False, indent=2)
    )
    print("saved", raw / f"{label}.json")


if __name__ == "__main__":
    main()

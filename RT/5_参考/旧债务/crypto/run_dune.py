#!/usr/bin/env python3
"""Execute the SQL through Dune's arbitrary-SQL API and download every row."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_ROOT = "https://api.dune.com/api/v1"
TERMINAL_STATES = {
    "QUERY_STATE_COMPLETED",
    "QUERY_STATE_COMPLETED_PARTIAL",
    "QUERY_STATE_FAILED",
    "QUERY_STATE_CANCELED",
    "QUERY_STATE_EXPIRED",
}


def dune_key(root: Path) -> str | None:
    """Read the process, workspace .env, then the caller's local .env."""
    key = os.environ.get("DUNE_API_KEY")
    if key:
        return key
    workspace = Path(__file__).resolve().parents[2]
    for env_path in dict.fromkeys((workspace / ".env", root / ".env")):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "DUNE_API_KEY":
                key = value.strip().strip("'\"")
                if key:
                    return key
    return None


def request(
    path: str,
    key: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> bytes:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-Dune-Api-Key": key}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(6):
        req = urllib.request.Request(
            f"{API_ROOT}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Dune HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 5:
                raise
            delay = min(30, 2**attempt)
            print(f"transient Dune connection error; retrying in {delay}s", flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


def json_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return json.loads(request(*args, **kwargs))


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", type=Path, default=root / "01_token_metrics.sql")
    parser.add_argument("--out", type=Path, default=root / "data/dune_token_metrics.csv")
    parser.add_argument("--performance", choices=("small", "medium", "large"), default="medium")
    parser.add_argument(
        "--validate", action="store_true", help="Ask Trino to validate SQL without running it"
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-minutes", type=float, default=90.0)
    parser.add_argument(
        "--execution-id", help="Resume polling/downloading an existing Dune execution"
    )
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Apply an exact in-memory SQL substitution; repeat for multiple values",
    )
    parser.add_argument(
        "--expanded-sql-out",
        type=Path,
        help="Persist the substituted SQL before validation/execution",
    )
    args = parser.parse_args()

    key = dune_key(root)
    if not key:
        raise SystemExit(
            "DUNE_API_KEY is not set. Put a read-scope Dune API key in the process "
            "environment; do not paste it into source files."
        )
    sql = args.sql.read_text(encoding="utf-8")
    for replacement in args.replace:
        if "=" not in replacement:
            raise SystemExit(f"--replace must be OLD=NEW: {replacement!r}")
        old, new = replacement.split("=", 1)
        occurrences = sql.count(old)
        if occurrences == 0:
            raise SystemExit(f"--replace source text not found: {old!r}")
        sql = sql.replace(old, new)
        print(f"SQL substitution: {old!r} -> {new!r} ({occurrences} occurrence(s))")
    if args.expanded_sql_out:
        args.expanded_sql_out.parent.mkdir(parents=True, exist_ok=True)
        args.expanded_sql_out.write_text(sql, encoding="utf-8")
        print(f"wrote expanded SQL -> {args.expanded_sql_out}")
    if args.validate:
        sql = "EXPLAIN (TYPE VALIDATE)\n" + sql
    if args.execution_id:
        execution_id = args.execution_id
        print(f"resuming Dune execution: {execution_id}", flush=True)
    else:
        started = json_request(
            "/sql/execute",
            key,
            method="POST",
            payload={"sql": sql, "performance": args.performance},
        )
        execution_id = started["execution_id"]
        print(f"Dune execution: {execution_id} ({started.get('state')})", flush=True)

    deadline = time.monotonic() + args.timeout_minutes * 60
    while True:
        status = json_request(f"/execution/{execution_id}/status", key)
        state = status["state"]
        print(f"Dune state: {state}", flush=True)
        if state in TERMINAL_STATES:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Dune execution did not finish: {execution_id}")
        time.sleep(args.poll_seconds)

    if state != "QUERY_STATE_COMPLETED":
        raise RuntimeError(json.dumps(status, ensure_ascii=False, indent=2))
    result_metadata = status.get("result_metadata") or {}
    expected_rows = result_metadata.get("total_row_count")
    if expected_rows is None:
        expected_rows = result_metadata.get("row_count")
    # Dune currently caps a CSV response below the requested one-million-row
    # limit (observed cap: 32,000). Page explicitly so a successful execution
    # can never be mistaken for a complete local file after a silent API cap.
    # Smaller pages complete reliably within short-lived execution sessions;
    # they are fetched concurrently below, so this does not add latency.
    page_size = 10_000
    csv_parts: list[bytes] = []
    header: bytes | None = None
    actual_rows = 0

    def fetch_result_page(offset: int) -> tuple[int, bytes]:
        query = urllib.parse.urlencode({"limit": page_size, "offset": offset})
        return offset, request(
            f"/execution/{execution_id}/results/csv?{query}", key, timeout=300
        )

    if expected_rows is not None:
        offsets = list(range(0, int(expected_rows), page_size))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, len(offsets) or 1)
        ) as pool:
            pages = sorted(pool.map(fetch_result_page, offsets))
    else:
        # Metadata should normally contain the count. Keep a one-page fallback
        # rather than guessing an unbounded number of concurrent requests.
        pages = [fetch_result_page(0)]

    for page_number, (offset, page) in enumerate(pages, start=1):
        first_newline = page.find(b"\n")
        if first_newline < 0:
            raise RuntimeError("Dune CSV page has no header newline")
        page_header = page[: first_newline + 1]
        page_body = page[first_newline + 1 :]
        if header is None:
            header = page_header
            csv_parts.append(header)
        elif page_header != header:
            raise RuntimeError("Dune CSV header changed between result pages")
        page_rows = page_body.count(b"\n")
        if page_body and not page_body.endswith(b"\n"):
            page_rows += 1
            page_body += b"\n"
        if page_rows == 0:
            continue
        csv_parts.append(page_body)
        actual_rows += page_rows
        print(
            f"downloaded result page {page_number}: {page_rows} rows "
            f"({actual_rows} cumulative)",
            flush=True,
        )
    csv_bytes = b"".join(csv_parts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(csv_bytes)
    if expected_rows is not None and actual_rows != int(expected_rows):
        raise RuntimeError(
            f"downloaded {actual_rows} rows but Dune reports {expected_rows}; "
            "refusing to treat a partial download as the universe"
        )
    print(
        f"downloaded all {actual_rows} rows -> {args.out}; "
        f"execution cost={status.get('execution_cost_credits', '?')} credits",
        flush=True,
    )


if __name__ == "__main__":
    main()

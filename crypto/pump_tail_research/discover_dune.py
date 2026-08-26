#!/usr/bin/env python3
"""Search Dune's dataset catalog without exposing the local API key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_dune import dune_key, json_request


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("queries", nargs="+", help="Dune dataset search terms")
    parser.add_argument("--out", type=Path, default=Path("/tmp/dune_datasets.json"))
    args = parser.parse_args()
    key = dune_key(root)
    if not key:
        raise SystemExit("DUNE_API_KEY is missing")
    combined = []
    for query in args.queries:
        payload = {
            "query": query,
            "include_metadata": True,
            "include_private": False,
            "include_schema": True,
            "limit": 100,
            "offset": 0,
        }
        response = json_request("/datasets/search", key, method="POST", payload=payload)
        results = response.get("results", [])
        print(f"{query!r}: {len(results)} returned / {response.get('total')} total")
        for result in results:
            name = result.get("full_name")
            print(f"  {name}")
            combined.append({"search_query": query, **result})
    args.out.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"saved schemas -> {args.out}")


if __name__ == "__main__":
    main()

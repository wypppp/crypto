#!/usr/bin/env python3
"""Collect current GeckoTerminal pool composition for material CCA pools."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = "https://api.geckoterminal.com/api/v2"


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch(url: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json;version=20230203",
            "user-agent": "primary-issuance-research/0.1",
        },
    )
    failures = []
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            failures.append(str(exc))
            if attempt < 4:
                time.sleep(10)
    raise RuntimeError("; ".join(failures))


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--onchain",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_onchain.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_current.json",
    )
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--sleep-seconds", type=float, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    source = json.loads(args.onchain.read_text())
    if not source.get("complete"):
        raise RuntimeError("on-chain pool list is incomplete")
    pool_ids = sorted({row["pool_id"].lower() for row in source["rows"]})
    results = []
    errors = {}
    batches = chunks(pool_ids, args.batch_size)
    for index, batch in enumerate(batches, 1):
        addresses = ",".join(batch)
        query = urllib.parse.urlencode({"include_composition": "true"})
        url = f"{ROOT}/networks/robinhood/pools/multi/{addresses}?{query}"
        try:
            payload = fetch(url, args.timeout)
            results.extend(payload.get("data", []))
        except Exception as exc:
            errors[str(index)] = str(exc)
        print(
            json.dumps(
                {"batch": index, "batches": len(batches), "rows": len(results), "errors": len(errors)}
            ),
            flush=True,
        )
        if index < len(batches):
            time.sleep(args.sleep_seconds)

    observed = {row["attributes"]["address"].lower() for row in results}
    missing = sorted(set(pool_ids) - observed)
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "GeckoTerminal public API; mother universe remains on-chain",
        "requested_pools": len(pool_ids),
        "rows": results,
        "complete": not errors and not missing,
        "missing_pool_ids": missing,
        "errors": errors,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "requested_pools": len(pool_ids),
                "rows": len(results),
                "complete": output["complete"],
                "missing": len(missing),
                "errors": len(errors),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

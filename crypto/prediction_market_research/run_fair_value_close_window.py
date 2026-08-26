"""Exploratory close-window replay suggested by same-pilot calibration."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from shadow_mm.replay import MakerReplayConfig, replay_paths


def configs(latencies=(0, 5, 15)):
    answer = []
    for latency in latencies:
        for window in (60, 30):
            answer.append(
                MakerReplayConfig(
                    name=f"fair_join_{latency}s_last_{window}s",
                    latency_seconds=latency,
                    quote_size=Decimal("5"),
                    policy="fair_join",
                    half_spread=Decimal("0.01"),
                    stop_before_end_seconds=15,
                    start_before_end_seconds=window,
                    max_shares_per_token=Decimal("50"),
                    max_unpaired_shares_per_market=Decimal("15"),
                )
            )
    return answer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--latency", type=float, action="append")
    args = parser.parse_args()
    result = replay_paths(
        [args.input, args.resolutions],
        configs(tuple(args.latency) if args.latency else (0, 5, 15)),
    )
    result["analysis_status"] = "posthoc_close_window_on_bad_quality_pilot"
    result["selection_warning"] = (
        "The 60s/30s windows were chosen after calibration on these same outcomes. "
        "Any positive cell requires a fresh forward capture."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Exploratory fair-value/adverse-selection replay on the frozen pilot capture.

This is deliberately a small grid.  The best cell is descriptive and must not
be promoted to a forward estimate because the same resolved pilot is used to
compare margins.
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from shadow_mm.replay import MakerReplayConfig, replay_paths


def configs():
    common = {
        "quote_size": Decimal("5"),
        "max_shares_per_token": Decimal("50"),
        "max_unpaired_shares_per_market": Decimal("15"),
    }
    return [
        MakerReplayConfig(
            name="fair_join_0s_margin_1c",
            latency_seconds=0,
            policy="fair_join",
            half_spread=Decimal("0.01"),
            **common,
        ),
        MakerReplayConfig(
            name="fair_value_0s_margin_1c",
            latency_seconds=0,
            policy="fair_value",
            half_spread=Decimal("0.01"),
            **common,
        ),
        MakerReplayConfig(
            name="fair_join_15s_margin_1c",
            latency_seconds=15,
            policy="fair_join",
            half_spread=Decimal("0.01"),
            **common,
        ),
        MakerReplayConfig(
            name="fair_join_15s_margin_3c",
            latency_seconds=15,
            policy="fair_join",
            half_spread=Decimal("0.03"),
            **common,
        ),
        MakerReplayConfig(
            name="fair_join_15s_margin_5c",
            latency_seconds=15,
            policy="fair_join",
            half_spread=Decimal("0.05"),
            **common,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = replay_paths([args.input, args.resolutions], configs())
    result["analysis_status"] = "exploratory_bad_quality_pilot"
    result["selection_warning"] = (
        "Margins are compared on the same resolved pilot; the best cell is not "
        "an out-of-sample profit estimate."
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

"""Evaluate the transparent fair-value model at fixed pre-resolution horizons."""

import argparse
import json
import math
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from shadow_mm.fair_value import FairValueModel
from shadow_mm.replay import ReplayMarket, iter_events


HORIZONS = (240, 120, 60, 30, 15)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    targets = {}
    winners = {}
    for event in iter_events(args.resolutions):
        payload = event.get("payload") or {}
        condition_id = str(payload.get("market") or payload.get("condition_id") or "")
        if not condition_id:
            continue
        if payload.get("price_to_beat") not in (None, ""):
            targets[condition_id] = Decimal(str(payload["price_to_beat"]))
        if payload.get("winning_asset_id"):
            winners[condition_id] = str(payload["winning_asset_id"])

    model = FairValueModel(["BTC", "ETH", "SOL"])
    markets = {}
    forecasts = {}
    events_read = 0
    for event in iter_events(args.input):
        events_read += 1
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if event.get("event_type") in ("discovery_update", "discovery_heartbeat"):
            for row in payload.get("markets", []) or []:
                market = ReplayMarket.from_record(row)
                if market.condition_id in targets and market.price_to_beat is None:
                    market = replace(
                        market,
                        price_to_beat=targets[market.condition_id],
                    )
                if market.condition_id:
                    markets[market.condition_id] = market
            continue
        timestamp_ns = int(
            event.get("socket_received_at_ns") or event.get("received_at_ns") or 0
        )
        changed_symbol = model.update_event(event, timestamp_ns)
        if changed_symbol is None:
            continue
        for condition_id, market in markets.items():
            if (
                market.symbol.upper() != changed_symbol
                or condition_id not in winners
                or market.end_ns is None
                or market.window_start_ns is None
                or timestamp_ns < market.window_start_ns
                or timestamp_ns >= market.end_ns
            ):
                continue
            probability = model.probability_up(market, timestamp_ns)
            if probability is None:
                continue
            remaining = (market.end_ns - timestamp_ns) / 1_000_000_000
            for horizon in HORIZONS:
                key = (condition_id, horizon)
                if remaining <= horizon and key not in forecasts:
                    up_token = next(
                        (
                            token_id
                            for token_id, outcome in market.outcomes.items()
                            if outcome.lower() == "up"
                        ),
                        None,
                    )
                    forecasts[key] = {
                        "condition_id": condition_id,
                        "symbol": market.symbol,
                        "interval_minutes": market.interval_minutes,
                        "horizon_seconds": horizon,
                        "actual_remaining_seconds": remaining,
                        "probability_up": float(probability),
                        "up_won": int(up_token == winners[condition_id]),
                    }

    by_horizon = []
    for horizon in HORIZONS:
        rows = [row for (_, h), row in forecasts.items() if h == horizon]
        n = len(rows)
        brier = sum((row["probability_up"] - row["up_won"]) ** 2 for row in rows) / n if n else None
        log_loss = (
            sum(
                -(
                    row["up_won"] * math.log(min(max(row["probability_up"], 1e-9), 1 - 1e-9))
                    + (1 - row["up_won"])
                    * math.log(min(max(1 - row["probability_up"], 1e-9), 1 - 1e-9))
                )
                for row in rows
            )
            / n
            if n
            else None
        )
        accuracy = (
            sum(int((row["probability_up"] >= 0.5) == bool(row["up_won"])) for row in rows) / n
            if n
            else None
        )
        by_horizon.append(
            {
                "horizon_seconds": horizon,
                "n": n,
                "brier": brier,
                "log_loss": log_loss,
                "directional_accuracy": accuracy,
                "mean_abs_probability_from_half": (
                    sum(abs(row["probability_up"] - 0.5) for row in rows) / n
                    if n
                    else None
                ),
            }
        )

    answer = {
        "events_read_n": events_read,
        "resolved_targets_n": len(targets),
        "markets_seen_n": len(markets),
        "forecasts_n": len(forecasts),
        "by_horizon": by_horizon,
        "forecasts": sorted(
            forecasts.values(),
            key=lambda row: (row["horizon_seconds"], row["condition_id"]),
        ),
        "warning": "Exploratory calibration on 18 resolved bad-quality pilot markets.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(answer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out), "by_horizon": by_horizon}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

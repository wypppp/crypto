#!/usr/bin/env python3
"""Merge available MetaDAO price histories without converting missing data to zero."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SECONDS_DAY = 86400
SECONDS_180D = 180 * SECONDS_DAY


def accepted_raw(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    for field in ("finalRaiseAmount", "totalApprovedAmount", "totalCommittedAmount"):
        value = decoded.get(field)
        if value is not None:
            return int(value)
    return 0


def launch_end(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    return int(
        launch.get("closed_at")
        or decoded.get("unixTimestampCompleted")
        or decoded.get("unixTimestampClosed")
        or int(launch["started_at"]) + int(decoded.get("secondsForLaunch") or 0)
    )


def percentile(values: Iterable[float], q: float) -> float | None:
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - index) + values[hi] * (index - lo)


def fmt(value: float | None, digits: int = 2) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--launches", type=Path, default=base / "data/metadao_current_launch_accounts.json"
    )
    parser.add_argument(
        "--markets", type=Path, default=base / "data/metadao_market_snapshot.json"
    )
    parser.add_argument(
        "--coingecko-dir", type=Path, default=base / "data/metadao_coingecko_history"
    )
    parser.add_argument(
        "--gecko-dir", type=Path, default=base / "data/metadao_ohlcv_daily"
    )
    parser.add_argument(
        "--allocations", type=Path, default=base / "output/metadao_allocation_audit.json"
    )
    parser.add_argument(
        "--output-json", type=Path, default=base / "output/metadao_outcomes_partial.json"
    )
    parser.add_argument(
        "--output-csv", type=Path, default=base / "output/metadao_outcomes_partial.csv"
    )
    parser.add_argument(
        "--output-md", type=Path, default=base / "output/metadao_outcomes_partial.md"
    )
    parser.add_argument("--minimum-raise-usd", type=float, default=10_000)
    args = parser.parse_args()

    now = int(datetime.now(timezone.utc).timestamp())
    markets = {row["launch_account"]: row for row in json.loads(args.markets.read_text())}
    allocations = {
        row["launch_account"]: row
        for row in json.loads(args.allocations.read_text())["by_launch"]
    }
    cg_by_mint = {}
    for path in args.coingecko_dir.glob("*.json"):
        payload = json.loads(path.read_text())
        cg_by_mint[payload["token_mint"]] = payload
    gt_by_mint = {}
    for path in args.gecko_dir.glob("*.json"):
        payload = json.loads(path.read_text())
        gt_by_mint[payload["token_mint"]] = payload

    launches = [
        row
        for row in json.loads(args.launches.read_text())
        if row["state"] == "Complete"
        and accepted_raw(row) / 1_000_000 >= args.minimum_raise_usd
    ]
    rows = []
    for launch in launches:
        mint = launch["base_mint"]
        end = launch_end(launch)
        target_end = min(now, end + SECONDS_180D)
        issue = accepted_raw(launch) / 1_000_000 / 10_000_000
        observations: list[dict[str, Any]] = []
        cg = cg_by_mint.get(mint)
        if cg:
            for timestamp_ms, price in cg.get("prices", []):
                timestamp = int(timestamp_ms / 1000)
                if end - SECONDS_DAY <= timestamp <= target_end + SECONDS_DAY:
                    observations.append(
                        {"timestamp": timestamp, "price": float(price), "kind": "sample", "source": "CoinGecko"}
                    )
        gt = gt_by_mint.get(mint)
        if gt:
            for candle in gt.get("candles", []):
                timestamp, _open, high, _low, close, _volume = candle
                if end - SECONDS_DAY <= timestamp <= target_end + SECONDS_DAY:
                    # A daily candle is timestamped at UTC midnight.  For the
                    # launch-day pool candle, the pool did not exist before
                    # launch completion, so keep the high but left-censor its
                    # event time at T+0 rather than reporting a negative day.
                    effective_open = max(int(timestamp), end)
                    observations.append(
                        {"timestamp": effective_open, "price": float(high), "kind": "daily_high", "source": "GeckoTerminal"}
                    )
                    observations.append(
                        {"timestamp": int(timestamp) + SECONDS_DAY - 1, "price": float(close), "kind": "daily_close", "source": "GeckoTerminal"}
                    )
        observations.sort(key=lambda item: item["timestamp"])
        max_observation = max(observations, key=lambda item: item["price"], default=None)
        five = [item for item in observations if item["price"] / issue >= 5]
        first_five = min(five, key=lambda item: item["timestamp"], default=None)
        sources = sorted({item["source"] for item in observations})
        market = markets.get(launch["launch_account"], {})
        allocation = allocations.get(launch["launch_account"], {})
        approval_dollars_ratio = allocation.get("approval_dollars_ratio")
        max_x = max_observation["price"] / issue if max_observation else None
        current_x = market.get("screen_spot_multiple_if_10m_public_tokens")
        rows.append(
            {
                "version": launch["version"],
                "launch_account": launch["launch_account"],
                "token_mint": mint,
                "symbol": market.get("token_symbol") or "",
                "launch_end_timestamp": end,
                "age_days": (now - end) / SECONDS_DAY,
                "mature_180d": now >= end + SECONDS_180D,
                "accepted_usd": accepted_raw(launch) / 1_000_000,
                "issue_price_usd": issue,
                "has_market_pair": market.get("has_market_pair", False),
                "history_sources": "+".join(sources),
                "price_observations": len(observations),
                "first_observation_delay_days": (observations[0]["timestamp"] - end) / SECONDS_DAY
                if observations
                else None,
                "last_observation_day": (observations[-1]["timestamp"] - end) / SECONDS_DAY
                if observations
                else None,
                "max_observed_x": max_x,
                "max_observed_day": (max_observation["timestamp"] - end) / SECONDS_DAY
                if max_observation
                else None,
                "max_observed_kind": max_observation["kind"] if max_observation else "",
                "observed_ge_5x": bool(five),
                "first_observed_ge_5x_day": (first_five["timestamp"] - end) / SECONDS_DAY
                if first_five
                else None,
                "current_spot_x": current_x,
                "aggregate_approval_dollars_ratio": approval_dollars_ratio,
                "commitment_required_per_100_accepted_aggregate": 100 / approval_dollars_ratio
                if approval_dollars_ratio
                else None,
                "commitment_roi_at_5x_gross": 4 * approval_dollars_ratio
                if approval_dollars_ratio is not None
                else None,
                "commitment_roi_at_observed_max_gross": approval_dollars_ratio * (max_x - 1)
                if approval_dollars_ratio is not None and max_x is not None
                else None,
                "commitment_roi_at_current_spot_gross": approval_dollars_ratio * (current_x - 1)
                if approval_dollars_ratio is not None and current_x is not None
                else None,
                "current_liquidity_usd": market.get("liquidity_usd"),
                "current_quote_reserve_usd": market.get("quote_reserve_usd"),
            }
        )

    mature = [row for row in rows if row["mature_180d"]]
    mature_observed = [row for row in mature if row["price_observations"]]
    mature_five = [row for row in mature if row["observed_ge_5x"]]
    all_five = [row for row in rows if row["observed_ge_5x"]]
    observed_maxes = [row["max_observed_x"] for row in mature_observed]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "issue_price": "confirmed public allocation: accepted USDC / 10,000,000 participant tokens",
            "max": "maximum of CoinGecko sampled price and GeckoTerminal daily high, capped at T+180d/current",
            "missing": "unknown, never imputed as zero",
            "warning": "daily high is not an executable exit; source coverage can begin after launch",
        },
        "material_launches": len(rows),
        "mature_180d_launches": len(mature),
        "mature_with_any_price_history": len(mature_observed),
        "mature_observed_ge_5x": len(mature_five),
        "full_mature_cohort_observed_ge_5x_lower_bound": len(mature_five) / len(mature) if mature else None,
        "observed_mature_ge_5x_rate": len(mature_five) / len(mature_observed) if mature_observed else None,
        "all_age_observed_ge_5x": len(all_five),
        "mature_max_observed_quantiles": {
            "p50": percentile(observed_maxes, 0.50),
            "p75": percentile(observed_maxes, 0.75),
            "p90": percentile(observed_maxes, 0.90),
            "max": max(observed_maxes) if observed_maxes else None,
        },
        "by_launch": rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# MetaDAO historical outcomes — partial, missing-preserving",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        f"- Material completed launches: **{len(rows)}**",
        f"- Mature at 180 days: **{len(mature)}**",
        f"- Mature with any historical price: **{len(mature_observed)}/{len(mature)}**",
        f"- Observed >=5x among mature full cohort (strict lower bound): **{len(mature_five)}/{len(mature)} = {100 * summary['full_mature_cohort_observed_ge_5x_lower_bound']:.1f}%**",
        f"- Observed >=5x among mature with price data: **{len(mature_five)}/{len(mature_observed)} = {100 * summary['observed_mature_ge_5x_rate']:.1f}%**",
        f"- Observed >=5x at any age: **{len(all_five)}/{len(rows)}**",
        "",
        "> Missing histories remain unknown. Daily highs and sampled prices establish a candidate, not a realizable $100->$500 exit.",
        "",
        "| Symbol | Mature | Max observed | >=5x | Accept/commit | Commit per $100 accepted | Max commitment ROI* | Current |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['symbol'] or row['token_mint'][:8]} | {str(row['mature_180d']).lower()} | {fmt(row['max_observed_x'])}x | {str(row['observed_ge_5x']).lower()} | {fmt(100 * row['aggregate_approval_dollars_ratio']) + '%' if row['aggregate_approval_dollars_ratio'] is not None else 'NA'} | ${fmt(row['commitment_required_per_100_accepted_aggregate'], 0)} | {fmt(100 * row['commitment_roi_at_observed_max_gross']) + '%' if row['commitment_roi_at_observed_max_gross'] is not None else 'NA'} | {fmt(row['current_spot_x'])}x |"
        )
    lines += [
        "",
        "`*` Max commitment ROI = aggregate accepted/committed dollars × (observed max multiple - 1). It assumes a perfect exit and full refund; it is a capital-dilution diagnostic, not realizable ROI. In v0.7 approvals vary by wallet, so aggregate ratios are not individual guarantees.",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps({key: value for key, value in summary.items() if key != "by_launch"}, indent=2))


if __name__ == "__main__":
    main()

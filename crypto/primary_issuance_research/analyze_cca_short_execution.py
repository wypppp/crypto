#!/usr/bin/env python3
"""Analyze actual short-CCA allocations against first-24h observed swap capacity."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Iterable

from analyze_cca_peak_minute_swaps import decode_swap


getcontext().prec = 60
WEI = Decimal(10**18)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
TARGET_BANDS = {
    "100": (Decimal("75"), Decimal("175"), Decimal("100")),
    "300": (Decimal("200"), Decimal("400"), Decimal("300")),
    "500": (Decimal("425"), Decimal("650"), Decimal("500")),
}
FLOOD_START = int(datetime(2026, 8, 3, tzinfo=timezone.utc).timestamp())


def quantile(values: Iterable[float], probability: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def quantiles(values: Iterable[float]) -> dict[str, float | None]:
    rows = list(values)
    return {
        name: quantile(rows, probability)
        for name, probability in (
            ("p10", 0.10),
            ("p25", 0.25),
            ("p50", 0.50),
            ("p75", 0.75),
            ("p90", 0.90),
        )
    }


def iso_timestamp(timestamp: int | None) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else ""


def candle_close(candles: dict[int, list], timestamp: int, granularity: int) -> Decimal:
    key = (timestamp // granularity) * granularity
    if key in candles:
        return Decimal(str(candles[key][4]))
    nearest = min(candles, key=lambda value: abs(value - key))
    if abs(nearest - key) > granularity:
        raise RuntimeError(f"no nearby ETHUSD candle for {timestamp}")
    return Decimal(str(candles[nearest][4]))


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allocations",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations.json",
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations_enriched.json",
    )
    parser.add_argument(
        "--candles",
        type=Path,
        default=base_dir / "data/coinbase_ethusd_cca_short_hourly.json",
    )
    parser.add_argument(
        "--daily",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily.csv",
    )
    parser.add_argument(
        "--swap-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_24h_swaps",
    )
    parser.add_argument(
        "--witness-enrichment",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_witness_transactions.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_short_execution_bids.csv",
    )
    parser.add_argument(
        "--output-auctions-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_short_execution_auctions.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=base_dir / "output/cca_robinhood_short_execution_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=base_dir / "output/cca_robinhood_short_execution.md",
    )
    args = parser.parse_args()

    allocations = json.loads(args.allocations.read_text())
    enriched = json.loads(args.enriched.read_text())
    candle_payload = json.loads(args.candles.read_text())
    swap_audit = json.loads((args.swap_dir / "audit.json").read_text())
    if not allocations.get("complete") or len(allocations.get("jobs", [])) != 29:
        raise RuntimeError("allocation collection is incomplete")
    if not enriched.get("complete"):
        raise RuntimeError("allocation enrichment is incomplete")
    if not candle_payload.get("complete"):
        raise RuntimeError("ETHUSD candle collection is incomplete")
    if not swap_audit.get("complete"):
        raise RuntimeError("24h swap collection is incomplete")
    witness_enrichment = (
        json.loads(args.witness_enrichment.read_text())
        if args.witness_enrichment.exists()
        else None
    )
    witness_transactions = (
        witness_enrichment.get("transactions", {}) if witness_enrichment else {}
    )
    gas_audit_complete = bool(witness_enrichment and witness_enrichment.get("complete"))

    daily = {row["auction"].lower(): row for row in csv.DictReader(args.daily.open())}
    granularity = int(candle_payload["granularity"])
    candles = {int(row[0]): row for row in candle_payload["candles"]}
    blocks = enriched["blocks"]
    owner_code = enriched["owner_code"]

    swaps_by_pool: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(args.swap_dir.glob("0x*.json")):
        payload = json.loads(path.read_text())
        row = daily[payload["auction"].lower()]
        issue_price = Decimal(str(row["issue_vwap_eth_per_token"]))
        swaps_by_pool[payload["pool_id"].lower()] = [
            decode_swap(log, issue_price) for log in payload["raw_logs"]
        ]

    bid_rows: list[dict[str, Any]] = []
    for job in allocations["jobs"]:
        event_sets: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
        for event in job["events"]:
            event_sets[int(event["bid_id"])][event["event"]] = event
        pool_swaps = swaps_by_pool[job["pool_id"]]
        sell_swaps = [swap for swap in pool_swaps if swap["side"] == "sell"]
        for bid_id, events in event_sets.items():
            submitted = events.get("bid_submitted")
            if not submitted:
                continue
            exited = events.get("bid_exited")
            claimed = events.get("tokens_claimed")
            owner = submitted["owner"].lower()
            submitted_timestamp = int(blocks[str(submitted["block_number"])]["timestamp"])
            ethusd = candle_close(candles, submitted_timestamp, granularity)
            submitted_eth = Decimal(submitted["amount_raw"]) / WEI
            submitted_usd = submitted_eth * ethusd
            progress = (submitted["block_number"] - job["start_block"]) / max(
                job["end_block"] - job["start_block"], 1
            )
            tokens_raw = int(exited["tokens_filled_raw"]) if exited else 0
            refund_raw = int(exited["currency_refunded_raw"]) if exited else 0
            accepted_raw = int(submitted["amount_raw"]) - refund_raw if exited else None
            accepted_eth = Decimal(accepted_raw) / WEI if accepted_raw is not None else None
            accepted_usd = accepted_eth * ethusd if accepted_eth is not None else None
            public = (
                job["validation_hook"] == ZERO_ADDRESS
                and owner not in {job["tokens_recipient"], job["funds_recipient"]}
                and owner_code.get(owner, {}).get("is_eoa_at_latest", False)
            )

            witness = None
            if exited and tokens_raw > 0 and accepted_eth and accepted_eth > 0:
                allocation_tokens = Decimal(tokens_raw) / WEI
                for swap in sell_swaps:
                    swap_tokens = Decimal(str(swap["token_amount"]))
                    if swap_tokens < allocation_tokens or swap_tokens <= 0:
                        continue
                    proportional_native = (
                        Decimal(str(swap["native_amount_eth"]))
                        / swap_tokens
                        * allocation_tokens
                        * Decimal("0.99")
                    )
                    multiple_before_gas = proportional_native / accepted_eth
                    if multiple_before_gas >= 5:
                        transaction_hash = swap["transaction_hash"].lower()
                        transaction = witness_transactions.get(transaction_hash)
                        gas_cost_eth = (
                            Decimal(transaction["gas_cost_raw"]) / WEI
                            if transaction is not None
                            else None
                        )
                        native_after_gas = (
                            max(Decimal(0), proportional_native - gas_cost_eth)
                            if gas_cost_eth is not None
                            else None
                        )
                        multiple_after_gas = (
                            native_after_gas / accepted_eth
                            if native_after_gas is not None
                            else None
                        )
                        candidate = {
                            "block_number": int(swap["block_number"]),
                            "transaction_hash": transaction_hash,
                            "net_native_for_allocation_eth": float(proportional_native),
                            "net_multiple_before_gas": float(multiple_before_gas),
                            "gas_cost_eth": float(gas_cost_eth) if gas_cost_eth is not None else None,
                            "net_native_after_gas_eth": (
                                float(native_after_gas) if native_after_gas is not None else None
                            ),
                            "net_multiple_after_gas": (
                                float(multiple_after_gas) if multiple_after_gas is not None else None
                            ),
                            "transaction_sender": (
                                transaction["from"] if transaction is not None else None
                            ),
                            "observed_swap_tokens": float(swap_tokens),
                            "observed_swap_native_out_eth": float(swap["native_amount_eth"]),
                        }
                        # On the first pass no gas metadata exists and this is a
                        # provisional witness.  Once enriched, only an observed
                        # transaction that remains >=5x after charging its full
                        # gas cost can survive the final physical gate.
                        candidate_passes = (
                            multiple_after_gas >= 5
                            if gas_audit_complete and multiple_after_gas is not None
                            else not gas_audit_complete
                        )
                        if candidate_passes and (
                            witness is None or candidate["block_number"] < witness["block_number"]
                        ):
                            witness = candidate

            bid_rows.append(
                {
                    "auction": job["auction"],
                    "token": job["token"],
                    "pool_id": job["pool_id"],
                    "migration_timestamp": job["migration_timestamp"],
                    "post_flood": job["migration_timestamp"] >= FLOOD_START,
                    "bid_id": bid_id,
                    "owner": owner,
                    "ordinary_public": public,
                    "submitted_block": submitted["block_number"],
                    "submitted_timestamp": submitted_timestamp,
                    "submitted_utc": iso_timestamp(submitted_timestamp),
                    "auction_progress": progress,
                    "late_quarter": progress >= 0.75,
                    "max_price_q96": submitted["price_q96"],
                    "ethusd": float(ethusd),
                    "submitted_eth": float(submitted_eth),
                    "submitted_usd": float(submitted_usd),
                    "exited_observed": bool(exited),
                    "claimed_observed": bool(claimed),
                    "accepted_eth": float(accepted_eth) if accepted_eth is not None else None,
                    "accepted_usd_at_submit": float(accepted_usd) if accepted_usd is not None else None,
                    "accepted_to_submitted": (
                        float(accepted_eth / submitted_eth)
                        if accepted_eth is not None and submitted_eth > 0
                        else None
                    ),
                    "tokens_filled_raw": tokens_raw if exited else None,
                    "capacity_witness_5x_24h": bool(witness),
                    "witness_block": witness["block_number"] if witness else None,
                    "witness_tx": witness["transaction_hash"] if witness else "",
                    "witness_net_multiple_before_gas": (
                        witness["net_multiple_before_gas"] if witness else None
                    ),
                    "witness_net_native_for_allocation_eth": (
                        witness["net_native_for_allocation_eth"] if witness else None
                    ),
                    "witness_gas_cost_eth": witness["gas_cost_eth"] if witness else None,
                    "witness_net_native_after_gas_eth": (
                        witness["net_native_after_gas_eth"] if witness else None
                    ),
                    "witness_net_multiple_after_gas": (
                        witness["net_multiple_after_gas"] if witness else None
                    ),
                    "witness_transaction_sender": (
                        witness["transaction_sender"] if witness else ""
                    ),
                    "witness_observed_swap_tokens": (
                        witness["observed_swap_tokens"] if witness else None
                    ),
                }
            )

    owner_auction_tokens: dict[tuple[str, str], int] = defaultdict(int)
    for row in bid_rows:
        if (
            row["ordinary_public"]
            and row["exited_observed"]
            and (row["tokens_filled_raw"] or 0) > 0
        ):
            owner_auction_tokens[(row["auction"], row["owner"])] += int(
                row["tokens_filled_raw"]
            )
    for row in bid_rows:
        total_tokens = owner_auction_tokens.get((row["auction"], row["owner"]), 0)
        observed_tokens_raw = int(
            Decimal(str(row["witness_observed_swap_tokens"] or 0)) * WEI
        )
        row["owner_total_tokens_filled_raw"] = total_tokens or None
        row["direct_same_owner_full_size_witness"] = bool(
            row["capacity_witness_5x_24h"]
            and row["witness_transaction_sender"] == row["owner"]
            and total_tokens > 0
            and observed_tokens_raw >= int(Decimal(total_tokens) * Decimal("0.99"))
        )

    selected_ids: dict[tuple[str, str], tuple[str, int]] = {}
    for job in allocations["jobs"]:
        candidates = [
            row
            for row in bid_rows
            if row["auction"] == job["auction"]
            and row["ordinary_public"]
            and row["exited_observed"]
            and (row["tokens_filled_raw"] or 0) > 0
            and row["late_quarter"]
        ]
        for label, (lower, upper, target) in TARGET_BANDS.items():
            band = [
                row
                for row in candidates
                if lower <= Decimal(str(row["submitted_usd"])) <= upper
            ]
            if not band:
                continue
            chosen = min(
                band,
                key=lambda row: (
                    abs(Decimal(str(row["submitted_usd"])) - target),
                    -row["submitted_timestamp"],
                ),
            )
            selected_ids[(job["auction"], label)] = (chosen["owner"], chosen["bid_id"])

    for row in bid_rows:
        matched = [
            label
            for label in TARGET_BANDS
            if selected_ids.get((row["auction"], label)) == (row["owner"], row["bid_id"])
        ]
        row["matched_target_bands"] = ",".join(matched)

    public_positive = [
        row
        for row in bid_rows
        if row["ordinary_public"]
        and row["exited_observed"]
        and (row["tokens_filled_raw"] or 0) > 0
    ]
    matched_by_band: dict[str, list[dict[str, Any]]] = {
        label: [
            row for row in bid_rows if label in row["matched_target_bands"].split(",")
        ]
        for label in TARGET_BANDS
    }
    band_summary = {}
    for label, rows in matched_by_band.items():
        band_summary[label] = {
            "matched_auctions": len(rows),
            "accepted_cost_usd_quantiles": quantiles(
                row["accepted_usd_at_submit"] for row in rows
            ),
            "acceptance_ratio_quantiles": quantiles(
                row["accepted_to_submitted"] for row in rows
            ),
            "capacity_witness_5x_24h_count": sum(
                row["capacity_witness_5x_24h"] for row in rows
            ),
            "capacity_witness_5x_24h_auction_count": len(
                {row["auction"] for row in rows if row["capacity_witness_5x_24h"]}
            ),
            "post_flood_matched": sum(row["post_flood"] for row in rows),
            "post_flood_witness": sum(
                row["post_flood"] and row["capacity_witness_5x_24h"] for row in rows
            ),
        }

    witness_auctions = {
        row["auction"]
        for row in public_positive
        if (row["accepted_usd_at_submit"] or 0) >= 100
        and row["capacity_witness_5x_24h"]
    }
    post_flood_witness_auctions = {
        row["auction"]
        for row in public_positive
        if row["post_flood"]
        and (row["accepted_usd_at_submit"] or 0) >= 100
        and row["capacity_witness_5x_24h"]
    }

    auction_rows: list[dict[str, Any]] = []
    for job in allocations["jobs"]:
        auction = job["auction"].lower()
        auction_bids = [row for row in public_positive if row["auction"] == auction]
        witness_bids = [
            row
            for row in auction_bids
            if (row["accepted_usd_at_submit"] or 0) >= 100
            and row["capacity_witness_5x_24h"]
        ]
        daily_row = daily[auction]
        migration = int(job["migration_timestamp"])
        migration_dt = datetime.fromtimestamp(migration, timezone.utc)
        duration = int(job["end_timestamp"]) - int(job["start_timestamp"])
        raised_eth = int(job["currency_raised_raw"]) / 10**18
        if raised_eth < 2:
            raise_bucket = "[1,2) ETH"
        elif raised_eth < 5:
            raise_bucket = "[2,5) ETH"
        elif raised_eth < 10:
            raise_bucket = "[5,10) ETH"
        else:
            raise_bucket = ">=10 ETH"
        if duration <= 120:
            duration_bucket = "<=120s"
        elif duration <= 300:
            duration_bucket = "121-300s"
        else:
            duration_bucket = "301-600s"
        auction_rows.append(
            {
                "auction": auction,
                "token": job["token"],
                "pool_id": job["pool_id"],
                "migration_timestamp": migration,
                "migration_utc": iso_timestamp(migration),
                "iso_week": f"{migration_dt.isocalendar().year}-W{migration_dt.isocalendar().week:02d}",
                "post_flood": migration >= FLOOD_START,
                "auction_duration_seconds": duration,
                "duration_bucket": duration_bucket,
                "onchain_notice_seconds": int(job["start_timestamp"])
                - int(job["created_timestamp"]),
                "currency_raised_eth": raised_eth,
                "raise_bucket": raise_bucket,
                "spot_5x_observed": daily_row["spot_5x_observed"] == "True",
                "mature_30d": daily_row["mature_30d"] == "True",
                "ordinary_positive_allocations": len(auction_bids),
                "ordinary_accepted_ge_100": sum(
                    (row["accepted_usd_at_submit"] or 0) >= 100 for row in auction_bids
                ),
                "witness_allocations_accepted_ge_100": len(witness_bids),
                "has_5x_capacity_witness_accepted_ge_100": bool(witness_bids),
                "direct_same_owner_full_size_witnesses": sum(
                    row["direct_same_owner_full_size_witness"] for row in auction_bids
                ),
                "matched_100": sum("100" in row["matched_target_bands"].split(",") for row in auction_bids),
                "matched_300": sum("300" in row["matched_target_bands"].split(",") for row in auction_bids),
                "matched_500": sum("500" in row["matched_target_bands"].split(",") for row in auction_bids),
            }
        )

    def grouped_auction_summary(field: str) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in auction_rows:
            grouped[str(row[field])].append(row)
        return {
            key: {
                "auctions": len(rows),
                "spot_5x_observed": sum(row["spot_5x_observed"] for row in rows),
                "auctions_with_accepted_ge_100_capacity_witness": sum(
                    row["has_5x_capacity_witness_accepted_ge_100"] for row in rows
                ),
                "ordinary_accepted_ge_100": sum(
                    row["ordinary_accepted_ge_100"] for row in rows
                ),
            }
            for key, rows in sorted(grouped.items())
        }

    witness_counts = Counter(
        row["auction"]
        for row in public_positive
        if (row["accepted_usd_at_submit"] or 0) >= 100
        and row["capacity_witness_5x_24h"]
    )
    witness_total = sum(witness_counts.values())
    top_witness_auction, top_witness_count = (
        witness_counts.most_common(1)[0] if witness_counts else (None, 0)
    )
    leave_one_out_failures = []
    all_auctions = {row["auction"] for row in auction_rows}
    for removed in sorted(all_auctions):
        remaining = witness_auctions - {removed}
        remaining_post_flood = post_flood_witness_auctions - {removed}
        if len(remaining) < 2 or not remaining_post_flood:
            leave_one_out_failures.append(removed)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": {
            "short_auctions": len(allocations["jobs"]),
            "submitted_bids": sum(
                job["event_counts"]["bid_submitted"] for job in allocations["jobs"]
            ),
            "exited_bids": sum(
                job["event_counts"]["bid_exited"] for job in allocations["jobs"]
            ),
            "claimed_bids": sum(
                job["event_counts"]["tokens_claimed"] for job in allocations["jobs"]
            ),
            "unexited_unknown": sum(not row["exited_observed"] for row in bid_rows),
            "ordinary_public_positive_allocations": len(public_positive),
            "all_zero_validation_hooks": all(
                job["validation_hook"] == ZERO_ADDRESS for job in allocations["jobs"]
            ),
        },
        "ordinary_public": {
            "accepted_cost_usd_quantiles": quantiles(
                row["accepted_usd_at_submit"] for row in public_positive
            ),
            "acceptance_ratio_quantiles": quantiles(
                row["accepted_to_submitted"] for row in public_positive
            ),
            "allocations_accepted_ge_100": sum(
                (row["accepted_usd_at_submit"] or 0) >= 100 for row in public_positive
            ),
            "capacity_witness_5x_24h": sum(
                row["capacity_witness_5x_24h"] for row in public_positive
            ),
            "witness_auction_count_for_accepted_ge_100": len(witness_auctions),
            "post_flood_witness_auction_count_for_accepted_ge_100": len(
                post_flood_witness_auctions
            ),
            "direct_same_owner_full_size_witness_count": sum(
                row["direct_same_owner_full_size_witness"] for row in public_positive
            ),
            "direct_same_owner_full_size_witness_auction_count": len(
                {
                    row["auction"]
                    for row in public_positive
                    if row["direct_same_owner_full_size_witness"]
                }
            ),
        },
        "matched_natural_experiments": band_summary,
        "auction_strata": {
            "iso_week": grouped_auction_summary("iso_week"),
            "fundraise": grouped_auction_summary("raise_bucket"),
            "duration": grouped_auction_summary("duration_bucket"),
            "observed_5x_outcome": grouped_auction_summary("spot_5x_observed"),
        },
        "concentration": {
            "witness_allocations_accepted_ge_100": witness_total,
            "top_auction": top_witness_auction,
            "top_auction_witness_allocations": top_witness_count,
            "top_auction_share": (
                top_witness_count / witness_total if witness_total else None
            ),
            "leave_one_auction_out_passes": len(all_auctions)
            - len(leave_one_out_failures),
            "leave_one_auction_out_total": len(all_auctions),
            "leave_one_out_failure_auctions": leave_one_out_failures,
            "interpretation": (
                "The post-flood requirement currently depends on one auction; "
                "removing that auction fails the cross-regime gate."
            ),
        },
        "historical_physical_gate": {
            "requires_two_distinct_auctions": len(witness_auctions) >= 2,
            "requires_one_post_flood": bool(post_flood_witness_auctions),
            "passes_before_gas_audit": len(witness_auctions) >= 2
            and bool(post_flood_witness_auctions),
            "gas_audit_complete": gas_audit_complete,
            "passes_after_gas_audit": gas_audit_complete
            and len(witness_auctions) >= 2
            and bool(post_flood_witness_auctions),
            "status": (
                "historical physical gate passed; forward judgment remains untested"
                if gas_audit_complete
                and len(witness_auctions) >= 2
                and bool(post_flood_witness_auctions)
                else "historical physical gate failed or gas audit incomplete"
            ),
        },
        "definitions": {
            "ordinary_public": (
                "zero validation hook; owner not tokens/funds recipient; EOA-like at latest"
            ),
            "capacity_witness": (
                "observed 24h token->native swap at least as large as allocation; "
                "proportional native out after 100bps and the full observed tx gas "
                ">=5x accepted cost"
            ),
            "direct_same_owner_full_size_witness": (
                "selected capacity-witness tx.from equals bidder owner and its single "
                "swap covers >=99% of that owner's total observed allocation in auction; "
                "diagnostic, not an exhaustive wallet-history reconstruction"
            ),
            "flood_start_utc": iso_timestamp(FLOOD_START),
        },
    }

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(bid_rows[0]))
        writer.writeheader()
        writer.writerows(bid_rows)
    with args.output_auctions_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(auction_rows[0]))
        writer.writeheader()
        writer.writerows(auction_rows)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# Robinhood CCA ≤10m：真实获配与24小时退出容量",
        "",
        "> 主结果使用真实 bid 的 submitted/refund/tokensFilled；24小时容量 witness 使用真实整笔 Swap 的平均执行价，并扣100 bps与该笔交易的全部真实 gas。",
        "",
        "## 覆盖",
        "",
        f"- 短拍卖：{summary['universe']['short_auctions']}；投标 {summary['universe']['submitted_bids']}；已退出 {summary['universe']['exited_bids']}；正获配且普通公开 {len(public_positive)}。",
        f"- 未退出、保持未知：{summary['universe']['unexited_unknown']}。",
        f"- accepted cost >= $100 的普通公开 allocation：{summary['ordinary_public']['allocations_accepted_ge_100']}。",
        "",
        "## 全部普通公开 allocation",
        "",
        f"- accepted cost USD P10/P50/P90：${summary['ordinary_public']['accepted_cost_usd_quantiles']['p10']:.2f} / ${summary['ordinary_public']['accepted_cost_usd_quantiles']['p50']:.2f} / ${summary['ordinary_public']['accepted_cost_usd_quantiles']['p90']:.2f}。",
        f"- accepted/submitted P10/P50/P90：{summary['ordinary_public']['acceptance_ratio_quantiles']['p10']:.2%} / {summary['ordinary_public']['acceptance_ratio_quantiles']['p50']:.2%} / {summary['ordinary_public']['acceptance_ratio_quantiles']['p90']:.2%}。",
        f"- accepted >= $100 且有24h 5x容量 witness 的不同 auction：{summary['ordinary_public']['witness_auction_count_for_accepted_ge_100']}；其中洪水后：{summary['ordinary_public']['post_flood_witness_auction_count_for_accepted_ge_100']}。",
        f"- 选定 witness 中 tx.from 与 bidder 相同且单笔覆盖该 owner 总获配的诊断案例：{summary['ordinary_public']['direct_same_owner_full_size_witness_count']} 笔 / {summary['ordinary_public']['direct_same_owner_full_size_witness_auction_count']} 个 auction（非穷尽钱包历史）。",
        f"- leave-one-auction-out：{summary['concentration']['leave_one_auction_out_passes']}/{summary['concentration']['leave_one_auction_out_total']} 仍通过；唯一失败是删掉洪水后单例 `{summary['concentration']['leave_one_out_failure_auctions'][0] if summary['concentration']['leave_one_out_failure_auctions'] else 'none'}`。",
        "",
        "## 最后25%时间的真实邻近资金档",
        "",
        "| submitted目标 | 有匹配auction | accepted P50 | acceptance P50 | 24h 5x witness | 洪水后匹配/命中 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for label in ("100", "300", "500"):
        row = band_summary[label]
        accepted_p50 = row["accepted_cost_usd_quantiles"]["p50"]
        ratio_p50 = row["acceptance_ratio_quantiles"]["p50"]
        lines.append(
            f"| ${label} | {row['matched_auctions']} | "
            f"${accepted_p50:.2f} | {ratio_p50:.2%} | "
            f"{row['capacity_witness_5x_24h_auction_count']} | "
            f"{row['post_flood_matched']}/{row['post_flood_witness']} |"
        )
    lines += [
        "",
        "## 分层审计",
        "",
        "| 分层 | auctions | observed 5x | accepted >=$100 witness auctions |",
        "|---|---:|---:|---:|",
    ]
    for section, groups in (
        ("周", summary["auction_strata"]["iso_week"]),
        ("募资", summary["auction_strata"]["fundraise"]),
        ("时长", summary["auction_strata"]["duration"]),
        ("结局", summary["auction_strata"]["observed_5x_outcome"]),
    ):
        for key, value in groups.items():
            lines.append(
                f"| {section}: {key} | {value['auctions']} | "
                f"{value['spot_5x_observed']} | "
                f"{value['auctions_with_accepted_ge_100_capacity_witness']} |"
            )
    lines += [
        "",
        "## 当前裁决",
        "",
        f"- gas前历史物理门：{summary['historical_physical_gate']['passes_before_gas_audit']}。",
        f"- gas审计完整：{summary['historical_physical_gate']['gas_audit_complete']}；gas后历史物理门：{summary['historical_physical_gate']['passes_after_gas_audit']}。",
        "- 市场容量 witness 是同规模真实成交下界，不等于我们的额外 bid 能以同样结果成交。",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps(summary["historical_physical_gate"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Analyze CCA timing, bidder concentration, and one direct realized exit."""

from __future__ import annotations

import argparse
import collections
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Iterable


getcontext().prec = 50
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DIRECT_OWNER = "0x4b0cf4f22e3f83c3e73dd6ce399b48a114ae8cb2"
DIRECT_TOKEN = "0x688db8ab311e39a9e3343e861ff5420b1b7bdde8"


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
    materialized = list(values)
    return {
        name: quantile(materialized, probability)
        for name, probability in (
            ("p25", 0.25),
            ("p50", 0.50),
            ("p75", 0.75),
            ("p90", 0.90),
            ("p95", 0.95),
        )
    }


def duration_bin(seconds: int) -> str:
    if seconds <= 600:
        return "<=10m"
    if seconds <= 3600:
        return "10m-1h"
    if seconds <= 21600:
        return "1h-6h"
    return ">6h"


def timestamp_iso(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--material-bids",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_bids.json",
    )
    parser.add_argument(
        "--daily",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily.csv",
    )
    parser.add_argument(
        "--allocations",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_allocations.json",
    )
    parser.add_argument(
        "--execution",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_execution_enriched.json",
    )
    parser.add_argument(
        "--capacity",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity_summary.json",
    )
    parser.add_argument(
        "--ethusd",
        type=Path,
        default=base_dir / "data/coinbase_ethusd_2026-07-13_1640_1649.json",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=base_dir / "output/cca_robinhood_bid_timing_execution_summary.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=base_dir / "output/cca_robinhood_bid_timing_execution.md",
    )
    args = parser.parse_args()

    material_payload = json.loads(args.material_bids.read_text())
    if not material_payload["audit"]["complete"]:
        raise RuntimeError("material bid audit is incomplete")
    rows = material_payload["rows"]
    daily = {row["token"]: row for row in csv.DictReader(args.daily.open())}
    allocations = json.loads(args.allocations.read_text())
    execution = json.loads(args.execution.read_text())
    if not allocations["complete"] or not execution["complete"]:
        raise RuntimeError("direct execution evidence is incomplete")
    capacity = json.loads(args.capacity.read_text())
    ethusd = json.loads(args.ethusd.read_text())

    total_bids = sum(row["bid_count"] for row in rows)
    owners: collections.Counter[str] = collections.Counter()
    owner_auctions: collections.Counter[str] = collections.Counter()
    owner_amount: collections.Counter[str] = collections.Counter()
    special_bid_count = 0
    special_bid_amount = 0
    for row in rows:
        seen = set()
        special = {row["tokens_recipient"], row["funds_recipient"]}
        for bid in row["bids"]:
            owner = bid["owner"]
            owners[owner] += 1
            owner_amount[owner] += bid["amount_raw"]
            seen.add(owner)
            if owner in special:
                special_bid_count += 1
                special_bid_amount += bid["amount_raw"]
        for owner in seen:
            owner_auctions[owner] += 1

    top10 = [owner for owner, _ in owner_auctions.most_common(10)]
    timing = {
        "auction_duration_seconds": quantiles(
            row["auction_duration_seconds"] for row in rows
        ),
        "onchain_notice_seconds": quantiles(row["onchain_notice_seconds"] for row in rows),
        "first_bid_delay_seconds": quantiles(
            row["first_bid_delay_seconds"] for row in rows
        ),
        "last_bid_seconds_before_end": quantiles(
            row["last_bid_seconds_before_end"] for row in rows
        ),
        "duration_bins": dict(
            collections.Counter(duration_bin(row["auction_duration_seconds"]) for row in rows)
        ),
    }

    mature = [row for row in rows if daily[row["token"]]["mature_30d"] == "True"]
    mature_5x = [
        row
        for row in mature
        if float(daily[row["token"]]["max_spot_30d_x"]) >= 5
    ]
    mature_by_duration: dict[str, dict[str, int | float | None]] = {}
    for label in ("<=10m", "10m-1h", "1h-6h", ">6h"):
        denominator = [
            row for row in mature if duration_bin(row["auction_duration_seconds"]) == label
        ]
        numerator = [row for row in mature_5x if duration_bin(row["auction_duration_seconds"]) == label]
        mature_by_duration[label] = {
            "mature_count": len(denominator),
            "mature_5x_count": len(numerator),
            "spot_5x_rate": len(numerator) / len(denominator) if denominator else None,
        }

    allocation_job = next(job for job in allocations["jobs"] if job["token"] == DIRECT_TOKEN)
    bid_events: dict[int, dict[str, dict[str, Any]]] = {}
    for event in allocation_job["events"]:
        bid_events.setdefault(event["bid_id"], {})[event["event"]] = event
    bid_id = next(
        bid_id
        for bid_id, events in bid_events.items()
        if events["bid_submitted"]["owner"] == DIRECT_OWNER
    )
    bid = bid_events[bid_id]
    amount_raw = bid["bid_submitted"]["amount_raw"]
    refund_raw = bid["bid_exited"]["currency_refunded_raw"]
    cost_raw = amount_raw - refund_raw
    allocation_tokens_raw = bid["bid_exited"]["tokens_filled_raw"]

    detail = next(
        detail
        for detail in capacity["details"].values()
        if detail["candidate"]["token"].lower() == DIRECT_TOKEN
    )
    sell_swaps = []
    for swap in detail["qualifying_sells"]:
        tx_hash = swap["transaction_hash"].lower()
        if execution["transactions"].get(tx_hash, {}).get("from") == DIRECT_OWNER:
            sell_swaps.append(swap)
    sell_tx_hashes = {swap["transaction_hash"].lower() for swap in sell_swaps}
    sold_tokens_raw = sum(abs(swap["amount1_raw"]) for swap in sell_swaps)
    proceeds_raw = sum(swap["amount0_raw"] for swap in sell_swaps)

    submit_tx = bid["bid_submitted"]["transaction_hash"]
    claim_tx = bid["tokens_claimed"]["transaction_hash"]
    entry_tx_hashes = {submit_tx, claim_tx}
    entry_gas_raw = sum(execution["receipts"][tx]["gas_cost_raw"] for tx in entry_tx_hashes)
    sell_gas_raw = sum(execution["receipts"][tx]["gas_cost_raw"] for tx in sell_tx_hashes)
    all_gas_raw = entry_gas_raw + sell_gas_raw

    wei = Decimal(10) ** 18
    cost_eth = Decimal(cost_raw) / wei
    proceeds_eth = Decimal(proceeds_raw) / wei
    entry_gas_eth = Decimal(entry_gas_raw) / wei
    sell_gas_eth = Decimal(sell_gas_raw) / wei
    total_gas_eth = Decimal(all_gas_raw) / wei
    haircut = Decimal("0.01")
    net_exit_eth = proceeds_eth * (Decimal(1) - haircut) - sell_gas_eth
    net_entry_eth = cost_eth + entry_gas_eth
    net_multiple = net_exit_eth / net_entry_eth

    candle_by_time = {int(candle[0]): candle for candle in ethusd["candles"]}
    submit_ts = execution["blocks"][str(bid["bid_submitted"]["block_number"])]["timestamp"]
    first_sell_ts = min(
        execution["blocks"][str(swap["block_number"])]["timestamp"] for swap in sell_swaps
    )
    last_sell_ts = max(
        execution["blocks"][str(swap["block_number"])]["timestamp"] for swap in sell_swaps
    )
    entry_ethusd_close = Decimal(str(candle_by_time[(submit_ts // 60) * 60][4]))
    exit_ethusd_close = Decimal(str(candle_by_time[(last_sell_ts // 60) * 60][4]))
    direct_row = next(row for row in rows if row["token"] == DIRECT_TOKEN)
    direct_case = {
        "auction": allocation_job["auction"],
        "token": DIRECT_TOKEN,
        "owner": DIRECT_OWNER,
        "owner_is_eoa_at_latest": execution["owner_code"][DIRECT_OWNER]["is_eoa_at_latest"],
        "owner_is_project_tokens_or_funds_recipient": DIRECT_OWNER
        in {allocation_job["tokens_recipient"], allocation_job["funds_recipient"]},
        "validation_hook": allocation_job["validation_hook"],
        "bid_id": bid_id,
        "submitted_eth": str(Decimal(amount_raw) / wei),
        "refund_eth": str(Decimal(refund_raw) / wei),
        "allocation_cost_eth": str(cost_eth),
        "allocation_tokens_raw": allocation_tokens_raw,
        "sold_tokens_raw": sold_tokens_raw,
        "allocation_minus_sold_raw": allocation_tokens_raw - sold_tokens_raw,
        "actual_proceeds_eth": str(proceeds_eth),
        "entry_gas_eth": str(entry_gas_eth),
        "sell_gas_eth": str(sell_gas_eth),
        "total_gas_eth": str(total_gas_eth),
        "net_exit_eth_after_100bps_and_sell_gas": str(net_exit_eth),
        "net_entry_eth_including_bid_and_claim_gas": str(net_entry_eth),
        "net_multiple_after_100bps_and_all_observed_gas": str(net_multiple),
        "allocation_cost_usd_at_coinbase_minute_close": str(cost_eth * entry_ethusd_close),
        "net_exit_usd_at_coinbase_minute_close": str(net_exit_eth * exit_ethusd_close),
        "entry_ethusd_close": str(entry_ethusd_close),
        "exit_ethusd_close": str(exit_ethusd_close),
        "sell_transaction_hashes": sorted(sell_tx_hashes),
        "auction_created_utc": timestamp_iso(direct_row["created_timestamp"]),
        "auction_start_utc": timestamp_iso(direct_row["start_timestamp"]),
        "bid_submitted_utc": timestamp_iso(submit_ts),
        "auction_end_utc": timestamp_iso(direct_row["end_timestamp"]),
        "migration_utc": timestamp_iso(direct_row["migration_timestamp"]),
        "first_sell_utc": timestamp_iso(first_sell_ts),
        "last_sell_utc": timestamp_iso(last_sell_ts),
        "auction_duration_seconds": direct_row["auction_duration_seconds"],
        "onchain_notice_seconds": direct_row["onchain_notice_seconds"],
        "seconds_from_start_to_bid": submit_ts - direct_row["start_timestamp"],
        "seconds_from_bid_to_full_exit": last_sell_ts - submit_ts,
        "passes_100_to_500_mechanical_gate": cost_eth * entry_ethusd_close >= 100
        and net_exit_eth * exit_ethusd_close >= 500
        and allocation_tokens_raw - sold_tokens_raw <= 1,
    }

    owner_participation = []
    for row in rows:
        bids = [bid for bid in row["bids"] if bid["owner"] == DIRECT_OWNER]
        if bids:
            owner_participation.append(
                {
                    "token": row["token"],
                    "migration_utc": timestamp_iso(row["migration_timestamp"]),
                    "submitted_eth": str(
                        Decimal(sum(bid["amount_raw"] for bid in bids)) / wei
                    ),
                    "max_spot_30d_x": float(daily[row["token"]]["max_spot_30d_x"]),
                    "p7d_x": float(daily[row["token"]]["p7d_x"]),
                    "current_spot_x": float(daily[row["token"]]["current_spot_x"]),
                }
            )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": {
            "definition": material_payload["selection"],
            "auction_count": len(rows),
            "bid_count": total_bids,
            "unique_owner_count": len(owners),
            "zero_validation_hook_count": sum(
                row["validation_hook"] == ZERO_ADDRESS for row in rows
            ),
        },
        "timing": timing,
        "concentration": {
            "owners_in_at_least_2_auctions": sum(value >= 2 for value in owner_auctions.values()),
            "owners_in_at_least_5_auctions": sum(value >= 5 for value in owner_auctions.values()),
            "owners_in_at_least_10_auctions": sum(value >= 10 for value in owner_auctions.values()),
            "max_auctions_by_one_owner": max(owner_auctions.values()),
            "top10_repeating_owner_bid_share": sum(owners[owner] for owner in top10)
            / total_bids,
            "top10_repeating_owner_submitted_amount_share": sum(
                owner_amount[owner] for owner in top10
            )
            / sum(owner_amount.values()),
            "project_recipient_bid_share": special_bid_count / total_bids,
            "project_recipient_submitted_amount_share": special_bid_amount
            / sum(owner_amount.values()),
        },
        "mature_30d": {
            "count": len(mature),
            "spot_5x_count": len(mature_5x),
            "spot_5x_rate": len(mature_5x) / len(mature),
            "duration_bins_all_mature": dict(
                collections.Counter(duration_bin(row["auction_duration_seconds"]) for row in mature)
            ),
            "duration_bins_mature_5x": dict(
                collections.Counter(duration_bin(row["auction_duration_seconds"]) for row in mature_5x)
            ),
            "by_duration": mature_by_duration,
            "caveat": (
                "duration strata are time-confounded and small; most 4-hour auctions are not yet 30-day mature"
            ),
        },
        "direct_realized_case": direct_case,
        "direct_owner_material_participation": owner_participation,
        "decision": {
            "physical_execution_gate": "pass_one_observed_case",
            "judgment_lane_gate": "not_yet_passed",
            "reason": (
                "the full realized case had a 119-second auction and 204 seconds of on-chain notice; "
                "the judgment-friendly four-hour cohort is mostly right-censored"
            ),
        },
        "sources": {
            "contract": "Uniswap/continuous-clearing-auction v2.1.0",
            "chain": "Robinhood Chain official JSON-RPC",
            "outcomes": "GeckoTerminal OHLCV and Uniswap v4 PoolManager Swap logs",
            "ethusd": "Coinbase Exchange public ETH-USD candles API",
        },
    }
    args.json_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    d = direct_case
    lines = [
        "# Robinhood CCA：竞价时间墙与直接可实现退出",
        "",
        f"生成时间：{summary['generated_at']}",
        "",
        "## 结论",
        "",
        "CCA 的物理可执行性门已被一个真实案例通过，但‘综合判断型一级发行’仍未通过。",
        "同一普通可调用 EOA 的真实竞价、领取和完整卖出在链上闭合；然而该拍卖只有 119 秒，",
        "所以它证明的是短窗发行可赚钱，不是几小时研究后仍能入场。",
        "",
        "## 直接实现案例",
        "",
        f"- 地址：`{d['owner']}`（EOA；不是 tokens/funds recipient；validation hook 为零）",
        f"- 实际获配成本：{Decimal(d['allocation_cost_eth']):.6f} ETH，按 Coinbase 分钟收盘约 ${Decimal(d['allocation_cost_usd_at_coinbase_minute_close']):.2f}",
        f"- 获配：{d['allocation_tokens_raw']} raw；实际卖出：{d['sold_tokens_raw']} raw；相差 {d['allocation_minus_sold_raw']} raw",
        f"- 两笔实际卖出收到：{Decimal(d['actual_proceeds_eth']):.6f} ETH",
        f"- 再扣 100 bps 与观察到的全部 gas 后：{Decimal(d['net_exit_eth_after_100bps_and_sell_gas']):.6f} ETH，约 ${Decimal(d['net_exit_usd_at_coinbase_minute_close']):.2f}",
        f"- 净倍数：{Decimal(d['net_multiple_after_100bps_and_all_observed_gas']):.3f}x；`$100 -> $500` 机械门：{d['passes_100_to_500_mechanical_gate']}",
        f"- 时间线：创建 {d['auction_created_utc']}；开拍 {d['auction_start_utc']}；竞价 {d['bid_submitted_utc']}；结束 {d['auction_end_utc']}；卖完 {d['last_sell_utc']}",
        f"- 从开拍到下单 {d['seconds_from_start_to_bid']} 秒；从下单到完整退出 {d['seconds_from_bid_to_full_exit']} 秒",
        "",
        "## 104 个实质性发行的时间与竞争形状",
        "",
        f"- 104 个发行、{total_bids:,} 笔竞价、{len(owners):,} 个钱包；其中 {summary['universe']['zero_validation_hook_count']}/104 为零验证钩子。",
        f"- 拍卖时长 P25/P50/P75/P90：{timing['auction_duration_seconds']['p25']:.0f}/{timing['auction_duration_seconds']['p50']:.0f}/{timing['auction_duration_seconds']['p75']:.0f}/{timing['auction_duration_seconds']['p90']:.0f} 秒。",
        f"- 时长分布：{timing['duration_bins']}。链上创建到开拍的预告 P50 仅 {timing['onchain_notice_seconds']['p50']:.0f} 秒；首笔竞价延迟 P50 {timing['first_bid_delay_seconds']['p50']:.1f} 秒。",
        f"- 前 10 个重复钱包只占 {summary['concentration']['top10_repeating_owner_bid_share']:.2%} 的竞价笔数和 {summary['concentration']['top10_repeating_owner_submitted_amount_share']:.2%} 的提交额；钱包级并非少数账户垄断，但尚未做实体聚类。",
        "",
        "## 不能越过的解释边界",
        "",
        f"- 30 日成熟样本只有 {len(mature)} 个，其中 {len(mature_5x)} 个观察到 5x；15 个赢家中时长分布为 {summary['mature_30d']['duration_bins_mature_5x']}。",
        "- 这不能推出短拍卖更赚钱：长达约 4 小时的发行主要更晚出现，尚未留足 30 天，是明显的日历时间混杂。",
        "- 直接赚钱钱包在当前 104 个实质性发行中只参加了 2 个，两个都曾达到 5x；这是值得冻结后前向跟踪的线索，不是可复现命中率，后验挑选与多重比较都很强。",
        "- 下一闸门应是：等待 4 小时 cohort 成熟，按拍卖开始前可见材料盲评，并前向验证实际分配与退出；不能用这个 119 秒案例宣称‘综合判断’成立。",
    ]
    args.markdown_output.write_text("\n".join(lines) + "\n")
    print(json.dumps(summary["decision"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

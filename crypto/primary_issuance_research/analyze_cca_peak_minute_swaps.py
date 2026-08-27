#!/usr/bin/env python3
"""Audit direction-level executable evidence in selected CCA >=5x minutes."""

from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 60
Q96 = Decimal(2**96)
WEI = Decimal(10**18)


def signed_word(word: bytes) -> int:
    value = int.from_bytes(word, "big")
    return value - 2**256 if value >= 2**255 else value


def decode_swap(log: dict, issue_price: Decimal) -> dict:
    raw = bytes.fromhex(log["data"][2:])
    words = [raw[index : index + 32] for index in range(0, len(raw), 32)]
    amount0 = signed_word(words[0])
    amount1 = signed_word(words[1])
    sqrt_price_x96 = int.from_bytes(words[2], "big")
    liquidity = int.from_bytes(words[3], "big")
    token_price_eth = (Q96 / Decimal(sqrt_price_x96)) ** 2
    if amount0 > 0 and amount1 < 0:
        side = "sell"
        native_amount = Decimal(amount0) / WEI
        token_amount = Decimal(-amount1) / WEI
        average_price_eth = native_amount / token_amount
        average_execution_x = average_price_eth / issue_price
    elif amount0 < 0 and amount1 > 0:
        side = "buy"
        native_amount = Decimal(-amount0) / WEI
        token_amount = Decimal(amount1) / WEI
        average_price_eth = native_amount / token_amount
        average_execution_x = average_price_eth / issue_price
    else:
        side = "other"
        native_amount = Decimal(abs(amount0)) / WEI
        token_amount = Decimal(abs(amount1)) / WEI
        average_price_eth = None
        average_execution_x = None

    # Local active-liquidity approximation for a 5% token-price decline.
    # It ignores initialized ticks crossed inside the move and is therefore a
    # diagnostic, not the executable capacity result.
    sqrt_current = Decimal(sqrt_price_x96)
    sqrt_after_5pct_down = sqrt_current / Decimal("0.95").sqrt()
    native_out_5pct = (
        Decimal(liquidity)
        * (Decimal(1) / sqrt_current - Decimal(1) / sqrt_after_5pct_down)
        * Q96
        / WEI
    )
    return {
        "side": side,
        "amount0_raw": amount0,
        "amount1_raw": amount1,
        "native_amount_eth": float(native_amount),
        "token_amount": float(token_amount),
        "post_spot_x": float(token_price_eth / issue_price),
        "average_execution_x": (
            float(average_execution_x) if average_execution_x is not None else None
        ),
        "initial_vwap_notional_eth": float(token_amount * issue_price),
        "liquidity": liquidity,
        "local_5pct_sell_capacity_eth_approx": float(native_out_5pct),
        "block_number": int(log["blockNumber"], 16),
        "transaction_hash": log["transactionHash"],
        "log_index": int(log["logIndex"], 16),
    }


def median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--swap-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_swaps",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity.md",
    )
    args = parser.parse_args()

    audit = json.loads((args.swap_dir / "audit.json").read_text())
    if not audit.get("complete"):
        raise RuntimeError("peak swap cache is incomplete")
    rows = []
    detail = {}
    for path in sorted(args.swap_dir.glob("0x*.json")):
        payload = json.loads(path.read_text())
        candidate = payload["candidate"]
        issue = Decimal(candidate["issue_vwap_eth_per_token"])
        swaps = [decode_swap(log, issue) for log in payload["raw_logs"]]
        sells = [swap for swap in swaps if swap["side"] == "sell"]
        buys = [swap for swap in swaps if swap["side"] == "buy"]
        qualifying_sells = [
            swap for swap in sells if (swap["average_execution_x"] or 0) >= 5
        ]
        executable_equivalent = [
            swap
            for swap in qualifying_sells
            if swap["initial_vwap_notional_eth"] >= 0.04
            and swap["native_amount_eth"] >= 0.20
        ]
        observed_native_volume = sum(swap["native_amount_eth"] for swap in swaps)
        candle_native_volume = float(payload["selected_minute_candle"][5])
        row = {
            "token": candidate["token"],
            "pool_id": candidate["pool_id"],
            "selected_minute_timestamp": payload["minute_timestamp"],
            "swap_count": len(swaps),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "qualifying_sell_count_avg_ge_5x": len(qualifying_sells),
            "native_volume_eth_from_logs": observed_native_volume,
            "candle_volume_eth": candle_native_volume,
            "log_to_candle_volume_ratio": (
                observed_native_volume / candle_native_volume if candle_native_volume else None
            ),
            "qualifying_sell_native_out_eth_total": sum(
                swap["native_amount_eth"] for swap in qualifying_sells
            ),
            "max_single_qualifying_sell_native_out_eth": max(
                (swap["native_amount_eth"] for swap in qualifying_sells), default=0
            ),
            "max_single_qualifying_sell_initial_vwap_notional_eth": max(
                (swap["initial_vwap_notional_eth"] for swap in qualifying_sells),
                default=0,
            ),
            "observed_equivalent_0_04_to_0_20_eth_exit": bool(executable_equivalent),
            "observed_equivalent_trade_count": len(executable_equivalent),
            "local_5pct_sell_capacity_eth_approx_median_at_ge5_spot": median(
                [
                    swap["local_5pct_sell_capacity_eth_approx"]
                    for swap in swaps
                    if swap["post_spot_x"] >= 5
                ]
            ),
        }
        rows.append(row)
        detail[candidate["pool_id"]] = {
            "candidate": candidate,
            "summary": row,
            "qualifying_sells": qualifying_sells,
        }

    qualifying_pools = [row for row in rows if row["qualifying_sell_count_avg_ge_5x"] > 0]
    executable_pools = [row for row in rows if row["observed_equivalent_0_04_to_0_20_eth_exit"]]
    summary = {
        "persistent_candidate_count": len(rows),
        "pools_with_directional_sell_avg_ge_5x": len(qualifying_pools),
        "pools_with_observed_0_04_to_0_20_eth_equivalent": len(executable_pools),
        "definition": {
            "entry_notional": "0.04 ETH at auction-wide token VWAP (~$100 if ETH=$2,500)",
            "exit_notional": ">=0.20 ETH in one observed token->ETH swap",
            "price": "whole-swap average execution >=5x auction-wide token VWAP",
        },
        "log_volume_reconciliation_ratio_median": median(
            [row["log_to_candle_volume_ratio"] for row in rows]
        ),
        "remaining_blockers": [
            "historical ETH/USD conversion for exact $100/$500 thresholds",
            "ordinary bidder-specific allocation and cost instead of auction-wide VWAP",
            "fees, gas and 100 bps haircut",
            "a single observed large sell is capacity evidence, not a guaranteed quote for every holder",
        ],
        "details": detail,
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    lines = [
        "# Robinhood CCA 峰值分钟：方向级卖出容量",
        "",
        "> 这是历史成交证据，不是最终 `first_exec_5x`。0.04/0.20 ETH 仅按 ETH=$2,500 近似 $100/$500。",
        "",
        f"- 持久 5x 候选：{len(rows)}",
        f"- 峰值分钟存在平均成交价 >=5x 的 token→ETH 卖单：{len(qualifying_pools)}/{len(rows)}",
        f"- 存在单笔同时覆盖 >=0.04 ETH 入场等价 token、并收到 >=0.20 ETH：{len(executable_pools)}/{len(rows)}",
        f"- 链上逐笔 native volume / Gecko 分钟 volume 的中位比：{summary['log_volume_reconciliation_ratio_median']:.4f}",
        "",
        "| token | swaps | sells >=5x | max sell ETH | max issue-notional ETH | 0.04→0.20 evidence | poolId |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda item: item["max_single_qualifying_sell_native_out_eth"], reverse=True):
        lines.append(
            f"| `{row['token']}` | {row['swap_count']} | {row['qualifying_sell_count_avg_ge_5x']} | {row['max_single_qualifying_sell_native_out_eth']:.4f} | {row['max_single_qualifying_sell_initial_vwap_notional_eth']:.4f} | {str(row['observed_equivalent_0_04_to_0_20_eth_exit']).lower()} | `{row['pool_id']}` |"
        )
    lines += [
        "",
        "仍需重建普通公开投标者的真实分配/成本，并加入历史 ETH/USD、费用与 100 bps 执行折损。",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps({key: value for key, value in summary.items() if key != "details"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

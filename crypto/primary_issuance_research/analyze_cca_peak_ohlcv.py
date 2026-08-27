#!/usr/bin/env python3
"""Measure persistence and quote volume around mature CCA spot 5x peaks."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def longest_run(timestamps: list[int], step: int) -> int:
    if not timestamps:
        return 0
    ordered = sorted(set(timestamps))
    longest = current = 1
    for previous, value in zip(ordered, ordered[1:]):
        if value - previous == step:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def quantile(values: list[float], probability: float) -> float | None:
    values = sorted(value for value in values if value is not None and math.isfinite(value))
    if not values:
        return None
    position = (len(values) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    weight = position - low
    return values[low] * (1 - weight) + values[high] * weight


def fmt(value: float | None, digits: int = 2) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_ohlcv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_persistence.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_persistence_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_persistence.md",
    )
    args = parser.parse_args()

    audit = json.loads((args.cache_dir / "audit.json").read_text())
    if not audit.get("complete"):
        raise RuntimeError("peak OHLCV cache is incomplete")

    rows = []
    for hour_path in sorted((args.cache_dir / "hour").glob("0x*.json")):
        hour = json.loads(hour_path.read_text())
        minute = json.loads((args.cache_dir / "minute" / hour_path.name).read_text())
        candidate = hour["candidate"]
        issue = float(candidate["issue_vwap_eth_per_token"])
        migration = int(float(candidate["migration_timestamp"]))
        hours = sorted(
            [
                {
                    "timestamp": int(candle[0]),
                    "open_x": float(candle[1]) / issue,
                    "high_x": float(candle[2]) / issue,
                    "low_x": float(candle[3]) / issue,
                    "close_x": float(candle[4]) / issue,
                    "volume_eth": float(candle[5]),
                }
                for candle in hour["payload"]["data"]["attributes"]["ohlcv_list"]
                if int(candle[0]) + 3600 > migration
                and int(candle[0]) < migration + 30 * 86_400
            ],
            key=lambda candle: candle["timestamp"],
        )
        peak_hour = max(hours, key=lambda candle: candle["high_x"])
        minutes = sorted(
            [
                {
                    "timestamp": int(candle[0]),
                    "open_x": float(candle[1]) / issue,
                    "high_x": float(candle[2]) / issue,
                    "low_x": float(candle[3]) / issue,
                    "close_x": float(candle[4]) / issue,
                    "volume_eth": float(candle[5]),
                }
                for candle in minute["payload"]["data"]["attributes"]["ohlcv_list"]
                if peak_hour["timestamp"] <= int(candle[0]) < peak_hour["timestamp"] + 3600
            ],
            key=lambda candle: candle["timestamp"],
        )
        max_minute = max(minutes, key=lambda candle: candle["high_x"]) if minutes else None
        hour_close_5x = [c["timestamp"] for c in hours if c["close_x"] >= 5]
        hour_low_5x = [c["timestamp"] for c in hours if c["low_x"] >= 5]
        minute_close_5x = [c["timestamp"] for c in minutes if c["close_x"] >= 5]
        minute_low_5x = [c["timestamp"] for c in minutes if c["low_x"] >= 5]
        rows.append(
            {
                "token": candidate["token"],
                "pool_id": candidate["pool_id"],
                "raised_eth": float(candidate["currency_raised_eth"]),
                "issue_vwap_eth_per_token": issue,
                "daily_max_30d_x": float(candidate["max_spot_30d_x"]),
                "hourly_max_30d_x": peak_hour["high_x"],
                "hourly_vs_daily_max_ratio": (
                    peak_hour["high_x"] / float(candidate["max_spot_30d_x"])
                ),
                "peak_hour_timestamp": peak_hour["timestamp"],
                "peak_hour_days_after_migration": max(
                    0, peak_hour["timestamp"] - migration
                )
                / 86_400,
                "hours_high_ge_5x": sum(c["high_x"] >= 5 for c in hours),
                "hours_close_ge_5x": len(hour_close_5x),
                "hours_low_ge_5x": len(hour_low_5x),
                "longest_consecutive_hour_close_ge_5x": longest_run(hour_close_5x, 3600),
                "longest_consecutive_hour_low_ge_5x": longest_run(hour_low_5x, 3600),
                "peak_hour_volume_eth": peak_hour["volume_eth"],
                "peak_hour_candles_observed": len(minutes),
                "peak_minute_high_x": max_minute["high_x"] if max_minute else None,
                "minutes_high_ge_5x_in_peak_hour": sum(c["high_x"] >= 5 for c in minutes),
                "minutes_close_ge_5x_in_peak_hour": len(minute_close_5x),
                "minutes_low_ge_5x_in_peak_hour": len(minute_low_5x),
                "longest_consecutive_minute_close_ge_5x": longest_run(
                    minute_close_5x, 60
                ),
                "longest_consecutive_minute_low_ge_5x": longest_run(minute_low_5x, 60),
                "max_minute_volume_eth_in_peak_hour": (
                    max((c["volume_eth"] for c in minutes), default=0)
                ),
                "peak_hour_volume_ge_0_2_eth": peak_hour["volume_eth"] >= 0.2,
                "triage_persistent_5x": (
                    longest_run(minute_close_5x, 60) >= 5
                    and peak_hour["volume_eth"] >= 0.2
                ),
            }
        )

    ratios = [row["hourly_vs_daily_max_ratio"] for row in rows]
    persistent = [row for row in rows if row["triage_persistent_5x"]]
    summary = {
        "candidate_count": len(rows),
        "hourly_reproduces_daily_within_1pct": sum(abs(value - 1) <= 0.01 for value in ratios),
        "hourly_vs_daily_ratio_min": min(ratios),
        "hourly_vs_daily_ratio_median": quantile(ratios, 0.5),
        "peak_hour_volume_eth_quantiles": {
            "p25": quantile([row["peak_hour_volume_eth"] for row in rows], 0.25),
            "p50": quantile([row["peak_hour_volume_eth"] for row in rows], 0.5),
            "p75": quantile([row["peak_hour_volume_eth"] for row in rows], 0.75),
            "p90": quantile([row["peak_hour_volume_eth"] for row in rows], 0.9),
        },
        "minutes_close_ge_5x_in_peak_hour_quantiles": {
            "p25": quantile([row["minutes_close_ge_5x_in_peak_hour"] for row in rows], 0.25),
            "p50": quantile([row["minutes_close_ge_5x_in_peak_hour"] for row in rows], 0.5),
            "p75": quantile([row["minutes_close_ge_5x_in_peak_hour"] for row in rows], 0.75),
            "p90": quantile([row["minutes_close_ge_5x_in_peak_hour"] for row in rows], 0.9),
        },
        "persistent_5x_triage_count": len(persistent),
        "persistent_5x_triage_rule": "peak hour >=0.2 ETH volume and >=5 consecutive minute closes at >=5x",
        "warning": "OHLCV volume is aggregate and does not prove a single $500 exit or direction-specific sell liquidity.",
    }

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    lines = [
        "# Robinhood CCA 5x 候选：峰值持续性筛查",
        "",
        "> 全部 15 个候选；小时/分钟 OHLCV 只用于收缩逐笔审计范围，不等于可执行退出。",
        "",
        f"- 小时 high 在 1% 内复现日线 high：{summary['hourly_reproduces_daily_within_1pct']}/{len(rows)}",
        f"- 峰值小时成交量（ETH）P25/P50/P75/P90：{fmt(summary['peak_hour_volume_eth_quantiles']['p25'],3)} / {fmt(summary['peak_hour_volume_eth_quantiles']['p50'],3)} / {fmt(summary['peak_hour_volume_eth_quantiles']['p75'],3)} / {fmt(summary['peak_hour_volume_eth_quantiles']['p90'],3)}",
        f"- 峰值小时内，分钟 close >=5x 的分钟数 P25/P50/P75/P90：{fmt(summary['minutes_close_ge_5x_in_peak_hour_quantiles']['p25'])} / {fmt(summary['minutes_close_ge_5x_in_peak_hour_quantiles']['p50'])} / {fmt(summary['minutes_close_ge_5x_in_peak_hour_quantiles']['p75'])} / {fmt(summary['minutes_close_ge_5x_in_peak_hour_quantiles']['p90'])}",
        f"- 临时持久性筛选通过：{len(persistent)}/{len(rows)}（>=5 个连续分钟 close 在 5x 以上，且峰值小时成交量 >=0.2 ETH）",
        "",
        "| token | max x | peak hour ETH vol | min close>=5x | longest min close>=5x | persistent | poolId |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda item: item["daily_max_30d_x"], reverse=True):
        lines.append(
            f"| `{row['token']}` | {row['daily_max_30d_x']:.2f} | {row['peak_hour_volume_eth']:.3f} | {row['minutes_close_ge_5x_in_peak_hour']} | {row['longest_consecutive_minute_close_ge_5x']} | {str(row['triage_persistent_5x']).lower()} | `{row['pool_id']}` |"
        )
    lines += [
        "",
        "下一步只对临时通过者读取峰值分钟逐笔 Swap，并按成交方向和当时 liquidity 检查 $100/$500/$1,000 退出。",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

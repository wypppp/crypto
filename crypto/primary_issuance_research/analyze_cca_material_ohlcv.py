#!/usr/bin/env python3
"""Analyze daily spot outcomes for materially funded Robinhood CCA pools.

Daily candle highs are screening upper bounds, not executable exits. The
pre-registered first_exec_5x result remains unresolved until allocation and
historical depth are reconstructed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DAY = 86_400
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def quantile(values: list[float], probability: float) -> float | None:
    values = sorted(value for value in values if value is not None and math.isfinite(value))
    if not values:
        return None
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def quantiles(values: list[float]) -> dict[str, float | None]:
    return {
        "p25": quantile(values, 0.25),
        "p50": quantile(values, 0.50),
        "p75": quantile(values, 0.75),
        "p90": quantile(values, 0.90),
        "p95": quantile(values, 0.95),
        "p99": quantile(values, 0.99),
        "max": max(values) if values else None,
    }


def transform_candle(candle: list[float], token_side: str) -> dict[str, float]:
    timestamp, open_, high, low, close, volume = candle
    if token_side == "base":
        return {
            "timestamp": int(timestamp),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }
    if token_side == "quote":
        return {
            "timestamp": int(timestamp),
            "open": 1 / float(open_),
            "high": 1 / float(low),
            "low": 1 / float(high),
            "close": 1 / float(close),
            "volume": float(volume),
        }
    raise ValueError(f"unknown token side: {token_side}")


def asof_close(candles: list[dict[str, float]], target: int) -> float | None:
    completed = [candle for candle in candles if candle["timestamp"] + DAY <= target]
    return completed[-1]["close"] if completed else None


def fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_ohlcv_daily",
    )
    parser.add_argument(
        "--onchain",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_onchain.json",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=base_dir / "data/cca_robinhood_status.json",
    )
    parser.add_argument(
        "--migration-events",
        type=Path,
        default=base_dir / "data/cca_robinhood_migrations_events.json",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_current.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily.md",
    )
    args = parser.parse_args()

    onchain_payload = json.loads(args.onchain.read_text())
    if not onchain_payload.get("complete"):
        raise RuntimeError("on-chain enrichment is incomplete")
    onchain = {row["pool_id"].lower(): row for row in onchain_payload["rows"]}
    cache = {
        path.stem.lower(): json.loads(path.read_text())
        for path in args.cache_dir.glob("0x*.json")
    }
    current_payload = json.loads(args.current.read_text())
    if not current_payload.get("complete"):
        raise RuntimeError("current pool snapshot is incomplete")
    current = {
        row["attributes"]["address"].lower(): row["attributes"]
        for row in current_payload["rows"]
    }
    fetched_timestamps = [
        int(datetime.fromisoformat(row["fetched_at"]).timestamp()) for row in cache.values()
    ]
    snapshot_timestamp = min(fetched_timestamps)

    rows: list[dict[str, Any]] = []
    for pool_id, chain in sorted(onchain.items(), key=lambda item: item[1]["migration_timestamp"]):
        source = cache[pool_id]
        raw_candles = source["payload"]["data"]["attributes"]["ohlcv_list"]
        candles = sorted(
            (transform_candle(candle, chain["gecko_token_side"]) for candle in raw_candles),
            key=lambda candle: candle["timestamp"],
        )
        issue_vwap = (
            chain["currency_raised_raw"]
            / chain["total_cleared_raw"]
            * 10 ** (chain["token_decimals"] - chain["currency_decimals"])
        )
        migration_timestamp = int(chain["migration_timestamp"])
        observed = [
            candle
            for candle in candles
            if candle["timestamp"] + DAY > migration_timestamp
            and candle["timestamp"] <= snapshot_timestamp
        ]
        first_30d = [
            candle for candle in observed if candle["timestamp"] < migration_timestamp + 30 * DAY
        ]
        max_30_candle = max(first_30d, key=lambda candle: candle["high"]) if first_30d else None
        max_observed_candle = max(observed, key=lambda candle: candle["high"]) if observed else None
        first_5x = next(
            (candle for candle in observed if candle["high"] >= 5 * issue_vwap), None
        )
        mature_30d = snapshot_timestamp >= migration_timestamp + 30 * DAY
        p1d_price = asof_close(observed, migration_timestamp + DAY)
        p7d_price = asof_close(observed, migration_timestamp + 7 * DAY)
        p30d_price = asof_close(observed, migration_timestamp + 30 * DAY)
        current_attributes = current[pool_id]
        if chain["gecko_token_side"] == "base":
            current_price_raw = current_attributes["base_token_price_native_currency"]
            current_native_liquidity_usd = float(
                current_attributes["quote_token_liquidity_usd"] or 0
            )
        else:
            current_price_raw = current_attributes["quote_token_price_native_currency"]
            current_native_liquidity_usd = float(
                current_attributes["base_token_liquidity_usd"] or 0
            )
        current_token_price_native = (
            float(current_price_raw) if current_price_raw is not None else None
        )
        rows.append(
            {
                "auction": chain["auction"],
                "token": chain["token"],
                "pool_id": pool_id,
                "token_side": chain["gecko_token_side"],
                "migration_timestamp": migration_timestamp,
                "migration_time_utc": datetime.fromtimestamp(
                    migration_timestamp, timezone.utc
                ).isoformat(),
                "currency_raised_eth": chain["currency_raised_raw"] / 10**18,
                "total_cleared_tokens": chain["total_cleared_raw"]
                / 10 ** chain["token_decimals"],
                "issue_vwap_eth_per_token": issue_vwap,
                "daily_candles": len(observed),
                "first_day_open_x": observed[0]["open"] / issue_vwap if observed else None,
                "p1d_x": p1d_price / issue_vwap if p1d_price is not None else None,
                "p7d_x": p7d_price / issue_vwap if p7d_price is not None else None,
                "p30d_x": (
                    p30d_price / issue_vwap
                    if mature_30d and p30d_price is not None
                    else None
                ),
                "current_daily_close_x": observed[-1]["close"] / issue_vwap if observed else None,
                "max_spot_30d_x": max_30_candle["high"] / issue_vwap if max_30_candle else None,
                "max_spot_30d_timestamp": (
                    max_30_candle["timestamp"] if max_30_candle else None
                ),
                "max_spot_observed_x": (
                    max_observed_candle["high"] / issue_vwap if max_observed_candle else None
                ),
                "time_to_max_30d_days": (
                    max(0, max_30_candle["timestamp"] - migration_timestamp) / DAY
                    if max_30_candle
                    else None
                ),
                "spot_5x_observed": first_5x is not None,
                "first_spot_5x_days": (
                    max(0, first_5x["timestamp"] - migration_timestamp) / DAY
                    if first_5x
                    else None
                ),
                "mature_30d": mature_30d,
                "mature_180d": snapshot_timestamp >= migration_timestamp + 180 * DAY,
                "current_spot_x": (
                    current_token_price_native / issue_vwap
                    if current_token_price_native is not None
                    else None
                ),
                "current_reserve_usd": float(current_attributes["reserve_in_usd"] or 0),
                "current_native_side_liquidity_usd": current_native_liquidity_usd,
                "current_5pct_native_side_capacity_usd_approx": (
                    0.05 * current_native_liquidity_usd
                ),
            }
        )

    status = json.loads(args.status.read_text())
    migration_events = json.loads(args.migration_events.read_text())
    migrated = {
        row["auction"].lower() for row in migration_events if row["event"] == "migrated"
    }
    latest_status_block = max(row["created_block"] for row in status)
    # Status was collected after all rows below this latest observed creation;
    # all reported material rows are already ended and migrated. The canonical
    # ended count is kept from the status snapshot's mechanical end-block test.
    ended = [row for row in status if row["end_block"] < 46_986_412]
    positive_required_migrated = [
        row
        for row in ended
        if row["required_currency_raised_raw"] > 0 and row["auction"].lower() in migrated
    ]
    mature30 = [row for row in rows if row["mature_30d"]]
    spot5 = [row for row in rows if row["spot_5x_observed"]]
    mature30_spot5 = [
        row for row in mature30 if row["max_spot_30d_x"] is not None and row["max_spot_30d_x"] >= 5
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_timestamp": snapshot_timestamp,
        "scope": "Robinhood native-currency CCA pools with successful migration and >=1 ETH raised",
        "denominators": {
            "all_v2_auctions": len(status),
            "ended_v2_auctions": len(ended),
            "positive_required_and_migrated": len(positive_required_migrated),
            "material_raised_ge_1_eth": len(rows),
            "material_mature_30d": len(mature30),
            "material_mature_180d": sum(row["mature_180d"] for row in rows),
        },
        "coverage": {
            "ohlcv_rows": len(rows),
            "nonempty_ohlcv": sum(row["daily_candles"] > 0 for row in rows),
            "base_side": sum(row["token_side"] == "base" for row in rows),
            "quote_side_inverted": sum(row["token_side"] == "quote" for row in rows),
        },
        "spot_upper_bound": {
            "observed_5x_count": len(spot5),
            "observed_5x_share_material": len(spot5) / len(rows),
            "mature30_5x_within_30d_count": len(mature30_spot5),
            "mature30_5x_within_30d_share": (
                len(mature30_spot5) / len(mature30) if mature30 else None
            ),
            "max_spot_30d_x_quantiles_mature30": quantiles(
                [row["max_spot_30d_x"] for row in mature30]
            ),
            "p1d_x_quantiles": quantiles(
                [row["p1d_x"] for row in rows if row["p1d_x"] is not None]
            ),
            "p7d_x_quantiles": quantiles(
                [row["p7d_x"] for row in rows if row["p7d_x"] is not None]
            ),
            "p30d_x_quantiles_mature30": quantiles(
                [row["p30d_x"] for row in mature30 if row["p30d_x"] is not None]
            ),
            "time_to_max_30d_days_quantiles_mature30": quantiles(
                [row["time_to_max_30d_days"] for row in mature30]
            ),
            "first_spot_5x_days_quantiles": quantiles(
                [row["first_spot_5x_days"] for row in spot5]
            ),
            "current_5pct_capacity_usd_quantiles_spot5": quantiles(
                [row["current_5pct_native_side_capacity_usd_approx"] for row in spot5]
            ),
            "spot5_current_capacity_ge_500_count": sum(
                row["current_5pct_native_side_capacity_usd_approx"] >= 500
                for row in spot5
            ),
        },
        "not_yet_measured": [
            "ordinary-public bidder allocation and bidder-specific average cost",
            "$100/$500/$1,000 historical executable exit depth at the high",
            "fees, gas and 100 bps execution haircut",
            "180-day outcomes (all Robinhood observations are right-censored)",
        ],
    }

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    q = summary["spot_upper_bound"]
    qmax = q["max_spot_30d_x_quantiles_mature30"]
    qp30 = q["p30d_x_quantiles_mature30"]
    qtime = q["time_to_max_30d_days_quantiles_mature30"]
    qcapacity = q["current_5pct_capacity_usd_quantiles_spot5"]
    top = sorted(rows, key=lambda row: row["max_spot_30d_x"] or -1, reverse=True)[:15]
    lines = [
        "# Robinhood CCA 物质性样本：日线现货上界筛查",
        "",
        "> 这不是 `first_exec_5x` 结果。日线 high 可能瞬时、被操纵或容量不足；入场锚是全拍卖 token-VWAP，尚不是普通账户逐笔成本。",
        "",
        "## 母体漏斗",
        "",
        f"- v2 拍卖账户：{len(status):,}",
        f"- 已结束：{len(ended):,}",
        f"- 最低筹资额 > 0 且成功迁移：{len(positive_required_migrated):,}",
        f"- 原生币筹资 >= 1 ETH 且成功迁移：{len(rows):,}",
        f"- 其中满 30 天：{len(mature30):,}；满 180 天：{sum(row['mature_180d'] for row in rows):,}",
        "",
        "## 现货形状（仅上界）",
        "",
        f"- 观察期内曾触及 5x：{len(spot5)}/{len(rows)} = {len(spot5)/len(rows):.2%}",
        f"- 满 30 天样本中，30 天内曾触及 5x：{len(mature30_spot5)}/{len(mature30)} = {len(mature30_spot5)/len(mature30):.2%}" if mature30 else "- 无满 30 天样本",
        f"- `max_spot_30d`（满 30 天）P50/P90/P95/P99/max：{fmt(qmax['p50'])} / {fmt(qmax['p90'])} / {fmt(qmax['p95'])} / {fmt(qmax['p99'])} / {fmt(qmax['max'])}",
        f"- `p30d`（满 30 天）P50/P90/P95/P99/max：{fmt(qp30['p50'])} / {fmt(qp30['p90'])} / {fmt(qp30['p95'])} / {fmt(qp30['p99'])} / {fmt(qp30['max'])}",
        f"- 到达 30 日内峰值的天数 P25/P50/P75/P90：{fmt(qtime['p25'],2)} / {fmt(qtime['p50'],2)} / {fmt(qtime['p75'],2)} / {fmt(qtime['p90'],2)}",
        f"- 曾触及 5x 的池，当前 5% 报价端容量近似 P50/P90：${fmt(qcapacity['p50'],2)} / ${fmt(qcapacity['p90'],2)}；其中 >=$500：{q['spot5_current_capacity_ge_500_count']}/{len(spot5)}（仅当前，不代表峰值当时）",
        "",
        "## 最大 15 个 spot 候选",
        "",
        "| token | raised ETH | max30d x | p30d x | first 5x days | current 5% cap ~$ | poolId |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in top:
        lines.append(
            f"| `{row['token']}` | {row['currency_raised_eth']:.3f} | {fmt(row['max_spot_30d_x'])} | {fmt(row['p30d_x'])} | {fmt(row['first_spot_5x_days'],2)} | {fmt(row['current_5pct_native_side_capacity_usd_approx'],2)} | `{row['pool_id']}` |"
        )
    lines += [
        "",
        "## 尚未通过的闸门",
        "",
        "- 普通公开投标者的实际分配和逐投标时点成本；",
        "- high 当时卖出 $100/$500/$1,000 的历史池深与滑点；",
        "- 手续费、gas 与额外 100 bps 执行损耗；",
        "- 180 天结局（当前全部右删失）。",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit public allocation and participant concentration in MetaDAO launches."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def accepted_raw(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    for field in ("finalRaiseAmount", "totalApprovedAmount", "totalCommittedAmount"):
        value = decoded.get(field)
        if value is not None:
            return int(value)
    return 0


def percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def fmt(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "NA"
    return f"{value:,.{digits}f}"


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--launches", type=Path, default=base / "data/metadao_current_launch_accounts.json"
    )
    parser.add_argument(
        "--funding-records", type=Path, default=base / "data/metadao_material_funding_records.json"
    )
    parser.add_argument(
        "--markets", type=Path, default=base / "data/metadao_market_snapshot.json"
    )
    parser.add_argument(
        "--output-json", type=Path, default=base / "output/metadao_allocation_audit.json"
    )
    parser.add_argument(
        "--output-csv", type=Path, default=base / "output/metadao_allocation_by_launch.csv"
    )
    parser.add_argument(
        "--output-md", type=Path, default=base / "output/metadao_allocation_audit.md"
    )
    parser.add_argument("--minimum-raise-usd", type=float, default=10_000)
    args = parser.parse_args()

    launches_all = json.loads(args.launches.read_text())
    launches = [
        row
        for row in launches_all
        if row["state"] == "Complete"
        and accepted_raw(row) / 1_000_000 >= args.minimum_raise_usd
    ]
    funding = json.loads(args.funding_records.read_text())
    records = funding["records"]
    markets = {row["launch_account"]: row for row in json.loads(args.markets.read_text())}
    by_launch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_launch[row["launch_account"]].append(row)

    launch_rows: list[dict[str, Any]] = []
    funder_launch_counts: Counter[str] = Counter()
    accepted_by_funder: Counter[str] = Counter()
    observable_funders: set[str] = set()
    for launch in launches:
        account = launch["launch_account"]
        group = by_launch[account]
        chain_total = accepted_raw(launch) / 1_000_000
        observed_total = sum(row["actual_accepted_usd"] for row in group)
        committed_total = sum(row["committed_usd"] for row in group)
        positive = [row for row in group if row["actual_accepted_usd"] > 0]
        positive_funders = {row["funder"] for row in positive}
        for funder in positive_funders:
            funder_launch_counts[funder] += 1
            observable_funders.add(funder)
        for row in positive:
            accepted_by_funder[row["funder"]] += row["actual_accepted_usd"]
        accepted_values = [row["actual_accepted_usd"] for row in positive]
        ratios = [
            row["acceptance_ratio"]
            for row in group
            if row["acceptance_ratio"] is not None and row["committed_usd"] > 0
        ]
        market = markets.get(account, {})
        launch_rows.append(
            {
                "version": launch["version"],
                "launch_account": account,
                "token_mint": launch["base_mint"],
                "symbol": market.get("token_symbol") or "",
                "started_at": launch.get("started_at"),
                "chain_accepted_usd": chain_total,
                "funding_records": len(group),
                "allocation_observable": bool(group),
                "positive_allocations": len(positive),
                "unique_positive_funders": len(positive_funders),
                "allocations_ge_100": sum(value >= 100 for value in accepted_values),
                "allocations_ge_500": sum(value >= 500 for value in accepted_values),
                "allocations_ge_1000": sum(value >= 1000 for value in accepted_values),
                "observed_accepted_usd": observed_total if group else None,
                "observed_to_chain_ratio": observed_total / chain_total if group and chain_total else None,
                "committed_usd": committed_total if group else None,
                "approval_dollars_ratio": observed_total / committed_total if committed_total else None,
                "allocation_usd_p25": percentile(accepted_values, 0.25),
                "allocation_usd_p50": percentile(accepted_values, 0.50),
                "allocation_usd_p75": percentile(accepted_values, 0.75),
                "allocation_usd_p90": percentile(accepted_values, 0.90),
                "allocation_usd_max": max(accepted_values) if accepted_values else None,
                "acceptance_ratio_p50": percentile(ratios, 0.50),
                "acceptance_ratio_p10": percentile(ratios, 0.10),
            }
        )

    observable = [row for row in launch_rows if row["allocation_observable"]]
    ratios = [row["observed_to_chain_ratio"] for row in observable]
    all_positive = [row for row in records if row["actual_accepted_usd"] > 0]
    all_ge_100 = [row for row in all_positive if row["actual_accepted_usd"] >= 100]
    concentration_denominator = sum(accepted_by_funder.values())
    top_accepted = accepted_by_funder.most_common()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "state": "Complete",
            "minimum_raise_usd": args.minimum_raise_usd,
            "launches": len(launch_rows),
        },
        "source_complete": funding["complete"],
        "funding_records": len(records),
        "observable_launches": len(observable),
        "unobservable_launches_closed_records": [
            row["launch_account"] for row in launch_rows if not row["allocation_observable"]
        ],
        "positive_allocation_records": len(all_positive),
        "allocation_records_ge_100": len(all_ge_100),
        "unique_positive_funders": len(observable_funders),
        "unique_funders_in_ge_100_records": len({row["funder"] for row in all_ge_100}),
        "launches_with_at_least_one_ge_100": sum(row["allocations_ge_100"] > 0 for row in observable),
        "observed_to_chain_ratio": {
            "min": min(ratios) if ratios else None,
            "median": statistics.median(ratios) if ratios else None,
            "max": max(ratios) if ratios else None,
        },
        "repeat_participation": {
            "funders_ge_2_launches": sum(count >= 2 for count in funder_launch_counts.values()),
            "funders_ge_5_launches": sum(count >= 5 for count in funder_launch_counts.values()),
            "funders_ge_10_launches": sum(count >= 10 for count in funder_launch_counts.values()),
            "max_launches": max(funder_launch_counts.values(), default=0),
        },
        "cross_launch_accepted_concentration": {
            "top_10_share": sum(value for _, value in top_accepted[:10]) / concentration_denominator
            if concentration_denominator
            else None,
            "top_100_share": sum(value for _, value in top_accepted[:100]) / concentration_denominator
            if concentration_denominator
            else None,
        },
        "by_launch": launch_rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(launch_rows[0]))
        writer.writeheader()
        writer.writerows(launch_rows)

    lines = [
        "# MetaDAO material-launch allocation audit",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Coverage",
        "",
        f"- Material completed launches: **{len(launch_rows)}**",
        f"- Launches with live FundingRecords: **{len(observable)}**",
        f"- Closed/unobservable early-version records: **{len(launch_rows) - len(observable)}**",
        f"- FundingRecords decoded: **{len(records):,}**",
        f"- Positive allocations: **{len(all_positive):,}**",
        f"- Allocation records >= $100: **{len(all_ge_100):,}**",
        f"- Unique funders with positive allocation: **{len(observable_funders):,}**",
        f"- Observable launches with at least one >= $100 allocation: **{summary['launches_with_at_least_one_ge_100']}/{len(observable)}**",
        "",
        "## Concentration",
        "",
        f"- Repeat funders in >=2 launches: **{summary['repeat_participation']['funders_ge_2_launches']:,}**",
        f"- Repeat funders in >=5 launches: **{summary['repeat_participation']['funders_ge_5_launches']:,}**",
        f"- Max launches for one funder: **{summary['repeat_participation']['max_launches']}**",
        f"- Top-10 funders' share of observed accepted dollars: **{fmt(100 * summary['cross_launch_accepted_concentration']['top_10_share'])}%**",
        "",
        "## By launch",
        "",
        "| Symbol | Version | Chain raise | Records | >=$100 | Alloc P50 | Alloc max | Observed/chain | Approval $ ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in launch_rows:
        lines.append(
            "| {symbol} | {version} | ${raise_} | {records} | {ge100} | ${p50} | ${max_} | {coverage} | {approval} |".format(
                symbol=row["symbol"] or row["token_mint"][:8],
                version=row["version"],
                raise_=fmt(row["chain_accepted_usd"], 0),
                records=row["funding_records"],
                ge100=row["allocations_ge_100"],
                p50=fmt(row["allocation_usd_p50"]),
                max_=fmt(row["allocation_usd_max"]),
                coverage=fmt(100 * row["observed_to_chain_ratio"]) + "%"
                if row["observed_to_chain_ratio"] is not None
                else "NA (closed)",
                approval=fmt(100 * row["approval_dollars_ratio"]) + "%"
                if row["approval_dollars_ratio"] is not None
                else "NA",
            )
        )
    lines.extend(
        [
            "",
            "`>= $100` is a mechanical allocation-capacity test. It does not establish that the funder was an ordinary unaffiliated participant, or that a $500 exit was available.",
            "",
        ]
    )
    args.output_md.write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in summary.items() if k != "by_launch"}, indent=2))


if __name__ == "__main__":
    main()

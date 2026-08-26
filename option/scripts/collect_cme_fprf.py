#!/usr/bin/env python3
"""Fetch and inventory CME's dated option product-reference ZIP files.

The v2 source date is fixed at 2026-08-21, before the common cutoff.  This
script stages unique option series for audit; it does not write U-MKT rows or
decide which CME product-complex values are commodities.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


SOURCE_DATE = "20260821"
BASE_URL = "https://www.cmegroup.com/ftp/fprf/csv"
EXCHANGES = ("cbt", "cme", "comex", "nymex")
REQUIRED_COLUMNS = {
    "BizDt",
    "UndlyClrAlias",
    "UndlyExch",
    "SeriesExch",
    "SeriesSym",
    "SeriesDesc",
    "SeriesProdCmplx",
    "SeriesStatus",
    "SeriesSecTyp",
    "SeriesFirstTrdDt",
    "SeriesLastTrdDt",
    "Tradable",
}


def filename(exchange: str) -> str:
    return "cmeg.{}.opt.prf.{}.csv.zip".format(exchange, SOURCE_DATE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, object] = {
        "source_date": SOURCE_DATE,
        "official_directory": BASE_URL + "/",
        "files": [],
    }
    for exchange in EXCHANGES:
        name = filename(exchange)
        target = output_dir / name
        if target.exists():
            raise ValueError("refusing to overwrite {}".format(target))
        url = "{}/{}".format(BASE_URL, name)
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        fd, temporary_name = tempfile.mkstemp(prefix=name + ".", dir=str(output_dir))
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                with temporary.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                status = response.status
                final_url = response.geturl()
                headers = dict(response.headers.items())
            if status != 200 or not zipfile.is_zipfile(temporary):
                raise ValueError("{} did not return a valid ZIP".format(url))
            temporary.rename(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        manifest["files"].append(
            {
                "exchange": exchange,
                "file": name,
                "url": url,
                "final_url": final_url,
                "http_status": status,
                "response_headers": headers,
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    with (output_dir / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print("saved {} dated CME FPRF ZIP files".format(len(EXCHANGES)))
    return 0


def rows_from_zip(path: Path) -> Iterable[Dict[str, str]]:
    if not zipfile.is_zipfile(path):
        raise ValueError("not a ZIP file: {}".format(path))
    with zipfile.ZipFile(path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("{} contains {} CSV files".format(path, len(csv_names)))
        with archive.open(csv_names[0]) as raw:
            # CME reference files are ASCII-compatible; replacement keeps an
            # unexpected vendor character visible without aborting inventory.
            import io

            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.DictReader(text)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "{} missing documented columns: {}".format(
                        path, ", ".join(sorted(missing))
                    )
                )
            for row in reader:
                yield row


def join_values(values: Set[str]) -> str:
    return "|".join(sorted(value for value in values if value))


def inventory(input_dir: Path, output: Path) -> int:
    records: Dict[Tuple[str, ...], Dict[str, object]] = {}
    row_counts: Dict[str, int] = defaultdict(int)
    biz_dates: Set[str] = set()

    for exchange in EXCHANGES:
        path = input_dir / filename(exchange)
        for row in rows_from_zip(path):
            row_counts[exchange] += 1
            biz_dates.add(row.get("BizDt", ""))
            key = (
                exchange,
                row.get("SeriesExch", ""),
                row.get("SeriesSym", ""),
                row.get("SeriesDesc", ""),
                row.get("SeriesProdCmplx", ""),
                row.get("UndlyExch", ""),
                row.get("UndlyClrAlias", ""),
            )
            record = records.setdefault(
                key,
                {
                    "exchange_file": exchange,
                    "series_exchange": row.get("SeriesExch", ""),
                    "series_symbol": row.get("SeriesSym", ""),
                    "series_description": row.get("SeriesDesc", ""),
                    "series_product_complex": row.get("SeriesProdCmplx", ""),
                    "underlying_exchange": row.get("UndlyExch", ""),
                    "underlying_clearing_alias": row.get("UndlyClrAlias", ""),
                    "security_types": set(),
                    "series_statuses": set(),
                    "tradable_values": set(),
                    "first_trade_dates": set(),
                    "last_trade_dates": set(),
                    "source_row_count": 0,
                },
            )
            record["security_types"].add(row.get("SeriesSecTyp", ""))
            record["series_statuses"].add(row.get("SeriesStatus", ""))
            record["tradable_values"].add(row.get("Tradable", ""))
            record["first_trade_dates"].add(row.get("SeriesFirstTrdDt", ""))
            record["last_trade_dates"].add(row.get("SeriesLastTrdDt", ""))
            record["source_row_count"] += 1

    fieldnames = [
        "exchange_file",
        "series_exchange",
        "series_symbol",
        "series_description",
        "series_product_complex",
        "underlying_exchange",
        "underlying_clearing_alias",
        "security_types",
        "series_statuses",
        "tradable_values",
        "earliest_first_trade_date",
        "latest_last_trade_date",
        "source_row_count",
    ]
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for key in sorted(records):
            record = records[key]
            first_dates = sorted(value for value in record.pop("first_trade_dates") if value)
            last_dates = sorted(value for value in record.pop("last_trade_dates") if value)
            record["security_types"] = join_values(record["security_types"])
            record["series_statuses"] = join_values(record["series_statuses"])
            record["tradable_values"] = join_values(record["tradable_values"])
            record["earliest_first_trade_date"] = first_dates[0] if first_dates else ""
            record["latest_last_trade_date"] = last_dates[-1] if last_dates else ""
            writer.writerow(record)

    summary = {
        "source_date": SOURCE_DATE,
        "business_dates": sorted(biz_dates),
        "source_rows_by_exchange": dict(sorted(row_counts.items())),
        "unique_series_records": len(records),
        "output": str(output),
        "next_gate": (
            "Inspect series_product_complex values, freeze a commodity allowlist, "
            "then deduplicate variants before writing U-MKT."
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch_parser = subparsers.add_parser("fetch", help="download four dated ZIPs")
    fetch_parser.add_argument("output_dir", type=Path)
    inventory_parser = subparsers.add_parser(
        "inventory", help="deduplicate strike rows into an auditable series inventory"
    )
    inventory_parser.add_argument("input_dir", type=Path)
    inventory_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            return fetch(args.output_dir)
        return inventory(args.input_dir, args.output)
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

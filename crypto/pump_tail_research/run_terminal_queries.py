#!/usr/bin/env python3
"""Execute all 12 frozen Pump terminal Dune queries with resumable outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_count(path: Path) -> int:
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        return sum(1 for _ in reader)


def csv_name(sql_name: str) -> str:
    stem = Path(sql_name).stem
    if stem.startswith("17_terminal_"):
        stem = "dune_terminal_" + stem.removeprefix("17_terminal_")
    elif stem.startswith("18_terminal_"):
        stem = "dune_terminal_" + stem.removeprefix("18_terminal_")
    else:
        raise ValueError(f"unexpected terminal SQL name: {sql_name}")
    return stem + ".csv"


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=root / "data/terminal_query_manifest.json"
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--only", help="Run outputs whose filename contains this text")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected_jobs = [
        job
        for job in manifest["jobs"]
        if not args.only or args.only in csv_name(job["output"])
    ]
    records = []
    for index, job in enumerate(selected_jobs, 1):
        output_name = csv_name(job["output"])
        sql_path = root / "data" / job["output"]
        output_path = root / "data" / output_name
        if sha256(sql_path) != job["output_sha256"]:
            raise RuntimeError(f"expanded SQL hash mismatch: {sql_path}")
        if output_path.exists() and not args.refresh and not args.validate_only:
            records.append(
                {
                    "output": output_name,
                    "status": "cached",
                    "rows": row_count(output_path),
                    "sha256": sha256(output_path),
                }
            )
            continue

        destination = Path("/tmp") / f"validate_{output_name}" if args.validate_only else output_path
        command = [
            sys.executable,
            str(root / "run_dune.py"),
            "--sql",
            str(sql_path),
            "--out",
            str(destination),
            "--performance",
            "large",
            "--timeout-minutes",
            "120",
        ]
        if args.validate_only:
            command.append("--validate")
        print(
            json.dumps(
                {"query": f"{index}/{len(selected_jobs)}", "output": output_name}
            ),
            flush=True,
        )
        completed = subprocess.run(command)
        if completed.returncode != 0:
            records.append({"output": output_name, "status": "failed"})
            break
        records.append(
            {
                "output": output_name,
                "status": "validated" if args.validate_only else "complete",
                "rows": row_count(destination),
                "sha256": sha256(destination),
            }
        )

    audit = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": manifest["protocol_sha256"],
        "validate_only": args.validate_only,
        "records": records,
        "complete": len(records) == len(selected_jobs)
        and all(row["status"] in {"cached", "complete", "validated"} for row in records),
    }
    audit_path = root / "data/terminal_query_run_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    if not audit["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

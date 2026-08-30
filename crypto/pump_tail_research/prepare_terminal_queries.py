#!/usr/bin/env python3
"""Mechanically materialize every pre-frozen Pump terminal SQL variant."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


JAN_BASE_REPLACEMENTS = [
    ("TIMESTAMP '2026-05-01 00:00:00'", "TIMESTAMP '2026-01-01 00:00:00'"),
    ("TIMESTAMP '2026-07-25 00:00:00'", "TIMESTAMP '2026-03-01 00:00:00'"),
    ("TIMESTAMP '2026-07-26 00:00:00'", "TIMESTAMP '2026-03-02 00:00:00'"),
    ("DATE '2026-05-01'", "DATE '2026-01-01'"),
    ("DATE '2026-07-24'", "DATE '2026-02-28'"),
    ("DATE '2026-07-25'", "DATE '2026-03-01'"),
]

JAN_ENTITY_REPLACEMENTS = [
    ("TIMESTAMP '2026-05-01 00:00:00'", "TIMESTAMP '2026-01-01 00:00:00'"),
    ("TIMESTAMP '2026-07-25 00:00:00'", "TIMESTAMP '2026-03-01 00:00:00'"),
    ("DATE '2026-05-01'", "DATE '2026-01-01'"),
    ("DATE '2026-07-24'", "DATE '2026-02-28'"),
    ("DATE '2026-04-01'", "DATE '2025-12-01'"),
    ("DATE '2026-07-25'", "DATE '2026-03-01'"),
]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def render(source_name: str, output_name: str, replacements: list[tuple[str, str]]) -> dict:
    source_path = ROOT / source_name
    source = source_path.read_text(encoding="utf-8")
    expanded = source
    applied = []
    for old, new in replacements:
        count = expanded.count(old)
        if count == 0:
            raise RuntimeError(f"replacement not found in {source_name}: {old!r}")
        expanded = expanded.replace(old, new)
        applied.append({"old": old, "new": new, "occurrences": count})
    output_path = DATA / output_name
    output_path.write_text(expanded, encoding="utf-8")
    return {
        "source": source_name,
        "source_sha256": sha256(source.encode()),
        "output": output_name,
        "output_sha256": sha256(expanded.encode()),
        "replacements": applied,
    }


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    jobs = []
    for delay, interval in (("30s", "INTERVAL '30' SECOND"), ("60s", "INTERVAL '1' MINUTE")):
        cutoff = [("INTERVAL '5' MINUTE", interval)]
        jobs.append(
            render("09_t5m_features.sql", f"17_terminal_base_mayjul_{delay}.sql", cutoff)
        )
        jobs.append(
            render(
                "09_t5m_features.sql",
                f"17_terminal_base_janfeb_{delay}.sql",
                JAN_BASE_REPLACEMENTS + cutoff,
            )
        )
        jobs.append(
            render("16_entity_features_core.sql", f"17_terminal_entity_mayjul_{delay}.sql", cutoff)
        )
        jobs.append(
            render(
                "16_entity_features_core.sql",
                f"17_terminal_entity_janfeb_{delay}.sql",
                JAN_ENTITY_REPLACEMENTS + cutoff,
            )
        )

    execution_anchors = {
        "30s": "INTERVAL '45' SECOND",
        "60s": "INTERVAL '1' MINUTE + INTERVAL '15' SECOND",
    }
    for delay, anchor in execution_anchors.items():
        source_anchor = "INTERVAL '5' MINUTE + INTERVAL '15' SECOND"
        execution_replacements = [
            (source_anchor, anchor),
            ("INTERVAL '24' HOUR", "INTERVAL '4' HOUR"),
        ]
        jobs.append(
            render(
                "10_first_passage.sql",
                f"18_terminal_execution_mayjul_{delay}.sql",
                execution_replacements,
            )
        )
        jobs.append(
            render(
                "13_first_passage_janfeb.sql",
                f"18_terminal_execution_janfeb_{delay}.sql",
                execution_replacements,
            )
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "PUMP_TERMINAL_EXPERIMENT_2026-08-28.md",
        "protocol_sha256": sha256((ROOT / "PUMP_TERMINAL_EXPERIMENT_2026-08-28.md").read_bytes()),
        "jobs": jobs,
    }
    path = DATA / "terminal_query_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"queries": len(jobs), "manifest": str(path)}, indent=2))


if __name__ == "__main__":
    main()

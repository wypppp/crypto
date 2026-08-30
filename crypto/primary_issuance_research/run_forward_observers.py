#!/usr/bin/env python3
"""Run the read-only CCA and MetaDAO observers on fixed cadences."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_observer(name: str, command: list[str], log_path: Path) -> None:
    started = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    completed = subprocess.run(command, text=True, capture_output=True)
    append_jsonl(
        log_path,
        {
            "observer": name,
            "started_at": started,
            "duration_seconds": time.monotonic() - before,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        },
    )
    print(
        json.dumps(
            {
                "observer": name,
                "returncode": completed.returncode,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        flush=True,
    )


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--cca-seconds", type=int, default=30)
    parser.add_argument("--metadao-seconds", type=int, default=600)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--log", type=Path, default=base_dir / "forward/observer_runner.jsonl"
    )
    args = parser.parse_args()
    if args.cca_seconds < 10 or args.metadao_seconds < 60:
        raise ValueError("CCA cadence must be >=10s and MetaDAO cadence >=60s")

    commands = {
        "cca": [
            sys.executable,
            str(base_dir / "observe_cca_forward.py"),
            "--proxy-mode",
            "direct",
            "--timeout",
            "30",
        ],
        "metadao": [
            sys.executable,
            str(base_dir / "observe_metadao_forward.py"),
            "--proxy-mode",
            "auto",
            "--timeout",
            "60",
        ],
    }
    next_run = {"cca": 0.0, "metadao": 0.0}
    intervals = {"cca": args.cca_seconds, "metadao": args.metadao_seconds}

    while True:
        now = time.monotonic()
        for name in ("cca", "metadao"):
            if now >= next_run[name]:
                run_observer(name, commands[name], args.log)
                next_run[name] = time.monotonic() + intervals[name]
        if args.once:
            return
        delay = max(0.25, min(next_run.values()) - time.monotonic())
        time.sleep(min(delay, 30))


if __name__ == "__main__":
    main()

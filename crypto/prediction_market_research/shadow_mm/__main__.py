import argparse
import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .collector import ShadowCollector, output_path
from .config import CollectorConfig
from .storage import JsonlEventWriter
from .ws_collector import WebSocketShadowCollector
from .replay import MakerReplayConfig, replay_paths
from .quality import analyze_capture
from .backfill import backfill_resolutions
from .latency_probe import run_probe


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Read-only Polymarket shadow market-making data collector"
    )
    sub = root.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="Run REST polling smoke collector")
    collect.add_argument("--config", type=Path)
    collect.add_argument("--duration-seconds", type=float, default=60.0)
    collect.add_argument("--out", type=Path)

    stream = sub.add_parser("stream", help="Run public WebSocket shadow collector")
    stream.add_argument("--config", type=Path)
    stream.add_argument("--duration-seconds", type=float, default=60.0)
    stream.add_argument("--out", type=Path)

    latency_probe = sub.add_parser(
        "latency-probe",
        help="Run a minimal public CLOB receive/decode latency probe",
    )
    latency_probe.add_argument("--duration-seconds", type=float, default=120.0)
    latency_probe.add_argument("--out", type=Path)

    discover = sub.add_parser("discover", help="Print selected markets without polling")
    discover.add_argument("--config", type=Path)

    replay = sub.add_parser("replay", help="Replay raw data through shadow maker policies")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--resolutions", type=Path, action="append", default=[])
    replay.add_argument(
        "--policy",
        choices=["join_bbo", "midpoint", "fair_value"],
        action="append",
    )
    replay.add_argument("--latency", type=float, action="append")
    replay.add_argument("--out", type=Path)

    quality = sub.add_parser("quality", help="Audit raw capture completeness and gaps")
    quality.add_argument("--input", type=Path, required=True)
    quality.add_argument("--out", type=Path)

    resolve = sub.add_parser(
        "resolve", help="Backfill explicit closed 1/0 Gamma resolutions"
    )
    resolve.add_argument("--config", type=Path)
    resolve.add_argument("--input", type=Path, required=True)
    resolve.add_argument("--out", type=Path, required=True)
    return root


def load_config(path: Optional[Path]) -> CollectorConfig:
    return CollectorConfig.from_path(path) if path else CollectorConfig()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    config = load_config(getattr(args, "config", None))
    if args.command == "collect":
        destination = args.out or output_path(config)
        with JsonlEventWriter(
            destination,
            fsync_every=config.fsync_every,
            queue_max_events=config.writer_queue_max_events,
            gzip_compresslevel=config.gzip_compresslevel,
        ) as writer:
            collector = ShadowCollector(config, writer)
            summary = collector.run(max(args.duration_seconds, 0.0))
        print(json.dumps({"output": str(destination), **summary}, indent=2, sort_keys=True))
        return 0
    if args.command == "discover":
        temporary = Path(config.output_dir) / "discovery.jsonl"
        with JsonlEventWriter(temporary, fsync_every=1) as writer:
            collector = ShadowCollector(config, writer)
            try:
                selected = collector.discover()
                payload = [
                    {
                        "condition_id": item.market.condition_id,
                        "question": item.market.question,
                        "slug": item.market.slug,
                        "symbol": item.symbol,
                        "interval_minutes": item.interval_minutes,
                        "tokens": [token.__dict__ for token in item.market.tokens],
                    }
                    for item in selected
                ]
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            finally:
                collector.client.close()
        return 0
    if args.command == "stream":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = args.out or Path(config.output_dir) / "raw_ws_{}.jsonl.gz".format(stamp)
        with JsonlEventWriter(
            destination,
            fsync_every=config.fsync_every,
            queue_max_events=config.writer_queue_max_events,
            gzip_compresslevel=config.gzip_compresslevel,
        ) as writer:
            collector = WebSocketShadowCollector(config, writer)
            summary = collector.run(max(args.duration_seconds, 0.0))
        print(json.dumps({"output": str(destination), **summary}, indent=2, sort_keys=True))
        return 0
    if args.command == "latency-probe":
        summary = run_probe(max(args.duration_seconds, 0.0))
        encoded = json.dumps(summary, indent=2, sort_keys=True)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.out)}, indent=2))
        else:
            print(encoded)
        return 0
    if args.command == "replay":
        configs = None
        if args.policy or args.latency:
            policies = args.policy or ["join_bbo", "midpoint", "fair_value"]
            latencies = args.latency or [5.0, 15.0, 30.0]
            configs = [
                MakerReplayConfig(
                    name="{}_{}s".format(policy, int(latency)),
                    latency_seconds=latency,
                    quote_size=Decimal("5"),
                    policy=policy,
                )
                for policy in policies
                for latency in latencies
            ]
        summary = replay_paths([args.input, *args.resolutions], configs)
        encoded = json.dumps(summary, indent=2, sort_keys=True, default=str)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.out)}, indent=2))
        else:
            print(encoded)
        return 0
    if args.command == "resolve":
        summary = backfill_resolutions(args.input, args.out, config)
        print(
            json.dumps(
                {"output": str(args.out), **summary},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "quality":
        summary = analyze_capture(args.input)
        encoded = json.dumps(summary, indent=2, sort_keys=True, default=str)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.out)}, indent=2))
        else:
            print(encoded)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

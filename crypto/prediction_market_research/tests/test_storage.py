import gzip
import json

from shadow_mm.storage import JsonlEventWriter


def test_jsonl_writer_appends_replayable_events(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    with JsonlEventWriter(path, fsync_every=1) as writer:
        writer.write({"b": 2, "a": 1})
        writer.write({"text": "中文"})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"a": 1, "b": 2}, {"text": "中文"}]


def test_gzip_jsonl_writer_round_trip_and_append(tmp_path) -> None:
    path = tmp_path / "events.jsonl.gz"
    with JsonlEventWriter(path, fsync_every=1) as writer:
        writer.write({"sequence": 1})
    with JsonlEventWriter(path, fsync_every=1) as writer:
        writer.write({"sequence": 2})
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert rows == [{"sequence": 1}, {"sequence": 2}]


def test_async_writer_drains_and_reports_no_loss(tmp_path) -> None:
    path = tmp_path / "events.jsonl.gz"
    with JsonlEventWriter(path, fsync_every=0, queue_max_events=1000) as writer:
        for sequence in range(500):
            writer.write({"sequence": sequence})
        writer.drain()
        summary = writer.summary()
        assert summary["events_enqueued_n"] == 500
        assert summary["events_written_n"] == 500
        assert summary["events_dropped_n"] == 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert sum(1 for _ in handle) == 500

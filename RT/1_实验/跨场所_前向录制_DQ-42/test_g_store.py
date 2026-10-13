"""g_store 的手算预期值测试（10-13）：日切换、多成员 gzip、清单行数与 sha256、清单不覆盖、待写清单的日期。"""

import gzip
import hashlib
import json

import g_store as S

NS = 1_000_000_000
T_1012_2359 = 1760313599 * NS  # 2025-10-12 23:59:59 UTC（只作构造时刻）
T_1013_0000 = 1760313600 * NS  # 2025-10-13 00:00:00 UTC


def test_utc_day_boundary():
    assert S.utc_day(T_1012_2359) == "2025-10-12"
    assert S.utc_day(T_1013_0000) == "2025-10-13"


def test_day_writer_splits_by_record_time_and_appends_members(tmp_path):
    w = S.DayWriter(tmp_path, "x")
    w.write({"a": 1}, T_1012_2359)
    w.write({"a": 2}, T_1013_0000)  # 换日：先把前一天落盘
    w.flush()
    w.write({"a": 3}, T_1013_0000 + NS)
    w.flush()  # 第二个 gzip 成员
    d12 = (tmp_path / "x" / "2025-10-12.jsonl.gz").read_bytes()
    d13 = tmp_path / "x" / "2025-10-13.jsonl.gz"
    assert gzip.decompress(d12) == b'{"a":1}\n'
    assert gzip.open(d13, "rb").read() == b'{"a":2}\n{"a":3}\n'
    assert w.lines == 3


def test_file_stats_hand(tmp_path):
    p = tmp_path / "f.jsonl.gz"
    raw = gzip.compress(b"x\ny\n") + gzip.compress(b"z\n")
    p.write_bytes(raw)
    st = S.file_stats(p)
    assert st == {
        "bytes": len(raw),
        "lines": 3,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_manifest_written_once(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "m"
    w = S.DayWriter(raw, "http/a")
    w.write({"k": 1}, T_1012_2359)
    w.flush()
    p = S.write_manifest("2025-10-12", raw, out)
    doc = json.loads(p.read_text())
    assert (
        doc["n_files"] == 1 and doc["files"][0]["path"] == "http/a/2025-10-12.jsonl.gz"
    )
    assert doc["files"][0]["lines"] == 1
    assert S.write_manifest("2025-10-12", raw, out) is None  # 已存在不覆盖


def test_pending_manifest_days(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "m"
    for t in (T_1012_2359 - 86400 * NS, T_1012_2359, T_1013_0000):
        w = S.DayWriter(raw, "s")
        w.write({}, t)
        w.flush()
    # 10-13 00:05：前一天还在 10 分钟的等待期里，只有 10-11 待写
    assert S.pending_manifest_days(raw, out, T_1013_0000 + 300 * NS) == ["2025-10-11"]
    # 10-13 00:11：10-11、10-12 都待写；当天 10-13 不写
    assert S.pending_manifest_days(raw, out, T_1013_0000 + 660 * NS) == [
        "2025-10-11",
        "2025-10-12",
    ]
    S.write_manifest("2025-10-11", raw, out)
    assert S.pending_manifest_days(raw, out, T_1013_0000 + 660 * NS) == ["2025-10-12"]


def test_heartbeat_writes_counts_only(tmp_path):
    hb = S.Heartbeat("p", lambda: {"a": [3, 1]}, root=tmp_path)
    assert hb.tick(force=True)
    assert not hb.tick()  # 一分钟内不重复
    files = list((tmp_path / "heartbeat" / "p").glob("*.jsonl.gz"))
    d = json.loads(gzip.open(files[0], "rt").read())
    assert d["kind"] == "heartbeat" and d["counters"] == {"a": [3, 1]}

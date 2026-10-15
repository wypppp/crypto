"""传输与账单护栏：分页、整数、恢复、非执行费停机。无需网络。"""

import csv
import gzip
import io
import json

import pytest

import dune_get_csv as C
import paid_guard as PG


def test_csv_gzip_integer_and_null_are_lossless():
    body = b'kind,amt,tx\nB,9007199254740993,"tx,with,comma"\nA,,\n'
    expected = [["B", "9007199254740993", "tx,with,comma"], ["A", "", ""]]
    assert C.decode(body, {}, ["kind", "amt", "tx"]) == expected
    assert (
        C.decode(
            gzip.compress(body), {"content-encoding": "gzip"}, ["kind", "amt", "tx"]
        )
        == expected
    )


@pytest.mark.parametrize(
    "n,rows,headers",
    [(3, [["a"]], {}), (1, [["a"]], {"x-dune-next-offset": "1"}), (1, [], {})],
)
def test_bad_page_rejected(n, rows, headers):
    with pytest.raises(ValueError):
        C.validate(rows, 0, n, headers)


def test_download_anomaly_latches_and_blocks_paid_but_allows_cancel(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")
    PG.check_download_usage((100, 2500), (100, 2500), "zero")
    with pytest.raises(PG.Refused, match="非执行费增量"):
        PG.check_download_usage((100, 2500), (100.001, 2500), "one")
    assert json.loads(PG.HALT.read_text())["non_execution_delta"] == "0.001"
    assert PG.halt_gate()
    with pytest.raises(PG.Refused, match="非执行费增量"):
        PG.request("POST", "/query/1/execute", ticket=PG.Ticket("x", 8, 3))
    assert PG.is_free("POST", "/execution/x/cancel")


def test_byte_download_requires_locked_ticket_before_network(tmp_path):
    with pytest.raises(PG.Refused, match="锁内批准"):
        PG.request_bytes(
            "/execution/x/results?limit=10", PG.Ticket("x", 0, 3), tmp_path / "a"
        )


def test_fault_resume_downloads_only_missing_pages(tmp_path, monkeypatch):
    (tmp_path / "runs").mkdir()
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(C, "H", tmp_path)
    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")
    monkeypatch.setattr(C, "PAGE", 2)
    monkeypatch.setattr(C, "usage", lambda: (100, 2500))
    metadata = {
        "total_row_count": 3,
        "column_names": ["amt"],
        "column_types": ["varchar"],
        "result_set_bytes": 100,
    }
    monkeypatch.setattr(
        C,
        "get",
        lambda p: (
            {"query_sql": "SELECT 1"}
            if p.startswith("/query")
            else {
                "query_id": 1,
                "state": "QUERY_STATE_COMPLETED",
                "result_metadata": metadata,
            }
        ),
    )
    calls = []
    fail = [True]

    def download(path, ticket, target, encoding):
        offset = int(path.rsplit("=", 1)[1])
        calls.append(offset)
        if offset == 2 and fail[0]:
            fail[0] = False
            raise OSError("断线")
        buf = io.StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(["amt"])
        writer.writerows([["9007199254740993"], ["2"]] if offset == 0 else [["3"]])
        body = gzip.compress(buf.getvalue().encode())
        target.write_bytes(body)
        return {
            "wire_bytes": len(body),
            "content-encoding": "gzip",
            **({"x-dune-next-offset": "2"} if offset == 0 else {}),
        }

    monkeypatch.setattr(PG, "request_bytes", download)
    ticket = PG.Ticket("x", 0, 3)
    with pytest.raises(OSError, match="断线"):
        C.fetch(1, "probe", "s.sql", ticket, "eid")
    out = C.fetch(1, "probe", "s.sql", ticket, "eid")
    assert calls == [0, 2, 2]
    assert out["page_count"] == 2
    with gzip.open(tmp_path / "raw/dune/probe.csv.gz", "rt", newline="") as f:
        assert list(csv.reader(f)) == [["amt"], ["9007199254740993"], ["2"], ["3"]]


def test_csv_endpoint_decimal_seconds_and_nil_normalize_exactly():
    body = (
        b"t,slot,amt,usr\n1786456126.000000,400000000.000000,9007199254740993,<nil>\n"
    )
    assert C.decode(
        body,
        {},
        ["t", "slot", "amt", "usr"],
        ["bigint", "bigint", "varchar", "varchar"],
    ) == [["1786456126", "400000000", "9007199254740993", ""]]


@pytest.mark.parametrize("text", ["1.5", "NaN", "9007199254740992", "9007199254740993"])
def test_csv_numeric_column_unsafe_or_fractional_value_rejected(text):
    with pytest.raises(ValueError, match="CSV整数"):
        C.decode(("slot\n" + text + "\n").encode(), {}, ["slot"], ["bigint"])


def test_gap_fee_latches_before_next_action(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")
    monkeypatch.setattr(PG, "ACTUAL", tmp_path / "actual.csv")
    PG.record_actual("prior", "eid", 100, 100, 0)
    PG.idle_usage_gate((100, 2500))
    with pytest.raises(PG.Refused, match="非执行费增量"):
        PG.idle_usage_gate((106, 2500))
    assert PG.halt_gate()


def test_latched_csv_command_does_not_mark_or_fetch(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")
    PG.HALT.write_text("{}")
    monkeypatch.setattr(PG, "check", lambda *a: PG.Ticket("next", 0, 3))
    lock = PG.one_at_a_time
    monkeypatch.setattr(PG, "one_at_a_time", lambda t: lock(t, tmp_path / "lock"))
    monkeypatch.setattr(C, "usage", lambda: (106, 2500))
    monkeypatch.setattr(PG, "mark_used", lambda *a: pytest.fail("已封锁仍消耗批准"))
    monkeypatch.setattr(C, "fetch", lambda *a: pytest.fail("已封锁仍下载"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dune_get_csv.py",
            "1",
            "x",
            "s.sql",
            "--execution=eid",
            "--approve=next",
            "--encoding=gzip",
        ],
    )
    with pytest.raises(PG.Refused, match="非执行费增量"):
        C.main()

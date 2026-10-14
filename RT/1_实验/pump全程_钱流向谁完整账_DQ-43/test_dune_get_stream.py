"""下载入口的整数精度：可空列不能经过浮点再写 CSV。"""

import csv
import gzip

import paid_guard as PG
import run_dune as R
import dune_get_stream as S


def test_nullable_integer_csv_is_exact(tmp_path, monkeypatch):
    (tmp_path / "raw" / "dune").mkdir(parents=True)
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(S, "H", tmp_path)
    meta = {"total_row_count": 2, "column_names": ["slot", "x"]}

    def get(path, ticket=None):
        if path == "/query/1":
            return {"query_sql": "SELECT 1"}
        if path == "/query/1/results?limit=1":
            return {"execution_id": "eid"}
        assert path == "/execution/eid/status"
        return {"state": "QUERY_STATE_COMPLETED", "result_metadata": meta}

    monkeypatch.setattr(S, "get", get)
    monkeypatch.setattr(
        S,
        "page",
        lambda *args: [{"slot": 2**63 - 1, "x": 200}, {"slot": None, "x": None}],
    )
    S.fetch("1", "fixture", "s.sql", object())
    with gzip.open(tmp_path / "raw/dune/fixture.csv.gz", "rt") as f:
        assert list(csv.DictReader(f)) == [
            {"slot": "9223372036854775807", "x": "200"},
            {"slot": "", "x": ""},
        ]


def test_authorized_download_reuses_execution_and_records_actual(tmp_path, monkeypatch):
    ticket = PG.Ticket("extra", 0, 3)
    ticket.download_cap = 7.5
    monkeypatch.setattr(PG, "check", lambda *args: ticket)
    lock = PG.one_at_a_time
    monkeypatch.setattr(PG, "one_at_a_time", lambda t: lock(t, tmp_path / "lock"))
    monkeypatch.setattr(PG, "round_gate", lambda *args: "")
    monkeypatch.setattr(PG, "mark_used", lambda *args: None)
    monkeypatch.setattr(PG, "ACTUAL", tmp_path / "actual.csv")
    readings = iter([(100.0, 2500), (106.0, 2500)])
    monkeypatch.setattr(R, "usage", lambda: next(readings))
    paths, downloads = [], []

    def status(path, ticket=None):
        paths.append(path)
        return {
            "state": "QUERY_STATE_COMPLETED",
            "result_metadata": {"result_set_bytes": 2952326},
        }

    monkeypatch.setattr(S, "get", status)
    monkeypatch.setattr(S, "fetch", lambda *args, **kwargs: downloads.append(kwargs))
    monkeypatch.setattr(
        "sys.argv",
        [
            "dune_get_stream.py",
            "1",
            "detail",
            "s.sql",
            "--approve=extra",
            "--execution=eid",
        ],
    )
    S.main()
    assert paths == ["/execution/eid/status"]
    assert downloads == [{"execution_id": "eid"}]
    assert PG._rows(PG.ACTUAL)[0]["合计实耗"] == "6.0"

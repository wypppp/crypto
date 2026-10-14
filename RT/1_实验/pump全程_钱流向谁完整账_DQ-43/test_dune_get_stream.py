"""下载入口的整数精度：可空列不能经过浮点再写 CSV。"""

import csv
import gzip

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

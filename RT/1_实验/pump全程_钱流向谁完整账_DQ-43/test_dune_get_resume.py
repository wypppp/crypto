"""网络中断后只取缺页；身份变化、损坏与截断停止，禁止静默漏页。"""

import csv
import gzip

import pytest

import dune_get_resume as D
import paid_guard as PG


def setup(tmp_path, monkeypatch):
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(D, "H", tmp_path)
    monkeypatch.setattr(D, "PAGE", 2)
    meta = {
        "total_row_count": 3,
        "column_names": ["x"],
        "column_types": ["bigint"],
        "result_set_bytes": 100,
    }
    ticket = PG.Ticket("fixture", 0, 1)
    return meta, ticket


def response(meta, offset):
    rs = [{"x": 2**63 - 1}, {"x": None}] if offset == 0 else [{"x": 1}]
    return {
        "execution_id": "eid",
        "result": {"rows": rs, "metadata": meta},
        "next_offset": 2 if offset == 0 else None,
    }


def test_interrupted_download_resumes_without_repaying_saved_page(
    tmp_path, monkeypatch
):
    meta, ticket = setup(tmp_path, monkeypatch)
    paid = []
    fail = [True]

    def get(path, t=None):
        if path == "/query/1":
            return {"query_sql": "SELECT 1"}
        if path.endswith("/status"):
            return {
                "state": "QUERY_STATE_COMPLETED",
                "query_id": 1,
                "result_metadata": meta,
            }
        assert t is ticket
        offset = int(path.split("offset=")[-1])
        paid.append(offset)
        if offset == 2 and fail[0]:
            raise OSError("网络中断")
        return response(meta, offset)

    monkeypatch.setattr(D, "get", get)
    with pytest.raises(OSError):
        D.fetch("1", "fixture", "s.sql", ticket, "eid")
    fail[0] = False
    D.fetch("1", "fixture", "s.sql", ticket, "eid")
    assert paid == [0, 2, 2]  # 已落盘的 0 页不重下；失败页仅手动恢复一次
    with gzip.open(tmp_path / "raw/dune/fixture.csv.gz", "rt") as f:
        assert list(csv.DictReader(f)) == [
            {"x": "9223372036854775807"},
            {"x": ""},
            {"x": "1"},
        ]
    meta["total_row_count"] = 4
    with pytest.raises(SystemExit, match="恢复身份"):
        D.fetch("1", "fixture", "s.sql", ticket, "eid")


@pytest.mark.parametrize("next_offset", [None, 0, 1, 3])
def test_noncontiguous_or_truncated_page_is_not_committed(
    tmp_path, monkeypatch, next_offset
):
    meta, ticket = setup(tmp_path, monkeypatch)

    def get(path, t=None):
        if path == "/query/1":
            return {"query_sql": "SELECT 1"}
        if path.endswith("/status"):
            return {
                "state": "QUERY_STATE_COMPLETED",
                "query_id": 1,
                "result_metadata": meta,
            }
        r = response(meta, 0)
        r["next_offset"] = next_offset
        return r

    monkeypatch.setattr(D, "get", get)
    with pytest.raises(SystemExit, match="分页游标"):
        D.fetch("1", "fixture", "s.sql", ticket, "eid")
    assert not (tmp_path / "raw/dune/fixture.pages/000000000000.json.gz").exists()

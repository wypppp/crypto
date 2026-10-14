"""下载测价只复用已有执行，持锁观察；上限拦截发生在付费下载前。"""

import json

import pytest

import a8_download_probe as P
import paid_guard as PG


def setup_probe(tmp_path, monkeypatch, mb=2.952326):
    (tmp_path / "runs").mkdir()
    raw = tmp_path / "raw/dune"
    raw.mkdir(parents=True)
    ticket = PG.Ticket("A8-01", 0, 3)
    ticket.download_cap = 15
    monkeypatch.setattr(PG, "H", tmp_path)
    monkeypatch.setattr(PG, "check", lambda *a: ticket)
    monkeypatch.setattr(PG, "round_gate", lambda *a: "")
    lock = PG.one_at_a_time
    monkeypatch.setattr(PG, "one_at_a_time", lambda t: lock(t, tmp_path / "lock"))
    monkeypatch.setattr(PG, "mark_used", lambda *a: None)
    monkeypatch.setattr(PG, "record_actual", lambda *a: None)
    monkeypatch.setattr(
        P,
        "get",
        lambda *a: {
            "state": "QUERY_STATE_COMPLETED",
            "result_metadata": {"result_set_bytes": mb * 1e6},
        },
    )
    return ticket, raw


def test_existing_execution_and_observations_stay_inside_lock(tmp_path, monkeypatch):
    ticket, raw = setup_probe(tmp_path, monkeypatch)
    values = iter([100, 100, 106])

    def usage():
        assert ticket.locked
        return next(values), 2500

    def fetch(qid, label, sql, ap, execution_id):
        assert ticket.locked and execution_id == P.EID and qid == P.QID
        (raw / (label + ".csv.gz")).write_bytes(b"fixture")

    monkeypatch.setattr(P, "usage", usage)
    monkeypatch.setattr(P, "fetch", fetch)
    P.observe(wait_sec=0)
    out = json.loads((tmp_path / "runs/a8_download_probe.json").read_text())
    assert out["immediate_delta"] == 0
    assert out["after_30_min_delta"] == 6
    assert len(out["observations"]) == 3
    assert not ticket.locked


def test_oversize_refuses_before_paid_fetch(tmp_path, monkeypatch):
    setup_probe(tmp_path, monkeypatch, mb=3.01)
    monkeypatch.setattr(P, "usage", lambda: (100, 2500))
    monkeypatch.setattr(P, "fetch", lambda *a, **k: pytest.fail("超限仍下载"))
    with pytest.raises(SystemExit, match="下载上限"):
        P.observe(wait_sec=0)

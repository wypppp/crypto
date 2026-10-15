"""JSON的整数、固定执行、分段结算、CSV禁用与400闸门，纯离线。"""

import datetime as dt
import gzip
import json
from decimal import Decimal

import pytest

import dune_get_json as J
import paid_guard as PG


def test_json_gzip_preserves_large_integer_and_null():
    body = b'{"result":{"rows":[{"amt":"9007199254740993","slot":9007199254740993,"tx":null}]}}'
    page, n = J.decode(gzip.compress(body), {"content-encoding": "gzip"})
    assert n == len(body)
    assert J.normalize(
        page["result"]["rows"], ["amt", "slot", "tx"], ["varchar", "bigint", "varchar"]
    ) == [["9007199254740993", "9007199254740993", None]]


@pytest.mark.parametrize(
    "path",
    [
        "/execution/e/results/csv?limit=1",
        "/query/1/results/csv",
        "/execution/e/results%2Fcsv?limit=1",
    ],
)
def test_csv_disabled_before_any_network(monkeypatch, tmp_path, path):
    monkeypatch.setattr(PG, "_key", lambda: pytest.fail("CSV不该读取凭证并发送请求"))
    with pytest.raises(PG.Refused, match="CSV导出禁用"):
        PG.request("GET", path)
    with pytest.raises(PG.Refused, match="CSV导出禁用"):
        PG.request_bytes(path, PG.Ticket("x", 0, 3), tmp_path / "body")


def test_delay_wait_uses_monotonic_and_latches_increment(monkeypatch, tmp_path):
    tick = [0]
    monkeypatch.setattr(J.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(J.time, "sleep", lambda s: tick.__setitem__(0, tick[0] + s))
    monkeypatch.setattr(J, "usage", lambda: (100 if tick[0] < 20 else 106, 2500))
    with pytest.raises(PG.Refused, match="非执行费增量"):
        J.observe((100, 2500), "late", tmp_path / "observe.json", 120)
    assert tick[0] == 20 and PG.HALT.exists()


def test_wait_without_increment_and_execution_settlement(monkeypatch, tmp_path):
    tick = [0]
    monkeypatch.setattr(J.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(J.time, "sleep", lambda s: tick.__setitem__(0, tick[0] + s))
    monkeypatch.setattr(J, "usage", lambda: (100, 2500))
    after, out = J.observe((100, 2500), "zero", tmp_path / "zero.json", 120)
    assert after == (100, 2500) and out["observations"][-1]["elapsed_seconds"] >= 120
    monkeypatch.setattr(J, "usage", lambda: (103.433, 2500))
    assert (
        J.observe(
            (100, 2500), "execution", tmp_path / "exec.json", 0, Decimal("3.433088236")
        )[0][0]
        == 103.433
    )


def policy(tmp_path):
    today = dt.datetime.now(dt.UTC).date()
    p = {
        "period_start": str(today),
        "period_end": str(today + dt.timedelta(days=14)),
        "baseline_used": 100,
        "limit_credits": 400,
        "gpt_review_passed": False,
        "reviewed_trial_sql_sha256": [],
        "settlement_wait_seconds": 0,
    }
    PG.S3_POLICY.write_text(json.dumps(p))
    return p


def test_400_limit_and_review_condition_before_execution(tmp_path):
    p = policy(tmp_path)
    assert PG.s3_period_gate((492, 2500), 8) == ""
    assert "超过400" in PG.s3_period_gate((492.001, 2500), 8)
    t = PG.Ticket("A10-01", 8, 3)
    t.source = "总控第十轮"
    t.sql_sha = "ok"
    with pytest.raises(PG.Refused, match="复审尚未通过"):
        PG.execution_review_gate(t)
    p.update(gpt_review_passed=True, reviewed_trial_sql_sha256=["ok"])
    PG.S3_POLICY.write_text(json.dumps(p))
    PG.execution_review_gate(t)
    t.sql_sha = "changed"
    with pytest.raises(PG.Refused, match="清单"):
        PG.execution_review_gate(t)


def test_bad_cursor_and_identity_rejected():
    identity = {
        "execution_id": "eid",
        "query_id": "1",
        "rows": 2,
        "cols": ["x"],
        "types": ["bigint"],
    }
    page = {
        "execution_id": "eid",
        "query_id": 1,
        "state": "QUERY_STATE_COMPLETED",
        "result": {
            "metadata": {"total_row_count": 2, "column_names": ["x"]},
            "rows": [{"x": 1}],
        },
        "next_offset": 9,
    }
    with pytest.raises(ValueError, match="游标"):
        J.validate(page, identity, 0)
    page["execution_id"] = "other"
    with pytest.raises(ValueError, match="身份"):
        J.validate(page, identity, 0)


def test_segment_checkpoint_before_next_page_and_cache_resume(monkeypatch, tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(J, "H", tmp_path)
    monkeypatch.setattr(J, "PAGE", 1)
    monkeypatch.setattr(J, "SEGMENT_CAP", 10)
    monkeypatch.setattr(J, "PAGE_WIRE_CAP", 6)
    monkeypatch.setattr(J, "usage", lambda: (100, 2500))
    monkeypatch.setattr(PG, "idle_usage_gate", lambda *a: None)
    st = {
        "query_id": 1,
        "state": "QUERY_STATE_COMPLETED",
        "result_metadata": {
            "total_row_count": 2,
            "column_names": ["x"],
            "column_types": ["bigint"],
            "result_set_bytes": 2,
        },
    }
    monkeypatch.setattr(
        J, "get", lambda p: {"query_sql": "SELECT 1"} if p.startswith("/query") else st
    )
    calls = []
    fail = [True]

    def request(path, ticket, destination, encoding, max_bytes):
        off = int(path.rsplit("=", 1)[-1])
        calls.append(("download", off))
        if off == 1 and fail[0]:
            fail[0] = False
            raise OSError("断线")
        result = {
            "execution_id": "eid",
            "query_id": 1,
            "state": "QUERY_STATE_COMPLETED",
            "result": {
                "metadata": {"total_row_count": 2, "column_names": ["x"]},
                "rows": [{"x": off + 1}],
            },
        }
        if off == 0:
            result["next_offset"] = 1
        destination.write_bytes(json.dumps(result).encode())
        return {"wire_bytes": 6}

    def observe(before, label, path, wait_sec):
        calls.append(("checkpoint", None))
        return before, {"wait_seconds": 0}

    monkeypatch.setattr(PG, "request_bytes", request)
    monkeypatch.setattr(J, "observe", observe)
    # 测试的小字节上限只控制传输段，JSON解码上限仍用真实20MB。
    real_decode = J.decode

    def decode(body, headers):
        old = J.SEGMENT_CAP
        J.SEGMENT_CAP = 20_000_000
        try:
            return real_decode(body, headers)
        finally:
            J.SEGMENT_CAP = old

    monkeypatch.setattr(J, "decode", decode)
    with pytest.raises(OSError, match="断线"):
        J.fetch(1, "probe", "s.sql", PG.Ticket("x", 0, 3), "eid", wait_sec=0)
    assert calls == [
        ("download", 0),
        ("checkpoint", None),
        ("download", 1),
        ("checkpoint", None),
    ]
    calls.clear()
    result = J.fetch(1, "probe", "s.sql", PG.Ticket("x", 0, 3), "eid", wait_sec=0)
    assert (
        calls == [("download", 1), ("checkpoint", None)] and result["page_count"] == 2
    )

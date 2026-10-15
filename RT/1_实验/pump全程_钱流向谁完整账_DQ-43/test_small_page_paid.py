"""用户批准小页平台验收后的费用、来源、绑定及分开下载保护。"""

import datetime as dt
import gzip
import json
from decimal import Decimal

import pytest

import dune_get_json as J
import paid_guard as PG
import run_dune as R
from test_run_dune_gate import _csv, _round_files, runner_fixture

SOURCE = "用户小页试跑（2026-10-15继续推进）"


def policy():
    today = dt.datetime.now(dt.UTC).date()
    p = {
        "active_paid_source_prefix": "用户小页试跑",
        "gpt_review_passed": True,
        "reviewed_trial_sql_sha256": ["sha"],
        "period_start": str(today),
        "period_end": str(today + dt.timedelta(days=14)),
        "baseline_used": 100,
        "limit_credits": 400,
        "settlement_wait_seconds": 120,
        "download_bindings": {},
    }
    PG.S3_POLICY.write_text(json.dumps(p))
    return p


def ticket():
    t = PG.Ticket("D1", 0, 0.2002)
    t.source = SOURCE
    t.sql_sha = "sha"
    t.download_cap = 0.8008
    t.locked = True
    return t


def bind(p, t):
    p["download_bindings"][t.approval] = {
        "query_id": "1",
        "execution_id": "eid",
        "sql_sha256": t.sql_sha,
        "metadata_bytes": 200200,
        "expected_credits": "0.4004",
        "page_rows": 1000,
    }
    PG.S3_POLICY.write_text(json.dumps(p))


def test_old_source_and_unreviewed_sql_cannot_execute(monkeypatch):
    policy()
    t = PG.Ticket("X1", 4, 0)
    t.sql_sha, t.source, t.download_cap = "sha", SOURCE, 0
    PG.execution_review_gate(t)
    t.sql_sha = "different"
    with pytest.raises(PG.Refused, match="清单"):
        PG.execution_review_gate(t)
    t.source = "总控第十轮"
    t.locked = True
    monkeypatch.setattr(PG, "_key", lambda: pytest.fail("旧来源不该读密钥"))
    with pytest.raises(PG.Refused, match="现行来源"):
        PG.request("POST", "/query/1/execute", ticket=t)


def test_small_source_round_limit_25_includes_execution_and_download(tmp_path):
    paths = _round_files(tmp_path, {"old1": "17", "old2": "900"})
    rows = PG._rows(paths[0])
    for row in rows:
        if row["编号"] in ("old1", "next"):
            row.update({"批准来源": SOURCE, "执行费上限": "4", "下载费上限": "4"})
    _csv(paths[0], PG.FIELDS, [[r.get(f, "") for f in PG.FIELDS] for r in rows])
    assert PG.round_gate("next", *paths) == ""
    _csv(paths[2], ["编号", "合计实耗"], [["old1", "17.001"], ["old2", "900"]])
    assert "超过 25" in PG.round_gate("next", *paths)


def test_registered_download_allowance_and_unknown_gap_are_separate():
    PG.check_download_usage((100, 2500), (100.4, 2500), "page", expected=Decimal("0.4"))
    assert not PG.HALT.exists()
    with pytest.raises(PG.Refused, match="超预计"):
        PG.check_download_usage(
            (100, 2500), (100.401, 2500), "late", expected=Decimal("0.4")
        )
    assert json.loads(PG.HALT.read_text())["expected_credits"] == "0.4"


@pytest.mark.parametrize(
    "path",
    [
        "/execution/other/results?limit=1000&offset=0",
        "/execution/eid/results?limit=5000&offset=0",
        "/execution/eid/results?limit=1000&offset=0&allow_partial_results=true",
    ],
)
def test_download_binding_refuses_wrong_execution_limit_and_partial(
    monkeypatch, tmp_path, path
):
    p, t = policy(), ticket()
    bind(p, t)
    monkeypatch.setattr(PG, "_key", lambda: pytest.fail("错误绑定不该发请求"))
    with pytest.raises(PG.Refused):
        PG.request_bytes(path, t, tmp_path / "body")


def test_query_binding_and_fee_budget_are_not_optional():
    p, t = policy(), ticket()
    bind(p, t)
    with pytest.raises(PG.Refused, match="查询号"):
        PG.small_download_binding(t, qid="2")
    t.download_cap = 0
    with pytest.raises(PG.Refused, match="2/MB"):
        PG.small_download_binding(t)


def test_small_fetch_1000_rows_exact_bytes_cached_and_delayed_settlement(
    monkeypatch, tmp_path
):
    (tmp_path / "runs").mkdir()
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(J, "H", tmp_path)
    p, t = policy(), ticket()
    t.sql_sha = PG.sha(tmp_path / "s.sql")
    bind(p, t)
    monkeypatch.setattr(PG, "idle_usage_gate", lambda *a: None)
    monkeypatch.setattr(J, "usage", lambda: (100, 2500))
    tick = [0]
    monkeypatch.setattr(J.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(J.time, "sleep", lambda s: tick.__setitem__(0, tick[0] + s))
    st = {
        "query_id": 1,
        "state": "QUERY_STATE_COMPLETED",
        "result_metadata": {
            "total_row_count": 1001,
            "column_names": ["x"],
            "column_types": ["bigint"],
            "result_set_bytes": 200200,
        },
    }
    monkeypatch.setattr(
        J,
        "get",
        lambda path: {"query_sql": "SELECT 1"} if path.startswith("/query") else st,
    )
    calls = []

    def download(path, _ticket, destination, encoding, max_bytes):
        assert "limit=1000&offset=" in path
        offset = int(path.rsplit("=", 1)[-1])
        calls.append(offset)
        n = min(1000, 1001 - offset)
        page = {
            "execution_id": "eid",
            "query_id": 1,
            "state": "QUERY_STATE_COMPLETED",
            "result": {
                "metadata": {
                    "total_row_count": 1001,
                    "column_names": ["x"],
                    "result_set_bytes": n * 200,
                },
                "rows": [{"x": i} for i in range(offset, offset + n)],
            },
        }
        if offset + n < 1001:
            page["next_offset"] = offset + n
        body = gzip.compress(json.dumps(page).encode())
        destination.write_bytes(body)
        return {"wire_bytes": len(body), "content-encoding": "gzip"}

    monkeypatch.setattr(PG, "request_bytes", download)
    out = J.fetch("1", "small", "s.sql", t, "eid")
    assert calls == [0, 1000] and out["page_rows"] == 1000
    assert tick[0] >= 120 and out["download_did_not_execute_sql"]
    calls.clear()
    J.fetch("1", "small", "s.sql", t, "eid")
    assert calls == []  # 恢复只核缓存，不能为已核页再付钱。


def test_execute_consumes_approval_before_submit_and_never_downloads(
    monkeypatch, tmp_path
):
    t = runner_fixture(tmp_path, monkeypatch)
    t.source, t.download_cap, t["max_mb"], t.sql_sha = SOURCE, 0, 0, "sha"
    policy()
    events, current = [], [100]
    monkeypatch.setattr(R, "usage", lambda: (current[0], 2500))
    monkeypatch.setattr(PG, "mark_used", lambda *a: events.append("consumed"))

    def call(method, path, body, ticket=None):
        if path == "/query":
            return {"query_id": 1}
        assert events == ["consumed"]
        events.append("submitted")
        return {"execution_id": "eid"}

    def settled(*args):
        events.append("settled")
        current[0] = 101
        return (101, 2500)

    monkeypatch.setattr(R, "call", call)
    monkeypatch.setattr(
        R,
        "get",
        lambda *a: {
            "state": "QUERY_STATE_COMPLETED",
            "execution_cost_credits": 1,
            "result_metadata": {"total_row_count": 2},
        },
    )
    monkeypatch.setattr(J, "settle_execution", settled)
    monkeypatch.setattr(J, "fetch", lambda *a: pytest.fail("执行不该自动下载"))
    monkeypatch.setattr(R, "fetch", lambda *a: pytest.fail("不该调用旧下载"))
    R.main()
    assert events == ["consumed", "submitted", "settled"]
    assert (
        json.loads((tmp_path / "runs/fixture_completed.json").read_text())["downloaded"]
        is False
    )


def test_unknown_submission_latches_halt_and_keeps_cost_unknown(monkeypatch, tmp_path):
    from urllib.error import HTTPError

    t = runner_fixture(tmp_path, monkeypatch)
    t.source, t.download_cap, t["max_mb"], t.sql_sha = SOURCE, 0, 0, "sha"
    policy()
    events = []
    monkeypatch.setattr(R, "usage", lambda: (100, 2500))
    monkeypatch.setattr(PG, "mark_used", lambda *a: events.append("consumed"))

    def call(method, path, body, ticket=None):
        if path == "/query":
            return {"query_id": 1}
        assert events == ["consumed"]
        events.append("submitted")
        raise HTTPError("unused", 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(R, "call", call)
    with pytest.raises(HTTPError):
        R.main()
    assert events == ["consumed", "submitted"]  # 不重试，不接着提交下一条。
    assert json.loads(PG.HALT.read_text())["http_status"] == 500
    assert "执行提交未返回执行号" in PG.halt_gate()
    assert PG._rows(PG.ACTUAL)[-1]["合计实耗"] == ""
    assert (tmp_path / "runs/fixture_submission_unknown.json").exists()


@pytest.mark.parametrize("sql", ["SELECT 1", "SELECT 2"])
def test_reuse_checks_exact_sql_and_never_creates_query(monkeypatch, tmp_path, sql):
    import sys
    from urllib.error import HTTPError

    t = runner_fixture(tmp_path, monkeypatch)
    t.source, t.download_cap, t["max_mb"], t.sql_sha = SOURCE, 0, 0, "sha"
    policy()
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--query-id=123"])
    monkeypatch.setattr(R, "get", lambda p: {"query_sql": sql})
    calls = []

    def call(method, path, body, ticket=None):
        calls.append(path)
        assert path == "/query/123/execute"
        raise HTTPError("unused", 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(R, "call", call)
    with pytest.raises(HTTPError if sql == "SELECT 1" else PG.Refused):
        R.main()
    assert calls == (["/query/123/execute"] if sql == "SELECT 1" else [])


def test_download_sql_comparison_preserves_whitespace_inside_literal(
    monkeypatch, tmp_path
):
    (tmp_path / "s.sql").write_text("SELECT 'a b'")
    monkeypatch.setattr(J, "H", tmp_path)
    monkeypatch.setattr(J, "get", lambda p: {"query_sql": "SELECT 'ab'"})
    with pytest.raises(ValueError, match="远端SQL与批准不同"):
        J.fetch("1", "unused", "s.sql", PG.Ticket("old", 0, 1), "eid")

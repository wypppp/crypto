"""全量分段预算、原 SQL 派生、完整种子与集中度边界。"""

import csv
import datetime as dt
import json
from decimal import Decimal

import a14_full as F
import paid_guard as PG
import pytest

import run_dune as RUN  # isort: skip -- before legacy graph imports
from test_edge_sgt_integer import integer_db
from test_edge_sgt_v6 import exported, sql
from test_wm2_semantic import coin, trade, xfer


def test_generated_service_reduction_keeps_all_wallet_representatives():
    import s3_ref as REF

    data = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", dt.datetime(2026, 8, 11))],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            trade("m", u, 12) for u in ("h", "b", "c")
        ],
        "tokens_solana.transfers": [
            xfer("h", u, 12) for u in ["b", "c"] + [f"n{i}" for i in range(199)]
        ]
        + [xfer("a_nonseed_min", "b", 12), xfer("a_nonseed_min", "c", 12)],
    }
    con = integer_db(data)
    original = exported(con, F.with_seeds(sql()))
    reduced = exported(con, F.without_service_nodes(sql()))
    ref = F.service_reduction_reference(original)
    assert sorted(tuple(r.values()) for r in reduced) == sorted(
        tuple(r.values()) for r in ref
    )
    edges = lambda rs: [r for r in rs if r["kind"] != "V"]
    full_map = REF.entities(edges(original))[0]
    assert full_map == REF.entities(edges(reduced))[0]
    assert full_map["b"] == full_map["c"] == "a_nonseed_min"
    assert "a_nonseed_min" in full_map


def test_service_hubs_are_per_class_and_cex_and_g_stay_identical():
    import s3_ref as REF

    rows = [{"kind": "S", "a": "h", "b": f"n{i}", "x": None} for i in range(201)] + [
        {"kind": "T", "a": "h", "b": "a", "x": None},
        {"kind": "S", "a": "cex", "b": "a", "x": None},
        {"kind": "S", "a": "b", "b": "a", "x": None},
        {"kind": "G", "a": "f", "b": "b", "x": 200},
        {"kind": "G", "a": "f", "b": "c", "x": 200},
        {"kind": "G", "a": "bad", "b": "d", "x": 201},
        {"kind": "G", "a": "bad", "b": "a", "x": 201},
    ]
    reduced = F.service_reduction_reference(rows)
    assert len(reduced) == 7
    full_map = REF.entities(rows, {"cex"})[0]
    assert (
        full_map
        == REF.entities(reduced, {"cex"})[0]
        == {"a": "a", "b": "a", "c": "a", "h": "a"}
    )


def test_export_keeps_edges_and_includes_isolated_seeds_before_cut():
    day = dt.datetime(2026, 8, 11)
    late = trade("m", "future", 18)
    data = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", day)],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            trade("m", u, 12) for u in ("a", "b", "isolated")
        ]
        + [late],
        "tokens_solana.transfers": [xfer("bridge", "a", 12), xfer("bridge", "b", 12)],
    }
    original = sql()
    con = integer_db(data)
    old = exported(con, original)
    new = exported(con, F.with_seeds(original))
    assert [r for r in new if r["kind"] != "V"] == old
    seeds = {r["a"] for r in new if r["kind"] == "V"}
    assert {"a", "b", "isolated"} <= seeds
    assert "future" not in seeds
    assert len(seeds) == len([r for r in new if r["kind"] == "V"])
    assert original[: -len(F.EDGE_END)] in F.with_seeds(original)


def graph(groups):
    rows = [{"kind": "V", "a": f"s{i:04}", "b": None, "x": None} for i in range(100)]
    offset = 0
    for size in groups:
        rows += [
            {"kind": "S", "a": f"s{offset:04}", "b": f"s{i:04}", "x": None}
            for i in range(offset + 1, offset + size)
        ]
        offset += size
    return rows


def test_entity_thresholds_use_W_seeds_include_isolates_and_allow_equality():
    result = F.concentration(graph([5, 2]))
    assert result["W_seed_wallets"] == 100
    assert result["top10_W_seed_wallets"] == [5, 2] + [1] * 8
    assert result["concentration_passed"]
    assert result["multiwallet_size_histogram_with_W_seeds"] == {5: 1, 2: 1}
    assert not F.concentration(graph([6]))["concentration_passed"]
    assert not F.concentration(graph([5, 3]))["concentration_passed"]


def test_nonseed_component_members_do_not_inflate_seed_fraction():
    rows = graph([]) + [
        {"kind": "S", "a": "s0000", "b": f"leaf{i}", "x": None} for i in range(200)
    ]
    result = F.concentration(rows)
    assert result["largest_entity_W_seed_fraction"] == 0.01
    assert result["multiwallet_size_histogram_with_W_seeds"] == {201: 1}
    with pytest.raises(ValueError, match="缺少"):
        F.concentration(rows[100:])
    with pytest.raises(ValueError, match="重复"):
        F.concentration(rows + [rows[0]])


def test_metadata_threshold_is_inclusive_and_requires_integers():
    result = F.metadata_gate({"row_count": 10_000_000, "result_set_bytes": 900_000_000})
    assert result["download_allowed_by_row_gate"]
    assert result["pages_1000"] == 10_000
    assert not F.metadata_gate({"row_count": 10_000_001, "result_set_bytes": 1})[
        "download_allowed_by_row_gate"
    ]
    for n in (None, True, -1, 0, "100"):
        with pytest.raises(ValueError):
            F.metadata_gate({"row_count": n, "result_set_bytes": 10})


def write_csv(path, fields, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_round14_uses_actuals_and_next_cap_not_unspent_approvals(tmp_path):
    approvals, used, actual = (tmp_path / s for s in ("a.csv", "u.csv", "c.csv"))
    write_csv(
        approvals,
        ["编号", "批准来源", "执行费上限", "下载费上限"],
        [
            {"编号": k, "批准来源": "总控第十四轮", "执行费上限": cap, "下载费上限": 0}
            for k, cap in (("done", 134), ("next", 84), ("unused", 134))
        ]
        + [{"编号": "old", "批准来源": "用户小页试跑", "执行费上限": 5}],
    )
    write_csv(used, ["编号"], [{"编号": "done"}, {"编号": "old"}])
    write_csv(actual, ["编号", "合计实耗"], [{"编号": "done", "合计实耗": 296}])
    assert not PG.round_gate("next", approvals, used, actual)
    write_csv(actual, ["编号", "合计实耗"], [{"编号": "done", "合计实耗": "296.001"}])
    assert "380" in PG.round_gate("next", approvals, used, actual)
    actual.unlink()
    assert "未核清" in PG.round_gate("next", approvals, used, actual)


def test_expected_cap_stop_threshold_and_stage_binding(monkeypatch):
    assert RUN.cancel_threshold(134, 67) == Decimal("100.5")
    for expected, cap in ((0, 0), (None, 134), ("NaN", 134), (67, 135)):
        with pytest.raises(ValueError):
            F.expected_gate(expected, cap)
    t = PG.Ticket("A14-E03", 134, 0)
    t.source, t.sql_sha, t.download_cap, t.expected = "总控第十四轮", "abc", 0, "67"
    PG.S3_POLICY.write_text(
        json.dumps(
            {
                "active_paid_source_prefix": "总控第十四轮",
                "gpt_review_passed": True,
                "full_approved": True,
                "full_execution_sql_sha256": ["abc"],
                "allowed_execution_approvals": ["A14-E03"],
            }
        )
    )
    PG.execution_review_gate(t)
    t.approval = "A14-F03"
    with pytest.raises(PG.Refused, match="分段"):
        PG.execution_review_gate(t)


def test_full_execution_terminal_overrun_latches_halt(monkeypatch, tmp_path):
    import dune_get_json as J
    from test_run_dune_gate import runner_fixture

    t = runner_fixture(tmp_path, monkeypatch)
    t.source, t.download_cap, t["max_mb"], t.sql_sha = "总控第十四轮", 0, 0, "sha"
    t.expected = "5"
    PG.S3_POLICY.write_text(
        json.dumps(
            {
                "active_paid_source_prefix": t.source,
                "gpt_review_passed": True,
                "full_approved": True,
                "allowed_execution_approvals": ["next"],
                "full_execution_sql_sha256": ["sha"],
                "period_start": "2026-01-01",
                "period_end": "2100-01-01",
                "baseline_used": 100,
                "limit_credits": 400,
            }
        )
    )
    current = [100]
    monkeypatch.setattr(RUN, "usage", lambda: (current[0], 2500))
    monkeypatch.setattr(
        RUN,
        "call",
        lambda m, p, b, t=None: (
            {"query_id": 1} if p == "/query" else {"execution_id": "eid"}
        ),
    )
    monkeypatch.setattr(
        RUN,
        "get",
        lambda *_: {"state": "QUERY_STATE_COMPLETED", "execution_cost_credits": 8},
    )
    monkeypatch.setattr(J, "settle_execution", lambda *_: current.__setitem__(0, 108))
    monkeypatch.setattr(RUN, "fetch", lambda *_: pytest.fail("不得自动下载"))
    RUN.main()
    assert "1.5倍" in PG.halt_gate()
    assert PG._rows(PG.ACTUAL)[-1]["下载费"] == "0"

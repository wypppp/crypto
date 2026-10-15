"""付费查询的闸门与批准（10-14，总控第六轮）：手算用例。"""

import csv

import pytest

import paid_guard as PG
import run_dune as R


def test_budget_gate_uses_live_usage_only_hand():
    assert R.budget_gate(None, 10) != ""  # 读不到即停
    assert R.budget_gate((1468.8, 2500.0), 1031.2) == ""  # 恰好用满额度
    assert R.budget_gate((1468.8, 2500.0), 1031.3) != ""
    assert R.budget_gate((0.0, 2500.0), 2600.0) != ""
    assert R.budget_gate((float("nan"), 2500), 10)
    assert R.budget_gate((100, 2500), float("inf"))


def _approvals(tmp_path, sql_rel, sha):
    p = tmp_path / "批准.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(PG.FIELDS)
        w.writerow(
            ["A1", "2026-10-14", "review原文", sql_rel, sha, "5", "1", "试跑", "7.5"]
        )
    return p


def test_approval_required_sha_bound_and_single_use(tmp_path):
    sql_rel = "sql/WM2AGG_COIN_SMK3_20260812.sql"
    good = PG.sha(PG.H / sql_rel)
    ap, used = _approvals(tmp_path, sql_rel, good), tmp_path / "已用.csv"
    assert PG.check("A1", sql_rel, ap, used) == {"cap": 5.0, "max_mb": 1.0}
    with pytest.raises(SystemExit):
        PG.check("A2", sql_rel, ap, used)  # 没有这条批准
    with pytest.raises(SystemExit):
        PG.check("A1", "sql/WM2AGG_COIN_SMK_20260812.sql", ap, used)  # 批准的是别的文件
    bad = _approvals(tmp_path, sql_rel, "0" * 64)
    with pytest.raises(SystemExit):
        PG.check("A1", sql_rel, bad, used)  # 内容与批准时不一致
    PG.mark_used("A1", "eid", 1.0, used)
    with pytest.raises(SystemExit):
        PG.check("A1", sql_rel, ap, used)  # 一条批准只用一次


def test_one_paid_query_at_a_time(tmp_path):
    lock = tmp_path / "lock"
    with PG.one_at_a_time(lock):
        with pytest.raises(SystemExit):
            with PG.one_at_a_time(lock):
                pass
    with PG.one_at_a_time(lock):  # 释放后可以再拿
        pass


def test_runner_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["run_dune.py", "x", "sql/WM2AGG_COIN_SMK3_20260812.sql"]
    )
    with pytest.raises(SystemExit) as e:
        R.main()
    assert "approve" in str(e.value)


def _csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)
    return path


def _round_files(tmp_path, totals):
    approvals = _csv(
        tmp_path / "批准.csv",
        PG.FIELDS,
        [
            [k, "2026-10-14", src, "s.sql", "", "10", "2", "试跑", "1"]
            for k, src in (
                ("old1", "总控第七轮（原文）"),
                ("old2", "总控第七轮"),
                ("other", "总控第六轮"),
                ("next", "总控第七轮（原文）"),
            )
        ],
    )
    used = _csv(tmp_path / "已用.csv", ["编号"], [[k] for k in totals])
    actual = _csv(tmp_path / "实耗.csv", ["编号", "合计实耗"], list(totals.items()))
    return approvals, used, actual


def test_round_budget_hand_includes_download_and_excludes_other_sources(tmp_path):
    # 20＋15＋本条(10＋5)＝50，可以跑；别轮 900 不计入。
    paths = _round_files(tmp_path, {"old1": "20", "old2": "15", "other": "900"})
    assert PG.round_gate("next", *paths) == ""
    paths = _round_files(tmp_path, {"old1": "20.001", "old2": "15"})
    assert "超过 50" in PG.round_gate("next", *paths)
    assert PG.round_gate("other", *paths) == ""


def test_user_extra_download_cap_hand(tmp_path):
    paths = _round_files(tmp_path, {"old1": "42.5"})
    rows = PG._rows(paths[0])
    for row in rows:
        if row["编号"] == "next":
            row.update({"执行费上限": "0", "下载上限MB": "3", "下载费上限": "7.5"})
    with paths[0].open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PG.FIELDS)
        w.writeheader()
        w.writerows(rows)
    assert PG.round_gate("next", *paths) == ""  # 42.5＋7.5＝50
    _csv(paths[2], ["编号", "合计实耗"], [["old1", "42.501"]])
    assert "超过 50" in PG.round_gate("next", *paths)


def test_round_eight_separate_from_seven_and_includes_download(tmp_path):
    paths = _round_files(tmp_path, {"old1": "49", "old2": "36"})
    rows = PG._rows(paths[0])
    for row in rows:
        if row["编号"] in ("old2", "next"):
            row["批准来源"] = "总控第八轮（续）"
    with paths[0].open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PG.FIELDS)
        w.writeheader()
        w.writerows(rows)
    assert "超过 50" in PG.round_gate("next", *paths)  # 36＋10＋5
    _csv(paths[2], ["编号", "合计实耗"], [["old1", "49"], ["old2", "35"]])
    assert PG.round_gate("next", *paths) == ""  # 第七轮的 49 不计入第八轮


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "-1", "执行中"])
def test_round_budget_refuses_unresolved_actual(tmp_path, value):
    paths = _round_files(tmp_path, {"old1": value})
    assert "实耗未核清" in PG.round_gate("next", *paths)
    paths[2].unlink()
    assert "实耗未核清" in PG.round_gate("next", *paths)


def test_actual_usage_includes_failed_execution_and_download_hand(tmp_path):
    p = tmp_path / "实耗.csv"
    # 执行 3＋下载 2.5；另一条已取消仍扣 4，两条都要累计。
    PG.record_actual("old1", "completed", 100, 105.5, 3, p)
    PG.record_actual("old2", "cancelled", 105.5, 109.5, 4, p)
    rows = PG._rows(p)
    assert rows[0]["合计实耗"] == "5.5"
    assert rows[0]["下载费"] == "2.5"
    assert rows[1]["合计实耗"] == "4.0"
    PG.record_actual("missing", "eid", 109.5, None, 2, p)
    assert PG._rows(p)[-1]["合计实耗"] == ""


def test_runner_round_gate_refuses_before_any_query_request(tmp_path, monkeypatch):
    paths = _round_files(tmp_path, {"old1": "36"})
    ap, used, actual = paths
    monkeypatch.setattr(PG, "APPROVALS", ap)
    monkeypatch.setattr(PG, "USED", used)
    monkeypatch.setattr(PG, "ACTUAL", actual)
    monkeypatch.setattr(PG, "check", lambda *args: PG.Ticket("next", 10, 2))
    lock = PG.one_at_a_time
    monkeypatch.setattr(
        PG, "one_at_a_time", lambda ticket: lock(ticket, tmp_path / "lock")
    )
    monkeypatch.setattr(R, "usage", lambda: (100, 2500))

    def request_forbidden(*args, **kwargs):
        pytest.fail("超过本轮总额仍创建或提交了查询")

    monkeypatch.setattr(R, "call", request_forbidden)
    monkeypatch.setattr("sys.argv", ["run_dune.py", "x", "s.sql", "--approve=next"])
    with pytest.raises(SystemExit, match="超过 50"):
        R.main()


def runner_fixture(tmp_path, monkeypatch):
    (tmp_path / "runs").mkdir()
    (tmp_path / "s.sql").write_text("SELECT 1")
    monkeypatch.setattr(R, "H", tmp_path)
    monkeypatch.setattr(R, "STATES", tmp_path / "runs/states.csv")
    monkeypatch.setattr(PG, "APPROVALS", tmp_path / "approvals.csv")
    monkeypatch.setattr(PG, "ACTUAL", tmp_path / "actual.csv")
    ticket = PG.Ticket("next", 10, 2)
    monkeypatch.setattr(PG, "check", lambda *a: ticket)
    lock = PG.one_at_a_time
    monkeypatch.setattr(PG, "one_at_a_time", lambda t: lock(t, tmp_path / "lock"))
    monkeypatch.setattr(PG, "round_gate", lambda *a: "")
    monkeypatch.setattr(PG, "mark_used", lambda *a: None)
    monkeypatch.setattr(R, "usage", lambda: (100, 2500))
    monkeypatch.setattr(R.time, "sleep", lambda *a: None)
    monkeypatch.setattr(
        "sys.argv", ["run_dune.py", "fixture", "s.sql", "--approve=next"]
    )
    return ticket


def test_runner_skips_paired_cost_cancel_before_usage_or_query(tmp_path, monkeypatch):
    runner_fixture(tmp_path, monkeypatch)
    _csv(
        PG.APPROVALS,
        ["编号", "双跑组", "SQL_sha256"],
        [["first", "pair", "sha"], ["next", "pair", "sha"]],
    )
    R.execution_state("first", "eid1", "QUERY_STATE_CANCELLED", "费用取消")

    def forbidden(*a, **k):
        pytest.fail("费用取消后配对条仍访问了 Dune")

    monkeypatch.setattr(R, "usage", forbidden)
    monkeypatch.setattr(R, "call", forbidden)
    with pytest.raises(SystemExit, match="自动跳过"):
        R.main()
    assert PG._rows(R.STATES)[-1]["平台状态"] == "SKIPPED"


def test_85_percent_requests_cancel_once_and_waits_for_terminal(tmp_path, monkeypatch):
    runner_fixture(tmp_path, monkeypatch)
    calls = []

    def call(method, path, body, ticket=None):
        calls.append(path)
        if path == "/query":
            return {"query_id": 1}
        if path.endswith("/execute"):
            return {"execution_id": "eid"}
        assert path == "/execution/eid/cancel"
        return {}

    statuses = iter(
        [
            {"state": "QUERY_STATE_EXECUTING", "execution_cost_credits": 8.49},
            {"state": "QUERY_STATE_EXECUTING", "execution_cost_credits": 8.5},
            {"state": "QUERY_STATE_EXECUTING", "execution_cost_credits": 8.7},
            {"state": "QUERY_STATE_CANCELLED", "execution_cost_credits": 8.8},
        ]
    )
    monkeypatch.setattr(R, "call", call)
    monkeypatch.setattr(R, "get", lambda *a: next(statuses))
    monkeypatch.setattr(R, "fetch", lambda *a: pytest.fail("取消查询仍下载"))
    with pytest.raises(SystemExit):
        R.main()
    assert calls.count("/execution/eid/cancel") == 1
    assert PG._rows(R.STATES)[-1]["原因"] == "费用取消"
    assert PG._rows(PG.ACTUAL)[0]["合计实耗"] == ""  # 未核清增量，下一条须拒绝


def test_threshold_hand():
    assert R.cancel_threshold(10) == 8.5
    assert R.cancel_threshold(14.95) == __import__("decimal").Decimal("12.7075")


def test_round_nine_25_and_zero_download_fee(tmp_path):
    paths = _round_files(tmp_path, {"old1": "17", "old2": "900"})
    rows = PG._rows(paths[0])
    for row in rows:
        if row["编号"] in ("old1", "next"):
            row.update({"批准来源": "总控第九轮", "执行费上限": "8", "下载费上限": "0"})
    with paths[0].open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PG.FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    assert PG.round_gate("next", *paths) == ""  # 17+8=25，别轮900不计
    _csv(paths[2], ["编号", "合计实耗"], [["old1", "17.001"], ["old2", "900"]])
    assert "超过 25" in PG.round_gate("next", *paths)

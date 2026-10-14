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

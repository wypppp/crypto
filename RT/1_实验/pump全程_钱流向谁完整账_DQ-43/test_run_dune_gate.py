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
        w.writerow(["A1", "2026-10-14", "review原文", sql_rel, sha, "5", "1", "试跑"])
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

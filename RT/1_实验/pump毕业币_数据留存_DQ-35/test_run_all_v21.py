"""run_all_v21.halves、row_ok 与 check_manifest_v21.audit 的手算预期值测试（10-04）。"""

import datetime as dt

from check_manifest_v21 import audit, check_slices
from run_all_v21 import halves, row_ok

D = dt.date


def test_halves_hand():
    sl = halves()
    # 前半月＝1～15 日：PumpSwap 上线日 2025-03-15 自成一片 202503a，03-16 起为 202503b
    assert sl[0] == ("202503a", D(2025, 3, 15), D(2025, 3, 15))
    assert sl[1] == ("202503b", D(2025, 3, 16), D(2025, 3, 31))
    # 末片 2026-10-01～10-04（R3 事件止日）
    assert sl[-1] == ("202610a", D(2026, 10, 1), D(2026, 10, 4))
    # 2（2025-03a、b）＋18 个月×2（2025-04～2026-09）＋1（2026-10a）＝39
    assert len(sl) == 39
    # 闰年无关；2026-02 下半月止于 02-28
    assert ("202602b", D(2026, 2, 16), D(2026, 2, 28)) in sl
    assert check_slices(sl) == []


def test_check_slices_detects_gap():
    sl = [("a", D(2025, 3, 15), D(2025, 3, 31)), ("b", D(2025, 4, 2), D(2026, 10, 4))]
    assert check_slices(sl) == ["b 与上一片不相接"]


def _r(**kw):
    r = dict(
        label="L",
        sql_sha256="S",
        state="QUERY_STATE_COMPLETED",
        execution_id="E1",
        rows_status="10",
        rows_file="10",
        file_sha256="F",
    )
    r.update(kw)
    return r


def test_row_ok_hand():
    assert row_ok(_r(), "S", 10, "F", "E1", 10)
    assert not row_ok(_r(), "S2", 10, "F", "E1", 10)  # SQL 变了
    assert not row_ok(_r(), "S", 10, "F", "E2", 10)  # 文件来自另一次执行
    assert not row_ok(_r(), "S", 9, "F", "E1", 10)  # 文件少一行
    assert not row_ok(_r(), "S", 10, "G", "E1", 10)  # 文件被换过
    # 零行片：无文件、状态 0 行、清单文件哈希为空
    assert row_ok(
        _r(rows_status="0", rows_file="", file_sha256=""), "S", None, None, "E1", 0
    )
    assert not row_ok(
        _r(rows_status="0", rows_file="", file_sha256=""), "S", None, None, None, 0
    )


def test_audit_hand():
    exp = ["A", "B", "C"]
    man = [
        _r(label="A"),
        _r(label="B", sql_sha256="OLD"),
        _r(label="X"),
    ]
    sql_sha = {"A": "S", "B": "S", "C": "S"}
    finfo = {"A": (10, "F"), "B": (10, "F")}
    sinfo = {"A": ("E1", 10), "B": ("E1", 10)}
    res = audit(exp, man, sql_sha, finfo, sinfo)
    assert res["A"] == []
    assert res["B"] == ["SQL 已变（清单里的不是当前冻结版本）"]
    assert res["C"] == ["缺片"]
    assert res["X"] == ["清单里有、预期片表里没有"]
    # 同一片两次完成执行：以最后一次为准，另报
    man2 = [_r(label="A", execution_id="E0"), _r(label="A")]
    assert audit(["A"], man2, {"A": "S"}, finfo, sinfo)["A"] == [
        "注：2 次完成执行，以最后一次为准"
    ]

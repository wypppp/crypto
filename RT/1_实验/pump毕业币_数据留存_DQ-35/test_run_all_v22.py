"""run_all_v22.row_ok、file_info 与 check_manifest_v22.audit 的手算预期值测试（10-05）。
含 GPT 批 1a-i 第 4 条的两个反例：错误 query_id 加“下载失败”；含换行字段的 CSV 行数。"""

import csv
import gzip

import run_all_v22 as R
from check_manifest_v22 import audit


def _r(**kw):
    r = dict(
        chain="solana",
        label="L",
        sql_sha256="S",
        query_id="101",
        execution_id="E1",
        state="QUERY_STATE_COMPLETED",
        rows_status="2",
        rows_file="2",
        file_sha256="F",
        download="ok",
    )
    r.update(kw)
    return r


LED = dict(query_id="101", execution_id="E1", state="QUERY_STATE_COMPLETED")
SINFO = ("101", "E1", "QUERY_STATE_COMPLETED", 2)


def test_row_ok_hand():
    assert R.row_ok(_r(), "S", (2, "F"), SINFO, LED)
    # GPT 反例：清单里 query_id 错、下载失败 → 不能算齐
    assert not R.row_ok(
        _r(query_id="999", download="下载失败"), "S", (2, "F"), SINFO, LED
    )
    assert not R.row_ok(_r(query_id="999"), "S", (2, "F"), SINFO, LED)  # 只错 query_id
    assert not R.row_ok(
        _r(download="失败或执行号不符"), "S", (2, "F"), SINFO, LED
    )  # 只下载失败
    assert not R.row_ok(
        _r(), "S", (2, "F"), ("101", "E2", "QUERY_STATE_COMPLETED", 2), LED
    )  # 文件来自另一次执行
    assert not R.row_ok(
        _r(), "S", (2, "F"), SINFO, dict(LED, query_id="102")
    )  # 台账不符
    assert not R.row_ok(_r(), "S", (1, "F"), SINFO, LED)  # 少一行
    # 零行片：无文件、状态 0 行
    assert R.row_ok(
        _r(rows_status="0", rows_file="", file_sha256=""),
        "S",
        (None, None),
        ("101", "E1", "QUERY_STATE_COMPLETED", 0),
        LED,
    )


def test_file_info_counts_records_not_lines(tmp_path, monkeypatch):
    # GPT 反例：名称字段含换行的一条记录，按行数会数成两行；按 CSV 记录数是一行
    d = tmp_path / "raw" / "dune"
    d.mkdir(parents=True)
    with gzip.open(d / "X.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pool", "name"])
        w.writerow(["P1", "第一行\n第二行"])
        w.writerow(["P2", "普通"])
    monkeypatch.setattr(R, "H", tmp_path)
    n, _ = R.file_info("X")
    assert n == 2


def test_audit_hand():
    exp = ["A", "B", "C"]
    man = [_r(label="A"), _r(label="B", query_id="999", download="下载失败")]
    sql_sha = {"A": "S", "B": "S", "C": "S"}
    finfo = {"A": (2, "F"), "B": (2, "F")}
    sinfo = {"A": SINFO, "B": SINFO}
    led = {"A": LED, "B": LED, "C": None}
    res = audit(exp, man, sql_sha, finfo, sinfo, led)
    assert res["A"] == []
    assert "下载状态 下载失败" in res["B"] and any(
        p.startswith("query_id 不符") for p in res["B"]
    )
    assert res["C"] == ["缺片"]


# ---- 10-06 GPT 批 1a-i 增量复核④的反例
def test_row_ok_rejects_missing_status_hand():
    import run_all_v22 as R

    r = dict(
        sql_sha256="s",
        state="QUERY_STATE_COMPLETED",
        download="ok",
        query_id="1",
        execution_id="e",
        rows_status="0",
        rows_file="",
        file_sha256="",
    )
    led = dict(query_id="1", execution_id="e", state="QUERY_STATE_COMPLETED")
    assert R.row_ok(r, "s", (None, None), ("1", "e", "QUERY_STATE_COMPLETED", 0), led)
    assert not R.row_ok(
        r, "s", (None, None), ("1", "e", None, 0), led
    )  # 状态缺失不放行


def test_resume_precheck_blocks_hand():
    import run_all_v22 as R

    sql = "SELECT 1 FROM solana.instruction_calls"
    assert not R.resume_precheck(sql, "B", "plus", None)[0]  # 读不到用量
    assert not R.resume_precheck(sql, "B", "plus", 43_001.0, ack=True)[0]  # 越过硬线
    assert R.resume_precheck(sql, "M", "trial", 100.0)[0]
    import budget_v22 as B

    assert B.task_of_sql(sql) == "vq" and B.task_of_sql("SELECT 1") == "refetch"


def test_content_l_key_ignores_kind_hand():
    import check_manifest_v22 as K

    base = dict(chain="solana", pool="p", slot="1", txi="2", oix="3", iix="-1", ovf="0")
    rows = [dict(base, kind="D"), dict(base, kind="W")]  # 同一事件键标成 D、W
    probs = K.content_rows(rows, "L", "GRAD")
    assert any("片内键重复 1" in p for p in probs)


def test_runner_refuses_before_gate3_fixed(monkeypatch):
    # 总控第二十二轮第三节：③ 修复并经 GPT 确认之前，运行器在取锁、读清单、执行查询之前就拒绝
    import pytest

    import run_all_v22 as R

    assert R.GATE3_FIXED is False
    monkeypatch.setattr(
        R, "_main", lambda: (_ for _ in ()).throw(AssertionError("不应运行"))
    )
    monkeypatch.setattr(
        R.bud, "run_lock", lambda: (_ for _ in ()).throw(AssertionError("不应取锁"))
    )
    with pytest.raises(SystemExit) as e:
        R.main()
    assert "取数挡板" in str(e.value)

"""budget_v22.check 的手算预期值测试（10-05）。"""

import budget_v22 as b


def _r(task, kind, c):
    return dict(
        time="",
        task=task,
        label="x",
        kind=kind,
        credits=str(c),
        usage_before="",
        usage_after="",
        note="",
    )


def test_report_line_hand():
    # 账户 19,900，本次执行上沿 50＋导出 40 MB×2＝130 → 20,030 ≥ 20,000：先停先报
    ok, why = b.check("refetch", 50, 40, "plus", 19_900, rs=[])
    assert not ok and "先报线" in why
    # 报过之后带 ack 才继续
    ok, _ = b.check("refetch", 50, 40, "plus", 19_900, ack_report=True, rs=[])
    assert ok


def test_hard_line_and_vq_cap_hand():
    # 硬线 25,000＋15,000＋3,000＝43,000：42,950＋100 越线
    ok, why = b.check("refetch", 100, 0, "plus", 42_950, ack_report=True, rs=[])
    assert not ok and "硬线" in why
    # vq 任务已用 2,950（执行 2,900＋失败 50），本次上沿 60 → 3,010 > 3,000
    rs = [
        _r("vq", "execute", 2900),
        _r("vq", "failed", 50),
        _r("refetch", "execute", 999),
    ]
    ok, why = b.check("vq", 60, 0, "trial", 2_000, rs=rs)
    assert not ok and "vq 解码累计 2950.0" in why
    ok, _ = b.check("vq", 40, 0, "trial", 2_000, rs=rs)
    assert ok


def test_export_counts_and_unknown_task_hand():
    # 试用期导出按 0 计、Plus 按每 MB 2：同样 100 MB，Plus 多 200
    ok_t, why_t = b.check("refetch", 10, 100, "trial", 1_000, rs=[])
    ok_p, why_p = b.check("refetch", 10, 100, "plus", 1_000, rs=[])
    assert ok_t and "上沿 10.0" in why_t and ok_p and "上沿 210.0" in why_p
    # 读不到用量或任务无预批：一律不跑
    assert not b.check("refetch", 1, 0, "plus", None, rs=[])[0]
    assert not b.check("other", 1, 0, "plus", 0, rs=[])[0]

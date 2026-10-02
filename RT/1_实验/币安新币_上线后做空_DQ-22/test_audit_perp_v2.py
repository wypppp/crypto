"""代码审计 10-03 第 9、13 处的永久测试：先用 GPT 的合成样例复现原版缺陷，再核对 perp_v2 的手算预期值。

python -m pytest test_audit_perp_v2.py
原版（perp_replicate.py）冻结不改；“复现”类测试断言原版仍给出审计指出的错误值，用来记录缺陷本身。
"""

from __future__ import annotations

import datetime as dt
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perp_replicate as P  # noqa: E402
import perp_v2 as V  # noqa: E402

UTC = dt.timezone.utc


def _zip(rows: list[tuple[dt.datetime, float]]) -> bytes:
    lines = ["calc_time,funding_interval_hours,last_funding_rate"]
    lines += [f"{int(t.timestamp() * 1000)},8,{r}" for t, r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("f.csv", "\n".join(lines) + "\n")
    return buf.getvalue()


@pytest.fixture
def june_only(monkeypatch):
    """只有六月文件（含 06-30 16:00 一次费率 0.001）；七月文件不存在。"""
    june = _zip([(dt.datetime(2024, 6, 30, 16, tzinfo=UTC), 0.001)])

    def fake(rel: str):
        return june if rel.endswith("2024-06.zip") else None

    monkeypatch.setattr(P, "fetch", fake)


# ---------- 第 9 处：右开月界 ----------


def test_9_old_reproduces_bug(june_only):
    t1 = dt.datetime(2024, 6, 30, tzinfo=UTC)
    t2 = dt.datetime(2024, 7, 1, tzinfo=UTC)
    assert P.funding("XUSDT", t1, t2) is None  # 原版多要七月文件，返回缺失


def test_9_fixed_returns_record(june_only):
    t1 = dt.datetime(2024, 6, 30, tzinfo=UTC)
    t2 = dt.datetime(2024, 7, 1, tzinfo=UTC)
    assert V.funding_v2("XUSDT", t1, t2) == [
        (dt.datetime(2024, 6, 30, 16, tzinfo=UTC), 0.001)
    ]


def test_9_fixed_still_needs_inner_month(june_only):
    """窗口跨进七月（t2＝07-01 00:00:00.001 之后）时，七月文件确实需要，缺了仍返回 None。"""
    t1 = dt.datetime(2024, 6, 30, tzinfo=UTC)
    t2 = dt.datetime(2024, 7, 1, 8, tzinfo=UTC)
    assert V.funding_v2("XUSDT", t1, t2) is None


# ---------- 第 13 处：资金费与逐仓保证金 ----------


def _flat(n: int, d0: dt.date, px: float = 1.0) -> tuple[list[dt.date], dict]:
    days = [d0 + dt.timedelta(days=k) for k in range(n + 1)]
    return days, {d: {"o": px, "h": px, "l": px, "c": px} for d in days}


def _hourly(d0: dt.date, n_days: int, rate: float) -> list[tuple]:
    t = dt.datetime.combine(d0 + dt.timedelta(days=1), dt.time(), UTC)
    return [(t + dt.timedelta(hours=h), rate) for h in range(24 * n_days)]


def test_13_long_flat_paying_hand_value():
    """GPT 样例：价格不动，672 次每次 +0.18%（每日 24 次，28 天），做多 1 倍。
    手算：每日扣 24×0.0018＝0.0432，第 k 日末 M＝1−0.0432k；k＝21 时 M＝0.0928 ≤ 0.1 → 第 21 日强平，r＝A−1＝−1。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    out = V.iso_path(+1, 1.0, 1.0, days, mk, _hourly(d0, 28, 0.0018))
    assert out["liq"] and out["liq_day"] == 21
    assert out["r"] == pytest.approx(-1.0)


def test_13_no_funding_equals_old_rule_short():
    """没有资金费：空头最高 1.9 倍强平（r＝−1）；1.89 倍不强平，收盘回到入场价 r＝−0.001。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    mk[days[3]] = {"o": 1, "h": 1.9, "l": 1, "c": 1}
    out = V.iso_path(-1, 1.0, 1.0, days, mk, [])
    assert out["liq"] and out["liq_day"] == 3 and out["r"] == pytest.approx(-1.0)
    mk[days[3]] = {"o": 1, "h": 1.89, "l": 1, "c": 1}
    out = V.iso_path(-1, 1.0, 1.0, days, mk, [])
    assert not out["liq"] and out["r"] == pytest.approx(-0.001)


def test_13_no_funding_equals_old_rule_long():
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    mk[days[5]] = {
        "o": 1,
        "h": 1,
        "l": 0.09,
        "c": 1,
    }  # 原版比较式 l ≤ 1×(1−0.9) 在 0.1 处因浮点为假
    out = V.iso_path(+1, 1.0, 1.0, days, mk, [])
    assert out["liq"] and out["liq_day"] == 5
    mk[days[5]] = {"o": 1, "h": 1, "l": 0.11, "c": 1}
    out = V.iso_path(+1, 1.0, 1.2, days, mk, [])
    assert not out["liq"] and out["r"] == pytest.approx(0.2 - 0.001)


def test_13_short_paying_liquidates_earlier_than_old():
    """空头付费：第 1、2 日各付 0.05（费率 −0.05，标记价 1）→ M＝0.9；第 3 日最高 1.85：
    权益 0.9＋(1−1.85)＝0.05 ≤ 0.1 → 强平，r＝−1。原版只看 1.9 不强平，收盘回到 1 时给 −0.001−0.1＝−0.101。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    mk[days[3]] = {"o": 1, "h": 1.85, "l": 1, "c": 1}
    fr = [
        (dt.datetime(2025, 1, 2, tzinfo=UTC), -0.05),
        (dt.datetime(2025, 1, 3, tzinfo=UTC), -0.05),
    ]
    out = V.iso_path(-1, 1.0, 1.0, days, mk, fr)
    assert out["liq"] and out["liq_day"] == 3 and out["r"] == pytest.approx(-1.0)


def test_13_received_funding_kept_after_liquidation():
    """空头收费：第 1～4 日各收 0.025（A＝0.1）；第 5 日最高 2.0 → 强平，r＝A−1＝−0.9（原版 −1）。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    mk[days[5]] = {"o": 1, "h": 2.0, "l": 1, "c": 1}
    fr = [(dt.datetime(2025, 1, 1 + k, tzinfo=UTC), 0.025) for k in range(1, 5)]
    out = V.iso_path(-1, 1.0, 1.0, days, mk, fr)
    assert out["liq"] and out["liq_day"] == 5
    assert out["r"] == pytest.approx(-0.9)


def test_13_paid_from_available_first():
    """空头第 1 日收 0.05（A＝0.05），第 2 日付 0.08：先扣 A 的 0.05，再扣 M 的 0.03 → A＝0、M＝0.97；
    不强平，退出价＝入场价：r＝0＋0.97−1−0.001＝−0.031（＝资金费净额 −0.03 减费用），与原版相同。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0)
    fr = [
        (dt.datetime(2025, 1, 2, tzinfo=UTC), 0.05),
        (dt.datetime(2025, 1, 3, tzinfo=UTC), -0.08),
    ]
    out = V.iso_path(-1, 1.0, 1.0, days, mk, fr)
    assert not out["liq"]
    assert out["A"] == pytest.approx(0.0) and out["M"] == pytest.approx(0.97)
    assert out["r"] == pytest.approx(-0.031)


def test_13_funding_uses_mark_close_over_entry():
    """结算额按“当日标记价收盘 / 入场价”折算：入场 2，当日收盘 3，费率 0.01，空头收 0.01×3/2＝0.015。"""
    d0 = dt.date(2025, 1, 1)
    days, mk = _flat(30, d0, px=2.0)
    mk[days[1]] = {"o": 2, "h": 3, "l": 2, "c": 3}
    fr = [(dt.datetime(2025, 1, 2, 8, tzinfo=UTC), 0.01)]
    out = V.iso_path(-1, 2.0, 2.0, days, mk, fr)
    assert out["A"] == pytest.approx(0.015)
    assert out["r"] == pytest.approx(0.015 - 0.001)

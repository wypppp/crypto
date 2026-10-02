"""代码审计 10-03 第 13 处（与第 9 处）的永久测试：用 GPT 的合成样例复现 long_squeeze.long_event 的缺陷，
再核对 DQ-22 perp_v2 的手算预期值。原 long_squeeze.py 冻结不改。

python -m pytest test_audit_long_squeeze.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "币安新币_上线后做空_DQ-22"))
import long_squeeze as L  # noqa: E402
import perp_replicate as P  # noqa: E402
import perp_v2 as V  # noqa: E402

UTC = dt.timezone.utc
D0 = dt.date(2025, 3, 1)  # 永续首日；入场日 D0＋1
BASE = "SYNA"  # sha256 首字节 mod 5 ＝ 3，不命中留出规则


def _flat_daily(kind, sym, d1, d2):
    out, d = {}, d1
    while d <= d2:
        out[d] = {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "t": 0}
        d += dt.timedelta(days=1)
    return out


def _gpt_funding(sym, t1, t2):
    """672 次每次 +0.18%（每小时一次，从入场后第一个零点起 28 天）。"""
    s = dt.datetime.combine(D0 + dt.timedelta(days=2), dt.time(), UTC)
    fr = [(s + dt.timedelta(hours=h), 0.0018) for h in range(672)]
    return [x for x in fr if t1 <= x[0] < t2]


@pytest.fixture
def gpt_case(monkeypatch):
    monkeypatch.setattr(P, "daily", _flat_daily)
    monkeypatch.setattr(P, "funding", _gpt_funding)
    monkeypatch.setattr(V, "funding_v2", _gpt_funding)


def test_13_old_reproduces_bug(gpt_case):
    """原版：价格不动、付 672 次资金费，回收 −1.2106 且未判强平（亏损超过全部保证金）。"""
    assert not L.T.holdout(BASE)
    out = L.long_event({"perp": f"{BASE}USDT", "base": BASE, "t0": D0.isoformat()})
    assert out["H30_status"] == "ok"
    assert not out["H30_liq"]
    assert out["H30_r"] == pytest.approx(-0.001 - 672 * 0.0018)  # −1.2106


def test_13_fixed_hand_value(gpt_case):
    """新版：每日扣 24×0.0018＝0.0432，第 21 个持有日末 M＝0.0928 ≤ 0.1 → 强平，r＝−1，之后不再计费。"""
    d = D0 + dt.timedelta(days=1)
    res = V.iso_event(+1, f"{BASE}USDT", d, d + dt.timedelta(days=30))
    assert res["liq"] and res["liq_day"] == 21
    assert res["r"] == pytest.approx(-1.0)


def test_13_fixed_equals_old_without_funding(monkeypatch):
    """没有资金费且未强平：新旧回收相同（价格从 1 涨到 1.5，r＝0.5−0.001）。"""

    def rising(kind, sym, d1, d2):
        out = _flat_daily(kind, sym, d1, d2)
        out[d2] = {"o": 1.0, "h": 1.5, "l": 1.0, "c": 1.5, "t": 0}
        return out

    monkeypatch.setattr(P, "daily", rising)
    monkeypatch.setattr(P, "funding", lambda s, a, b: [])
    monkeypatch.setattr(V, "funding_v2", lambda s, a, b: [])
    d = D0 + dt.timedelta(days=1)
    old = L.long_event({"perp": f"{BASE}USDT", "base": BASE, "t0": D0.isoformat()})
    new = V.iso_event(+1, f"{BASE}USDT", d, d + dt.timedelta(days=30))
    assert old["H30_r"] == pytest.approx(0.499)
    assert new["r"] == pytest.approx(old["H30_r"])

"""代码审计 10-03 第 14 处的永久测试：GPT 的合成成交复现 k1_paths 的秒内前视，再核对 k1_paths_v2 的手算值。

python -m pytest test_audit_k1.py
"""

from __future__ import annotations

import datetime as dt
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import k1_paths as K  # noqa: E402
import k1_paths_v2 as K2  # noqa: E402

T0 = dt.datetime(2025, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
SEC0 = int(T0.timestamp())
R = {"_sym": "XUSDT", "_t0": T0}


def _zip(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "\n".join(lines) + "\n")
    path.write_bytes(buf.getvalue())


@pytest.fixture
def agg(tmp_path, monkeypatch):
    """币安 aggTrades：第 5.000 秒价 1，第 5.900 秒价 2。"""
    monkeypatch.setattr(K, "CACHE", tmp_path)
    t5 = (SEC0 + 5) * 1000
    _zip(
        tmp_path / "um" / "XUSDT" / "XUSDT-aggTrades-2025-01-01.zip",
        ["agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker",
         f"1,1.0,1,1,1,{t5},false", f"2,2.0,1,2,2,{t5 + 900},false"],
    )  # fmt: skip


@pytest.fixture
def kline(tmp_path, monkeypatch):
    """币安现货 1 秒 K 线：第 4 秒收盘 1，第 5 秒（[5, 6)）收盘 2。"""
    monkeypatch.setattr(K, "CACHE", tmp_path)
    rows = []
    for s, c in ((4, 1.0), (5, 2.0)):
        o = (SEC0 + s) * 1000
        rows.append(f"{o},{c},{c},{c},{c},1,{o + 999},{c},1,0,0,0")
    _zip(tmp_path / "spot" / "XUSDT" / "XUSDT-1s-2025-01-01.zip", rows)


def test_14_old_reproduces_bug_aggtrades(agg):
    ts, pts, _ = K.series(R)
    assert K.px_at(ts, pts, SEC0 + 5) == 2.0


def test_14_fixed_hand_value_aggtrades(agg):
    ts, pts, _ = K2.series(R)
    assert K2.px_at(ts, pts, SEC0 + 5) == 1.0
    assert K2.px_at(ts, pts, SEC0 + 6) == 2.0


def test_14_old_reproduces_bug_kline(kline):
    ts, pts, _ = K.series(R)
    assert K.px_at(ts, pts, SEC0 + 5) == 2.0  # 第 5 秒 K 线的收盘挂在 5.000


def test_14_fixed_hand_value_kline(kline):
    """v2：第 5 秒 K 线的收盘到 6.000 才可知；请求第 5 秒得到第 4 秒的收盘 1。"""
    ts, pts, _ = K2.series(R)
    assert K2.px_at(ts, pts, SEC0 + 5) == 1.0
    assert K2.px_at(ts, pts, SEC0 + 6) == 2.0

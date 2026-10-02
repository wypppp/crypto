"""代码审计 10-03 第 5、11 处的永久测试：GPT 的合成样例复现原版缺陷，再核对 v2 的手算值。
第 5 处：analyze_d.simulate / oracle 的期末回款遗漏；第 11 处：make_d_block 月初零点信号丢入场（DuckDB 执行 CORE）。

python -m pytest test_audit_dq18.py
样例：估值回调固定为 2 倍，第 1 天投入全部本金，第 2 天退出，第 10 天截止，没有其他机会。
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_d as A  # noqa: E402
import analyze_d_v2 as A2  # noqa: E402
import make_d_block as M  # noqa: E402
import make_d_block_v2 as M2  # noqa: E402

ST = A.W0 + timedelta(days=1)
ROW = {
    "ok": True,
    "est": True,
    "cap5_buy_usd": 1e12,
    "st": ST,
    "et": ST + timedelta(days=1),
    "mint": "M",
    **{f"c_{h}": None for h in ("D1", "D7", "D30", "D90", "D180")},
}
OPPS = [{"st": ST, "tier": "t", "stratum": "s", "mint": "M", "own": ROW}]


@pytest.fixture(autouse=True)
def two_x(monkeypatch):
    monkeypatch.setattr(A, "mult_for", lambda r, usd, chain_sol: 2.0)
    monkeypatch.setattr(A2, "mult_for", lambda r, usd, chain_sol: 2.0)


def test_5_simulate_old_reproduces_bug():
    cash, open_usd, n = A.simulate(
        OPPS, {}, 1.0, 0.0, random.Random(1), days=10, replay=False
    )
    assert (
        n == 1
        and cash == pytest.approx(0.0)
        and open_usd == pytest.approx(2 * A.START_USD)
    )


def test_5_simulate_fixed_hand_value():
    """应得：现金 2 倍本金、未平仓 0；现金＋未平仓与原版相同。"""
    cash, open_usd, n = A2.simulate(
        OPPS, {}, 1.0, 0.0, random.Random(1), days=10, replay=False
    )
    assert (
        n == 1
        and cash == pytest.approx(2 * A.START_USD)
        and open_usd == pytest.approx(0.0)
    )


def test_5_oracle_old_reproduces_bug():
    """原版：k＝2 的路径期末现金为 0（净 −1 万元），于是上界选了不交易的 k（净 0）。"""
    res = A.oracle([ROW], replay=False, days=10)
    assert res["net_gain_rmb"] == 0 and res["trades"] == 0


def test_5_oracle_fixed_hand_value():
    """应得：k＝2 买入并在第 2 天以 2 倍退出，净赚 1 万元（本金 10,000 元），期末未平仓 0。"""
    res = A2.oracle([ROW], replay=False, days=10)
    assert res["k"] == 2 and res["trades"] == 1
    assert res["net_gain_rmb"] == 10000 and res["open_at_end_rmb"] == 0


# ---------- 第 11 处：月初零点信号的入场 ----------


def _block_rows(scan_start: datetime) -> list:
    """一个币一个池：01-31 20:00～02-01 04:00 每 2 分钟一笔（每笔 1 SOL＝200 美元），另加 02-01 00:00:10 一笔；
    只保留块扫描起点之后的成交（模拟 SQL 的分区与时间围栏）。"""
    rows, t, k = [], datetime(2025, 1, 31, 20), 0
    times = []
    while t < datetime(2025, 2, 1, 4):
        times.append(t)
        t += timedelta(minutes=2)
    times.append(datetime(2025, 2, 1, 0, 0, 10))
    for ts in sorted(times):
        k += 1
        rows.append(
            (ts, f"tx{k}", "POOL_A", "pumpswap", 1, "MINT", M.SOL, 200_000.0, 1.0)
        )
    return [r for r in rows if r[0] >= scan_start]


def _run_core(core: str, scan_start: datetime) -> list[dict]:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE tr(block_time TIMESTAMP, tx_id VARCHAR, pool VARCHAR, project VARCHAR, "
        "version INTEGER, mint VARCHAR, quote_mint VARCHAR, token_amount DOUBLE, quote_amount DOUBLE)"
    )
    con.executemany(
        "INSERT INTO tr VALUES (?,?,?,?,?,?,?,?,?)", _block_rows(scan_start)
    )
    con.execute(
        "CREATE TABLE sol_minute AS SELECT * FROM (SELECT range AS minute FROM "
        "range(TIMESTAMP '2025-01-31', TIMESTAMP '2025-02-02', INTERVAL 1 MINUTE)) CROSS JOIN (SELECT 200.0 AS sol_usd)"
    )
    con.execute(
        "CREATE TABLE sig AS SELECT 'MINT' AS mint, 1000000 AS tier, TIMESTAMP '2025-02-01 00:00:00' AS signal_time"
    )
    sql = core.format(
        SOL=M.SOL,
        USDC=M.USDC,
        USDT=M.USDT,
        MINBY="arg_min",
        MAXBY="arg_max",
        START="2025-02-01",
        END="2025-03-01",
    )
    cur = con.execute("WITH " + sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_11_old_reproduces_bug():
    """v1 的二月块：成交从 02-01 00:00 起，没有穿越小时（01-31 23 时）→ 没有入场行；一月块不收该信号（信号 < 块终点 为假）。"""
    out = _run_core(M.CORE, datetime(2025, 2, 1))
    assert not any(r["rt"] == "E" for r in out)


def test_11_fixed_hand_value():
    """v2：扫描提前 1 小时 → 入场行的穿越小时为 01-31 23:00，入场成交为 02-01 00:00:10；路径行都在 02-01 及以后、不重复。"""
    out = _run_core(M2.CORE, datetime(2025, 1, 31, 23))
    e = [r for r in out if r["rt"] == "E"]
    assert len(e) == 1
    assert e[0]["h"] == datetime(2025, 1, 31, 23) and e[0]["x_time"] == datetime(
        2025, 2, 1, 0, 0, 10
    )
    p = [r for r in out if r["rt"] == "P"]
    assert p and min(r["h"] for r in p) >= datetime(2025, 2, 1)
    assert len({r["h"] for r in p}) == len(p)

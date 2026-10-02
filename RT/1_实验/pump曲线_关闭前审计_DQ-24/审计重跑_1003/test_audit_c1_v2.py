"""代码审计 10-03 第 2、12 处的永久测试（DuckDB 执行 SQL 片段）：先用 GPT 的合成样例复现 v1，再核对 v2 的手算值。

python -m pytest test_audit_c1_v2.py
v1 片段取自冻结的 sql/C1_W20250407.sql（由 DQ-7 F2_dev.sql 截取），v2 取自 build_c1_sql_v2 生成的同一周。
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_c1_sql_v2 as B  # noqa: E402

V1_SQL = (HERE.parent / "sql" / "C1_W20250407.sql").read_text()
V2_SQL = B.sql(dt.date(2025, 4, 7), dt.date(2025, 4, 13), "周 2025-04-07")


def pool_sub(sql: str) -> str:
    a = sql.index("SELECT pool, ts, slot, txi, ")  # v1 无 oix，v2 有
    b = sql.index(") e", a)
    return sql[a:b] + ") e"


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA pumpdotfun_solana")
    cols = (
        "pool VARCHAR, evt_block_time TIMESTAMP, evt_block_date DATE, evt_block_slot BIGINT, evt_tx_index INT,"
        " evt_inner_instruction_index INT, pool_quote_token_reserves DOUBLE, pool_base_token_reserves DOUBLE,"
        " protocol_fee DOUBLE, coin_creator_fee DOUBLE, lp_fee DOUBLE, lp_fee_basis_points DOUBLE,"
        ' protocol_fee_basis_points DOUBLE, coin_creator_fee_basis_points DOUBLE, "user" VARCHAR'
    )
    c.execute(
        f"CREATE TABLE pumpdotfun_solana.pump_amm_evt_buyevent ({cols}, quote_amount_in DOUBLE, base_amount_out DOUBLE, quote_amount_in_with_lp_fee DOUBLE, evt_outer_instruction_index INT)"
    )
    c.execute(
        f"CREATE TABLE pumpdotfun_solana.pump_amm_evt_sellevent ({cols}, quote_amount_out DOUBLE, base_amount_in DOUBLE, evt_outer_instruction_index INT)"
    )
    c.execute("CREATE TABLE mapping (pool VARCHAR)")
    c.execute("INSERT INTO mapping VALUES ('P')")
    return c


def buy(c, slot, q, b, qin, bout, qinl=None, pf=0.0):
    """qinl＝quote_amount_in_with_lp_fee（缺省等于 qin，即无 LP 费）；pf＝protocol_fee。"""
    c.execute(
        "INSERT INTO pumpdotfun_solana.pump_amm_evt_buyevent VALUES"
        " ('P', TIMESTAMP '2025-04-08 00:00:00' + to_seconds(?), DATE '2025-04-08', ?, 0, 0, ?, ?, ?, 0, 0, 20, 5, 0, 'u', ?, ?, ?, 0)",
        [slot, slot, q, b, pf, qin, bout, qin if qinl is None else qinl],
    )


def states(c, sql: str) -> list[tuple]:
    q = f"SELECT slot, qraw / 1e9, braw / 1e6 FROM ({pool_sub(sql)}) ORDER BY slot"
    return c.execute(q).fetchall()


def test_2_old_reproduces_bug(con):
    """GPT 样例：本笔前 (100 SOL, 1000 枚)，本笔 (+10, −100)；下一笔前因加池变为 (220, 1800)。v1 给出本笔后 (220, 1800)。"""
    buy(con, 1, 100e9, 1000e6, 10e9, 100e6)
    buy(con, 2, 220e9, 1800e6, 1e9, 1e6)
    assert states(con, V1_SQL)[0] == (1, pytest.approx(220.0), pytest.approx(1800.0))


def test_2_fixed_hand_value(con):
    """v2：本笔后＝(100＋10, 1000−100)＝(110, 900)；最后一笔仍按本笔前＋变动：(220＋1, 1800−1)。"""
    buy(con, 1, 100e9, 1000e6, 10e9, 100e6)
    buy(con, 2, 220e9, 1800e6, 1e9, 1e6)
    got = states(con, V2_SQL)
    assert got[0] == (1, pytest.approx(110.0), pytest.approx(900.0))
    assert got[1] == (2, pytest.approx(221.0), pytest.approx(1799.0))


def test_2_fixed_buy_uses_with_lp_fee(con):
    """买入：交易前 (100, 1000)，quote_amount_in 10、LP 费 0.02（quote_amount_in_with_lp_fee＝10.02）、协议费 0.05
    → v2 交易后 quote＝100＋10.02＝110.02（LPCHK3 核实的公式）；F59 旧式会给 100＋10−0.05＝109.95。"""
    buy(con, 1, 100e9, 1000e6, 10e9, 100e6, qinl=10.02e9, pf=0.05e9)
    assert states(con, V2_SQL)[0] == (1, pytest.approx(110.02), pytest.approx(900.0))
    assert states(con, V1_SQL)[0] == (
        1,
        pytest.approx(109.95),
        pytest.approx(900.0),
    )  # v1 每池最后一笔用 F59 旧式


def test_2_fixed_sell_formula(con):
    """卖出（F59 公式）：本笔前 (100, 1000)，卖入 100 枚、quote_amount_out 9 SOL、lp_fee 0.02 SOL
    → 本笔后 quote＝100−(9−0.02)＝91.02，base＝1100。"""
    con.execute(
        "INSERT INTO pumpdotfun_solana.pump_amm_evt_sellevent VALUES"
        " ('P', TIMESTAMP '2025-04-08 00:00:01', DATE '2025-04-08', 1, 0, 0, 100e9, 1000e6, 0, 0, 0.02e9, 20, 5, 0, 'u', 9e9, 100e6, 0)"
    )
    assert states(con, V2_SQL)[0] == (1, pytest.approx(91.02), pytest.approx(1100.0))


def expr(sql: str, name: str) -> str:
    m = re.search(r"(bool_or\([^\n]*?\)) AS " + name + r"\b", sql)
    assert m, name
    return m.group(1)


def test_12_old_and_fixed():
    """入场状态相同（rn ≤ 2 都正常），只有入场后 rn＝3 出现曲线 x＝130：v1 整币判异常（剔除），v2 不剔除、记入场后异常。"""
    c = duckdb.connect()
    c.execute(
        "CREATE TABLE s14 AS SELECT * FROM (VALUES (0, 50.0, 1, 2), (0, 60.0, 2, 2), (0, 130.0, 3, 2)) t(venue, x, rn, entry_rn)"
    )
    assert c.execute(f"SELECT {expr(V1_SQL, 'anomaly')} FROM s14").fetchone()[0] is True
    assert (
        c.execute(f"SELECT {expr(V2_SQL, 'anomaly')} FROM s14").fetchone()[0] is False
    )
    assert (
        c.execute(f"SELECT {expr(V2_SQL, 'anomaly_post')} FROM s14").fetchone()[0]
        is True
    )
    c.execute("UPDATE s14 SET x = 130 WHERE rn = 2")
    assert (
        c.execute(f"SELECT {expr(V2_SQL, 'anomaly')} FROM s14").fetchone()[0] is True
    )  # 入场时已异常：仍剔除


def test_order_key_includes_outer_index():
    """重跑中发现：同一交易内多笔成交的 (时间, slot, tx, 内层指令) 会并列；v2 的行号排序必须含外层指令序号。"""
    assert "ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn" in V1_SQL
    assert "ORDER BY s.ts, s.venue, s.slot, s.txi, s.oix, s.iix) AS rn" in V2_SQL

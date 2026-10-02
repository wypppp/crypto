"""代码审计 10-03 第 6 处（与第 8 处的口径）的永久测试：GPT 的合成样例复现 sn.py 的“删现金、留费用”，再核对 sn_v2 的手算值。

python -m pytest test_audit_sn_v2.py
样例：一个钱包两个格。正常格 A：付出 1、收回 1.1、成交费 0.01；转移格 B（被剔除）：成交费 0.90。
应得 R_hi＝1.1/1.01＝1.0891；原版按钱包合计费用得 1.1/1.91＝0.5759，触发错误的停止读法。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "sql"))
sys.path.insert(0, str(HERE.parents[1] / "pump曲线_钱包持续性可行性_DQ-26" / "sql"))
import sn as S1  # noqa: E402
import sn_v2 as S2  # noqa: E402

U = "U1"
TR = pd.DataFrame(
    {
        "mint": ["A", "B"],
        "usr": [U, U],
        "created_at": ["t", "t"],
        "first_buy_slot_gap": [0, 0],
        "pay": [1.0, 0.5],
        "recv": [1.1, 0.0],
        "tok_b": [100.0, 100.0],
        "tok_s": [100.0, 0.0],
        "n_buy": [1, 1],
        "n_sell": [1, 0],
        "n_amm": [0, 0],
        "liq_sol": [0.0, 0.0],
    }
)
XF = pd.DataFrame(
    {"kind": ["TOK"], "usr": [U], "mint": ["B"], "a1": [100.0], "a2": [0.0], "n": [1]}
)


def test_6_old_reproduces_bug(tmp_path, monkeypatch):
    (tmp_path / "raw" / "dune").mkdir(parents=True)
    (tmp_path / "runs").mkdir()
    pd.DataFrame({"usr": [U]}).to_csv(tmp_path / "runs" / "snipers_S.csv", index=False)
    TR.to_csv(tmp_path / "raw" / "dune" / "SN_TRADES.csv.gz", index=False)
    pd.DataFrame(
        {
            "usr": [U],
            "n_tx_all": [2],
            "fee_all": [0.91],
            "n_tx_trade": [2],
            "fee_trade": [0.91],
        }
    ).to_csv(tmp_path / "raw" / "dune" / "SN_FEES.csv.gz", index=False)
    XF.to_csv(tmp_path / "raw" / "dune" / "SN_XFER.csv.gz", index=False)
    monkeypatch.setattr(S1, "H", tmp_path)
    monkeypatch.setattr(S1, "RAW", tmp_path / "raw" / "dune")
    S1.main()
    out = json.loads((tmp_path / "runs" / "sn.json").read_text())
    assert out["R_hi"] == pytest.approx(1.1 / 1.91, abs=1e-4)
    assert out["reading"].startswith("读法 2")


def test_6_fixed_hand_value():
    fe = pd.DataFrame(
        {"usr": [U, U], "mint": ["A", "B"], "n_tx": [1, 1], "fee": [0.01, 0.90]}
    )
    tp = pd.DataFrame({"usr": [], "mint": [], "n": [], "tip": []})
    out, _ = S2.score(pd.DataFrame({"usr": [U]}), TR, fe, tp, XF)
    assert out["n_cells_xfer_excluded"] == 1
    assert out["R_hi"] == pytest.approx(1.1 / 1.01, abs=1e-4)
    assert out["R_lo"] == pytest.approx(1.1 / 1.01, abs=1e-4)


def test_6_non_trade_costs_stay_in_r_lo_only():
    """非成交交易的费用（mint 为空）0.05 与小费 0.04：只进 R_lo，不进 R_hi。"""
    fe = pd.DataFrame(
        {
            "usr": [U, U, U],
            "mint": ["A", "B", None],
            "n_tx": [1, 1, 3],
            "fee": [0.01, 0.90, 0.05],
        }
    )
    tp = pd.DataFrame({"usr": [U], "mint": [None], "n": [1], "tip": [0.04]})
    out, _ = S2.score(pd.DataFrame({"usr": [U]}), TR, fe, tp, XF)
    assert out["R_hi"] == pytest.approx(1.1 / 1.01, abs=1e-4)
    assert out["R_lo"] == pytest.approx(1.1 / 1.10, abs=1e-4)


# ---------- 第 3、8 处：SQL 片段（DuckDB 执行） ----------

import re  # noqa: E402

import build_sn_sql_v2 as B  # noqa: E402
import duckdb  # noqa: E402
from build_rank_sql import chain  # noqa: E402


def _fee_expr(sql: str) -> str:
    m = re.search(r"\((COALESCE\(CAST\(t\.fee AS DOUBLE\).*?)\) / 1e9 AS fee_evt", sql)
    assert m
    return m.group(1)


def test_3_curve_fee_excludes_buyback():
    """曲线买入 1 SOL：fee 0.0095、creator_fee 0.003、buyback_fee 0.00475（＝fee 的一半）。交易者实付费用 0.0125（F59）。"""
    c = duckdb.connect()
    c.execute(
        "CREATE TABLE t AS SELECT 9500000.0 AS fee, 3000000.0 AS creator_fee, 4750000.0 AS buyback_fee"
    )
    old = c.execute(
        f"SELECT ({_fee_expr(chain(B.C0, B.C1, B.C1, extra=True))}) / 1e9 FROM t"
    ).fetchone()[0]
    new = c.execute(f"SELECT ({_fee_expr(B.chain_v2())}) / 1e9 FROM t").fetchone()[0]
    assert old == pytest.approx(0.01725) and new == pytest.approx(0.0125)


def test_8_fee_trade_includes_pumpswap_only_tx():
    """窗口币的一笔只含 PumpSwap 的成交交易，网络费 0.1 SOL：v1 的成交交易集合只取曲线成交，漏掉它；v2 记到（钱包, 币）。"""
    c = duckdb.connect()
    c.execute("CREATE SCHEMA pumpdotfun_solana")
    c.execute("CREATE SCHEMA gas_solana")
    c.execute(
        'CREATE TABLE pumpdotfun_solana.pump_evt_tradeevent (evt_tx_id VARCHAR, "user" VARCHAR, mint VARCHAR, evt_block_date DATE)'
    )
    c.execute(
        "CREATE TABLE gas_solana.fees (tx_hash VARCHAR, signer VARCHAR, tx_fee DOUBLE, block_date DATE)"
    )
    c.execute(
        f"INSERT INTO gas_solana.fees VALUES ('amm_tx', '{U}', 0.1, DATE '{B.C0}')"
    )
    c.execute(f"CREATE TABLE sel AS SELECT '{U}' AS usr")
    c.execute("CREATE TABLE sol_cohort AS SELECT 'A' AS mint")
    c.execute(
        f"CREATE TABLE amm_raw AS SELECT 'amm_tx' AS tx_id, '{U}' AS usr, 'A' AS mint"
    )
    sql = B.fees([U])
    q = "WITH " + sql[sql.index("tt2 AS (") :]
    rows = c.execute(q).fetchall()
    assert rows == [(U, "A", 1, pytest.approx(0.1))]
    # v1：成交交易集合 tt 只来自曲线成交事件，这笔交易不在其中，fee_trade＝0
    import build_sn_sql as V1  # noqa: E402

    v1 = V1.fees([U])
    assert "pump_amm_evt" not in v1[v1.index("tt AS (") :]


def test_1_chain_carries_amm_tx_id():
    """第 1 处 SQL 一侧：v1 成交链的 PumpSwap 行交易号为 NULL；v2 从 amm_raw 带出 evt_tx_id（两支都带）。"""
    v1 = chain(B.C0, B.C1, B.C1, extra=True)
    v2 = B.chain_v2()
    assert "CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE), CAST(NULL AS varchar)" in v1
    assert (
        "a.evt_tx_id AS tx_id," in v2
        and "COALESCE(a.evt_inner_instruction_index, -1), a.evt_tx_id," in v2
    )
    assert "CAST(0 AS DOUBLE), tx_id" in v2

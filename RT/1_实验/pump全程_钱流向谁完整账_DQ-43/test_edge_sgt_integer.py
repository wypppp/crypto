"""EDGE 整数与压缩：边界手算、未来围栏、实体结果和前缀风险。"""

from decimal import Decimal

import pytest

import build_wm2_sql as B
import edge_sgt_integer as I
import s3_ref as R
from test_wm2_semantic import D, T, coin, db, edge_v3_rows, run, trade, xfer, X, Y


def integer_db(rows):
    con = db(rows)
    con.execute("ALTER TABLE tokens_solana.transfers ADD COLUMN amount DECIMAL(38,0)")
    for row in rows.get("tokens_solana.transfers", []):
        raw = row.get("raw_amount")
        if raw is None:
            scale = 10**9 if row["token_version"] == "native" else 10**6
            raw = int(Decimal(str(row["amount_display"])) * scale)
        con.execute(
            "UPDATE tokens_solana.transfers SET amount=? WHERE tx_id=?",
            [raw, row["tx_id"]],
        )
    return con


def sql():
    return I.build(
        D(2026, 8, 10), D(2026, 8, 16), D(2026, 8, 23), D(2026, 8, 3), D(2026, 8, 17)
    )


def test_integer_amount_preserves_low_bits_and_exact_threshold():
    # display 值故意放在阈值另一侧；只有原始整数决定是否纳入。
    trs = [xfer(X, Y, 12, amt=0.01), xfer(Y, X, 12, amt=1), xfer(X, Y, 13, amt=1)]
    amounts = [50000000, 49999999, 9007199254740993]
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", T(2026, 8, 11))],
        "pumpdotfun_solana.pump_evt_tradeevent": [trade("m", u, 12) for u in (X, Y)],
        "tokens_solana.transfers": trs,
    }
    con = integer_db(rows)
    for row, raw in zip(trs, amounts):
        con.execute(
            "UPDATE tokens_solana.transfers SET amount=? WHERE tx_id=?",
            [raw, row["tx_id"]],
        )
    got = run(con, sql(), "s_edges")
    assert len(got) == 1
    assert got[0][0:3] == (X, Y, 2)
    assert got[0][3] == Decimal(9007199304740993)


def test_compact_four_columns_preserve_entities_and_future_filter():
    rows = edge_v3_rows()
    rows["tokens_solana.transfers"].append(xfer(X, "future", 18))
    con = integer_db(rows)
    old = run(
        con,
        B.build(
            "EDGE",
            D(2026, 8, 10),
            D(2026, 8, 16),
            D(2026, 8, 10),
            D(2026, 8, 23),
            edge_from=D(2026, 8, 3),
            edge_cut=D(2026, 8, 17),
            edge_kinds="SGT",
        ),
        "out",
    )
    new = run(con, sql(), "out")

    def edges(rs):
        return [{"kind": r[0], "a": r[2], "b": r[3], "x": r[8]} for r in rs]

    assert R.entities(edges(old)) == R.entities(edges(new))
    assert "future" not in {r[3] for r in new}
    assert "SELECT kind,a,b,x FROM out" in sql()
    assert "amount_display" not in sql()


@pytest.mark.parametrize("receivers", [200, 201])
def test_service_threshold_uses_exact_fanout(receivers):
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", T(2026, 8, 11))],
        "pumpdotfun_solana.pump_evt_tradeevent": [trade("m", u, 12) for u in (X, Y)],
        "tokens_solana.transfers": [
            xfer("f", u, 12) for u in [X, Y] + [f"n{i}" for i in range(receivers - 2)]
        ],
    }
    fan = run(integer_db(rows), sql(), "f_fan")
    assert fan == [("f", receivers)]


def test_calibration_is_four_days_and_checks_full_identity():
    q = I.calibration()
    assert "block_date BETWEEN DATE '2026-08-08' AND DATE '2026-08-11'" in q
    assert "n_prefix16_collisions" in q and "ck_full_hex" in q
    # 原始金额未转 DOUBLE；比较和哈希使用整数。
    assert "x.amount >= 50000000" in q
    assert "amount_display" not in q
    assert "SELECT kind,a,b,x FROM out" in sql()

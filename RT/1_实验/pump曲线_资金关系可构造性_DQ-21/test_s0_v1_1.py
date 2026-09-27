#!/usr/bin/env python3
"""Small invariant tests for S0 v1.1's PumpSwap orientation normalization."""
from pathlib import Path

H = Path(__file__).resolve().parent


def buy_event(reversed_pool, sol_pre, target_pre, quote_in_with_lp, base_out):
    if reversed_pool:
        return sol_pre - base_out, target_pre + quote_in_with_lp, False, base_out
    return sol_pre + quote_in_with_lp, target_pre - base_out, True, quote_in_with_lp


def sell_event(reversed_pool, sol_pre, target_pre, quote_out, base_in, lp_fee):
    if reversed_pool:
        return sol_pre + base_in, target_pre - quote_out + lp_fee, True, base_in
    return sol_pre - quote_out + lp_fee, target_pre + base_in, False, quote_out


def main():
    assert buy_event(False, 100, 1000, 10, 80) == (110, 920, True, 10)
    assert buy_event(True, 100, 1000, 100, 8) == (92, 1100, False, 8)
    assert sell_event(False, 100, 1000, 10, 100, 1) == (91, 1100, False, 10)
    assert sell_event(True, 100, 1000, 100, 10, 10) == (110, 910, True, 10)

    # B1C2 raw-chain fixture: the pool's SOL increase equals the event's
    # quote_amount_in_with_lp_fee exactly.  Subtracting protocol/creator fees
    # would understate both the buyer's spend and the post-trade reserve.
    b1c2_sol_pre = 17_904_184_167
    b1c2_quote_in_with_lp = 26_113_797_485
    b1c2_sol_post = 44_017_981_652
    assert b1c2_sol_pre + b1c2_quote_in_with_lp == b1c2_sol_post

    # Curve overlay: buying q from (x,y), then immediately selling q from the
    # adjusted state recovers the net input before the exit fee.
    x, y, net_in = 30.0, 1_000_000_000.0, 0.49375
    q = y - x * y / (x + net_in)
    overlay_x = x * y / (y - q)
    gross_back = overlay_x - overlay_x * (y - q) / y
    assert abs(gross_back - net_in) < 1e-10

    sql = (H / "sql" / "S0_AB_事件时点机会普查_v1_1.sql").read_text()
    assert "base_mint = 'So11111111111111111111111111111111111111112' AS pool_reversed" in sql
    assert "quote_amount_in_with_lp_fee" in sql
    assert "lead(sol_pre_raw)" not in sql
    assert "ORDER BY s.slot, s.txi, s.oix, s.iix, s.venue" in sql
    assert "ORDER BY s.ts, s.venue" not in sql
    assert "max(s.ts) OVER" in sql
    assert "max_sell_30d_e30" in sql and "max_sell_30d_e120" in sql
    assert "objective_inclusion_probability" in sql
    assert "max(CASE WHEN rn >= e5_rn THEN pm END) OVER" in sql
    assert "COALESCE(IF(" not in sql
    assert sql.count("\nstates AS (") == 1
    assert sql.count("\namm_states AS (") == 1
    print("S0 v1.1 semantic invariants: OK")


if __name__ == "__main__":
    main()

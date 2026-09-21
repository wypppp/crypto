"""Render H1 S1 DuneSQL: new-position recovery after each A-week S0 trigger (no credentials, no execution).

Per event (mint, signal tx) and delay D in {30, 120, 300} s (120 s = main, per H1 spec):
  entry state   = last state (chain order) with block_time <= signal_time + D
  position      = buy 0.5 SOL at the entry state: tok = ey - ex*ey/(ex + 0.5*(1 - efee/1e4))   (F2 valuation)
  value         = sm: curve (x*y/(y-tok) - x)*(1-fee) capped at xr + 0.5*(1-efee) ("position counted in curve state",
                  DQ-1M M2); pool (x - x*y/(y+tok))*(1-fee); divided by 0.5                          (F2 valuation)
  stop          = first state after entry with pm <= 0.5 * max(1, running max pm since entry);
                  executed at the LAST state with block_time <= trigger_time + 5 s (spec: fixed execution delay,
                  not just the next trade)
  idle exit     = 24 h without a state after max(ts, entry): value at that state (F2 b50 convention)
  horizon       = entry + 30 days: value at the last state (exit_reason 'horizon')
  recovery      = value / 0.5 SOL; the fixed 0.004 deduction is applied in analysis, not here.
Changes vs F2's path build: chain order (slot, tx_index, outer_ix, inner_ix) instead of (ts, venue, ...);
AMM buy fallback delta uses quote_amount_in_with_lp_fee (matches pool balance, S0); states start at the signal tx.
Known gaps: buyback/cashback fee fields are not in the F2 fee sum (reported as a column); no priority fee/MEV/failed tx.
"""
import argparse
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
P0, P1 = "2026-06-01", "2026-07-10"  # event partitions: A-week signals .. last entry + 30 d
CURVE_END = "2026-06-17"  # curve TradeEvent partitions end here (cost: largest table); >= 8 d after the last signal.
# Curve activity after CURVE_END is not seen: events whose curve path is still active near the cut are flagged
# (last_curve_ts >= cut - 24 h and no pool state after the cut) and must be re-checked, never read as idle exits.


def render(events: pd.DataFrame, delays=(30, 120, 300), part=(P0, P1), curve_end=CURVE_END) -> str:
    vals = ",\n    ".join(
        f"('{r.mint}', from_iso8601_timestamp('{pd.Timestamp(r.signal_time).strftime('%Y-%m-%dT%H:%M:%S')}Z'), "
        f"BIGINT '{int(r.signal_slot)}', {int(r.signal_tx_index)})" for r in events.itertuples())
    dl = ", ".join(f"({d})" for d in delays)
    pr = f"evt_block_date BETWEEN DATE '{part[0]}' AND DATE '{part[1]}'"
    prc = f"evt_block_date BETWEEN DATE '{part[0]}' AND DATE '{curve_end}'"
    return f"""-- H1 S1: new-position recovery after each S0 trigger; delays {list(delays)} s (120 s main). Rendered by build_h1_s1.py.
-- {len(events)} A-week events from RT/case_timing/h1_events_A.csv. Partitions {part[0]} .. {part[1]} (curve TradeEvent only to {curve_end};
-- see curve_cut_risk). No SQL credit stop:
-- the platform per-execution cap applies. Recovery excludes the fixed 0.004 deduction (applied in analysis).
WITH
ev (mint, sig_time, sig_slot, sig_txi) AS (VALUES
    {vals}
),
dl (d) AS (VALUES {dl}),
cp AS (
    SELECT base_mint AS mint, min(pool) AS pool, max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE {pr}
      AND base_mint IN (SELECT mint FROM ev)
      AND evt_outer_executing_account = '{PUMP}'
      AND index = 0
    GROUP BY 1
),
curve AS (
    SELECT t.mint, t.evt_block_time AS ts, 0 AS venue, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           t.evt_outer_instruction_index AS oix, COALESCE(t.evt_inner_instruction_index, -1) AS iix,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
           COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
           COALESCE(CAST(t.buyback_fee_basis_points AS DOUBLE), 0) AS extra_fee_bps
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN ev e ON e.mint = t.mint
    WHERE t.{prc} AND t.mint IN (SELECT mint FROM ev) AND t.evt_block_time >= e.sig_time
),
pool_raw AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           evt_outer_instruction_index AS oix, COALESCE(evt_inner_instruction_index, -1) AS iix,
           CAST(pool_quote_token_reserves AS DOUBLE) AS qraw, CAST(pool_base_token_reserves AS DOUBLE) AS braw,
           CAST(quote_amount_in_with_lp_fee AS DOUBLE) AS dq, -CAST(base_amount_out AS DOUBLE) AS db,
           COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
             + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE {pr} AND pool IN (SELECT pool FROM cp)
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index,
           evt_outer_instruction_index, COALESCE(evt_inner_instruction_index, -1),
           CAST(pool_quote_token_reserves AS DOUBLE), CAST(pool_base_token_reserves AS DOUBLE),
           -(CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)), CAST(base_amount_in AS DOUBLE),
           COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
             + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0)
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE {pr} AND pool IN (SELECT pool FROM cp)
),
pool_states AS (
    SELECT c.mint, r.ts, 1 AS venue, r.slot, r.txi, r.oix, r.iix,
           COALESCE(lead(r.qraw) OVER (PARTITION BY r.pool ORDER BY r.slot, r.txi, r.oix, r.iix), r.qraw + r.dq) / power(10, c.qd) AS x,
           COALESCE(lead(r.braw) OVER (PARTITION BY r.pool ORDER BY r.slot, r.txi, r.oix, r.iix), r.braw + r.db) / power(10, c.bd) AS y,
           CAST(NULL AS DOUBLE) AS xr, r.fee_bps, CAST(0 AS DOUBLE) AS extra_fee_bps
    FROM pool_raw r
    JOIN cp c ON c.pool = r.pool
),
states AS (
    SELECT s.* FROM (SELECT * FROM curve UNION ALL SELECT * FROM pool_states) s
    JOIN ev e ON e.mint = s.mint
    WHERE s.ts >= e.sig_time AND s.x > 0 AND s.y > 0
),
paths AS (
    SELECT s.*, e.sig_time, e.sig_slot, e.sig_txi, dl.d,
           date_add('second', dl.d, e.sig_time) AS t_entry,
           date_add('day', 30, date_add('second', dl.d, e.sig_time)) AS t_end,
           to_unixtime(s.ts) AS ts_s,
           row_number() OVER (PARTITION BY s.mint, dl.d ORDER BY s.slot, s.txi, s.oix, s.iix) AS rn
    FROM states s
    JOIN ev e ON e.mint = s.mint
    CROSS JOIN dl
    WHERE s.ts <= date_add('day', 30, date_add('second', dl.d, e.sig_time))
),
p1 AS (
    SELECT *, max(IF(ts <= t_entry, rn)) OVER (PARTITION BY mint, d) AS entry_rn,
           max(IF(slot = sig_slot AND txi = sig_txi, rn)) OVER (PARTITION BY mint, d) AS sig_rn
    FROM paths
),
p2 AS (
    SELECT *,
        max(IF(rn = entry_rn, x)) OVER (PARTITION BY mint, d) AS ex,
        max(IF(rn = entry_rn, y)) OVER (PARTITION BY mint, d) AS ey,
        max(IF(rn = entry_rn, fee_bps)) OVER (PARTITION BY mint, d) AS efee,
        max(IF(rn = entry_rn, venue)) OVER (PARTITION BY mint, d) AS evenue,
        max(IF(rn = entry_rn, ts)) OVER (PARTITION BY mint, d) AS entry_state_ts,
        max(IF(rn = sig_rn, x / y)) OVER (PARTITION BY mint, d) AS sig_price
    FROM p1
),
p3 AS (
    SELECT *,
        ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok,
        (x / y) / (ex / ey) AS pm
    FROM p2
    WHERE rn >= entry_rn
),
p4 AS (
    SELECT *,
        LEAST(
            CASE WHEN venue = 0 AND y > tok THEN (x * y / (y - tok) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS sm,
        max(pm) OVER (PARTITION BY mint, d ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax,
        lead(ts_s) OVER (PARTITION BY mint, d ORDER BY rn) AS next_ts_s,
        IF(ts_s < max(ts_s) OVER (PARTITION BY mint, d ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 1, 0) AS ts_regress
    FROM p3
),
p5 AS (
    SELECT *,
        max_by(sm, rn) OVER (PARTITION BY mint, d ORDER BY ts_s RANGE BETWEEN CURRENT ROW AND 5 FOLLOWING) AS sm_exec5,
        rn > entry_rn AND pm <= 0.5 * greatest(1.0, runmax) AS stop_hit,
        COALESCE(next_ts_s, to_unixtime(t_end)) - greatest(ts_s, to_unixtime(t_entry)) > 86400 AS idle_hit
    FROM p4
),
agg AS (
    SELECT mint, d,
        arbitrary(sig_time) AS sig_time, arbitrary(t_entry) AS t_entry, arbitrary(entry_state_ts) AS entry_state_ts,
        arbitrary(evenue) AS entry_venue, arbitrary(efee) AS entry_fee_bps,
        arbitrary((ex / ey) / sig_price) AS entry_over_signal,
        arbitrary(ex) AS entry_x,
        min(rn) FILTER (WHERE stop_hit OR idle_hit) AS exit_rn,
        min_by(IF(stop_hit, sm_exec5, sm), rn) FILTER (WHERE stop_hit OR idle_hit) AS exit_v,
        min_by(IF(stop_hit, 'stop', 'idle'), rn) FILTER (WHERE stop_hit OR idle_hit) AS exit_kind,
        min_by(ts, rn) FILTER (WHERE stop_hit OR idle_hit) AS exit_ts,
        min_by(venue, rn) FILTER (WHERE stop_hit OR idle_hit) AS exit_venue,
        min_by(runmax, rn) FILTER (WHERE stop_hit OR idle_hit) AS runmax_at_exit,
        max_by(sm, rn) AS sm_last, max(ts) AS last_ts, max(pm) AS max_pm_30d, max(runmax) AS runmax_all,
        max(IF(venue = 0, ts)) AS last_curve_ts, max(IF(venue = 1, ts)) AS last_pool_ts,
        count(*) AS n_states, sum(ts_regress) AS n_ts_regress,
        count_if(sm IS NULL) AS n_null_sm, max(extra_fee_bps) AS max_extra_fee_bps
    FROM p5
    GROUP BY 1, 2
)
SELECT
    a.mint, a.d, a.sig_time, a.t_entry, a.entry_state_ts, a.entry_venue, a.entry_fee_bps, a.entry_over_signal, a.entry_x,
    COALESCE(a.exit_kind, 'horizon') AS exit_kind,
    COALESCE(a.exit_ts, a.last_ts) AS exit_ts,
    date_diff('second', a.t_entry, COALESCE(a.exit_ts, a.last_ts)) / 3600.0 AS hold_h,
    a.exit_venue,
    round(COALESCE(a.exit_v, a.sm_last, power(1 - a.entry_fee_bps / 1e4, 2)), 6) AS recovery,
    a.exit_v IS NULL AND a.exit_rn IS NOT NULL AS exit_value_missing,
    COALESCE(a.runmax_at_exit, a.runmax_all) AS runmax_at_exit,
    a.max_pm_30d, a.n_states, a.n_ts_regress, a.n_null_sm, a.max_extra_fee_bps,
    a.last_curve_ts, a.last_pool_ts,
    a.last_curve_ts >= from_iso8601_timestamp('{curve_end}T00:00:00Z')
      AND COALESCE(a.last_pool_ts < from_iso8601_timestamp('{curve_end}T00:00:00Z'), true)
      AND COALESCE(a.exit_ts, a.last_ts) >= from_iso8601_timestamp('{curve_end}T00:00:00Z') - INTERVAL '1' DAY AS curve_cut_risk
FROM agg a
ORDER BY a.sig_time, a.mint, a.d
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=str(HERE / "h1_events_A.csv"))
    ap.add_argument("--out", default=str(HERE / "sql" / "H1_S1_A.sql"))
    a = ap.parse_args()
    ev = pd.read_csv(a.events)
    Path(a.out).write_text(render(ev))
    print(a.out, len(ev), "events")

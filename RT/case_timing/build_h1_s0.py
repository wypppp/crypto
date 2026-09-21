"""Render H1 event-only DuneSQL for ONE opened A-week creation day.

No credentials, API requests, or query execution. The output requires Dune
schema/engine validation; local event fixtures are in ignition_review/.
"""
import argparse
from datetime import date, timedelta
from pathlib import Path


def render(day: date) -> str:
    if not date(2026, 6, 1) <= day <= date(2026, 6, 7):
        raise ValueError("Only already-opened A-week creation days are allowed")
    end = day + timedelta(days=2)  # last creation + 24.5h spills into day+2
    part = f"evt_block_date BETWEEN DATE '{day}' AND DATE '{end}'"
    return f'''-- H1 S0: ONE creation day {day}; event enumeration, NO returns.
-- DRAFT: not executed on Dune. First validate table/column binding and fixtures.
-- Scan partitions: {day} .. {end}; per-mint end = created_at + 1470 minutes.
-- There is NO SQL credit stop. Set/verify the platform per-execution cost cap.
-- Amounts are lamports: curve sol_amount; AMM quote_amount_in_with_lp_fee.
-- The latter was checked against cached raw BuyEvents and pool balance deltas.
-- Deposit/Withdraw decoded-table availability still needs Dune binding validation.
-- One successful-transaction join is explicit; its raw-table scan cost is unknown.
-- Pool scope: pump curve + pump-created index=0 PumpSwap pools, not every venue.
-- One heavy events -> txs -> windows -> per_coin chain; no returns/30d scan.
WITH
cohort AS (
    SELECT e.mint, min(e.evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent e
    WHERE e.evt_block_date = DATE '{day}'
    GROUP BY 1
),
creation_mints AS (
    -- This small lookup deliberately includes all quotes. Successful creation
    -- and SOL scope are established below, after the single success join.
    SELECT mint, created_at FROM cohort
),
pools AS (
    SELECT pool, base_mint AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE {part}
      AND base_mint IN (SELECT mint FROM creation_mints)
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1, 2
),
events AS (
    SELECT mint, evt_block_time AS ts, evt_block_slot AS slot,
           evt_tx_index AS txi, evt_tx_id AS sig, 'curve' AS venue,
           CAST("user" AS varchar) AS actor,
           IF(COALESCE(is_buy, isBuy), TRY_CAST(COALESCE(sol_amount, solAmount) AS BIGINT), BIGINT '0') AS buy_lamports,
           IF(COALESCE(is_buy, isBuy), 0, 1) AS sells,
           0 AS special,
           IF(COALESCE(is_buy, isBuy) IS NULL, 1, 0) AS missing_direction
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE {part} AND mint IN (SELECT mint FROM creation_mints)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(e."user" AS varchar),
           TRY_CAST(e.quote_amount_in_with_lp_fee AS BIGINT), 0, 0, 0
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.{part}
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(e."user" AS varchar), BIGINT '0', 1, 0, 0
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.{part}
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_depositevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.{part}
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.{part}
    UNION ALL
    SELECT mint, evt_block_time, evt_block_slot, evt_tx_index,
           evt_tx_id, 'migration', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE {part} AND mint IN (SELECT mint FROM creation_mints)
    UNION ALL
    SELECT base_mint, evt_block_time, evt_block_slot, evt_tx_index,
           evt_tx_id, 'pool_create', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE {part} AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT mint, evt_block_time, evt_block_slot, evt_tx_index, evt_tx_id,
           IF(quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111',
              'creation_sol', 'creation_other'),
           CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '{day}'
),
txs AS (
    SELECT e.mint, e.sig, max(e.ts) AS ts,
           max(e.slot) AS slot, max(e.txi) AS txi,
           sum(COALESCE(e.buy_lamports, BIGINT '0')) AS buy_lamports,
           sum(e.sells) AS sells, sum(e.special) AS special,
           count_if(e.buy_lamports IS NULL OR e.buy_lamports < 0 OR e.missing_direction > 0
                    OR e.slot IS NULL OR e.txi IS NULL OR e.sig IS NULL) AS bad_rows,
           count(DISTINCT e.venue) AS venue_count,
           bool_or(e.venue IN ('creation_sol', 'creation_other')) AS is_create,
           bool_or(e.venue = 'creation_sol') AS is_sol_create,
           array_join(array_sort(array_distinct(array_agg(e.venue))), ',') AS venues,
           array_join(array_sort(array_distinct(array_agg(e.actor) FILTER (WHERE e.buy_lamports > 0))), ',') AS actors
    FROM events e
    GROUP BY 1, 2
),
successful_txs AS (
    SELECT x.* FROM txs x
    JOIN solana.transactions t ON t.id = x.sig
        AND t.block_date BETWEEN DATE '{day}' AND DATE '{end}'
        AND t.success = true
),
dated AS (
    SELECT *,
        min(ts) FILTER (WHERE is_create) OVER (PARTITION BY mint) AS created_at,
        bool_or(is_sol_create) OVER (PARTITION BY mint) AS is_sol
    FROM successful_txs
),
monitored AS (
    SELECT * FROM dated
    WHERE created_at IS NOT NULL
      AND ts >= created_at AND ts < created_at + INTERVAL '1470' MINUTE
),
sequenced AS (
    SELECT *,
        row_number() OVER (PARTITION BY mint ORDER BY slot, txi, sig) AS seq,
        max(ts) OVER (PARTITION BY mint ORDER BY slot, txi, sig ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS clock_ts
    FROM monitored
),
clock_checked AS (
    SELECT *, bad_rows + IF(ts <> clock_ts, 1, 0) AS bad_clock_rows
    FROM sequenced
),
windowed AS (
    -- A monotone prefix clock prevents a later slot with a regressed blockTime
    -- leaking into an earlier event's RANGE window. Regressed rows are flagged.
    SELECT *,
        sum(buy_lamports) OVER (PARTITION BY mint ORDER BY clock_ts RANGE BETWEEN INTERVAL '30' MINUTE PRECEDING AND CURRENT ROW)
          - sum(buy_lamports) OVER (PARTITION BY mint, clock_ts ORDER BY slot, txi, sig ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS pre30_buy_lamports,
        sum(bad_clock_rows) OVER (PARTITION BY mint ORDER BY clock_ts RANGE BETWEEN INTERVAL '30' MINUTE PRECEDING AND CURRENT ROW)
          - sum(bad_clock_rows) OVER (PARTITION BY mint, clock_ts ORDER BY slot, txi, sig ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS pre30_bad_rows
    FROM clock_checked
),
marked AS (
    SELECT *,
        is_sol AND ts >= created_at + INTERVAL '30' MINUTE
        AND buy_lamports >= BIGINT '4000000000'
        AND pre30_buy_lamports < BIGINT '4000000000'
        AND bad_clock_rows = 0 AND pre30_bad_rows = 0
        AND sells = 0 AND special = 0 AND venue_count = 1 AS eligible
    FROM windowed
),
per_coin AS (
    SELECT mint, min(created_at) AS created_at, bool_or(is_sol) AS is_sol,
        count_if(buy_lamports > 0 OR sells > 0) AS n_decoded_txs,
        count_if(bad_clock_rows > 0) AS n_bad_txs,
        count_if(ts >= created_at + INTERVAL '30' MINUTE AND buy_lamports >= BIGINT '4000000000'
                 AND (sells > 0 OR special > 0 OR venue_count <> 1)) AS n_large_mixed_txs,
        count_if(eligible) AS n_eligible_txs,
        min_by(ts, seq) FILTER (WHERE eligible) AS signal_time,
        min_by(slot, seq) FILTER (WHERE eligible) AS signal_slot,
        min_by(txi, seq) FILTER (WHERE eligible) AS signal_tx_index,
        min_by(sig, seq) FILTER (WHERE eligible) AS signal_signature,
        min_by(venues, seq) FILTER (WHERE eligible) AS signal_venue,
        min_by(actors, seq) FILTER (WHERE eligible) AS signal_actors,
        min_by(buy_lamports, seq) FILTER (WHERE eligible) AS signal_buy_lamports,
        min_by(pre30_buy_lamports, seq) FILTER (WHERE eligible) AS signal_pre30_lamports
    FROM marked GROUP BY 1
),
joined AS (
    SELECT p.mint, p.created_at, p.is_sol,
        p.n_decoded_txs, p.n_bad_txs, p.n_large_mixed_txs, p.n_eligible_txs,
        p.signal_time, p.signal_slot, p.signal_tx_index, p.signal_signature,
        p.signal_venue, p.signal_actors, p.signal_buy_lamports, p.signal_pre30_lamports
    FROM per_coin p
)
SELECT
    IF(grouping(mint) = 1, '__SUMMARY__', mint) AS mint,
    IF(grouping(mint) = 1, 'summary',
       IF(max(n_eligible_txs) > 0,
          IF(max(n_bad_txs) > 0, 'candidate_needs_data_review', 'candidate'), 'data_quality')) AS row_type,
    IF(grouping(mint) = 0, arbitrary(created_at)) AS created_at,
    IF(grouping(mint) = 0, arbitrary(signal_time)) AS signal_time,
    IF(grouping(mint) = 0, arbitrary(signal_slot)) AS signal_slot,
    IF(grouping(mint) = 0, arbitrary(signal_tx_index)) AS signal_tx_index,
    IF(grouping(mint) = 0, arbitrary(signal_signature)) AS signal_signature,
    IF(grouping(mint) = 0, arbitrary(signal_venue)) AS signal_venue,
    IF(grouping(mint) = 0, arbitrary(signal_actors)) AS signal_actors,
    IF(grouping(mint) = 0, arbitrary(signal_buy_lamports)) AS signal_buy_lamports,
    IF(grouping(mint) = 0, arbitrary(signal_pre30_lamports)) AS signal_pre30_lamports,
    count(*) AS n_created, count_if(is_sol) AS n_sol_created,
    count_if(is_sol AND COALESCE(n_decoded_txs, 0) = 0) AS n_sol_without_decoded_events,
    count_if(n_eligible_txs > 0) AS n_triggered_coins,
    sum(COALESCE(n_eligible_txs, 0)) AS n_eligible_txs,
    sum(COALESCE(n_bad_txs, 0)) AS n_bad_txs,
    sum(COALESCE(n_large_mixed_txs, 0)) AS n_large_mixed_txs
FROM joined
GROUP BY GROUPING SETS ((mint), ())
HAVING grouping(mint) = 1 OR max(n_eligible_txs) > 0 OR max(n_bad_txs) > 0
ORDER BY row_type DESC, signal_time, mint
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 6, 1))
    args = parser.parse_args()
    target = Path(__file__).parent / "sql" / f"H1_S0_{args.day.isoformat()}.sql"
    target.parent.mkdir(exist_ok=True)
    target.write_text(render(args.day))
    print(target)


# ---------------------------------------------------------------------------
# v1 (2026-09-21, executor): explicit, asserted patches on the v0 text above.
#   1. Drop the solana.transactions success join (3-day raw scan, unknown cost). Rationale: F60 + the
#      failed-event check V_failed_evt_check_20260601.sql must pass first; the fixture rows below then
#      confirm per-coin decoded counts equal the success-only local counts.
#   2. Window-aggregate FILTER replaced by IF() (no DuneSQL evidence for FILTER in OVER()).
#   3. 30-min RANGE on numeric seconds (same form as the executed F2 SQL), identical semantics.
#   4. Mayhem flag from CreateEvent.is_mayhem_mode (column used in executed F2 SQL).
#   5. Known case mints of that creation day are always output with n_decoded_txs / n_eligible_txs,
#      for comparison with RT/case_timing/sql/h1_s0_fixture_expected.csv.
FIXTURES = {
    date(2026, 6, 1): ["B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump", "YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump"],
    date(2026, 6, 3): ["5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump", "6vpjdKC8EAHdqXgX3gry3voXnQYGuRR6RJkH7hMxpump"],
    date(2026, 6, 6): ["BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump", "FbZbeMQGonXiUKK5QGDWXTGvraY2A3fRvwBZTbYRpump"],
}


def _sub(text, old, new):
    assert text.count(old) == 1, f"v1 patch anchor not unique/found: {old[:60]!r}"
    return text.replace(old, new)


def render_v1(day: date) -> str:
    s = render(day)
    end = day + timedelta(days=2)
    s = _sub(s, f"-- H1 S0: ONE creation day {day}; event enumeration, NO returns.\n",
             f"-- H1 S0 v1: ONE creation day {day}; event enumeration, NO returns. Rendered by build_h1_s0.py render_v1.\n"
             "-- v1 vs v0: no solana.transactions join (run V_failed_evt_check first); IF() instead of FILTER in OVER();\n"
             "-- numeric-seconds RANGE; is_mayhem flag; case fixture mints always output (compare h1_s0_fixture_expected.csv).\n")
    s = _sub(s, "-- One successful-transaction join is explicit; its raw-table scan cost is unknown.\n",
             "-- Success filtering relies on decoded event tables excluding failed txs (F60 + V_failed_evt_check).\n")
    s = _sub(s, f"""successful_txs AS (
    SELECT x.* FROM txs x
    JOIN solana.transactions t ON t.id = x.sig
        AND t.block_date BETWEEN DATE '{day}' AND DATE '{end}'
        AND t.success = true
),
""", "")
    s = _sub(s, """        min(ts) FILTER (WHERE is_create) OVER (PARTITION BY mint) AS created_at,
        bool_or(is_sol_create) OVER (PARTITION BY mint) AS is_sol
    FROM successful_txs""", """        min(IF(is_create, ts)) OVER (PARTITION BY mint) AS created_at,
        bool_or(is_sol_create) OVER (PARTITION BY mint) AS is_sol
    FROM txs""")
    s = _sub(s, "    SELECT *, bad_rows + IF(ts <> clock_ts, 1, 0) AS bad_clock_rows\n",
             "    SELECT *, bad_rows + IF(ts <> clock_ts, 1, 0) AS bad_clock_rows, to_unixtime(clock_ts) AS clock_s\n")
    for col in ("buy_lamports", "bad_clock_rows"):
        s = _sub(s, f"        sum({col}) OVER (PARTITION BY mint ORDER BY clock_ts RANGE BETWEEN INTERVAL '30' MINUTE PRECEDING AND CURRENT ROW)\n"
                    f"          - sum({col}) OVER (PARTITION BY mint, clock_ts ORDER BY slot, txi, sig",
                 f"        sum({col}) OVER (PARTITION BY mint ORDER BY clock_s RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW)\n"
                 f"          - sum({col}) OVER (PARTITION BY mint, clock_s ORDER BY slot, txi, sig")
    s = _sub(s, "WITH\ncohort AS (", f"""WITH
mayhem AS (
    SELECT mint, bool_or(COALESCE(CAST(is_mayhem_mode AS varchar) IN ('true', '1'), false)) AS is_mayhem
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '{day}'
    GROUP BY 1
),
cohort AS (""")
    s = _sub(s, """        p.signal_venue, p.signal_actors, p.signal_buy_lamports, p.signal_pre30_lamports
    FROM per_coin p
)""", """        p.signal_venue, p.signal_actors, p.signal_buy_lamports, p.signal_pre30_lamports,
        COALESCE(m.is_mayhem, false) AS is_mayhem
    FROM per_coin p
    LEFT JOIN mayhem m ON m.mint = p.mint
)""")
    s = _sub(s, """       IF(max(n_eligible_txs) > 0,
          IF(max(n_bad_txs) > 0, 'candidate_needs_data_review', 'candidate'), 'data_quality')) AS row_type,""",
             """       IF(max(n_eligible_txs) > 0,
          IF(max(n_bad_txs) > 0, 'candidate_needs_data_review', 'candidate'),
          IF(max(n_bad_txs) > 0, 'data_quality', 'fixture'))) AS row_type,
    IF(grouping(mint) = 0, arbitrary(is_mayhem)) AS is_mayhem,""")
    s = _sub(s, "    sum(COALESCE(n_eligible_txs, 0)) AS n_eligible_txs,\n",
             "    sum(COALESCE(n_eligible_txs, 0)) AS n_eligible_txs,\n"
             "    sum(COALESCE(n_decoded_txs, 0)) AS n_decoded_txs,\n"
             "    count_if(n_eligible_txs > 0 AND is_mayhem) AS n_triggered_mayhem,\n")
    fx = FIXTURES.get(day, [])
    having_fx = (" OR mint IN (" + ", ".join(f"'{m}'" for m in fx) + ")") if fx else ""
    s = _sub(s, "HAVING grouping(mint) = 1 OR max(n_eligible_txs) > 0 OR max(n_bad_txs) > 0\n",
             f"HAVING grouping(mint) = 1 OR max(n_eligible_txs) > 0 OR max(n_bad_txs) > 0{having_fx}\n")
    s = _sub(s, "    -- and SOL scope are established below, after the single success join.\n",
             "    -- and SOL scope are established below from decoded creation events.\n")
    assert "JOIN solana.transactions" not in s and "FILTER (WHERE is_create)" not in s and "RANGE BETWEEN INTERVAL" not in s
    return s


def main_v1():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 6, 1))
    args = parser.parse_args()
    target = Path(__file__).parent / "sql" / f"H1_S0_v1_{args.day.isoformat()}.sql"
    target.write_text(render_v1(args.day))
    print(target)


# ---------------------------------------------------------------------------
# v1 range (2026-09-21, executor): the SAME v1 query over several consecutive creation days in one execution.
# Only changes vs render_v1(d1): creation-day filters become a BETWEEN range, event partitions end at d2+2,
# fixture mints of all days are output, and a per-creation-day summary row (row_type 'day_summary') is added.
def render_v1_range(d1: date, d2: date) -> str:
    assert date(2026, 6, 1) <= d1 <= d2 <= date(2026, 6, 7)
    s = render_v1(d1)
    e1, e2 = d1 + timedelta(days=2), d2 + timedelta(days=2)
    s = _sub(s, f"-- H1 S0 v1: ONE creation day {d1}; event enumeration, NO returns. Rendered by build_h1_s0.py render_v1.\n",
             f"-- H1 S0 v1 RANGE: creation days {d1} .. {d2}; event enumeration, NO returns. Rendered by build_h1_s0.py render_v1_range.\n"
             "-- Same v1 logic per coin; adds per-creation-day summary rows (row_type day_summary).\n")
    s = _sub(s, f"-- Scan partitions: {d1} .. {e1}; per-mint end = created_at + 1470 minutes.\n",
             f"-- Scan partitions: {d1} .. {e2}; per-mint end = created_at + 1470 minutes.\n")
    n = s.count(f"DATE '{d1}' AND DATE '{e1}'")
    assert n >= 8, n
    s = s.replace(f"DATE '{d1}' AND DATE '{e1}'", f"DATE '{d1}' AND DATE '{e2}'")
    n = s.count(f"evt_block_date = DATE '{d1}'")
    assert n == 3, n  # mayhem, cohort, creation branch
    s = s.replace(f"evt_block_date = DATE '{d1}'", f"evt_block_date BETWEEN DATE '{d1}' AND DATE '{d2}'")
    s = _sub(s, "    SELECT p.mint, p.created_at, p.is_sol,\n", "    SELECT p.mint, CAST(p.created_at AS date) AS cday, p.created_at, p.is_sol,\n")
    s = _sub(s, "    IF(grouping(mint) = 1, '__SUMMARY__', mint) AS mint,\n    IF(grouping(mint) = 1, 'summary',\n",
             "    CASE WHEN grouping(mint) = 0 THEN mint WHEN grouping(cday) = 0 THEN '__DAY__' ELSE '__SUMMARY__' END AS mint,\n"
             "    IF(grouping(mint) = 1, IF(grouping(cday) = 0, 'day_summary', 'summary'),\n")
    s = _sub(s, "    IF(grouping(mint) = 0, arbitrary(is_mayhem)) AS is_mayhem,\n",
             "    IF(grouping(mint) = 0, arbitrary(is_mayhem)) AS is_mayhem,\n"
             "    CASE WHEN grouping(cday) = 0 THEN cday WHEN grouping(mint) = 0 THEN arbitrary(cday) END AS cday,\n")
    s = _sub(s, "GROUP BY GROUPING SETS ((mint), ())\n", "GROUP BY GROUPING SETS ((mint), (cday), ())\n")
    fx = [m for d, ms in FIXTURES.items() if d1 <= d <= d2 for m in ms]
    old_having = [l for l in s.split("\n") if l.startswith("HAVING ")]
    assert len(old_having) == 1
    having = "HAVING grouping(mint) = 1 OR max(n_eligible_txs) > 0 OR max(n_bad_txs) > 0"
    if fx:
        having += " OR mint IN (" + ", ".join(f"'{m}'" for m in fx) + ")"
    s = s.replace(old_having[0], having)
    s = _sub(s, "ORDER BY row_type DESC, signal_time, mint\n", "ORDER BY row_type DESC, cday, signal_time, mint\n")
    return s

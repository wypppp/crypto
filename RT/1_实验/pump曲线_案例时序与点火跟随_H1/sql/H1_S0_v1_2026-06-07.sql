-- H1 S0 v1: ONE creation day 2026-06-07; event enumeration, NO returns. Rendered by build_h1_s0.py render_v1.
-- v1 vs v0: no solana.transactions join (run V_failed_evt_check first); IF() instead of FILTER in OVER();
-- numeric-seconds RANGE; is_mayhem flag; case fixture mints always output (compare h1_s0_fixture_expected.csv).
-- DRAFT: not executed on Dune. First validate table/column binding and fixtures.
-- Scan partitions: 2026-06-07 .. 2026-06-09; per-mint end = created_at + 1470 minutes.
-- There is NO SQL credit stop. Set/verify the platform per-execution cost cap.
-- Amounts are lamports: curve sol_amount; AMM quote_amount_in_with_lp_fee.
-- The latter was checked against cached raw BuyEvents and pool balance deltas.
-- Deposit/Withdraw decoded-table availability still needs Dune binding validation.
-- Success filtering relies on decoded event tables excluding failed txs (F60 + V_failed_evt_check).
-- Pool scope: pump curve + pump-created index=0 PumpSwap pools, not every venue.
-- One heavy events -> txs -> windows -> per_coin chain; no returns/30d scan.
WITH
mayhem AS (
    SELECT mint, bool_or(COALESCE(CAST(is_mayhem_mode AS varchar) IN ('true', '1'), false)) AS is_mayhem
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '2026-06-07'
    GROUP BY 1
),
cohort AS (
    SELECT e.mint, min(e.evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent e
    WHERE e.evt_block_date = DATE '2026-06-07'
    GROUP BY 1
),
creation_mints AS (
    -- This small lookup deliberately includes all quotes. Successful creation
    -- and SOL scope are established below from decoded creation events.
    SELECT mint, created_at FROM cohort
),
pools AS (
    SELECT pool, base_mint AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09' AND mint IN (SELECT mint FROM creation_mints)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(e."user" AS varchar),
           TRY_CAST(e.quote_amount_in_with_lp_fee AS BIGINT), 0, 0, 0
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(e."user" AS varchar), BIGINT '0', 1, 0, 0
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_depositevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index,
           e.evt_tx_id, 'pool', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
    UNION ALL
    SELECT mint, evt_block_time, evt_block_slot, evt_tx_index,
           evt_tx_id, 'migration', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09' AND mint IN (SELECT mint FROM creation_mints)
    UNION ALL
    SELECT base_mint, evt_block_time, evt_block_slot, evt_tx_index,
           evt_tx_id, 'pool_create', CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09' AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT mint, evt_block_time, evt_block_slot, evt_tx_index, evt_tx_id,
           IF(quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111',
              'creation_sol', 'creation_other'),
           CAST(NULL AS varchar), BIGINT '0', 0, 1, 0
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '2026-06-07'
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
dated AS (
    SELECT *,
        min(IF(is_create, ts)) OVER (PARTITION BY mint) AS created_at,
        bool_or(is_sol_create) OVER (PARTITION BY mint) AS is_sol
    FROM txs
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
    SELECT *, bad_rows + IF(ts <> clock_ts, 1, 0) AS bad_clock_rows, to_unixtime(clock_ts) AS clock_s
    FROM sequenced
),
windowed AS (
    -- A monotone prefix clock prevents a later slot with a regressed blockTime
    -- leaking into an earlier event's RANGE window. Regressed rows are flagged.
    SELECT *,
        sum(buy_lamports) OVER (PARTITION BY mint ORDER BY clock_s RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW)
          - sum(buy_lamports) OVER (PARTITION BY mint, clock_s ORDER BY slot, txi, sig ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS pre30_buy_lamports,
        sum(bad_clock_rows) OVER (PARTITION BY mint ORDER BY clock_s RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW)
          - sum(bad_clock_rows) OVER (PARTITION BY mint, clock_s ORDER BY slot, txi, sig ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS pre30_bad_rows
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
        p.signal_venue, p.signal_actors, p.signal_buy_lamports, p.signal_pre30_lamports,
        COALESCE(m.is_mayhem, false) AS is_mayhem
    FROM per_coin p
    LEFT JOIN mayhem m ON m.mint = p.mint
)
SELECT
    IF(grouping(mint) = 1, '__SUMMARY__', mint) AS mint,
    IF(grouping(mint) = 1, 'summary',
       IF(max(n_eligible_txs) > 0,
          IF(max(n_bad_txs) > 0, 'candidate_needs_data_review', 'candidate'),
          IF(max(n_bad_txs) > 0, 'data_quality', 'fixture'))) AS row_type,
    IF(grouping(mint) = 0, arbitrary(is_mayhem)) AS is_mayhem,
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
    sum(COALESCE(n_decoded_txs, 0)) AS n_decoded_txs,
    count_if(n_eligible_txs > 0 AND is_mayhem) AS n_triggered_mayhem,
    sum(COALESCE(n_bad_txs, 0)) AS n_bad_txs,
    sum(COALESCE(n_large_mixed_txs, 0)) AS n_large_mixed_txs
FROM joined
GROUP BY GROUPING SETS ((mint), ())
HAVING grouping(mint) = 1 OR max(n_eligible_txs) > 0 OR max(n_bad_txs) > 0
ORDER BY row_type DESC, signal_time, mint

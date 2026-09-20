-- Review draft, not executed. Total network fee among transactions with a decoded
-- pump trade event in this window; NOT exact priority fees or a strategy cost estimate.
-- required_signatures is documented by Dune. fee % 5000 cannot identify signatures.
-- Exact priority attribution additionally needs precompile/fee-rule verification.
-- Event selection does not enumerate all attempted/failed/unlanded orders.
-- One date and one hour limit the logical scope; neither guarantees a credit ceiling.
WITH ev AS (
    SELECT DISTINCT evt_tx_id AS tx_id
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date = DATE '2026-06-01'
      AND evt_block_time >= TIMESTAMP '2026-06-01 12:00:00'
      AND evt_block_time < TIMESTAMP '2026-06-01 13:00:00'
), tx AS (
    SELECT id, fee, success, required_signatures, compute_units_consumed
    FROM solana.transactions
    WHERE block_date = DATE '2026-06-01'
      AND block_time >= TIMESTAMP '2026-06-01 12:00:00'
      AND block_time < TIMESTAMP '2026-06-01 13:00:00'
)
SELECT t.required_signatures,
       count(*) AS n_event_transactions,
       count(t.id) AS n_matched,
       count_if(t.id IS NULL) AS n_unmatched,
       count_if(t.success = false) AS n_failed_with_event,
       count_if(t.id IS NOT NULL AND t.success IS NULL) AS n_unknown_success,
       count_if(t.id IS NOT NULL AND t.fee IS NULL) AS n_unknown_fee,
       approx_percentile(t.fee, 0.10) AS total_fee_lamports_p10,
       approx_percentile(t.fee, 0.50) AS total_fee_lamports_p50,
       approx_percentile(t.fee, 0.90) AS total_fee_lamports_p90,
       approx_percentile(t.fee, 0.99) AS total_fee_lamports_p99,
       approx_percentile(t.compute_units_consumed, 0.50) AS cu_p50
FROM ev
LEFT JOIN tx t ON t.id = ev.tx_id
GROUP BY t.required_signatures
ORDER BY t.required_signatures

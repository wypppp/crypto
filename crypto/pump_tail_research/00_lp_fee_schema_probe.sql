-- Header-only schema probes for the decoded PumpSwap swap events.
-- The two tables are queried separately because their event payloads differ.
SELECT *
FROM pumpdotfun_solana.pump_amm_evt_sellevent
WHERE evt_block_date = DATE '2026-07-24'
LIMIT 1

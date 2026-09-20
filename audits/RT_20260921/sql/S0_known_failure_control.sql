-- Review draft, not executed. Replaces the inference "zero failures in one hour => table excludes failures".
-- Fixed positive failure control: RPC scan_failed_amm_27.json (PumpSwap CPI succeeded,
-- parent transaction later failed). Success control was already used in DQ-1M F60.
-- This checks these two records only, not historical completeness or our strategy's failure rate.
-- Partition bounded to one date; actual billed scan cost is not yet measured.
WITH controls (label, tx_id, expected_success) AS (
    VALUES
      ('known_failed_parent', '5wXqz4uo9Rfk5UnmmKNvYHz2C1edcqwJRy2wBokH6PDrY5Vw8yu6Vi317j9sgBKPLHqGm4A395EY3gzhhdUoJZK7', false),
      ('known_success', '2pjEDLDhH4hkTiQcdNKiuaMtSA2GKZtkVwyqQxNuLANZKtCbKfsTgBSm4kj4ue4iM311pJ9J5KwF8wVVvGn1jeuT', true)
), tx AS (
    SELECT id, success, fee, required_signatures
    FROM solana.transactions
    WHERE block_date = DATE '2026-09-15'
      AND id IN (SELECT tx_id FROM controls)
), calls AS (
    SELECT tx_id,
           count(*) AS n_instruction_rows,
           count_if(tx_success = false) AS n_failed_parent_rows,
           count_if(executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA') AS n_pumpswap_rows
    FROM solana.instruction_calls
    WHERE block_date = DATE '2026-09-15'
      AND tx_id IN (SELECT tx_id FROM controls)
    GROUP BY tx_id
)
SELECT c.label, c.tx_id, c.expected_success,
       t.id IS NOT NULL AS found_in_transactions, t.success,
       t.fee AS total_network_fee_lamports, t.required_signatures,
       COALESCE(i.n_instruction_rows, 0) AS n_instruction_rows,
       COALESCE(i.n_failed_parent_rows, 0) AS n_failed_parent_rows,
       COALESCE(i.n_pumpswap_rows, 0) AS n_pumpswap_rows
FROM controls c
LEFT JOIN tx t ON t.id = c.tx_id
LEFT JOIN calls i ON i.tx_id = c.tx_id
ORDER BY c.label

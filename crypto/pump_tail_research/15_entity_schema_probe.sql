-- Read-only schema discovery for the preregistered entity-feature E1 stage.
-- This returns metadata only; it does not inspect labels or outcomes.

SELECT
    table_schema,
    table_name,
    array_agg(column_name ORDER BY ordinal_position) AS columns
FROM information_schema.columns
WHERE
    (table_schema = 'pumpdotfun_solana' AND table_name = 'pump_evt_tradeevent')
    OR (table_schema = 'tokens_solana' AND table_name = 'transfers')
    OR lower(table_name) LIKE '%jito%'
    OR lower(table_name) LIKE '%bundle%'
    OR (
        table_schema IN ('solana', 'system_solana')
        AND lower(table_name) LIKE '%transfer%'
    )
GROUP BY 1, 2
ORDER BY 1, 2

-- Targeted, low-cost schema probe after the broad information_schema scan was cancelled.
SELECT
    table_schema,
    table_name,
    array_agg(column_name ORDER BY ordinal_position) AS columns
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('pumpdotfun_solana', 'pump_evt_tradeevent'),
    ('tokens_solana', 'transfers'),
    ('solana', 'transactions'),
    ('solana', 'account_activity'),
    ('system_solana', 'system_call_transfer')
)
GROUP BY 1, 2
ORDER BY 1, 2

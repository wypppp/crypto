SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pumpdotfun_solana'
  AND (
      lower(table_name) LIKE '%pump%swap%'
      OR lower(table_name) LIKE '%buy%event%'
      OR lower(table_name) LIKE '%sell%event%'
      OR lower(table_name) LIKE '%create%pool%'
      OR lower(table_name) LIKE '%migrate%'
  )
ORDER BY table_name, ordinal_position

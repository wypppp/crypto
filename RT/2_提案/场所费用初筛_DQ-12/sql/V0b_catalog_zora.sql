-- DQ-12 V0b：Zora（Base）目录发现。与 Meteora 是不同的问题，见卡片说明。
SELECT table_schema, table_name, count(*) AS n_cols,
       array_join(array_agg(column_name ORDER BY column_name), ', ') AS cols
FROM information_schema.columns
WHERE lower(table_schema) LIKE '%zora%'
  AND (lower(table_name) LIKE '%swap%' OR lower(table_name) LIKE '%coin%' OR lower(table_name) LIKE '%trade%')
GROUP BY 1, 2
ORDER BY 1, 2

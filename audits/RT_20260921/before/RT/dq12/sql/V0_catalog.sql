-- DQ-12 V0：目录发现（先跑这条，几乎不扫数据）
-- 目的：拿到 Meteora DBC 在 Dune 上的确切表名与列名。不猜表名，避免浪费一次运行。
-- information_schema 只读元数据，不扫事件数据，成本应接近 0。
SELECT table_schema, table_name, count(*) AS n_cols,
       array_join(array_agg(column_name ORDER BY column_name), ', ') AS cols
FROM information_schema.columns
WHERE (
        lower(table_schema) LIKE '%meteora%'
     OR lower(table_schema) LIKE '%dynamic_bonding%'
     OR lower(table_schema) LIKE '%dbc%'
      )
  AND lower(table_name) LIKE '%swap%'
GROUP BY 1, 2
ORDER BY 1, 2

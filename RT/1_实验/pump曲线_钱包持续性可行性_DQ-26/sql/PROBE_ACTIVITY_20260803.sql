/* DQ-26 探针：solana.account_activity 的费用与字段（逐笔 SOL 净变动、代币账户余额）。
   只读 2026-08-03 一天；5 个地址（08-03 冒烟 W 中初排前 5，只用于测费用与字段，不用于排名）。 */
WITH sel(usr) AS (
    SELECT usr FROM (VALUES
        ('DYJTG67gKdYfjRQvfemGzLrGidmPbLT5EPTnJ5RuVrJk'),
        ('4feBVTDC2ZMZCcr52cwCimjGt1WvGodPmMPneeq5tVSh'),
        ('6h4yPA1spMXnkV57vUALqnsRFeABv1FD9GkQmHL7qAo1'),
        ('G6qwt2o4KrFtBekYuQsoTTa2xz1d6Ur33QBBbyTa8E1B'),
        ('BQ8HfgWgkzmtEwnS4ACmdkDFNhaeXqLb3hFsasqjLVjn')
    ) AS v(usr)
)
SELECT
    IF(a.token_mint_address IS NULL, 'SOL', 'TOKEN') AS kind,
    COALESCE(a.token_balance_owner, a.address) AS owner,
    count(*) AS n_rows,
    count(DISTINCT a.tx_id) AS n_tx,
    count_if(a.signed) AS n_signed,
    count_if(NOT a.tx_success) AS n_failed,
    sum(a.balance_change) / 1e9 AS sol_change,
    count(DISTINCT a.token_mint_address) AS n_mints,
    min(a.block_time) AS t0, max(a.block_time) AS t1
FROM solana.account_activity a
WHERE a.block_time >= TIMESTAMP '2026-08-03 00:00:00'
  AND a.block_time < TIMESTAMP '2026-08-04 00:00:00'
  AND (a.address IN (SELECT usr FROM sel) OR a.token_balance_owner IN (SELECT usr FROM sel))
GROUP BY 1, 2

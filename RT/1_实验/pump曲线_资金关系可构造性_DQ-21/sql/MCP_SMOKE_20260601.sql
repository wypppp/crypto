/* Dune 官方 MCP 冒烟（2026-09-30）：2026-06-01 00:00–01:00 UTC 的 pump 曲线成交笔数。
   只读开发窗口 06-01 一个日期分区；表名与列名（evt_block_date、evt_block_time、mint）照抄 S1 双口径 SQL。 */
SELECT
    count(*) AS n_trades,
    count(DISTINCT mint) AS n_mints,
    min(evt_block_time) AS first_ts,
    max(evt_block_time) AS last_ts
FROM pumpdotfun_solana.pump_evt_tradeevent
WHERE evt_block_date = DATE '2026-06-01'
  AND evt_block_time >= TIMESTAMP '2026-06-01 00:00:00'
  AND evt_block_time < TIMESTAMP '2026-06-01 01:00:00'

-- DQ-43 PROBE01（10-13）：Dune 新账户能否执行查询、能否读 pump 解码表。只数行，不读任何字段内容。
-- 日期取开发周（2026-06-02，周二；weeks.py：06-01 周为开发周），早于止日。
SELECT 'ok' AS status,
       count(*) AS n_create_events
FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_date = DATE '2026-06-02'

/* DQ-35 v2.2 探针（10-05，执行模型）：同一小时解码事件表的买卖笔数（核两种原始来源的覆盖率）；只输出计数。 */
SELECT (SELECT count(*) FROM pumpdotfun_solana.pump_amm_evt_buyevent
         WHERE evt_block_date = DATE '2026-09-23'
           AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 13:00:00') AS n_buy,
       (SELECT count(*) FROM pumpdotfun_solana.pump_amm_evt_sellevent
         WHERE evt_block_date = DATE '2026-09-23'
           AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 13:00:00') AS n_sell

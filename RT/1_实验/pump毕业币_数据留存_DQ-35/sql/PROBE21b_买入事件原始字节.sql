/* DQ-35 v2.1 探针（10-04，执行模型；总控第十八轮第一节第 1 条）：买入事件的原始字节，按新版 IDL 解码 cashback／回购费。
   范围：2026-09-23（DQ-37 开发周）当日由 pump 迁移创建的池，12:00～12:10 的 buy／sell 调用；只看字段布局与费用值，不看价格或收益。
   做法：Anchor event-CPI 的自调用内层指令 data＝8 字节 event-CPI 标签 e445a52e51cb9a1d＋8 字节事件判别符＋borsh 序列化的事件。
   不扫 solana.instruction_calls（全表 156 TB），改从解码调用表的 inner_instructions 取自调用的 data（base58）；
   另输出同一批交易在解码事件表里的行，离线按（交易、数值）逐字段对齐偏移，再读出解码表没有的尾部字段。 */
WITH
pl AS (
    SELECT DISTINCT pool
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date = DATE '2026-09-23'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
calls AS (
    SELECT 'B' AS side, call_tx_id AS tx_id, call_block_slot AS slot, call_outer_instruction_index AS oix,
           call_inner_instruction_index AS iix, account_pool AS pool, call_inner_instructions AS ins
    FROM pumpdotfun_solana.pump_amm_call_buy
    WHERE call_block_date = DATE '2026-09-23'
      AND call_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND call_block_time < TIMESTAMP '2026-09-23 12:10:00'
      AND account_pool IN (SELECT pool FROM pl)
    UNION ALL
    SELECT 'S', call_tx_id, call_block_slot, call_outer_instruction_index, call_inner_instruction_index, account_pool,
           call_inner_instructions
    FROM pumpdotfun_solana.pump_amm_call_sell
    WHERE call_block_date = DATE '2026-09-23'
      AND call_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND call_block_time < TIMESTAMP '2026-09-23 12:10:00'
      AND account_pool IN (SELECT pool FROM pl)
),
raw AS (
    SELECT c.side, c.tx_id, c.slot, c.oix, c.iix, c.pool, t.k AS ins_ord,
           length(from_base58(t.data)) AS nbytes, to_hex(from_base58(t.data)) AS raw,
           row_number() OVER (PARTITION BY c.side ORDER BY c.slot, c.tx_id, c.oix, c.iix, t.k) AS rn
    FROM calls c
    CROSS JOIN UNNEST(transform(c.ins, x -> CAST(ROW(x.data, x.executing_account) AS ROW(data varchar, ea varchar))))
         WITH ORDINALITY AS t(data, ea, k)
    WHERE t.ea = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
      AND bytearray_substring(from_base58(t.data), 1, 8) = 0xe445a52e51cb9a1d
),
rs AS (SELECT * FROM raw WHERE (side = 'B' AND rn <= 40) OR (side = 'S' AND rn <= 15)),
dec AS (
    SELECT 'B' AS side, evt_tx_id AS tx_id, evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix,
           CAST(base_amount_out AS varchar) AS a1, CAST(pool_quote_token_reserves AS varchar) AS a2,
           CAST(lp_fee AS varchar) AS a3, CAST(protocol_fee AS varchar) AS a4,
           CAST(coin_creator_fee AS varchar) AS a5, CAST(user_quote_amount_in AS varchar) AS a6,
           CAST(min_base_amount_out AS varchar) AS a7, ix_name AS a8,
           CAST(NULL AS varchar) AS cb_bps, CAST(NULL AS varchar) AS cb, CAST(NULL AS varchar) AS bb_bps, CAST(NULL AS varchar) AS bb
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-09-23'
      AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 12:10:00'
      AND evt_tx_id IN (SELECT tx_id FROM rs WHERE side = 'B')
    UNION ALL
    SELECT 'S', evt_tx_id, evt_outer_instruction_index, evt_inner_instruction_index,
           CAST(base_amount_in AS varchar), CAST(pool_quote_token_reserves AS varchar),
           CAST(lp_fee AS varchar), CAST(protocol_fee AS varchar),
           CAST(coin_creator_fee AS varchar), CAST(user_quote_amount_out AS varchar),
           CAST(min_quote_amount_out AS varchar), CAST(NULL AS varchar),
           CAST(cashback_fee_basis_points AS varchar), CAST(cashback AS varchar),
           CAST(buyback_fee_basis_points AS varchar), CAST(buyback_fee AS varchar)
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-09-23'
      AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 12:10:00'
      AND evt_tx_id IN (SELECT tx_id FROM rs WHERE side = 'S')
)
SELECT 'raw' AS src, side, tx_id, oix, iix, ins_ord, nbytes, raw,
       NULL AS a1, NULL AS a2, NULL AS a3, NULL AS a4, NULL AS a5, NULL AS a6, NULL AS a7, NULL AS a8,
       NULL AS cb_bps, NULL AS cb, NULL AS bb_bps, NULL AS bb
FROM rs
UNION ALL
SELECT 'dec', side, tx_id, oix, iix, NULL, NULL, NULL, a1, a2, a3, a4, a5, a6, a7, a8, cb_bps, cb, bb_bps, bb
FROM dec
ORDER BY 2, 3, 1, 4, 5

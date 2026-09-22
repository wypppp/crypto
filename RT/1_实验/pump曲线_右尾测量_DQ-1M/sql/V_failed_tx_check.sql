-- DQ-1M · V：Dune 解码事件表是否收录失败交易的事件
-- 只扫 1 个单日分区，预计 <1 credit。
-- 背景（F59）：链上抽查发现失败交易仍可能带事件——下面第一笔 PumpSwap 交易在后续指令报错，
-- 但其 SellEvent 已经发出。若该交易出现在 Dune 表中，说明表内混有"从未真正成交"的状态，
-- 测量需要额外按交易成功与否过滤；若只有对照交易出现，则说明 Dune 已过滤。
WITH ev AS (
    SELECT 'sell' AS side, evt_tx_id
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-09-15'
      AND evt_tx_id IN (
          '5wXqz4uo9Rfk5UnmmKNvYHz2C1edcqwJRy2wBokH6PDrY5Vw8yu6Vi317j9sgBKPLHqGm4A395EY3gzhhdUoJZK7',
          '2pjEDLDhH4hkTiQcdNKiuaMtSA2GKZtkVwyqQxNuLANZKtCbKfsTgBSm4kj4ue4iM311pJ9J5KwF8wVVvGn1jeuT')
    UNION ALL
    SELECT 'buy' AS side, evt_tx_id
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-09-15'
      AND evt_tx_id IN (
          '5wXqz4uo9Rfk5UnmmKNvYHz2C1edcqwJRy2wBokH6PDrY5Vw8yu6Vi317j9sgBKPLHqGm4A395EY3gzhhdUoJZK7',
          '2pjEDLDhH4hkTiQcdNKiuaMtSA2GKZtkVwyqQxNuLANZKtCbKfsTgBSm4kj4ue4iM311pJ9J5KwF8wVVvGn1jeuT')
)
SELECT
    CASE WHEN evt_tx_id LIKE '5wXqz4uo%' THEN '失败交易（链上确认已发出 SellEvent）'
         ELSE '对照：成功交易' END AS tx_kind,
    side,
    count(*) AS n_rows
FROM ev
GROUP BY 1, 2
ORDER BY 1, 2

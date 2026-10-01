/* DQ-28 同槽买家拆分 C2 创建者资金往来（卡片_v1.md）；由 sql/build_ss_sql.py 生成。
   币：2026-08-04～2026-08-05 创建的 SOL 计价 pump 币；格＝创建 slot 内有买入的非创建者钱包。原生 SOL 只读 2026-07-28～2026-08-05 的分区；成交读 2026-08-04～2026-08-12。 */
WITH
cr AS (
    SELECT mint, min(evt_block_slot) AS cslot, min(evt_block_time) AS created_at,
           max(CAST("user" AS varchar)) AS dev
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-05'
      AND (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
    GROUP BY 1
),
ev AS (
    SELECT
        t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, t.mint, c.dev, c.created_at,
        max(IF(COALESCE(t.is_buy, t.isBuy) AND t.evt_block_slot = c.cslot
               AND CAST(t."user" AS varchar) <> c.dev, 1, 0))
            OVER (PARTITION BY t.mint, CAST(t."user" AS varchar)) AS is_cell
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN cr c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
),
tt AS (
    SELECT DISTINCT tx_id, usr, mint, dev, created_at FROM ev WHERE is_cell = 1
),
cell AS (
    SELECT DISTINCT mint, usr, dev, created_at FROM tt
),
nt AS (
    SELECT c.mint, c.usr, t.amount_display AS amt, 1 AS dev_to_usr, t.block_time, c.created_at
    FROM cell c
    JOIN tokens_solana.transfers t ON t.from_owner = c.dev AND t.to_owner = c.usr
    WHERE t.block_date BETWEEN DATE '2026-07-28' AND DATE '2026-08-05'
      AND t.token_version = 'native' AND t.action = 'transfer'
    UNION ALL
    SELECT c.mint, c.usr, t.amount_display, 0, t.block_time, c.created_at
    FROM cell c
    JOIN tokens_solana.transfers t ON t.from_owner = c.usr AND t.to_owner = c.dev
    WHERE t.block_date BETWEEN DATE '2026-07-28' AND DATE '2026-08-05'
      AND t.token_version = 'native' AND t.action = 'transfer'
)
SELECT
    mint, usr,
    count(*) AS n_link,
    sum(amt) AS link_sol,
    sum(dev_to_usr) AS n_dev_to_usr
FROM nt
WHERE block_time <= created_at AND block_time >= created_at - INTERVAL '7' DAY
GROUP BY 1, 2

/* DQ-28 同槽买家拆分 B 网络费（卡片_v1.md）；由 sql/build_ss_sql.py 生成。
   币：2026-08-04～2026-08-05 创建的 SOL 计价 pump 币；格＝创建 slot 内有买入的非创建者钱包。只读 2026-08-04～2026-08-12 的分区。 */
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
tn AS (
    SELECT tx_id, usr, mint, count(*) OVER (PARTITION BY tx_id, usr) AS n_mint FROM tt
)
SELECT
    tn.mint, tn.usr,
    count(*) AS n_tx,
    count(g.tx_hash) AS n_fee_found,
    sum(IF(g.signer = tn.usr, g.tx_fee / tn.n_mint, 0)) AS fee_sol,
    count_if(g.signer IS NOT NULL AND g.signer <> tn.usr) AS n_other_signer
FROM tn
LEFT JOIN gas_solana.fees g
  ON g.tx_hash = tn.tx_id AND g.block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
GROUP BY 1, 2

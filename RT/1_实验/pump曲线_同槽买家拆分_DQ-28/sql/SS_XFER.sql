/* DQ-28 同槽买家拆分 C1 小费与筹码转移（卡片_v1.md）；由 sql/build_ss_sql.py 生成。
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
),
tr AS (
    SELECT t.tx_id, t.token_mint_address AS mint, t.token_version, t.from_owner, t.to_owner, t.amount_display AS amt
    FROM tokens_solana.transfers t
    WHERE t.block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
      AND t.from_owner <> t.to_owner
      AND (
          (t.token_version = 'native' AND t.action = 'transfer' AND t.to_owner IN ('DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh', 'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL', '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5', 'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe', 'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49', 'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY', '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT', 'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt')
           AND t.tx_id IN (SELECT tx_id FROM tn))
          OR (t.token_mint_address IN (SELECT mint FROM cr)
              AND (t.from_owner IN (SELECT usr FROM tn) OR t.to_owner IN (SELECT usr FROM tn)))
      )
),
tip AS (
    SELECT tn.mint, tn.usr, sum(tr.amt / tn.n_mint) AS tip_sol, count(*) AS n_tip
    FROM tr
    JOIN tn ON tn.tx_id = tr.tx_id AND tn.usr = tr.from_owner
    WHERE tr.token_version = 'native'
    GROUP BY 1, 2
),
tok AS (
    SELECT s.mint, s.usr, sum(IF(s.sgn < 0, s.amt, 0)) AS tok_out, sum(IF(s.sgn > 0, s.amt, 0)) AS tok_in
    FROM (
        SELECT tr.mint, tr.from_owner AS usr, -1 AS sgn, tr.amt FROM tr WHERE tr.token_version <> 'native'
        UNION ALL
        SELECT tr.mint, tr.to_owner, 1, tr.amt FROM tr WHERE tr.token_version <> 'native'
    ) s
    GROUP BY 1, 2
)
SELECT
    COALESCE(tip.mint, tok.mint) AS mint, COALESCE(tip.usr, tok.usr) AS usr,
    tip.tip_sol, tip.n_tip, tok.tok_out, tok.tok_in
FROM tip
FULL OUTER JOIN tok ON tok.mint = tip.mint AND tok.usr = tip.usr

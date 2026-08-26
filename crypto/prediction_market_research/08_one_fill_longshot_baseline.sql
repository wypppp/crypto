-- Exact-outcome baseline for the simplest non-speed strategy:
-- wallets in the May 1-7 first-observed v2 cohort that made exactly one v2
-- OrderFilled event during their 90-day horizon.  One row per wallet.
--
-- This creates a denominator for isolated long-odds winners.  It is not a
-- claim that a wallet equals a new human, nor that the observed trade was the
-- owner's only off-chain or cross-wallet exposure.

WITH
v2_first AS (
    SELECT maker AS wallet, min(evt_block_time) AS first_trade_time
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2026-04-01' AND DATE '2026-05-07'
    GROUP BY 1
),
candidate AS (
    SELECT
        wallet,
        first_trade_time,
        first_trade_time + INTERVAL '90' DAY AS horizon_time
    FROM v2_first
    WHERE first_trade_time >= TIMESTAMP '2026-05-01 00:00:00'
      AND first_trade_time < TIMESTAMP '2026-05-08 00:00:00'
),
old_seen AS (
    SELECT DISTINCT maker AS wallet
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date < DATE '2026-05-01'
      AND maker IN (SELECT wallet FROM candidate)

    UNION

    SELECT DISTINCT maker AS wallet
    FROM polymarket_polygon.negriskctfexchange_evt_orderfilled
    WHERE evt_block_date < DATE '2026-05-01'
      AND maker IN (SELECT wallet FROM candidate)
),
cohort AS (
    SELECT c.*
    FROM candidate c
    LEFT JOIN old_seen o ON o.wallet = c.wallet
    WHERE o.wallet IS NULL
),
v3_users AS (
    SELECT DISTINCT v.maker AS wallet
    FROM polymarket_v3_polygon.exchange_evt_orderfilled v
    JOIN cohort c ON c.wallet = v.maker
    WHERE v.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
      AND v.evt_block_time <= c.horizon_time
),
raw_trades AS (
    SELECT
        c.wallet,
        c.first_trade_time,
        c.horizon_time,
        v.evt_block_time,
        v.evt_tx_hash,
        v.evt_index,
        v.side,
        v.tokenId AS token_id,
        CASE WHEN v.side = 0
            THEN CAST(v.takerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(v.makerAmountFilled AS DOUBLE) / 1e6 END AS qty,
        CASE WHEN v.side = 0
            THEN CAST(v.makerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(v.takerAmountFilled AS DOUBLE) / 1e6 END AS collateral,
        CAST(v.fee AS DOUBLE) / 1e6 AS fee
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled v
    JOIN cohort c ON c.wallet = v.maker
    WHERE v.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
      AND v.evt_block_time >= c.first_trade_time
      AND v.evt_block_time <= c.horizon_time
),
one_fill AS (
    SELECT r.*
    FROM raw_trades r
    JOIN (
        SELECT wallet
        FROM raw_trades
        GROUP BY 1
        HAVING count(*) = 1
    ) n ON n.wallet = r.wallet
    LEFT JOIN v3_users v ON v.wallet = r.wallet
    WHERE v.wallet IS NULL
      AND r.qty > 0
      AND r.collateral >= 0
),
condition_resolutions AS (
    SELECT
        lower(to_hex(conditionId)) AS condition_key,
        max(evt_block_time) AS onchain_resolution_time
    FROM polymarket_polygon.ctf_evt_conditionresolution
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
    GROUP BY 1
),
md_raw AS (
    SELECT
        token_id,
        max_by(condition_id, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS condition_id,
        max_by(question, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS question,
        max_by(tags, coalesce(last_changed_at, TIMESTAMP '1970-01-01')) AS tags,
        max_by(outcome_index, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS outcome_index,
        max_by(settlement_value, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS settlement_value
    FROM polymarket_polygon.market_details
    GROUP BY 1
),
enriched AS (
    SELECT
        o.*,
        m.condition_id,
        m.question,
        m.tags,
        m.outcome_index,
        m.settlement_value,
        r.onchain_resolution_time,
        o.collateral / nullif(o.qty, 0) AS price,
        CASE WHEN o.side = 0
            THEN o.collateral + o.fee
            ELSE greatest(o.qty - o.collateral + o.fee, 0) END AS capital_at_risk,
        CASE WHEN o.side = 0
            THEN m.settlement_value * o.qty - o.collateral - o.fee
            ELSE o.collateral - m.settlement_value * o.qty - o.fee END AS net_profit
    FROM one_fill o
    LEFT JOIN md_raw m ON m.token_id = o.token_id
    LEFT JOIN condition_resolutions r
      ON r.condition_key = replace(lower(m.condition_id), '0x', '')
),
classified AS (
    SELECT
        *,
        CASE
            WHEN contains(tags, 'Crypto Prices') AND contains(tags, '5M') THEN 'crypto_5m'
            WHEN contains(tags, 'Crypto Prices') AND contains(tags, '15M') THEN 'crypto_15m'
            WHEN contains(tags, 'Crypto Prices') THEN 'crypto_other'
            WHEN contains(tags, 'Sports') THEN 'sports'
            WHEN contains(tags, 'Politics') THEN 'politics'
            WHEN contains(tags, 'Finance') OR contains(tags, 'Business')
                THEN 'finance_business'
            ELSE 'other'
        END AS strategy_bucket,
        CASE
            WHEN price < 0.01 THEN 'p_lt_01'
            WHEN price < 0.05 THEN 'p_01_05'
            WHEN price < 0.20 THEN 'p_05_20'
            WHEN price < 0.80 THEN 'p_20_80'
            WHEN price < 0.95 THEN 'p_80_95'
            WHEN price < 0.99 THEN 'p_95_99'
            ELSE 'p_ge_99'
        END AS price_bucket
    FROM enriched
)
SELECT
    to_hex(wallet) AS wallet,
    first_trade_time,
    horizon_time,
    evt_block_time,
    CASE WHEN side = 0 THEN 'BUY' ELSE 'SELL' END AS side,
    CAST(token_id AS VARCHAR) AS token_id,
    condition_id,
    question,
    tags,
    strategy_bucket,
    price_bucket,
    price,
    qty,
    collateral,
    fee,
    capital_at_risk,
    onchain_resolution_time,
    settlement_value,
    onchain_resolution_time IS NOT NULL
        AND onchain_resolution_time <= horizon_time AS resolved_by_horizon,
    CASE WHEN onchain_resolution_time IS NOT NULL
              AND onchain_resolution_time <= horizon_time
        THEN net_profit END AS net_profit,
    CASE WHEN onchain_resolution_time IS NOT NULL
              AND onchain_resolution_time <= horizon_time
              AND capital_at_risk > 0
        THEN (capital_at_risk + net_profit) / capital_at_risk END AS return_multiple
FROM classified
ORDER BY return_multiple DESC NULLS LAST

-- DQ-18 第 1 步 / S0：HOUSE 单币单日字段与扫描成本冒烟。
-- 只核对 Dune dex_solana.trades 的池标识、价格字段和扫描成本；不计算收益。
-- HOUSE mint 来源：https://housecoin.meme/ ，是否为 pump 创建以链上 CreateEvent 为准。
-- 查询前须在 Dune 网页设单次执行成本上限 3 credits。
-- 预估 1–3 credits，仅是事前估算；取消或超时也可能计费。
-- DQ-18 第 1 步 Dune 总预算 10 credits，执行后须先读控制台实际扣费。
-- 输出每个 project × project_program_id × 两侧 vault 一行，至多 30 行；
-- 2025-04-25 的 HOUSE 结果中，project_program_id 与公开池地址吻合；
-- 不能仅凭字段名推断它始终代表程序 ID。
-- 网页查看即可，暂不导出 CSV（导出按大小另计费）。
-- 如本查询碰到 3-credit 上限，请停下，不直接重跑或扩窗。

WITH sample_trades AS (
    SELECT
        project,
        project_program_id,
        token_bought_vault,
        token_sold_vault,
        trade_source,
        block_time,
        tx_id,
        amount_usd,
        fee_tier,
        CASE
            WHEN token_bought_mint_address = 'DitHyRMQiSDhn5cnKMJV2CDDt6sVct96YrECiM49pump'
                THEN token_bought_amount
            ELSE token_sold_amount
        END AS house_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2025-04-01'
      AND block_date = DATE '2025-04-25'
      AND (
          token_bought_mint_address = 'DitHyRMQiSDhn5cnKMJV2CDDt6sVct96YrECiM49pump'
          OR token_sold_mint_address = 'DitHyRMQiSDhn5cnKMJV2CDDt6sVct96YrECiM49pump'
      )
)
SELECT
    project,
    project_program_id,
    token_bought_vault,
    token_sold_vault,
    COUNT(*) AS n_trades,
    COUNT(DISTINCT tx_id) AS n_transactions,
    COUNT_IF(amount_usd IS NULL OR amount_usd <= 0) AS n_bad_usd,
    COUNT_IF(house_amount IS NULL OR house_amount <= 0) AS n_bad_house_amount,
    SUM(amount_usd) AS volume_usd,
    MIN(fee_tier) AS min_curated_fee_tier,
    MAX(fee_tier) AS max_curated_fee_tier,
    MIN(block_time) AS first_time,
    MAX(block_time) AS last_time,
    MIN_BY(tx_id, block_time) AS example_tx_id
FROM sample_trades
GROUP BY 1, 2, 3, 4
ORDER BY volume_usd DESC NULLS LAST
LIMIT 30

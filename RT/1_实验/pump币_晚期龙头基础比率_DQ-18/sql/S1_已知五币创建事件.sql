-- DQ-18 第 1 步 / S1：仅核对五个知名候选是否由 pump.fun 创建。
-- 不查价格、收益或倍数。候选日期只来自 GeckoTerminal 第一页池目录的最早建池日；
-- 池创建 ≠ 币创建，所以查询不到时应记待查，而不是判非 pump 币。
-- 预估查询执行 1–8 credits（未经本表实测），建议网页单次成本上限 15 credits；
-- 用户批准的每条查询硬上限为 50 credits。超出建议额或返回 0 行，先回报，不扩窗重跑。
-- 输出至多五条创建事件；可直接复制结果，不需网页 CSV 导出。

SELECT
    mint,
    name,
    symbol,
    evt_block_time AS created_at,
    evt_block_date AS created_date,
    evt_tx_id AS create_tx,
    creator,
    token_program,
    is_mayhem_mode,
    token_total_supply,
    quote_mint
FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_date IN (
    DATE '2024-10-10',
    DATE '2024-10-17', DATE '2024-10-18',
    DATE '2024-10-30', DATE '2024-10-31',
    DATE '2025-10-12', DATE '2025-10-13',
    DATE '2026-01-15', DATE '2026-01-16'
)
  AND mint IN (
    '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
    'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
    '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump',
    'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
    '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
)
ORDER BY evt_block_time, mint

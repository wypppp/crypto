-- 由 make_sql.py 从 raw/sample.csv 生成，勿手改。只读。平台单次执行成本上限请设 20 credits。
-- 只输出汇总行；运行后先看结果大小（免费档导出 20 credits/MB），>1.5 MB 不下载。
-- DQ-16 Q1（r1）：30 个入样地址 2026-06-07 UTC 的 pump 曲线 / PumpSwap 事件（按 user）与触及这些地址的全部转账。
WITH w(k, wallet) AS (VALUES
    (0, 'BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ'),
    (1, 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x'),
    (2, '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ'),
    (3, 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY'),
    (4, 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me'),
    (5, 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5'),
    (6, 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd'),
    (7, 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr'),
    (8, 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc'),
    (9, 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe'),
    (10, 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj'),
    (11, '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp'),
    (12, 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt'),
    (13, 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB'),
    (14, '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm'),
    (15, '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn'),
    (16, '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx'),
    (17, 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs'),
    (18, '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd'),
    (19, '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK'),
    (20, '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz'),
    (21, 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU'),
    (22, 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk'),
    (23, '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13'),
    (24, 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv'),
    (25, '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9'),
    (26, '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT'),
    (27, 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw'),
    (28, '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX'),
    (29, 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD')
),
ev AS (
    SELECT w.k, 'curve' AS venue, CAST(t.mint AS varchar) AS key, t.evt_tx_id AS sig, t.evt_block_slot AS slot,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           CAST(COALESCE(t.fee_basis_points, 0) + COALESCE(t.creator_fee_basis_points, 0) AS DECIMAL(38,0)) AS bps,
           CAST(NULL AS DECIMAL(38,0)) AS uq
    FROM pumpdotfun_solana.pump_evt_tradeevent t JOIN w ON CAST(t."user" AS varchar) = w.wallet
    WHERE t.evt_block_date = DATE '2026-06-07' AND CAST(t."user" AS varchar) IN ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD')
    UNION ALL
    SELECT w.k, 'amm', CAST(e.pool AS varchar), e.evt_tx_id, e.evt_block_slot, true,
           CAST(e.base_amount_out AS DECIMAL(38,0)), CAST(e.quote_amount_in AS DECIMAL(38,0)), NULL,
           CAST(e.user_quote_amount_in AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e JOIN w ON CAST(e."user" AS varchar) = w.wallet
    WHERE e.evt_block_date = DATE '2026-06-07' AND CAST(e."user" AS varchar) IN ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD')
    UNION ALL
    SELECT w.k, 'amm', CAST(e.pool AS varchar), e.evt_tx_id, e.evt_block_slot, false,
           CAST(e.base_amount_in AS DECIMAL(38,0)), CAST(e.quote_amount_out AS DECIMAL(38,0)), NULL,
           CAST(e.user_quote_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e JOIN w ON CAST(e."user" AS varchar) = w.wallet
    WHERE e.evt_block_date = DATE '2026-06-07' AND CAST(e."user" AS varchar) IN ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD')
),
ev_sig AS (   -- one row per wallet x venue x mint-or-pool x signature
    SELECT k, venue, key, sig, max(slot) AS slot, count(*) AS n_ev,
           sum(IF(is_buy, tok, 0)) AS tok_buy, sum(IF(is_buy, 0, tok)) AS tok_sell,
           sum(CASE WHEN venue = 'curve' AND is_buy THEN -(sol + ceiling(sol * bps / 10000))
                    WHEN venue = 'curve' THEN sol - ceiling(sol * bps / 10000)
                    WHEN is_buy THEN -uq ELSE uq END) AS sol_user
    FROM ev GROUP BY 1, 2, 3, 4
),
tr AS (
    SELECT w.k, w.wallet, x.tx_id, x.block_slot, x.token_mint_address AS mint, x.token_version,
           x.from_owner, x.to_owner, x.tx_signer, CAST(CAST(x.amount AS varchar) AS DECIMAL(38,0)) AS amt
    FROM tokens_solana.transfers x JOIN w ON (x.from_owner = w.wallet OR x.to_owner = w.wallet)
    WHERE x.block_date = DATE '2026-06-07' AND (x.from_owner IN ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD') OR x.to_owner IN ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD'))
),
touch_tx AS (   -- transactions touching the wallet whose first signer is someone else
    SELECT DISTINCT k, tx_id, block_slot FROM tr WHERE tx_signer <> wallet
),
natout AS (
    SELECT k, to_owner, token_version, sum(amt) AS amt, count(DISTINCT tx_id) AS n,
           row_number() OVER (PARTITION BY k ORDER BY sum(amt) DESC) AS rk
    FROM tr WHERE from_owner = wallet AND to_owner NOT IN ('HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe', '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT', '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5', 'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY', 'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49', 'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt', 'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL', 'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh')
      AND (mint IS NULL OR mint = 'So11111111111111111111111111111111111111112') AND to_owner <> wallet
    GROUP BY 1, 2, 3
)
SELECT 'ev' AS kind, k, key, CAST(count(*) AS varchar) AS n, CAST(sum(slot) AS varchar) AS s_slot,
       venue AS v1, CAST(sum(n_ev) AS varchar) AS v2, CAST(sum(tok_buy) AS varchar) AS v3,
       CAST(sum(tok_sell) AS varchar) AS v4, CAST(sum(sol_user) AS varchar) AS v5, CAST(NULL AS varchar) AS v6
FROM ev_sig GROUP BY k, venue, key
UNION ALL
SELECT 'tip', k, NULL, CAST(count(DISTINCT tx_id) AS varchar), NULL, CAST(sum(amt) AS varchar), NULL, NULL, NULL, NULL, NULL
FROM tr WHERE from_owner = wallet AND to_owner IN ('HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe', '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT', '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5', 'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY', 'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49', 'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt', 'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL', 'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh') GROUP BY k
UNION ALL
SELECT 'touchset', k, NULL, CAST(count(*) AS varchar), CAST(sum(block_slot) AS varchar), NULL, NULL, NULL, NULL, NULL, NULL
FROM touch_tx GROUP BY k
UNION ALL
SELECT 'touch', k, COALESCE(mint, 'null') || '|' || COALESCE(token_version, 'null'),
       CAST(count(DISTINCT tx_id) AS varchar), NULL,
       CAST(sum(IF(to_owner = wallet, amt, 0)) AS varchar), CAST(sum(IF(from_owner = wallet, amt, 0)) AS varchar),
       NULL, NULL, NULL, NULL
FROM tr WHERE tx_signer <> wallet GROUP BY k, COALESCE(mint, 'null') || '|' || COALESCE(token_version, 'null')
UNION ALL
SELECT 'natout', k, to_owner, CAST(n AS varchar), NULL, CAST(amt AS varchar), token_version, NULL, NULL, NULL, NULL
FROM natout WHERE rk <= 5
UNION ALL
SELECT 'versions', NULL, COALESCE(token_version, 'null') || '|' || COALESCE(IF(mint = 'So11111111111111111111111111111111111111112', 'wsol', IF(mint IS NULL, 'null', 'other')), ''),
       CAST(count(*) AS varchar), NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM tr GROUP BY 3

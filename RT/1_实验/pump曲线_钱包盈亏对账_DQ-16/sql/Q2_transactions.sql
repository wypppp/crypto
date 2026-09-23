-- 由 make_sql.py 从 raw/sample.csv 生成，勿手改。只读。平台单次执行成本上限请设 20 credits。
-- 只输出汇总行；运行后先看结果大小（免费档导出 20 credits/MB），>1.5 MB 不下载。
-- DQ-16 Q2（r1）：入样地址为签名者之一的全部交易（含失败）：费用、本地址与其代币账户的 lamports 和代币余额变化。
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
tx AS (
    SELECT t.id, t.block_slot, t.index AS txi, t.success, t.fee, t.signers,
           concat(t.account_keys,
                  COALESCE(t.loaded_addresses.writable, CAST(ARRAY[] AS ARRAY(VARCHAR))),
                  COALESCE(t.loaded_addresses.readonly, CAST(ARRAY[] AS ARRAY(VARCHAR)))) AS keys,
           t.pre_balances, t.post_balances, t.pre_token_balances, t.post_token_balances
    FROM solana.transactions t
    WHERE t.block_date = DATE '2026-06-07' AND arrays_overlap(t.signers, ARRAY['BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ', 'FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x', '3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ', 'AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY', 'CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me', 'C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5', 'FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd', 'BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr', 'DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc', 'D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe', 'Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj', '3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp', 'FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt', 'ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB', '9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm', '6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn', '7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx', 'AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs', '991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd', '827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK', '7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz', 'F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU', 'hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk', '4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13', 'AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv', '2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9', '5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT', 'DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw', '8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX', 'Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD'])
),
x AS (
    SELECT w.k, w.wallet, tx.* FROM tx JOIN w ON contains(tx.signers, w.wallet)
),
per_tx AS (
    SELECT k, id, block_slot, success, IF(keys[1] = wallet, fee, 0) AS fee_paid,
           element_at(post_balances, array_position(keys, wallet)) - element_at(pre_balances, array_position(keys, wallet)) AS d_wallet
    FROM x
),
tb AS (
    SELECT x.k, x.id, x.block_slot, x.txi, b.account, b.mint, 'pre' AS side, b.amount AS amt,
           element_at(x.pre_balances, NULLIF(array_position(x.keys, b.account), 0)) AS pre_lam,
           element_at(x.post_balances, NULLIF(array_position(x.keys, b.account), 0)) AS post_lam
    FROM x CROSS JOIN UNNEST(x.pre_token_balances) AS b(account, mint, owner, amount)
    WHERE b.owner = x.wallet
    UNION ALL
    SELECT x.k, x.id, x.block_slot, x.txi, b.account, b.mint, 'post', b.amount,
           element_at(x.pre_balances, NULLIF(array_position(x.keys, b.account), 0)),
           element_at(x.post_balances, NULLIF(array_position(x.keys, b.account), 0))
    FROM x CROSS JOIN UNNEST(x.post_token_balances) AS b(account, mint, owner, amount)
    WHERE b.owner = x.wallet
),
acct AS (
    SELECT k, id, block_slot, txi, account, max(mint) AS mint,
           COALESCE(max(IF(side = 'pre', amt)), 0) AS pre_amt, COALESCE(max(IF(side = 'post', amt)), 0) AS post_amt,
           max(pre_lam) AS pre_lam, max(post_lam) AS post_lam
    FROM tb GROUP BY 1, 2, 3, 4, 5
),
tm AS (
    SELECT k, id, block_slot, txi, mint, sum(pre_amt) AS pre_amt, sum(post_amt) AS post_amt
    FROM acct WHERE mint <> 'So11111111111111111111111111111111111111112' GROUP BY 1, 2, 3, 4, 5
)
SELECT 'wal' AS kind, k, CAST(NULL AS varchar) AS key, CAST(count(*) AS varchar) AS n, CAST(sum(block_slot) AS varchar) AS s_slot,
       CAST(count_if(NOT success) AS varchar) AS v1, CAST(sum(fee_paid) AS varchar) AS v2,
       CAST(sum(IF(success, 0, fee_paid)) AS varchar) AS v3, CAST(sum(d_wallet) AS varchar) AS v4,
       CAST(NULL AS varchar) AS v5, CAST(NULL AS varchar) AS v6
FROM per_tx GROUP BY k
UNION ALL
SELECT 'wacc', k, NULL, CAST(count(*) AS varchar), NULL,
       CAST(sum(IF(mint = 'So11111111111111111111111111111111111111112', post_lam - pre_lam, 0)) AS varchar),
       CAST(sum(IF(mint <> 'So11111111111111111111111111111111111111112', post_lam - pre_lam, 0)) AS varchar),
       CAST(sum(IF(mint = 'So11111111111111111111111111111111111111112', post_amt - pre_amt, 0)) AS varchar),
       CAST(count_if(pre_lam IS NULL OR post_lam IS NULL) AS varchar), NULL, NULL
FROM acct GROUP BY k
UNION ALL
SELECT 'wm', k, mint, CAST(count(*) AS varchar), CAST(sum(block_slot) AS varchar),
       CAST(sum(post_amt - pre_amt) AS varchar),
       CAST(min_by(pre_amt, block_slot * 100000 + txi) AS varchar),
       CAST(max_by(post_amt, block_slot * 100000 + txi) AS varchar), NULL, NULL, NULL
FROM tm GROUP BY k, mint

-- 由 make_sql.py 从 raw/sample.csv 生成，勿手改。只读；平台成本上限请设 20 credits。
-- DQ-16 Q2：30 个入样地址 2026-06-07 UTC 作为首签名者的全部交易（含失败）：成功性、费用、本地址 SOL 与名下代币的前后余额。
WITH w(wallet) AS (VALUES
    ('BLimgBQPAGzC32E1txVtEVrTDEzn28HMux8ZR6ny1voQ'),
    ('FS9NcUi3ExoUWJmeiTFFfppaUEB6hfj2wvZnKejkgJ1x'),
    ('3w8vWtsAeaN3JyePUu9HwPwcmG6VDuKE4FQ67hon3LZQ'),
    ('AmcNekukkoa41uEFxU4HJYEjvmXR5BzdFrA8Qhq6N7iY'),
    ('CbY5inaMyeUzAbA28J4pV62Co3kpZ2gFiBZJYXyFn7me'),
    ('C61yCWc7HDcuwCK9b49E3iARb5bGzZGE5pNDA7ZhHBs5'),
    ('FCPVbVpLg9U58XdyHQdKMWiCNcADva2XhT32gp1XZpQd'),
    ('BrPvAKYzhTLixxFTdZGUTGqTSduuvJQ3jbk7t6YUXnjr'),
    ('DnDULUK5nhHZbnUknRHDYabrGi1xdkiMkc2ed3CWXmoc'),
    ('D79guzAKGNCtndqYKbVZTwmr9mqM9daU9fYLMxxfqVCe'),
    ('Dxt8syYZD5QnFbtrerrGGrX8FDzMERePYGZidH2B2UZj'),
    ('3zYVewKhux94eDQioK7opVWPF9H9TwzuaA2bXn2PLWWp'),
    ('FUCKNiggAS8VdjcGbpAgoPZtfmpA32Q5CGbVbxHeuAgt'),
    ('ALi2JTnJkqA6yuZzXgBPaJuyswG5oqv3SwBcZ1mTTwWB'),
    ('9RhM9QfGaszojVpzghSb75jqmMcFCdDv1ZvFbwkC52Hm'),
    ('6UFfv9hYEc882QPGw2ococTZX6bjsUzkP1Ngf4ZzUCTn'),
    ('7a1crJnsQ4AqqGdaMxUaiyQRRdjovofUxeB8mCPKraqx'),
    ('AVwzHt8CUPtmU4L6RXb2ymyw4yASqWXfNV3dRDCHmsPs'),
    ('991azNS8PGBswfJsmJCzpsE4RpU5BW6QQdo2dqNR56dd'),
    ('827L2BZ4gdNG5GyUdfjTwtBhLSh1qjVQLx4obS6HAiQK'),
    ('7YKBiaNxoNxapEqeFE3zfGaSHHzLu4J8FL1FYva3obkz'),
    ('F49ipuTnzzGAm8maR57jePcSx1fyQ2E6XTTiuVajg7zU'),
    ('hWJCRPNTt9fUBohpCdGsotGerPGu3BKx3sDmSd43qbk'),
    ('4XHCiLn2rNqPBYQ2RA721j5ar4cU1H13Wui6Z3NE2o13'),
    ('AgAaEion8EwAMtaiNCmyJSF3sECSRWmNi71hcys44afv'),
    ('2uaLzCzAf9hPeJqXV8BUDw99yho19uW2t6FFj7hKKKY9'),
    ('5LwYjCKu495nkpoCTikLfdNiedwDewqjbwGivhuRkMTT'),
    ('DE4Y1i3LZD6fXNh7gcCekMyReBV23kRgbinnXp1iahYw'),
    ('8fG5zMaQjpQNgVgE8yWn8mge3HmfKBpwUY36VLvrNyxX'),
    ('Fx8wFmPc6LarYr2ucwEDrUxbLnGzLUT2NUdxmmjzLTTD')
)
SELECT t.id AS sig, t.block_slot AS slot, t.index AS txi, t.signer AS wallet, t.success, t.fee,
       t.compute_units_consumed AS cu,
       t.pre_balances[1] AS pre_sol, t.post_balances[1] AS post_sol,
       json_format(CAST(filter(t.pre_token_balances, x -> x.owner = t.signer) AS JSON)) AS pre_tok,
       json_format(CAST(filter(t.post_token_balances, x -> x.owner = t.signer) AS JSON)) AS post_tok
FROM solana.transactions t
WHERE t.block_date = DATE '2026-06-07' AND t.signer IN (SELECT wallet FROM w)
ORDER BY slot, txi

/* DQ-26 探针：tokens_solana.transfers 中原生 SOL 的表示（token_version、mint、symbol）。
   只读 2026-08-03 一个分区、一个地址（08-03 冒烟中的活跃钱包），LIMIT 200。不是收益数据。 */
SELECT token_version, token_mint_address, symbol, action, outer_executing_account,
       inner_instruction_index IS NULL AS is_outer, count(*) AS n, sum(amount_display) AS amt
FROM tokens_solana.transfers
WHERE block_date = DATE '2026-08-03'
  AND tx_signer = 'FJQUpLWUgAbuVYTFW6iLviy4ogWJUFHVRLL6KdDx1VbW'
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY n DESC
LIMIT 200

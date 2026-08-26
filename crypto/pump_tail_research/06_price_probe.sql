SELECT
    timestamp,
    typeof(timestamp) AS timestamp_type,
    to_base58(contract_address) AS mint,
    symbol,
    price
FROM prices_external.hour
WHERE blockchain = 'solana'
  AND contract_address IN (
      from_base58('So11111111111111111111111111111111111111112'),
      from_base58('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v')
  )
  AND timestamp BETWEEN TIMESTAMP '2026-07-09 16:00:00'
                    AND TIMESTAMP '2026-07-09 17:00:00'
ORDER BY mint, timestamp

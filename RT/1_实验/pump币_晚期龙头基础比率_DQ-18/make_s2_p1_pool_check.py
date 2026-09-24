"""Generate one frozen-sample pool query for DQ-18 P1 price acceptance."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "raw" / "s2" / "P1_202512_sample10.json"
EXPECTED_SHA256 = "d3976fc120e3cc21dfd9d6f6c8745e7f41b91876edbb3ab5838ae198e284ae84"
OUTPUT = ROOT / "sql" / "S2_P1_202512_十币主池末笔合并核查.sql"


def main():
    blob = SAMPLE.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == EXPECTED_SHA256
    selected = json.loads(blob)
    assert len(selected) == 10 and len({x["mint"] for x in selected}) == 10
    times = [datetime.strptime(x["hour_start"], "%Y-%m-%d %H:%M:%S.000 UTC")
             for x in selected]
    low, high = min(times), max(times) + timedelta(hours=1)
    values = ",\n        ".join(
        "('{}', TIMESTAMP '{}')".format(x["mint"], t.strftime("%Y-%m-%d %H:%M:%S"))
        for x, t in zip(selected, times)
    )
    query = """-- DQ-18 P1 acceptance: frozen random 10, main-pool last trade per signal hour.
-- Sample list SHA256: {sample_hash}
-- One December dex_solana.trades scan; project curve excluded at scan layer.
-- No returns or post-signal prices. Run with per-query cap <= 50 credits.
-- The last swap's post-state is not automatically the exact hour-end state if
-- later LP events occurred. Later RPC/event checks must inspect that gap.

WITH sample(mint, hour_start) AS (
    VALUES
        {values}
), completed AS (
    SELECT mint, MIN(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date < DATE '2026-01-01'
      AND mint IN (SELECT mint FROM sample)
    GROUP BY mint
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd
    FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '{low}'
      AND minute < TIMESTAMP '{high}'
    GROUP BY minute
), selected_trades AS (
    SELECT s.mint, s.hour_start, t.block_time, t.tx_id, t.project,
           t.project_program_id AS pool_id,
           IF(t.token_bought_mint_address = s.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = s.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = s.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM dex_solana.trades t
    JOIN sample s
      ON t.block_time >= s.hour_start
     AND t.block_time < s.hour_start + INTERVAL '1' HOUR
     AND (t.token_bought_mint_address = s.mint
          OR t.token_sold_mint_address = s.mint)
    JOIN completed c ON c.mint = s.mint AND t.block_time >= c.completed_at
    WHERE t.block_month = DATE '2025-12-01'
      AND t.block_time >= TIMESTAMP '{low}'
      AND t.block_time < TIMESTAMP '{high}'
      AND t.project <> 'pumpdotfun'
), valued AS (
    SELECT t.*,
           CASE
             WHEN quote_mint = 'So11111111111111111111111111111111111111112'
               THEN quote_amount * s.sol_usd
             WHEN quote_mint IN (
               'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
               'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
               THEN quote_amount
             ELSE NULL
           END AS quote_usd
    FROM selected_trades t
    LEFT JOIN sol_minute s
      ON t.quote_mint = 'So11111111111111111111111111111111111111112'
     AND s.minute = date_trunc('minute', t.block_time)
), valid AS (
    SELECT *
    FROM valued
    WHERE token_amount > 0 AND quote_usd > 0
      AND ((quote_mint = 'So11111111111111111111111111111111111111112'
            AND quote_amount >= 0.001)
        OR (quote_mint IN (
            'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
            'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
            AND quote_amount >= 0.10))
), per_pool AS (
    SELECT mint, hour_start, project, pool_id, quote_mint,
           COUNT(*) AS n_valid_trades,
           SUM(quote_usd) AS valid_usd_volume,
           SUM(token_amount) AS token_volume,
           1000000000.0 * SUM(quote_usd) / NULLIF(SUM(token_amount), 0)
               AS pool_vwap_cap_usd,
           MAX(block_time) AS last_trade_at,
           MAX_BY(tx_id, block_time) AS last_tx_id
    FROM valid
    GROUP BY mint, hour_start, project, pool_id, quote_mint
), ranked AS (
    SELECT *,
           valid_usd_volume / NULLIF(SUM(valid_usd_volume)
               OVER (PARTITION BY mint, hour_start), 0) AS share_of_valid_usd_volume,
           ROW_NUMBER() OVER (PARTITION BY mint, hour_start
               ORDER BY valid_usd_volume DESC, pool_id) AS pool_rank
    FROM per_pool
)
SELECT mint, hour_start, project, pool_id, quote_mint, pool_rank,
       n_valid_trades, valid_usd_volume, share_of_valid_usd_volume,
       pool_vwap_cap_usd, last_trade_at, last_tx_id
FROM ranked
WHERE pool_rank <= 5
ORDER BY mint, pool_rank
""".format(
        sample_hash=EXPECTED_SHA256,
        values=values,
        low=low.strftime("%Y-%m-%d %H:%M:%S"),
        high=high.strftime("%Y-%m-%d %H:%M:%S"),
    )
    OUTPUT.write_text(query)
    print(OUTPUT, "bytes", OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()

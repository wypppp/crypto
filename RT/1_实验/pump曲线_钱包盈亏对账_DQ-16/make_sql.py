"""Generate the two DQ-16 Dune queries (r1) from raw/sample.csv. Outputs are aggregates only (export is billed per MB).

Q1: pump curve / PumpSwap events by user + tokens_solana.transfers touching the wallets.
Q2: solana.transactions where a sampled wallet is among the signers: balances of the wallet and its token accounts.
Every output row: kind, k, key, n, s_slot, v1..v6 (all varchar). See README §9 for the meaning of each kind.
"""
import csv
from pathlib import Path

HERE = Path(__file__).parent
S = [(int(r["k"]), r["wallet"]) for r in csv.DictReader(open(HERE / "raw" / "sample.csv"))]
W = ",\n    ".join(f"({k}, '{w}')" for k, w in S)
LIST = ", ".join(f"'{w}'" for _, w in S)
WSOL = "'So11111111111111111111111111111111111111112'"
TIPS = ", ".join(f"'{t}'" for t in [
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh"])
HEAD = ("-- 由 make_sql.py 从 raw/sample.csv 生成，勿手改。只读。平台单次执行成本上限请设 20 credits。\n"
        "-- 只输出汇总行；运行后先看结果大小（免费档导出 20 credits/MB），>1.5 MB 不下载。\n")
D = "DATE '2026-06-07'"

Q1 = HEAD + f"""-- DQ-16 Q1（r1）：30 个入样地址 2026-06-07 UTC 的 pump 曲线 / PumpSwap 事件（按 user）与触及这些地址的全部转账。
WITH w(k, wallet) AS (VALUES
    {W}
),
ev AS (
    SELECT w.k, 'curve' AS venue, CAST(t.mint AS varchar) AS key, t.evt_tx_id AS sig, t.evt_block_slot AS slot,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           CAST(COALESCE(t.fee_basis_points, 0) + COALESCE(t.creator_fee_basis_points, 0) AS DECIMAL(38,0)) AS bps,
           CAST(NULL AS DECIMAL(38,0)) AS uq
    FROM pumpdotfun_solana.pump_evt_tradeevent t JOIN w ON CAST(t."user" AS varchar) = w.wallet
    WHERE t.evt_block_date = {D} AND CAST(t."user" AS varchar) IN ({LIST})
    UNION ALL
    SELECT w.k, 'amm', CAST(e.pool AS varchar), e.evt_tx_id, e.evt_block_slot, true,
           CAST(e.base_amount_out AS DECIMAL(38,0)), CAST(e.quote_amount_in AS DECIMAL(38,0)), NULL,
           CAST(e.user_quote_amount_in AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e JOIN w ON CAST(e."user" AS varchar) = w.wallet
    WHERE e.evt_block_date = {D} AND CAST(e."user" AS varchar) IN ({LIST})
    UNION ALL
    SELECT w.k, 'amm', CAST(e.pool AS varchar), e.evt_tx_id, e.evt_block_slot, false,
           CAST(e.base_amount_in AS DECIMAL(38,0)), CAST(e.quote_amount_out AS DECIMAL(38,0)), NULL,
           CAST(e.user_quote_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e JOIN w ON CAST(e."user" AS varchar) = w.wallet
    WHERE e.evt_block_date = {D} AND CAST(e."user" AS varchar) IN ({LIST})
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
    WHERE x.block_date = {D} AND (x.from_owner IN ({LIST}) OR x.to_owner IN ({LIST}))
),
touch_tx AS (   -- transactions touching the wallet whose first signer is someone else
    SELECT DISTINCT k, tx_id, block_slot FROM tr WHERE tx_signer <> wallet
),
natout AS (
    SELECT k, to_owner, token_version, sum(amt) AS amt, count(DISTINCT tx_id) AS n,
           row_number() OVER (PARTITION BY k ORDER BY sum(amt) DESC) AS rk
    FROM tr WHERE from_owner = wallet AND to_owner NOT IN ({TIPS})
      AND (mint IS NULL OR mint = {WSOL}) AND to_owner <> wallet
    GROUP BY 1, 2, 3
)
SELECT 'ev' AS kind, k, key, CAST(count(*) AS varchar) AS n, CAST(sum(slot) AS varchar) AS s_slot,
       venue AS v1, CAST(sum(n_ev) AS varchar) AS v2, CAST(sum(tok_buy) AS varchar) AS v3,
       CAST(sum(tok_sell) AS varchar) AS v4, CAST(sum(sol_user) AS varchar) AS v5, CAST(NULL AS varchar) AS v6
FROM ev_sig GROUP BY k, venue, key
UNION ALL
SELECT 'tip', k, NULL, CAST(count(DISTINCT tx_id) AS varchar), NULL, CAST(sum(amt) AS varchar), NULL, NULL, NULL, NULL, NULL
FROM tr WHERE from_owner = wallet AND to_owner IN ({TIPS}) GROUP BY k
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
SELECT 'versions', NULL, COALESCE(token_version, 'null') || '|' || COALESCE(IF(mint = {WSOL}, 'wsol', IF(mint IS NULL, 'null', 'other')), ''),
       CAST(count(*) AS varchar), NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM tr GROUP BY 3
"""

Q2 = HEAD + f"""-- DQ-16 Q2（r1）：入样地址为签名者之一的全部交易（含失败）：费用、本地址与其代币账户的 lamports 和代币余额变化。
WITH w(k, wallet) AS (VALUES
    {W}
),
tx AS (
    SELECT t.id, t.block_slot, t.index AS txi, t.success, t.fee, t.signers,
           concat(t.account_keys,
                  COALESCE(t.loaded_addresses.writable, CAST(ARRAY[] AS ARRAY(VARCHAR))),
                  COALESCE(t.loaded_addresses.readonly, CAST(ARRAY[] AS ARRAY(VARCHAR)))) AS keys,
           t.pre_balances, t.post_balances, t.pre_token_balances, t.post_token_balances
    FROM solana.transactions t
    WHERE t.block_date = {D} AND arrays_overlap(t.signers, ARRAY[{LIST}])
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
    FROM acct WHERE mint <> {WSOL} GROUP BY 1, 2, 3, 4, 5
)
SELECT 'wal' AS kind, k, CAST(NULL AS varchar) AS key, CAST(count(*) AS varchar) AS n, CAST(sum(block_slot) AS varchar) AS s_slot,
       CAST(count_if(NOT success) AS varchar) AS v1, CAST(sum(fee_paid) AS varchar) AS v2,
       CAST(sum(IF(success, 0, fee_paid)) AS varchar) AS v3, CAST(sum(d_wallet) AS varchar) AS v4,
       CAST(NULL AS varchar) AS v5, CAST(NULL AS varchar) AS v6
FROM per_tx GROUP BY k
UNION ALL
SELECT 'wacc', k, NULL, CAST(count(*) AS varchar), NULL,
       CAST(sum(IF(mint = {WSOL}, post_lam - pre_lam, 0)) AS varchar),
       CAST(sum(IF(mint <> {WSOL}, post_lam - pre_lam, 0)) AS varchar),
       CAST(sum(IF(mint = {WSOL}, post_amt - pre_amt, 0)) AS varchar),
       CAST(count_if(pre_lam IS NULL OR post_lam IS NULL) AS varchar), NULL, NULL
FROM acct GROUP BY k
UNION ALL
SELECT 'wm', k, mint, CAST(count(*) AS varchar), CAST(sum(block_slot) AS varchar),
       CAST(sum(post_amt - pre_amt) AS varchar),
       CAST(min_by(pre_amt, block_slot * 100000 + txi) AS varchar),
       CAST(max_by(post_amt, block_slot * 100000 + txi) AS varchar), NULL, NULL, NULL
FROM tm GROUP BY k, mint
"""

(HERE / "sql" / "Q1_events_transfers.sql").write_text(Q1)
(HERE / "sql" / "Q2_transactions.sql").write_text(Q2)
print(len(S), "wallets;", len(Q1), len(Q2), "chars")

"""Generate the two DQ-16 Dune queries from raw/sample.csv (wallet list embedded verbatim)."""
import csv
from pathlib import Path
HERE = Path(__file__).parent
W = [r["wallet"] for r in csv.DictReader(open(HERE / "raw" / "sample.csv"))]
VALS = ",\n    ".join(f"('{w}')" for w in W)
HEAD = "-- 由 make_sql.py 从 raw/sample.csv 生成，勿手改。只读；平台成本上限请设 20 credits。\n"

Q1 = HEAD + f"""-- DQ-16 Q1：30 个入样地址在 2026-06-07 UTC 的 pump 曲线 / PumpSwap 事件与全部转账（含原生 SOL）。逐行输出，不做汇总。
WITH w(wallet) AS (VALUES
    {VALS}
),
pools AS (
    SELECT pool, max(base_mint) AS mint FROM pumpdotfun_solana.pump_amm_evt_createpoolevent GROUP BY 1
),
ev AS (
    SELECT 'curve' AS src, evt_tx_id AS sig, evt_block_slot AS slot, evt_tx_index AS txi,
           evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix,
           CAST("user" AS varchar) AS wallet, CAST(mint AS varchar) AS mint, CAST(NULL AS varchar) AS pool,
           COALESCE(is_buy, isBuy) AS is_buy,
           CAST(COALESCE(sol_amount, solAmount) AS varchar) AS sol_raw,
           CAST(COALESCE(token_amount, tokenAmount) AS varchar) AS tok_raw,
           CAST(fee_basis_points AS varchar) AS fee_a, CAST(creator_fee_basis_points AS varchar) AS fee_b, CAST(NULL AS varchar) AS fee_c,
           CAST(NULL AS varchar) AS user_quote,
           CAST(NULL AS varchar) AS from_owner, CAST(NULL AS varchar) AS to_owner,
           CAST(NULL AS varchar) AS token_version, CAST(NULL AS varchar) AS executing
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date = DATE '2026-06-07' AND CAST("user" AS varchar) IN (SELECT wallet FROM w)
    UNION ALL
    SELECT 'amm_buy', e.evt_tx_id, e.evt_block_slot, e.evt_tx_index, e.evt_outer_instruction_index, e.evt_inner_instruction_index,
           CAST(e."user" AS varchar), CAST(p.mint AS varchar), CAST(e.pool AS varchar), true,
           CAST(e.quote_amount_in AS varchar), CAST(e.base_amount_out AS varchar),
           CAST(e.protocol_fee AS varchar), CAST(e.coin_creator_fee AS varchar), CAST(e.lp_fee AS varchar),
           CAST(e.user_quote_amount_in AS varchar), NULL, NULL, NULL, NULL
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e LEFT JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date = DATE '2026-06-07' AND CAST(e."user" AS varchar) IN (SELECT wallet FROM w)
    UNION ALL
    SELECT 'amm_sell', e.evt_tx_id, e.evt_block_slot, e.evt_tx_index, e.evt_outer_instruction_index, e.evt_inner_instruction_index,
           CAST(e."user" AS varchar), CAST(p.mint AS varchar), CAST(e.pool AS varchar), false,
           CAST(e.quote_amount_out AS varchar), CAST(e.base_amount_in AS varchar),
           CAST(e.protocol_fee AS varchar), CAST(e.coin_creator_fee AS varchar), CAST(e.lp_fee AS varchar),
           CAST(e.user_quote_amount_out AS varchar), NULL, NULL, NULL, NULL
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e LEFT JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date = DATE '2026-06-07' AND CAST(e."user" AS varchar) IN (SELECT wallet FROM w)
    UNION ALL
    SELECT 'transfer', tx_id, block_slot, tx_index, outer_instruction_index, inner_instruction_index,
           CASE WHEN from_owner IN (SELECT wallet FROM w) THEN from_owner ELSE to_owner END,
           token_mint_address, NULL, NULL, NULL, CAST(amount AS varchar),
           action, NULL, NULL, NULL, from_owner, to_owner, token_version, outer_executing_account
    FROM tokens_solana.transfers
    WHERE block_date = DATE '2026-06-07'
      AND (from_owner IN (SELECT wallet FROM w) OR to_owner IN (SELECT wallet FROM w))
)
SELECT * FROM ev ORDER BY slot, txi, oix, iix
"""

Q2 = HEAD + f"""-- DQ-16 Q2：30 个入样地址 2026-06-07 UTC 作为首签名者的全部交易（含失败）：成功性、费用、本地址 SOL 与名下代币的前后余额。
WITH w(wallet) AS (VALUES
    {VALS}
)
SELECT t.id AS sig, t.block_slot AS slot, t.index AS txi, t.signer AS wallet, t.success, t.fee,
       t.compute_units_consumed AS cu,
       t.pre_balances[1] AS pre_sol, t.post_balances[1] AS post_sol,
       json_format(CAST(filter(t.pre_token_balances, x -> x.owner = t.signer) AS JSON)) AS pre_tok,
       json_format(CAST(filter(t.post_token_balances, x -> x.owner = t.signer) AS JSON)) AS post_tok
FROM solana.transactions t
WHERE t.block_date = DATE '2026-06-07' AND t.signer IN (SELECT wallet FROM w)
ORDER BY slot, txi
"""
(HERE / "sql" / "Q1_events_transfers.sql").write_text(Q1)
(HERE / "sql" / "Q2_transactions.sql").write_text(Q2)
print(len(W), "wallets;", len(Q1), len(Q2), "chars")

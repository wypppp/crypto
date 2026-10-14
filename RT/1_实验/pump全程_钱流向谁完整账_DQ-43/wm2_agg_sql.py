"""DQ-43（WM2）汇总版取数 SQL 的模板（10-14，取数附录 v2 §3；总控第四轮第三节：在 SQL 里先汇总，C 不保留逐笔）。

由 build_wm2_sql.build() 调用，母体、池子与过滤沿用同一套 CTE（coins、pop、pools）。四层：
  CYCC  曲线阶段：每个“钱包 × 币”一行（Y），加每币两个时点的定价状态（P）。只读事件表，不读原始字节。
  CYCA  PumpSwap 阶段：同上。
  COSTF 交易成本（一天一条，交易表只扫一次）：成功成交交易按腿均摊的链上费用与未解释负残差（K），
        失败交易按触及的币均摊的费用（F）。行粒度＝签名者 × 币 × 阶段。
  VQ    每个池一行：InitBoost 设定的虚拟报价储备 vq（DQ-35 §1e：只有 InitBoost 写 vq，与建池同一笔交易、同一秒）。

金额一律整数（DECIMAL(38,0)），输出文本。均摊用整数除法（(x − mod(x, n)) / n），余数给排序第一的腿（contract_ledger）。
"""

# ---------- CYC：事件（曲线） ----------

CYC_EV_CURVE = """,
ev AS (
    /* 曲线成交（事件表）：抽样币、逐币 30 天窗口、止日之前。
       现金按 T2a 候选口径 v1（冒烟结果 §3）：买入付出 sol＋协议费＋创建者费，卖出到手 sol−两费。
       r1～r4＝成交后的虚拟 SOL、虚拟代币、真实 SOL、真实代币储备；bps1、bps2＝协议费率、创建者费率 */
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           t.evt_outer_instruction_index AS oix, COALESCE(t.evt_inner_instruction_index, -1) AS iix,
           t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS amt,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           COALESCE(CAST(t.fee AS DECIMAL(38,0)), 0) AS f_pr, COALESCE(CAST(t.creator_fee AS DECIMAL(38,0)), 0) AS f_cr,
           CAST(0 AS DECIMAL(38,0)) AS f_lp,
           CAST(t.cashback AS DECIMAL(38,0)) AS f_cb, CAST(t.buyback_fee AS DECIMAL(38,0)) AS f_bb,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DECIMAL(38,0)) AS r1,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DECIMAL(38,0)) AS r2,
           CAST(t.real_sol_reserves AS DECIMAL(38,0)) AS r3, CAST(t.real_token_reserves AS DECIMAL(38,0)) AS r4,
           CAST(t.fee_basis_points AS DECIMAL(38,0)) AS bps1, CAST(t.creator_fee_basis_points AS DECIMAL(38,0)) AS bps2,
           CAST(NULL AS DECIMAL(38,0)) AS bps3
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
),
e1 AS (
    SELECT ev.*, CASE WHEN is_buy THEN amt + f_pr + f_cr ELSE amt - f_pr - f_cr END AS cash
    FROM ev
)"""

# ---------- CYC：事件（PumpSwap） ----------

CYC_EV_AMM = """,
ev AS (
    /* PumpSwap 成交（解码事件表，不读原始字节）：允许池（pump 迁移、池序号 0、WSOL 计价）、逐币 30 天窗口、止日之前。
       现金：买入＝用户付出的报价（含 LP、协议、创建者费），卖出＝用户到手的报价。amt＝进出池子的报价（含 LP 费）。
       r1、r2＝成交前的池报价、池代币储备；r3、r4＝成交后；bps1～bps3＝LP、协议、创建者费率。vq 另见 VQ 层 */
    SELECT p.mint, a.ts, a.slot, a.txi, a.oix, a.iix, a.tx_id, a.usr, a.is_buy, a.amt, a.tok, a.f_pr, a.f_cr, a.f_lp,
           a.f_cb, a.f_bb, a.q0 AS r1, a.b0 AS r2,
           CASE WHEN a.is_buy THEN a.q0 + a.amt ELSE a.q0 - a.amt END AS r3,
           CASE WHEN a.is_buy THEN a.b0 - a.tok ELSE a.b0 + a.tok END AS r4,
           a.bps1, a.bps2, a.bps3, a.cash
    FROM (
        SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
               COALESCE(evt_inner_instruction_index, -1) AS iix, evt_tx_id AS tx_id, CAST("user" AS varchar) AS usr,
               true AS is_buy, CAST(user_quote_amount_in AS DECIMAL(38,0)) AS cash,
               CAST(quote_amount_in_with_lp_fee AS DECIMAL(38,0)) AS amt, CAST(base_amount_out AS DECIMAL(38,0)) AS tok,
               CAST(protocol_fee AS DECIMAL(38,0)) AS f_pr, CAST(coin_creator_fee AS DECIMAL(38,0)) AS f_cr,
               CAST(lp_fee AS DECIMAL(38,0)) AS f_lp, CAST(NULL AS DECIMAL(38,0)) AS f_cb, CAST(NULL AS DECIMAL(38,0)) AS f_bb,
               CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0, CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
               CAST(lp_fee_basis_points AS DECIMAL(38,0)) AS bps1, CAST(protocol_fee_basis_points AS DECIMAL(38,0)) AS bps2,
               CAST(coin_creator_fee_basis_points AS DECIMAL(38,0)) AS bps3
        FROM pumpdotfun_solana.pump_amm_evt_buyevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
        UNION ALL
        SELECT pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index,
               COALESCE(evt_inner_instruction_index, -1), evt_tx_id, CAST("user" AS varchar),
               false, CAST(user_quote_amount_out AS DECIMAL(38,0)),
               CAST(quote_amount_out AS DECIMAL(38,0)) - COALESCE(CAST(lp_fee AS DECIMAL(38,0)), 0),
               CAST(base_amount_in AS DECIMAL(38,0)),
               CAST(protocol_fee AS DECIMAL(38,0)), CAST(coin_creator_fee AS DECIMAL(38,0)), CAST(lp_fee AS DECIMAL(38,0)),
               CAST(cashback AS DECIMAL(38,0)), CAST(buyback_fee AS DECIMAL(38,0)),
               CAST(pool_quote_token_reserves AS DECIMAL(38,0)), CAST(pool_base_token_reserves AS DECIMAL(38,0)),
               CAST(lp_fee_basis_points AS DECIMAL(38,0)), CAST(protocol_fee_basis_points AS DECIMAL(38,0)),
               CAST(coin_creator_fee_basis_points AS DECIMAL(38,0))
        FROM pumpdotfun_solana.pump_amm_evt_sellevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
    ) a
    JOIN pools p ON p.pool = a.pool
    WHERE a.ts >= p.created_at AND a.ts < p.coin_created_at + INTERVAL '{hz}' DAY
      AND a.ts < TIMESTAMP '{cutoff} 00:00:00'
),
e1 AS (SELECT * FROM ev)"""

# ---------- CYC：汇总（两个阶段共用） ----------

CYC_AGG = """,
ag AS (
    /* 每个“钱包 × 币”的本阶段合计；pre＝快照截点 {snap} 之前（T3 排名用）；
       sb＝本阶段内首笔卖出早于末笔买入（“先卖后买”，阶段结转近似的敏感性打标，取数附录 §5） */
    SELECT usr, mint,
           count_if(is_buy) AS n_buy, count_if(NOT is_buy) AS n_sell,
           sum(IF(is_buy, cash, 0)) AS in_cash, sum(IF(is_buy, 0, cash)) AS out_cash,
           sum(IF(is_buy, tok, 0)) AS tok_buy, sum(IF(is_buy, 0, tok)) AS tok_sell,
           sum(IF(is_buy, amt, 0)) AS amt_buy, sum(IF(is_buy, 0, amt)) AS amt_sell,
           sum(IF(is_buy AND ts < TIMESTAMP '{snap}', cash, 0)) AS in_pre,
           sum(IF(NOT is_buy AND ts < TIMESTAMP '{snap}', cash, 0)) AS out_pre,
           sum(IF(is_buy AND ts < TIMESTAMP '{snap}', tok, 0)) AS tok_buy_pre,
           sum(IF(NOT is_buy AND ts < TIMESTAMP '{snap}', tok, 0)) AS tok_sell_pre,
           sum(f_cb) AS f_cb, sum(f_bb) AS f_bb, count_if(f_cb IS NULL) AS n_cb_null,
           min(IF(NOT is_buy, ARRAY[slot, txi, oix, iix])) < max(IF(is_buy, ARRAY[slot, txi, oix, iix])) AS sb,
           to_unixtime(min(ts)) AS first_t, to_unixtime(max(ts)) AS last_t
    FROM e1
    GROUP BY 1, 2
),
w AS (
    /* 买入当时可见的状态（a_riskset 的分箱输入）：前 60 秒净买入＝顺序键在前、时刻晚于 t−60 秒的成交净额（进出池子的 SOL） */
    SELECT x.*,
           sum(sg) OVER (PARTITION BY mint ORDER BY slot, txi, oix, iix ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cum_x,
           sum(sg) OVER (PARTITION BY mint ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60' SECOND PRECEDING) AS cum_60
    FROM (SELECT e1.*, CASE WHEN is_buy THEN amt ELSE -amt END AS sg FROM e1) x
),
wb AS (
    /* K 标签的输入：本阶段截至这笔之前全部买入（现金口径）的第 99 百分位（近似分位，取数附录 §5 第 3 条）与笔数 */
    SELECT w.*,
           approx_percentile(CAST(cash AS double), 0.99) OVER (PARTITION BY mint ORDER BY slot, txi, oix, iix
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS p99_prior,
           count(*) OVER (PARTITION BY mint ORDER BY slot, txi, oix, iix
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS n_prior,
           row_number() OVER (PARTITION BY usr, mint ORDER BY slot, txi, oix, iix) AS rb
    FROM w
    WHERE is_buy
),
fb AS (SELECT * FROM wb WHERE rb = 1),
y AS (
    SELECT a.*, f.slot AS fb_slot, f.txi AS fb_txi, f.oix AS fb_oix, f.iix AS fb_iix, to_unixtime(f.ts) AS fb_t,
           f.tx_id AS fb_tx, f.cash AS fb_cash, f.amt AS fb_amt, f.tok AS fb_tok,
           f.r1 AS fb_r1, f.r2 AS fb_r2, f.r3 AS fb_r3, f.r4 AS fb_r4,
           CASE WHEN f.usr IS NOT NULL THEN COALESCE(f.cum_x, 0) - COALESCE(f.cum_60, 0) END AS fb_net60, f.p99_prior AS fb_p99, f.n_prior AS fb_nprior
    FROM ag a
    LEFT JOIN fb f ON f.usr = a.usr AND f.mint = a.mint{yslice}
),
z AS (
    /* 每币两个时点的定价状态：S＝快照截点之前最后一笔成交后，E＝观察窗内最后一笔成交后；另附本阶段费用合计 */
    SELECT mint, 'S' AS z_cut, slot, txi, oix, iix, ts, r1, r2, r3, r4, bps1, bps2, bps3,
           CAST(NULL AS DECIMAL(38,0)) AS zf_pr, CAST(NULL AS DECIMAL(38,0)) AS zf_cr, CAST(NULL AS DECIMAL(38,0)) AS zf_lp,
           CAST(NULL AS BIGINT) AS z_n
    FROM (SELECT e1.*, row_number() OVER (PARTITION BY mint ORDER BY slot DESC, txi DESC, oix DESC, iix DESC) AS rz
          FROM e1 WHERE ts < TIMESTAMP '{snap}')
    WHERE rz = 1
    UNION ALL
    SELECT mint, 'E', slot, txi, oix, iix, ts, r1, r2, r3, r4, bps1, bps2, bps3, zf_pr, zf_cr, zf_lp, z_n
    FROM (SELECT e1.*, row_number() OVER (PARTITION BY mint ORDER BY slot DESC, txi DESC, oix DESC, iix DESC) AS rz,
                 sum(f_pr) OVER (PARTITION BY mint) AS zf_pr, sum(f_cr) OVER (PARTITION BY mint) AS zf_cr,
                 sum(f_lp) OVER (PARTITION BY mint) AS zf_lp, count(*) OVER (PARTITION BY mint) AS z_n
          FROM e1)
    WHERE rz = 1
),
out AS (
    SELECT 'solana' AS chain, 'Y' AS kind, '{stage}' AS stage, mint, usr,
           n_buy, n_sell, CAST(in_cash AS varchar) AS in_cash, CAST(out_cash AS varchar) AS out_cash,
           CAST(tok_buy AS varchar) AS tok_buy, CAST(tok_sell AS varchar) AS tok_sell,
           CAST(amt_buy AS varchar) AS amt_buy, CAST(amt_sell AS varchar) AS amt_sell,
           CAST(in_pre AS varchar) AS in_pre, CAST(out_pre AS varchar) AS out_pre,
           CAST(tok_buy_pre AS varchar) AS tok_buy_pre, CAST(tok_sell_pre AS varchar) AS tok_sell_pre,
           CAST(f_cb AS varchar) AS f_cb, CAST(f_bb AS varchar) AS f_bb, n_cb_null, sb, first_t, last_t,
           fb_slot, fb_txi, fb_oix, fb_iix, fb_t, fb_tx, CAST(fb_cash AS varchar) AS fb_cash, CAST(fb_amt AS varchar) AS fb_amt,
           CAST(fb_tok AS varchar) AS fb_tok, CAST(fb_r1 AS varchar) AS fb_r1, CAST(fb_r2 AS varchar) AS fb_r2,
           CAST(fb_r3 AS varchar) AS fb_r3, CAST(fb_r4 AS varchar) AS fb_r4, CAST(fb_net60 AS varchar) AS fb_net60,
           fb_p99, fb_nprior,
           CAST(NULL AS varchar) AS z_cut, CAST(NULL AS BIGINT) AS z_slot, CAST(NULL AS BIGINT) AS z_txi,
           CAST(NULL AS BIGINT) AS z_oix, CAST(NULL AS BIGINT) AS z_iix, CAST(NULL AS double) AS z_t,
           CAST(NULL AS varchar) AS z_r1, CAST(NULL AS varchar) AS z_r2, CAST(NULL AS varchar) AS z_r3, CAST(NULL AS varchar) AS z_r4,
           CAST(NULL AS varchar) AS z_bps1, CAST(NULL AS varchar) AS z_bps2, CAST(NULL AS varchar) AS z_bps3,
           CAST(NULL AS varchar) AS zf_pr, CAST(NULL AS varchar) AS zf_cr, CAST(NULL AS varchar) AS zf_lp, CAST(NULL AS BIGINT) AS z_n,
           count(*) OVER (PARTITION BY mint, usr) AS n_key
    FROM y{zpart}
)"""

CYC_Z_PART = """
    UNION ALL
    SELECT 'solana', 'P', '{stage}', mint, NULL,
           NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
           NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
           z_cut, slot, txi, oix, iix, to_unixtime(ts),
           CAST(r1 AS varchar), CAST(r2 AS varchar), CAST(r3 AS varchar), CAST(r4 AS varchar),
           CAST(bps1 AS varchar), CAST(bps2 AS varchar), CAST(bps3 AS varchar),
           CAST(zf_pr AS varchar), CAST(zf_cr AS varchar), CAST(zf_lp AS varchar), z_n,
           count(*) OVER (PARTITION BY mint, z_cut)
    FROM z"""

CYC_COLS = (
    "chain kind stage mint usr n_buy n_sell in_cash out_cash tok_buy tok_sell amt_buy amt_sell in_pre out_pre "
    "tok_buy_pre tok_sell_pre f_cb f_bb n_cb_null sb first_t last_t fb_slot fb_txi fb_oix fb_iix fb_t fb_tx fb_cash fb_amt "
    "fb_tok fb_r1 fb_r2 fb_r3 fb_r4 fb_net60 fb_p99 fb_nprior z_cut z_slot z_txi z_oix z_iix z_t z_r1 z_r2 z_r3 z_r4 "
    "z_bps1 z_bps2 z_bps3 zf_pr zf_cr zf_lp z_n n_key"
)

# ---------- COSTF：交易成本（成功与失败，一天一条，交易表只扫一次） ----------

COSTF = """,
lg0 AS (
    /* 抽样币的成交腿（成功交易；事件表），本时段 [{t0}, {t1})。交易者现金：曲线按 v1（买入为负），PumpSwap 用用户报价金额 */
    SELECT t.evt_tx_id AS tx_id, t.mint, 'curve' AS stage, CAST(t."user" AS varchar) AS usr,
           CASE WHEN COALESCE(t.is_buy, t.isBuy)
                THEN -(CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) + COALESCE(CAST(t.fee AS DECIMAL(38,0)), 0)
                       + COALESCE(CAST(t.creator_fee AS DECIMAL(38,0)), 0))
                ELSE CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) - COALESCE(CAST(t.fee AS DECIMAL(38,0)), 0)
                       - COALESCE(CAST(t.creator_fee AS DECIMAL(38,0)), 0) END AS cash
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= TIMESTAMP '{t0}' AND t.evt_block_time < TIMESTAMP '{t1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    UNION ALL
    SELECT a.tx_id, p.mint, 'amm', a.usr, a.cash
    FROM (
        SELECT evt_tx_id AS tx_id, pool, evt_block_time AS ts, CAST("user" AS varchar) AS usr,
               -CAST(user_quote_amount_in AS DECIMAL(38,0)) AS cash
        FROM pumpdotfun_solana.pump_amm_evt_buyevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
          AND evt_block_time >= TIMESTAMP '{t0}' AND evt_block_time < TIMESTAMP '{t1}'
        UNION ALL
        SELECT evt_tx_id, pool, evt_block_time, CAST("user" AS varchar), CAST(user_quote_amount_out AS DECIMAL(38,0))
        FROM pumpdotfun_solana.pump_amm_evt_sellevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
          AND evt_block_time >= TIMESTAMP '{t0}' AND evt_block_time < TIMESTAMP '{t1}'
    ) a
    JOIN pools p ON p.pool = a.pool
    WHERE a.ts >= p.created_at AND a.ts < p.coin_created_at + INTERVAL '{hz}' DAY
      AND a.ts < TIMESTAMP '{cutoff} 00:00:00'
),
lt AS (
    SELECT tx_id, count(DISTINCT usr) AS n_users, max(usr) AS usr1, sum(cash) AS cash,
           array_distinct(array_agg(mint)) AS mints,
           array_distinct(array_agg(mint || '|' || stage)) AS slegs
    FROM lg0
    GROUP BY 1
),
la AS (
    /* 同一批交易里的全部 pump 腿（任何币；只用来数腿与定序，不读金额）：腿号＝币|阶段；非抽样币的 PumpSwap 腿用池地址代币 */
    SELECT DISTINCT t.evt_tx_id AS tx_id, t.mint || '|curve' AS leg
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= TIMESTAMP '{t0}' AND t.evt_block_time < TIMESTAMP '{t1}'
      AND t.evt_tx_id IN (SELECT tx_id FROM lt)
    UNION
    SELECT DISTINCT a.evt_tx_id, COALESCE(p.mint, a.pool) || '|amm'
    FROM (SELECT evt_tx_id, pool FROM pumpdotfun_solana.pump_amm_evt_buyevent
           WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
             AND evt_block_time >= TIMESTAMP '{t0}' AND evt_block_time < TIMESTAMP '{t1}'
          UNION ALL
          SELECT evt_tx_id, pool FROM pumpdotfun_solana.pump_amm_evt_sellevent
           WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
             AND evt_block_time >= TIMESTAMP '{t0}' AND evt_block_time < TIMESTAMP '{t1}') a
    LEFT JOIN pools p ON p.pool = a.pool
    WHERE a.evt_tx_id IN (SELECT tx_id FROM lt)
),
ln AS (SELECT tx_id, array_sort(array_agg(leg)) AS alegs FROM la GROUP BY 1),
sk AS (
    /* 抽样币与它的建池时刻：失败交易按时刻归阶段（建池之后为 PumpSwap） */
    SELECT k.mint, p.created_at AS pool_t FROM coins k LEFT JOIN pools p ON p.mint = k.mint
),
s AS (
    /* 交易表只扫一次：成功的成交交易（在 lt 里）＋调用 pump 或 PumpSwap 的失败交易 */
    SELECT s.id AS tx_id, s.block_time, s.signer, s.success, CAST(s.fee AS DECIMAL(38,0)) AS fee, s.required_signatures,
           s.pre_balances, s.post_balances, s.pre_token_balances, s.post_token_balances, fk.keys,
           l.n_users, l.usr1, l.cash, l.slegs, n.alegs,
           cardinality(fk.keys) = cardinality(s.pre_balances) AND cardinality(fk.keys) = cardinality(s.post_balances)
             AND cardinality(array_distinct(fk.keys)) = cardinality(fk.keys)
             AND NOT any_match(fk.keys, x -> x IS NULL) AS keys_ok,
           NOT (COALESCE(any_match(s.pre_token_balances, b -> b.owner = s.signer AND b.mint <> '{wsol}' AND NOT contains(l.mints, b.mint)), false)
                OR COALESCE(any_match(s.post_token_balances, b -> b.owner = s.signer AND b.mint <> '{wsol}' AND NOT contains(l.mints, b.mint)), false))
             AS scope_complete
    FROM solana.transactions s
    LEFT JOIN lt l ON l.tx_id = s.id
    LEFT JOIN ln n ON n.tx_id = s.id
    CROSS JOIN UNNEST(ARRAY[
        CASE WHEN cardinality(s.account_keys) = cardinality(s.pre_balances) THEN s.account_keys
             ELSE concat(s.account_keys, COALESCE(s.loaded_addresses.writable, CAST(ARRAY[] AS array(varchar))),
                         COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar)))) END]) AS fk(keys)
    WHERE s.block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND s.block_time >= TIMESTAMP '{t0}' AND s.block_time < TIMESTAMP '{t1}'
      AND s.block_time < TIMESTAMP '{cutoff} 00:00:00'
      AND (l.tx_id IS NOT NULL
           OR (s.success = false
               AND (contains(s.account_keys, '{pump}') OR contains(s.account_keys, '{amm}')
                    OR contains(COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar))), '{pump}')
                    OR contains(COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar))), '{amm}'))))
),
u AS (
    SELECT s.tx_id, s.block_time, s.signer, s.success, s.fee, s.required_signatures, s.n_users, s.usr1, s.cash,
           s.slegs, s.alegs, s.keys_ok, s.scope_complete, x.acct,
           CAST(x.post AS DECIMAL(38,0)) - CAST(x.pre AS DECIMAL(38,0)) AS d,
           s.success AND (x.acct = s.signer
             OR COALESCE(any_match(s.pre_token_balances, b -> b.account = x.acct AND b.owner = s.signer), false)
             OR COALESCE(any_match(s.post_token_balances, b -> b.account = x.acct AND b.owner = s.signer), false)) AS is_trader,
           kp.mint AS pop_mint,
           CASE WHEN ks.mint IS NULL THEN NULL
                WHEN ks.pool_t IS NOT NULL AND s.block_time >= ks.pool_t THEN ks.mint || '|amm'
                ELSE ks.mint || '|curve' END AS f_leg
    FROM s
    CROSS JOIN UNNEST(s.keys, s.pre_balances, s.post_balances) AS x(acct, pre, post)
    LEFT JOIN pop kp ON kp.mint = x.acct AND NOT s.success
    LEFT JOIN sk ks ON ks.mint = x.acct AND NOT s.success
),
g AS (
    SELECT tx_id, arbitrary(signer) AS signer, arbitrary(success) AS success, arbitrary(fee) AS fee,
           arbitrary(required_signatures) AS sigs, arbitrary(n_users) AS n_users, arbitrary(usr1) AS usr1,
           arbitrary(cash) AS cash, arbitrary(slegs) AS slegs, arbitrary(alegs) AS alegs,
           bool_and(keys_ok) AS keys_ok, bool_and(scope_complete) AS scope_complete,
           sum(IF(is_trader, d, 0)) AS d_trader,
           sum(IF(acct IN ({jito}) AND d > 0, d, 0)) AS tip,
           array_distinct(array_agg(f_leg) FILTER (WHERE f_leg IS NOT NULL)) AS flegs,
           array_sort(array_distinct(array_agg(pop_mint) FILTER (WHERE pop_mint IS NOT NULL))) AS pops
    FROM u
    GROUP BY 1
),
v AS (
    /* 每条腿一行（成功交易的抽样腿，或失败交易触及的抽样币）。
       成功：总费＋小费按全部 pump 腿数 n 均摊，余数给排序第一的腿（contract_ledger.allocate_tx_costs）；
       未解释负残差（v1：交易者净变化＋总费＋小费−事件现金 <0）只在“范围完整、唯一用户就是签名者、账户键无误”的交易里计，同样均摊。
       失败：总费按触及的母体币数均摊，余数给排序第一的币 */
    SELECT g.signer, split_part(leg, '|', 1) AS mint, split_part(leg, '|', 2) AS stage, g.success,
           CASE WHEN g.success THEN cardinality(g.alegs) ELSE cardinality(g.pops) END AS n,
           CASE WHEN g.success THEN array_position(g.alegs, leg) = 1
                ELSE array_position(g.pops, split_part(leg, '|', 1)) = 1 END AS first_leg,
           CASE WHEN g.success THEN g.fee + g.tip ELSE g.fee END AS c_tot,
           CASE WHEN g.success THEN CAST(5000 * g.sigs AS DECIMAL(38,0)) ELSE CAST(0 AS DECIMAL(38,0)) END AS c_net,
           CASE WHEN g.success THEN g.tip ELSE CAST(0 AS DECIMAL(38,0)) END AS c_tip,
           g.success AND g.scope_complete AND g.keys_ok AND g.n_users = 1 AND g.usr1 = g.signer AS clean,
           CASE WHEN g.success AND g.scope_complete AND g.keys_ok AND g.n_users = 1 AND g.usr1 = g.signer
                     AND g.d_trader + g.fee + g.tip - g.cash < 0
                THEN -(g.d_trader + g.fee + g.tip - g.cash) ELSE CAST(0 AS DECIMAL(38,0)) END AS r_tot
    FROM g
    CROSS JOIN UNNEST(CASE WHEN g.success THEN g.slegs ELSE g.flegs END) AS lv(leg)
),
out AS (
    SELECT 'solana' AS chain, CASE WHEN success THEN 'K' ELSE 'F' END AS kind, '{e0}' AS day, '{t0}' AS t_from,
           signer, mint, stage, count(*) AS n_tx,
           CAST(sum((c_tot - mod(c_tot, n)) / n + IF(first_leg, mod(c_tot, n), 0)) AS varchar) AS cost,
           CAST(sum((c_net - mod(c_net, n)) / n + IF(first_leg, mod(c_net, n), 0)) AS varchar) AS cost_net,
           CAST(sum((c_tip - mod(c_tip, n)) / n + IF(first_leg, mod(c_tip, n), 0)) AS varchar) AS cost_tip,
           CAST(sum((r_tot - mod(r_tot, n)) / n + IF(first_leg, mod(r_tot, n), 0)) AS varchar) AS res_neg,
           count_if(clean) AS n_tx_clean, count_if(success AND NOT clean) AS n_tx_unclean,
           count(*) OVER (PARTITION BY CASE WHEN success THEN 'K' ELSE 'F' END, signer, mint, stage) AS n_key
    FROM v
    GROUP BY success, signer, mint, stage
)"""

COSTF_COLS = "chain kind day t_from signer mint stage n_tx cost cost_net cost_tip res_neg n_tx_clean n_tx_unclean n_key"

# ---------- VQ：每池的虚拟报价储备 ----------

VQ = """,
vp AS (SELECT pool, mint, created_at, pool_slot, pool_tx FROM pools WHERE created_at >= TIMESTAMP '{vq_from} 00:00:00'),
ib AS (
    /* 只读允许池的建池交易里的 InitBoost 原始记录（GPT 02 的写法：先按允许键筛，再解码）。
       vq 为 i128 小端有符号，偏移与 DQ-35 build_boostscan_sql.py 相同（121～136；池地址 89～120） */
    SELECT vp.pool, vp.mint, c.block_time AS ts, to_base58(bytearray_substring(c.data, 89, 32)) AS ev_pool,
           bytearray_to_bigint(reverse(bytearray_substring(c.data, 121, 8))) AS lo_s,
           bytearray_to_bigint(reverse(bytearray_substring(c.data, 129, 8))) AS hi_s
    FROM solana.instruction_calls c
    JOIN vp ON vp.pool_tx = c.tx_id
    WHERE c.block_date BETWEEN DATE '{v0}' AND DATE '{v1}'
      AND c.executing_account = '{amm}' AND c.is_inner = true AND c.tx_success = true
      AND bytearray_substring(c.data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(c.data, 9, 8) = {d_init}
      AND length(c.data) >= 136
),
iv AS (
    SELECT pool, ts, ev_pool,
           CASE WHEN abs(hi_s) < 4000000000000000000
                THEN CAST(hi_s AS DECIMAL(38,0)) * DECIMAL '18446744073709551616' + CAST(lo_s AS DECIMAL(38,0))
                     + CASE WHEN lo_s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END END AS vq,
           CASE WHEN abs(hi_s) >= 4000000000000000000 THEN 1 ELSE 0 END AS ovf
    FROM ib
),
out AS (
    SELECT 'solana' AS chain, p.pool, p.mint, to_unixtime(p.created_at) AS pool_t, p.pool_slot, p.pool_tx,
           count(i.pool) AS n_init, count_if(i.ev_pool <> i.pool) AS n_pool_mismatch,
           CAST(min(i.vq) AS varchar) AS vq_min, CAST(max(i.vq) AS varchar) AS vq_max,
           to_unixtime(min(i.ts)) AS init_t, COALESCE(sum(i.ovf), 0) AS n_ovf,
           p.created_at < TIMESTAMP '{vq_from} 00:00:00' AS layout0, 1 AS n_key
    FROM pools p
    LEFT JOIN iv i ON i.pool = p.pool
    GROUP BY p.pool, p.mint, p.created_at, p.pool_slot, p.pool_tx
)"""

VQ_COLS = "chain pool mint pool_t pool_slot pool_tx n_init n_pool_mismatch vq_min vq_max init_t n_ovf layout0 n_key"

# ---------- 冒烟：结构核对＋逐行哈希（双跑比对用） ----------

CHECKSUM = """,
       count(*) AS ck_rows,
       sum(CAST(bitwise_and(from_big_endian_64(xxhash64(to_utf8(concat_ws('|', {ck_cols})))), 9223372036854775807) AS DECIMAL(38,0))) AS ck_sum,
       bitwise_xor_agg(from_big_endian_64(xxhash64(to_utf8(concat_ws('|', {ck_cols}))))) AS ck_xor"""

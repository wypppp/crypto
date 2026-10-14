#!/usr/bin/env python3
"""DQ-43（WM2）取数 SQL 生成器（10-13，冻结卡 v3 §5、§6；GPT 审 SQL 之前不跑全量）。

python build_wm2_sql.py <层> <创建起日> <创建止日> <事件起日> <事件止日> <标签> [建边起日 建边截日] [--smoke]
  [--p=抽样率] [--snap=快照截日] [--part=i/n] [--tpart=i/n]  → sql/<标签>.sql

层：
  COIN    母体：曲线创建于 [创建起日, 创建止日] 的 SOL 计价 pump 新币，每币一行（含毕业与迁移）。
  CTRADE  曲线成交逐笔（冻结卡 §5 为 C 保留的字段全在）；2026-05-07 起从原始字节补虚拟报价储备与持有人奖励（DQ-37 写法）。
  MAY     mayhem 币的储备改写事件（成交之外改写曲线储备，估值并入状态流；DQ-37 写法）。
  ATRADE  PumpSwap 成交逐笔（只取由 pump 迁移创建、池序号 0 的池）；07-15 起逐笔解出 vq、返现、回购费（DQ-35 v2.2 模板原样调用）。
  TX      成交交易的成本与 T2a：签名费、优先费、Jito 小费；交易者一类（签名者＋签名者名下的代币账户）的 lamport 变化。
  FAIL    失败交易：触及母体币、调用 pump 或 PumpSwap 程序的失败交易（全成本含失败交易，冻结卡 §6）。
  EDGE    实体边：顶层 System Program 的 SOL 转账 ≥0.05（DQ-26 E1 规则），一端是母体成交的交易者；
          以及母体币的直接代币转移（顶层代币程序或关联账户程序，不含成交腿）。
  汇总版（10-14，取数附录 v2；模板在 wm2_agg_sql.py）：CYCC、CYCA（钱包 × 币的阶段合计与首笔买入状态，每币两个时点的定价状态）、
  COSTF（一天一条：成功交易的链上费用与未解释负残差、失败交易费用，按腿均摊）、VQ（每池 InitBoost 的 vq）。

保护边界在 SQL 里先落实（冻结卡 §5，过滤在导出之前）：
- 币：创建时刻在 [创建起日, 创建止日]，这些日子必须全在 DQ-43 的六个窗口周内（都是 DQ-37 开发周）；早于 2026-10-05；
  代号缺失或规范化后为空、或与 152 个留出名单同名的不取（upper(trim(replace(symbol,'$',''))）；非 SOL 计价不取。
- 成交与一切事件：时刻严格早于 2026-10-05 00:00 UTC，且在币创建后 30 天之内；事件止日不晚于 2026-10-04。
- 边：只用止日之前的转账；代币转移只取母体币（母体已过滤）。
- 被去掉的币不出行；冒烟模式的计数只报“入选”与“排除合计”，不分原因（不展示保护范围的活跃度）。

排序键一律输出四列 (slot, 交易序, 外层, 内层；内层缺失记 −1)，SQL 里按多列元组排序，不拼定宽整数（DQ-35 ③ 的教训）。
金额一律整数（DECIMAL(38,0)），输出文本；时间输出 epoch 秒（to_unixtime）。

--smoke：同一套 CTE，最后一步只出结构核对（行数、键重复、字段缺失、估计导出字节；TX 层出 T2a 残差分布与资金路径），
不出任何按标签、按实体的盈亏或分布（冻结卡 §5 冒烟的输出边界）。
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parents[0] / "pump毕业币_数据留存_DQ-35"))
sys.path.insert(0, str(H.parents[0] / "发射台_前期右尾评测底座_DQ-37"))
import build_curve_sql_v1 as C37  # noqa: E402
import build_grad_sql_v22 as G35  # noqa: E402
import contract_pairs as CP  # noqa: E402
import weeks as W  # noqa: E402
import wm2_agg_sql as AG  # noqa: E402

CUTOFF = dt.date(2026, 10, 5)
LAST_EVENT_DAY = dt.date(2026, 10, 4)
HORIZON_DAYS = 30
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
SYS = "11111111111111111111111111111111"
QUOTE_FIELDS_FROM = dt.date(
    2026, 5, 7
)  # DQ-37：曲线成交的 quote 字段从这天的 IDL 版本起
JITO = (
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
)
TOKEN_PROGRAMS = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
)
EDGE_MIN_SOL = 0.05  # DQ-26 E1
LAYERS = (
    "COIN",
    "CTRADE",
    "MAY",
    "ATRADE",
    "TX",
    "FAIL",
    "EDGE",
    "CYCC",
    "CYCA",
    "CYCCP",
    "CYCAP",
    "COSTF",
    "VQ",
)
VQ_FROM = dt.date(
    2026, 7, 15
)  # DQ-35 §1d：vq 字段在 07-15 升级时上线，之前建的池 vq＝0（layout0）
D_INIT = "0xae7c4af90451f611"  # DQ-35 过程/build_boostscan_sql.py：InitBoost 判别符


def window_days() -> set[dt.date]:
    """六个窗口周（三对的 W 与 W+1）的全部日子。"""
    sel = CP.select()
    out = set()
    for w in [sel["old"]] + sel["late"]:
        for m in (w, w + dt.timedelta(days=7)):
            out |= {m + dt.timedelta(days=i) for i in range(7)}
    return out


def q(items) -> str:
    return ", ".join("'%s'" % x for x in items)


def check_dates(c0, c1, e0, e1) -> None:
    days = window_days()
    d = c0
    while d <= c1:
        if d not in days or W.week_class(d - dt.timedelta(days=d.weekday())) != W.DEV:
            raise SystemExit("创建日 %s 不在 DQ-43 窗口周或不是开发周" % d)
        d += dt.timedelta(days=1)
    if not (c0 <= c1 and c0 <= e0 <= e1):
        raise SystemExit("日期次序不对：创建起 ≤ 创建止，创建起 ≤ 事件起 ≤ 事件止")
    if e1 > LAST_EVENT_DAY:
        raise SystemExit("事件止日不能晚于 %s（观测止日）" % LAST_EVENT_DAY)
    if e1 > c1 + dt.timedelta(days=HORIZON_DAYS):
        raise SystemExit("事件止日超出创建后 30 天")


# ---------- 母体（各层共用） ----------

POP = """/* DQ-43 WM2 取数（冻结卡 v4、取数附录 v2）：层 {layer}{smoke_tag}；曲线创建于 {c0}～{c1} 的 SOL 计价 pump 新币；事件 {e0}～{e1}；
   只存不分析；由 build_wm2_sql.py 生成。保护过滤在导出之前：开发窗口周、止日 2026-10-05、代号缺失或为空、留出同名、非 SOL。 */
WITH
{names},
c0 AS (
    SELECT mint, min(evt_block_time) AS created_at, count(*) AS n_create,
           min_by(name, evt_block_time) AS name, min_by(symbol, evt_block_time) AS symbol,
           min_by(uri, evt_block_time) AS uri, min_by(COALESCE(creator, "user"), evt_block_time) AS creator,
           min_by("user", evt_block_time) AS create_user, min_by(evt_tx_signer, evt_block_time) AS create_signer,
           min_by(evt_tx_id, evt_block_time) AS create_tx, min_by(evt_block_slot, evt_block_time) AS c_slot,
           min_by(evt_tx_index, evt_block_time) AS c_txi, min_by(evt_outer_instruction_index, evt_block_time) AS c_oix,
           min_by(COALESCE(evt_inner_instruction_index, -1), evt_block_time) AS c_iix,
           min_by(bonding_curve, evt_block_time) AS bonding_curve,
           min_by(token_program, evt_block_time) AS token_program,
           min_by(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
           min_by(is_cashback_enabled, evt_block_time) AS is_cashback_enabled,
           min_by(quote_mint, evt_block_time) AS quote_mint,
           min_by(CAST(virtual_sol_reserves AS DECIMAL(38,0)), evt_block_time) AS vsr0,
           min_by(CAST(virtual_token_reserves AS DECIMAL(38,0)), evt_block_time) AS vtr0,
           min_by(CAST(real_token_reserves AS DECIMAL(38,0)), evt_block_time) AS rtr0,
           min_by(CAST(virtual_quote_reserves AS DECIMAL(38,0)), evt_block_time) AS vqr0,
           min_by(CAST(token_total_supply AS DECIMAL(38,0)), evt_block_time) AS supply
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{c0}' AND DATE '{c1}'
    GROUP BY 1
),
c1 AS (
    SELECT c0.*,
           CASE WHEN symbol IS NULL OR trim(replace(symbol, '$', '')) = '' THEN 'excl'
                WHEN upper(trim(replace(symbol, '$', ''))) IN (SELECT base FROM excl) THEN 'excl'
                WHEN quote_mint IS NOT NULL AND quote_mint <> '{sys}' THEN 'excl'
                ELSE 'in' END AS pop_class
    FROM c0
    WHERE created_at >= TIMESTAMP '{c0} 00:00:00' AND created_at < TIMESTAMP '{c1} 00:00:00' + INTERVAL '1' DAY
      AND created_at < TIMESTAMP '{cutoff} 00:00:00'
),
pop AS (SELECT * FROM c1 WHERE pop_class = 'in'),
coins AS (SELECT * FROM pop{samp})"""

# ---------- 曲线成交 ----------

CURVE = """,
tr AS (
    SELECT t.mint, k.created_at, t.evt_block_time AS ts,
           t.evt_block_slot AS slot, t.evt_tx_index AS txi, t.evt_outer_instruction_index AS oix,
           COALESCE(t.evt_inner_instruction_index, -1) AS iix, t.evt_inner_instruction_index AS iix0,
           t.evt_tx_id AS tx_id, t.evt_tx_signer AS signer, CAST(t."user" AS varchar) AS usr,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DECIMAL(38,0)) AS vsr,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DECIMAL(38,0)) AS vtr,
           CAST(t.real_sol_reserves AS DECIMAL(38,0)) AS rsr, CAST(t.real_token_reserves AS DECIMAL(38,0)) AS rtr,
           CAST(t.fee AS DECIMAL(38,0)) AS f_pr, CAST(t.creator_fee AS DECIMAL(38,0)) AS f_cr,
           CAST(t.cashback AS DECIMAL(38,0)) AS f_cb, CAST(t.buyback_fee AS DECIMAL(38,0)) AS f_bb,
           CAST(t.fee_basis_points AS DECIMAL(38,0)) AS fee_bps, CAST(t.creator_fee_basis_points AS DECIMAL(38,0)) AS cfee_bps,
           CAST(t.cashback_fee_basis_points AS DECIMAL(38,0)) AS cb_bps, CAST(t.buyback_fee_basis_points AS DECIMAL(38,0)) AS bb_bps,
           t.fee_recipient, t.creator AS ev_creator, t.mayhem_mode AS mayhem, t.ix_name, t.track_volume,
           t.quote_mint AS q_mint, CAST(t.quote_amount AS DECIMAL(38,0)) AS q_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
){raw}"""

CURVE_OUT = """,
r AS (SELECT tr.* FROM tr),
out AS (
    SELECT 'solana' AS chain, r.mint, to_unixtime(r.created_at) AS created_t, to_unixtime(r.ts) AS ts,
           r.slot, r.txi, r.oix, r.iix, count(*) OVER (PARTITION BY r.slot, r.txi, r.oix, r.iix) AS n_key,
           r.tx_id, r.signer, r.usr, r.is_buy,
           CAST(r.sol AS varchar) AS sol, CAST(r.tok AS varchar) AS tok,
           CAST(r.vsr AS varchar) AS vsr, CAST(r.vtr AS varchar) AS vtr, CAST(r.rsr AS varchar) AS rsr, CAST(r.rtr AS varchar) AS rtr,
           CAST(r.f_pr AS varchar) AS f_pr, CAST(r.f_cr AS varchar) AS f_cr, CAST(r.f_cb AS varchar) AS f_cb, CAST(r.f_bb AS varchar) AS f_bb,
           CAST(r.fee_bps AS varchar) AS fee_bps, CAST(r.cfee_bps AS varchar) AS cfee_bps,
           CAST(r.cb_bps AS varchar) AS cb_bps, CAST(r.bb_bps AS varchar) AS bb_bps,
           r.fee_recipient, r.ev_creator, r.mayhem, r.ix_name, r.track_volume, r.q_mint, CAST(r.q_amt AS varchar) AS q_amt{raw_cols}
    FROM r{raw_join}
)"""

RAW_COLS = """,
           CAST(rv.vqr AS varchar) AS vqr, CAST(rv.rqr AS varchar) AS rqr, CAST(rv.hr_bps AS varchar) AS hr_bps, CAST(rv.hr AS varchar) AS hr,
           CASE WHEN r.ts < TIMESTAMP '{r0} 00:00:00' THEN 'layout0' WHEN rv.tx_id IS NULL THEN 'missing'
                WHEN rv.vqr IS NOT NULL THEN 'raw' ELSE 'layout0' END AS q_src,
           CASE WHEN rv.tx_id IS NULL THEN NULL
                WHEN rv.r_mint = r.mint AND rv.r_sol = r.sol AND (rv.r_qa IS NULL OR r.q_amt IS NULL OR rv.r_qa = r.q_amt) THEN 1 ELSE 0 END AS xchk_ok"""

NO_RAW_COLS = """,
           CAST(NULL AS varchar) AS vqr, CAST(NULL AS varchar) AS rqr, CAST(NULL AS varchar) AS hr_bps, CAST(NULL AS varchar) AS hr,
           'layout0_date' AS q_src, CAST(NULL AS INTEGER) AS xchk_ok"""

MAY = """,
out AS (
    SELECT 'solana' AS chain, u.mint, to_unixtime(u.evt_block_time) AS ts, u.evt_block_slot AS slot, u.evt_tx_index AS txi,
           u.evt_outer_instruction_index AS oix, COALESCE(u.evt_inner_instruction_index, -1) AS iix,
           count(*) OVER (PARTITION BY u.evt_block_slot, u.evt_tx_index, u.evt_outer_instruction_index,
                          COALESCE(u.evt_inner_instruction_index, -1)) AS n_key,
           u.evt_tx_id AS tx_id,
           CAST(u.virtual_token_reserves AS varchar) AS vtr_old, CAST(u.virtual_sol_reserves AS varchar) AS vsr_old,
           CAST(u.new_virtual_token_reserves AS varchar) AS vtr_new, CAST(u.new_virtual_sol_reserves AS varchar) AS vsr_new,
           CAST(u.real_token_reserves AS varchar) AS rtr, CAST(u.real_sol_reserves AS varchar) AS rsr
    FROM pumpdotfun_solana.pump_evt_updatemayhemvirtualparamsevent u
    JOIN coins k ON k.mint = u.mint
    WHERE u.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND u.evt_block_time >= k.created_at AND u.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND u.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
)"""

# ---------- 母体每币一行 ----------

COIN = """,
comp AS (
    /* 10-14（GPT 01）：聚合前 JOIN coins，逐币限 created_at ≤ 事件 < created_at＋30 天，并保留全局止日 */
    SELECT e.mint, to_unixtime(min(e.evt_block_time)) AS completed_t, count(*) AS n_complete,
           /* 10-14（汇总版）：毕业事件的键、交易与触发者，A 的命中与自身触发要用 */
           min_by(e.evt_block_slot, e.evt_block_time) AS comp_slot, min_by(e.evt_tx_index, e.evt_block_time) AS comp_txi,
           min_by(e.evt_outer_instruction_index, e.evt_block_time) AS comp_oix,
           min_by(COALESCE(e.evt_inner_instruction_index, -1), e.evt_block_time) AS comp_iix,
           min_by(e.evt_tx_id, e.evt_block_time) AS comp_tx, min_by(CAST(e."user" AS varchar), e.evt_block_time) AS comp_user
    FROM pumpdotfun_solana.pump_evt_completeevent e
    JOIN coins k ON k.mint = e.mint
    WHERE e.evt_block_date BETWEEN DATE '{c0}' AND DATE '{e1}'
      AND e.evt_block_time >= k.created_at AND e.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND e.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    GROUP BY 1
),
mig AS (
    SELECT e.mint, to_unixtime(min(e.evt_block_time)) AS migrated_t, min_by(e.pool, e.evt_block_time) AS pool, count(*) AS n_mig
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent e
    JOIN coins k ON k.mint = e.mint
    WHERE e.evt_block_date BETWEEN DATE '{c0}' AND DATE '{e1}'
      AND e.evt_block_time >= k.created_at AND e.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND e.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    GROUP BY 1
),
out AS (
    /* 10-14 精简（取数附录 v2 §3）：不出名称、URI、创建交易号、曲线账户、代币程序、计价币（都已在入口过滤或用不到）；
       创建交易由 (c_slot, c_txi) 唯一确定 */
    SELECT 'solana' AS chain, k.mint, to_unixtime(k.created_at) AS created_t, k.n_create, k.symbol, k.creator,
           k.create_user, k.c_slot, k.c_txi, k.c_oix, k.c_iix,
           k.is_mayhem_mode, k.is_cashback_enabled,
           CAST(k.vsr0 AS varchar) AS vsr0, CAST(k.vtr0 AS varchar) AS vtr0, CAST(k.rtr0 AS varchar) AS rtr0,
           CAST(k.supply AS varchar) AS supply,
           cp.completed_t, cp.n_complete, cp.comp_slot, cp.comp_txi, cp.comp_oix, cp.comp_iix, cp.comp_tx, cp.comp_user,
           mg.migrated_t, mg.pool, mg.n_mig,
           k.created_at + INTERVAL '{hz}' DAY <= TIMESTAMP '{cutoff} 00:00:00' AS window_complete,
           count(*) OVER (PARTITION BY k.mint) AS n_key
    FROM coins k
    LEFT JOIN comp cp ON cp.mint = k.mint
    LEFT JOIN mig mg ON mg.mint = k.mint
)"""

COIN_SMOKE_EXTRA = """,
       (SELECT count(*) FROM c1 WHERE pop_class <> 'in') AS n_excluded,
       (SELECT count(DISTINCT mint) FROM pumpdotfun_solana.pump_evt_createevent
         WHERE evt_block_date BETWEEN DATE '{c0}' AND DATE '{c1}'
           AND evt_block_time >= TIMESTAMP '{c0} 00:00:00' AND evt_block_time < TIMESTAMP '{c1} 00:00:00' + INTERVAL '1' DAY)
         - (SELECT count(*) FROM c1) AS identity_gap"""

# ---------- PumpSwap 成交 ----------

POOLS = """,
cp AS (
    /* 10-14（GPT 01）：建池事件聚合前 JOIN coins，逐币 30 天窗口与全局止日 */
    SELECT c.pool, min(c.evt_block_time) AS created_at, min_by(c.evt_block_slot, c.evt_block_time) AS pool_slot,
           min_by(c.evt_tx_id, c.evt_block_time) AS pool_tx,
           max(c.base_mint) AS mint, max(c.quote_mint) AS quote_mint,
           max(c.base_mint_decimals) AS bd, max(c.quote_mint_decimals) AS qd, count(*) AS n_cp
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent c
    JOIN coins k ON k.mint = c.base_mint
    WHERE c.evt_block_date BETWEEN DATE '{c0}' AND DATE '{e1}'
      AND c.evt_outer_executing_account = '{pump}'
      AND c.index = 0
      AND c.evt_block_time >= k.created_at AND c.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND c.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    GROUP BY 1
),
pools AS (
    SELECT cp.*, k.created_at AS coin_created_at
    FROM cp JOIN coins k ON k.mint = cp.mint
    WHERE cp.quote_mint = '{wsol}'
)"""

AMM_KEYS = """,
ak AS (
    /* 10-14（GPT 02）：允许的 PumpSwap 事件键（允许池、逐币窗口内的买卖），原始字节先按它筛选再解码 */
    SELECT DISTINCT 'B' AS side, a.evt_tx_id AS tx_id, a.evt_outer_instruction_index AS oix, a.evt_inner_instruction_index AS iix0
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a
    JOIN pools p ON p.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '{r_start}' AND DATE '{e1}'
      AND a.evt_block_time >= p.created_at AND a.evt_block_time < p.coin_created_at + INTERVAL '{hz}' DAY
      AND a.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    UNION ALL
    SELECT DISTINCT 'S', a.evt_tx_id, a.evt_outer_instruction_index, a.evt_inner_instruction_index
    FROM pumpdotfun_solana.pump_amm_evt_sellevent a
    JOIN pools p ON p.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '{r_start}' AND DATE '{e1}'
      AND a.evt_block_time >= p.created_at AND a.evt_block_time < p.coin_created_at + INTERVAL '{hz}' DAY
      AND a.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
)"""

AMM_IC = """ic AS (
    /* 10-14（GPT 02）：只读允许事件键对应的原始记录；boost 原始记录本层不用，不读 */
    SELECT c.tx_id, c.block_slot AS slot, c.tx_index AS txi, c.outer_instruction_index AS oix, c.inner_instruction_index AS iix,
           c.block_time AS ts, c.data AS b, bytearray_substring(c.data, 9, 8) AS disc
    FROM solana.instruction_calls c
    JOIN ak ON ak.tx_id = c.tx_id AND ak.oix = c.outer_instruction_index AND ak.iix0 = c.inner_instruction_index
    WHERE c.block_date BETWEEN DATE '{r_start}' AND DATE '{e1}'
      AND c.executing_account = '{amm}'
      AND c.is_inner = true AND c.tx_success = true
      AND bytearray_substring(c.data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(c.data, 9, 8) = CASE ak.side WHEN 'B' THEN {d_buy} ELSE {d_sell} END
)"""

CURVE_IC = """ic AS (
    /* 10-14（GPT 02）：只读允许曲线事件键（tr 里逐币窗口内的成交）对应的原始记录，同笔交易的其他事件不进 */
    SELECT c.tx_id, c.outer_instruction_index AS oix, c.inner_instruction_index AS iix, c.block_slot AS slot,
           c.tx_index AS txi, c.data AS b
    FROM solana.instruction_calls c
    JOIN (SELECT DISTINCT tx_id, oix, iix0 FROM tr WHERE ts >= TIMESTAMP '{r0} 00:00:00') rk
      ON rk.tx_id = c.tx_id AND rk.oix = c.outer_instruction_index AND rk.iix0 = c.inner_instruction_index
    WHERE c.block_date BETWEEN DATE '{r0}' AND DATE '{t1}'
      AND c.executing_account = '{program}' AND c.is_inner = true AND c.tx_success = true
      AND bytearray_substring(c.data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(c.data, 9, 8) = {d_trade}
)"""


def _swap_ic(raw: str, new_ic: str, end_marker: str) -> str:
    """把复用模板里的 ic CTE 换成按允许事件键筛选的版本（其余解码逻辑原样复用）。"""
    i = raw.index("ic AS (")
    j = raw.index(end_marker, i)
    assert raw.count("ic AS (") == 1
    return raw[:i] + new_ic + raw[j:]


AMM_OUT = """,
out AS (
    SELECT 'solana' AS chain, p.mint, k.pool, to_unixtime(p.coin_created_at) AS created_t, to_unixtime(p.created_at) AS pool_t,
           to_unixtime(k.ts) AS ts, k.slot, k.txi, k.oix, k.iix, k.n_key, k.tx_id, k.side, CAST(k.usr AS varchar) AS usr,
           CAST(k.q0 AS varchar) AS q0, CAST(k.b0 AS varchar) AS b0, CAST(k.q1 AS varchar) AS q1, CAST(k.b1 AS varchar) AS b1,
           CAST(k.q_pool AS varchar) AS q_pool, CAST(k.b_amt AS varchar) AS b_amt, CAST(k.q_user AS varchar) AS q_user,
           CAST(k.q_gross_out AS varchar) AS q_gross_out,
           CAST(k.f_lp AS varchar) AS f_lp, CAST(k.f_pr AS varchar) AS f_pr, CAST(k.f_cr AS varchar) AS f_cr,
           CAST(k.f_cb AS varchar) AS f_cb, CAST(k.f_bb AS varchar) AS f_bb,
           CAST(k.vq AS varchar) AS vq, k.vq_src, k.vq_ovf, k.ovf,
           CASE WHEN k.vlo IS NULL THEN NULL WHEN k.vq IS NULL THEN NULL
                WHEN k.vq >= k.vlo AND k.vq <= k.vhi THEN 1 ELSE 0 END AS xchk_ok,
           k.bd, k.qd
    FROM k
    JOIN pools p ON p.pool = k.pool
    WHERE k.ts < p.coin_created_at + INTERVAL '{hz}' DAY
      AND k.ts < TIMESTAMP '{cutoff} 00:00:00'
)"""

# ---------- 交易成本与 T2a ----------

LEGS = """,
cl AS (
    SELECT t.evt_tx_id AS tx_id, t.mint, CAST(t."user" AS varchar) AS usr, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           COALESCE(CAST(t.fee AS DECIMAL(38,0)), 0) AS f_pr, COALESCE(CAST(t.creator_fee AS DECIMAL(38,0)), 0) AS f_cr,
           COALESCE(CAST(t.cashback AS DECIMAL(38,0)), 0) AS f_cb, COALESCE(CAST(t.buyback_fee AS DECIMAL(38,0)), 0) AS f_bb,
           t.fee_recipient
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
),
al AS (
    SELECT a.evt_tx_id AS tx_id, p.mint, CAST(a."user" AS varchar) AS usr, a.side,
           CAST(a.q_user AS DECIMAL(38,0)) AS q_user
    FROM (
        SELECT evt_tx_id, "user", 'B' AS side, user_quote_amount_in AS q_user, pool, evt_block_time
        FROM pumpdotfun_solana.pump_amm_evt_buyevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
        UNION ALL
        SELECT evt_tx_id, "user", 'S', user_quote_amount_out, pool, evt_block_time
        FROM pumpdotfun_solana.pump_amm_evt_sellevent
        WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
    ) a
    JOIN pools p ON p.pool = a.pool
    WHERE a.evt_block_time >= p.created_at AND a.evt_block_time < p.coin_created_at + INTERVAL '{hz}' DAY
      AND a.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
),
legs AS (
    SELECT tx_id, mint, usr, 'C' AS venue,
           CASE WHEN is_buy THEN -(sol + f_pr + f_cr) ELSE sol - f_pr - f_cr END AS cash_v1,
           CASE WHEN is_buy THEN -(sol + f_pr + f_cr + f_bb) ELSE sol - f_pr - f_cr - f_bb END AS cash_v2,
           CASE WHEN is_buy THEN -(sol + f_pr + f_cr + f_bb) + f_cb ELSE sol - f_pr - f_cr - f_bb + f_cb END AS cash_v3,
           fee_recipient
    FROM cl
    UNION ALL
    SELECT tx_id, mint, usr, 'A',
           CASE WHEN side = 'B' THEN -q_user ELSE q_user END,
           CASE WHEN side = 'B' THEN -q_user ELSE q_user END,
           CASE WHEN side = 'B' THEN -q_user ELSE q_user END,
           CAST(NULL AS varchar)
    FROM al
),
lt AS (
    SELECT tx_id, count(*) AS n_legs, count(DISTINCT usr) AS n_users, max(usr) AS usr1,
           count_if(venue = 'C') AS n_curve, count_if(venue = 'A') AS n_amm,
           sum(cash_v1) AS cash_v1, sum(cash_v2) AS cash_v2, sum(cash_v3) AS cash_v3,
           array_distinct(array_agg(fee_recipient) FILTER (WHERE fee_recipient IS NOT NULL)) AS fee_recips,
           array_distinct(array_agg(mint)) AS mints
    FROM legs{tx_sample}
    GROUP BY 1
),
bal AS (
    /* 10-13：交易表只扫一次（CTE 被多处引用时 Trino 会重扫；首次冒烟 30 分钟超时、104.19 credits）。
       account_keys 在 v0 交易里已含查找表地址（再拼会错位），只有长度不够时才补拼；
       transaction_config.priority_fee 在 Dune 里为空，优先费＝总费 − 5000 × 签名数。 */
    SELECT s.id AS tx_id, s.block_time, s.block_slot AS slot, s.index AS txi, s.signer, s.success, s.fee,
           s.fee - 5000 * s.required_signatures AS priority_fee, s.required_signatures, s.compute_units_consumed,
           s.transaction_config.compute_unit_limit AS cu_limit,
           cardinality(s.account_keys) = cardinality(s.pre_balances) AS keys_aligned,
           /* 10-14（GPT 11）：用最终账户键同时核前、后余额长度、唯一性与非空 */
           cardinality(fk.keys) = cardinality(s.pre_balances) AND cardinality(fk.keys) = cardinality(s.post_balances)
             AND cardinality(array_distinct(fk.keys)) = cardinality(fk.keys)
             AND NOT any_match(fk.keys, x -> x IS NULL) AS keys_ok,
           /* 10-14（GPT 07）：范围完整＝签名者名下的代币账户只涉及本交易的允许币与 WSOL（只用币种元数据，不读保护币的现金） */
           NOT (COALESCE(any_match(s.pre_token_balances, b -> b.owner = s.signer AND b.mint <> '{wsol}' AND NOT contains(l.mints, b.mint)), false)
                OR COALESCE(any_match(s.post_token_balances, b -> b.owner = s.signer AND b.mint <> '{wsol}' AND NOT contains(l.mints, b.mint)), false))
             AS scope_complete,
           u.acct, CAST(u.post AS DECIMAL(38,0)) - CAST(u.pre AS DECIMAL(38,0)) AS d,
           COALESCE(any_match(s.pre_token_balances, b -> b.account = u.acct AND b.owner = s.signer), false)
             OR COALESCE(any_match(s.post_token_balances, b -> b.account = u.acct AND b.owner = s.signer), false) AS signer_owned,
           element_at(transform(filter(s.post_token_balances, b -> b.account = u.acct), b -> b.owner), 1) AS tok_owner
    FROM solana.transactions s
    JOIN lt l ON l.tx_id = s.id
    CROSS JOIN UNNEST(ARRAY[
        CASE WHEN cardinality(s.account_keys) = cardinality(s.pre_balances) THEN s.account_keys
             ELSE concat(s.account_keys, COALESCE(s.loaded_addresses.writable, CAST(ARRAY[] AS array(varchar))),
                         COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar)))) END]) AS fk(keys)
    CROSS JOIN UNNEST(fk.keys, s.pre_balances, s.post_balances) AS u(acct, pre, post)
    WHERE s.block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
),
cls AS (
    /* 账户类：交易者（签名者＋签名者名下的代币账户）、Jito、池子（曲线账户、PumpSwap 池名下的代币账户）、
       pump 协议费收款方（事件里的 fee_recipient）、其他 */
    SELECT b.*,
           CASE WHEN b.acct = b.signer OR b.signer_owned THEN 'trader'
                WHEN b.acct IN ({jito}) THEN 'jito'
                WHEN bc.bonding_curve IS NOT NULL OR p.pool IS NOT NULL THEN 'pool'
                WHEN contains(COALESCE(l.fee_recips, CAST(ARRAY[] AS array(varchar))), b.acct) THEN 'fee_recipient'
                ELSE 'other' END AS cls
    FROM bal b
    LEFT JOIN (SELECT DISTINCT bonding_curve FROM coins) bc ON bc.bonding_curve = b.acct
    LEFT JOIN pools p ON p.pool = b.tok_owner
    LEFT JOIN lt l ON l.tx_id = b.tx_id
),
agg AS (
    SELECT tx_id, arbitrary(block_time) AS block_time, arbitrary(slot) AS slot, arbitrary(txi) AS txi,
           arbitrary(signer) AS signer, arbitrary(success) AS success, arbitrary(fee) AS fee,
           arbitrary(priority_fee) AS priority_fee, arbitrary(required_signatures) AS required_signatures,
           arbitrary(compute_units_consumed) AS compute_units_consumed, arbitrary(cu_limit) AS cu_limit,
           bool_and(keys_aligned) AS keys_aligned, bool_and(keys_ok) AS keys_ok, bool_and(scope_complete) AS scope_complete,
           count(*) AS n_acct,
           sum(IF(cls = 'trader', d, 0)) AS d_trader,
           sum(IF(cls = 'jito' AND d > 0, d, 0)) AS tip_jito,
           sum(IF(cls = 'fee_recipient', d, 0)) AS d_fee_recip,
           sum(IF(cls = 'other', d, 0)) AS d_other,
           sum(IF(cls = 'other' AND d > 0, d, 0)) AS d_other_pos,
           sum(IF(cls = 'pool', d, 0)) AS d_pool,
           sum(d) AS d_all
    FROM cls GROUP BY 1
),
out AS (
    SELECT 'solana' AS chain, x.tx_id, to_unixtime(x.block_time) AS ts, x.slot, x.txi, x.signer, x.success,
           CAST(x.fee AS varchar) AS fee, CAST(x.priority_fee AS varchar) AS priority_fee, x.required_signatures,
           x.compute_units_consumed, x.cu_limit,
           l.n_legs, l.n_users, l.n_curve, l.n_amm, l.usr1 = x.signer AND l.n_users = 1 AS signer_is_user,
           CAST(l.cash_v1 AS varchar) AS cash_v1, CAST(l.cash_v2 AS varchar) AS cash_v2, CAST(l.cash_v3 AS varchar) AS cash_v3,
           CAST(x.d_trader AS varchar) AS d_trader, CAST(x.tip_jito AS varchar) AS tip_jito,
           CAST(x.d_fee_recip AS varchar) AS d_fee_recip, CAST(x.d_other AS varchar) AS d_other, CAST(x.d_all AS varchar) AS d_all,
           CAST(x.d_other_pos AS varchar) AS d_other_pos, CAST(x.d_pool AS varchar) AS d_pool,
           x.keys_aligned, x.keys_ok, x.scope_complete, 1 AS n_key,
           /* T2a 交易者残差（lamports）：流水口径的交易者净变化＋签名费＋Jito 小费 − 事件口径的交易者现金 */
           CAST(x.d_trader + x.fee + x.tip_jito - l.cash_v1 AS varchar) AS res_v1,
           CAST(x.d_trader + x.fee + x.tip_jito - l.cash_v2 AS varchar) AS res_v2,
           CAST(x.d_trader + x.fee + x.tip_jito - l.cash_v3 AS varchar) AS res_v3
    FROM agg x
    JOIN lt l ON l.tx_id = x.tx_id
)"""


TX_SMOKE = """
SELECT 'solana' AS chain, '{e0}' AS e0, '{e1}' AS e1,
       (SELECT count(*) FROM lt) AS n_trade_tx_from_events,
       count(*) AS n_tx_rows, count_if(n_key > 1) AS n_dup_key, count_if(NOT success) AS n_failed_in_set,
       count_if(NOT keys_aligned) AS n_keys_misaligned,
       count_if(NOT keys_ok) AS n_keys_not_ok,
       /* 优先费按定义＝总费 − 5000 × 签名数，下面只是算式一致性，另报异常（GPT 11） */
       count_if(CAST(priority_fee AS DECIMAL(38,0)) < 0) AS n_prio_negative,
       count_if(required_signatures IS NULL OR fee IS NULL) AS n_fee_or_sigs_null,
       count_if(scope_complete) AS n_scope_complete,
       count_if(signer_is_user AND scope_complete) AS n_clean_complete,
       count_if(signer_is_user AND scope_complete AND CAST(res_v1 AS DECIMAL(38,0)) = 0) AS n_res0_v1_complete,
       count_if(signer_is_user AND scope_complete AND CAST(res_v1 AS DECIMAL(38,0)) < 0) AS n_res_v1_neg_complete,
       count_if(signer_is_user AND scope_complete AND CAST(res_v1 AS DECIMAL(38,0)) > 0) AS n_res_v1_pos_complete,
       count_if(CAST(tip_jito AS DECIMAL(38,0)) > 0) AS n_with_jito_tip,
       count_if(signer_is_user) AS n_clean,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) = 0) AS n_res0_v1,
       count_if(signer_is_user AND CAST(res_v2 AS DECIMAL(38,0)) = 0) AS n_res0_v2,
       count_if(signer_is_user AND CAST(res_v3 AS DECIMAL(38,0)) = 0) AS n_res0_v3,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) < 0 AND CAST(res_v1 AS DECIMAL(38,0)) > -1000000) AS n_res_v1_neg_small,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) <= -1000000 AND CAST(res_v1 AS DECIMAL(38,0)) > -10000000) AS n_res_v1_neg_mid,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) <= -10000000) AS n_res_v1_neg_big,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) > 0) AS n_res_v1_pos,
       count_if(signer_is_user AND CAST(res_v1 AS DECIMAL(38,0)) = -2039280) AS n_res_v1_eq_minus_ata_rent,
       count_if(signer_is_user AND keys_aligned) AS n_clean_aligned,
       count_if(signer_is_user AND keys_aligned AND CAST(res_v1 AS DECIMAL(38,0)) = 0) AS n_res0_v1_aligned,
       count_if(signer_is_user AND keys_aligned AND CAST(res_v1 AS DECIMAL(38,0)) <> 0
                AND CAST(res_v1 AS DECIMAL(38,0)) = -CAST(d_other_pos AS DECIMAL(38,0))) AS n_res_v1_eq_minus_other_inflow,
       count_if(signer_is_user AND keys_aligned AND CAST(res_v1 AS DECIMAL(38,0)) < 0
                AND CAST(d_other_pos AS DECIMAL(38,0)) > 0) AS n_res_v1_neg_with_other_inflow,
       count_if(CAST(d_all AS DECIMAL(38,0)) + CAST(fee AS DECIMAL(38,0)) <> 0) AS n_lamports_not_conserved_after_fee,
       sum(length(concat_ws(',', {tx_cols}))) + count(*) * {tx_ncols} AS est_csv_bytes
       /* 资金路径表在 10-13 第一次抽样冒烟里已出；本版不再二次引用 cls（会重扫交易表） */
FROM out
"""

# ---------- 失败交易 ----------

FAIL = """,
f AS (
    SELECT s.id AS tx_id, s.block_time, s.block_slot AS slot, s.index AS txi, s.signer, s.fee,
           s.fee - 5000 * s.required_signatures AS priority_fee, s.error,
           CASE WHEN cardinality(s.account_keys) >= cardinality(s.pre_balances) THEN s.account_keys ELSE concat(s.account_keys, COALESCE(s.loaded_addresses.writable, CAST(ARRAY[] AS array(varchar))), COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar)))) END AS keys
    FROM solana.transactions s
    WHERE s.block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND s.success = false
      AND s.block_time < TIMESTAMP '{cutoff} 00:00:00'
      AND (contains(s.account_keys, '{pump}') OR contains(s.account_keys, '{amm}')
           OR contains(COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar))), '{pump}')
           OR contains(COALESCE(s.loaded_addresses.readonly, CAST(ARRAY[] AS array(varchar))), '{amm}'))
),
out AS (
    /* 10-13：f 只引用一次（避免重扫交易表） */
    SELECT 'solana' AS chain, f.tx_id, to_unixtime(arbitrary(f.block_time)) AS ts, arbitrary(f.slot) AS slot,
           arbitrary(f.txi) AS txi, arbitrary(f.signer) AS signer,
           CAST(arbitrary(f.fee) AS varchar) AS fee, CAST(arbitrary(f.priority_fee) AS varchar) AS priority_fee,
           arbitrary(f.error) AS error, count(DISTINCT k.mint) AS n_mints,
           array_join(array_agg(DISTINCT k.mint), ',') AS mints, 1 AS n_key
    FROM f
    CROSS JOIN UNNEST(f.keys) AS u(acct)
    JOIN coins k ON k.mint = u.acct
    WHERE f.block_time >= k.created_at AND f.block_time < k.created_at + INTERVAL '{hz}' DAY
    GROUP BY f.tx_id
)"""

# ---------- 实体边与代币转移 ----------

EDGE = """,
kc AS (
    /* 截点之前创建的母体币（10-14，GPT 窄范围复核 04）：未来的币与未来的创建者不进种子、C 边与 T 边 */
    SELECT * FROM coins WHERE created_at < TIMESTAMP '{xcut}'
),
seed AS (
    /* 取边种子：截点之前、逐币窗口内的曲线用户与 PumpSwap 用户（10-14，GPT 03），加截点之前创建的币的创建者 */
    SELECT DISTINCT CAST(t."user" AS varchar) AS usr
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN kc k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{s1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{hz}' DAY
      AND t.evt_block_time < TIMESTAMP '{xcut}' AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    UNION
    SELECT DISTINCT CAST(a."user" AS varchar)
    FROM (SELECT "user", pool, evt_block_time FROM pumpdotfun_solana.pump_amm_evt_buyevent
           WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{s1}'
          UNION ALL
          SELECT "user", pool, evt_block_time FROM pumpdotfun_solana.pump_amm_evt_sellevent
           WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{s1}') a
    JOIN pools p ON p.pool = a.pool
    WHERE a.evt_block_time >= p.created_at AND a.evt_block_time < p.coin_created_at + INTERVAL '{hz}' DAY
      AND p.coin_created_at < TIMESTAMP '{xcut}'
      AND a.evt_block_time < TIMESTAMP '{xcut}' AND a.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    UNION
    SELECT DISTINCT creator FROM kc
),
nat AS (
    /* 顶层 System Program 的 SOL 转账 ≥ {edge_min}（DQ-26 E1），建边窗口 [{x0}, 截点) 内，止日之前 */
    SELECT x.from_owner, x.to_owner, x.amount_display AS amt, x.block_time, x.tx_id
    FROM tokens_solana.transfers x
    WHERE x.block_date BETWEEN DATE '{xd0}' AND DATE '{xd1}'
      AND x.block_time >= TIMESTAMP '{x0}' AND x.block_time < TIMESTAMP '{xcut}'
      AND x.block_time < TIMESTAMP '{cutoff} 00:00:00'
      AND x.token_version = 'native' AND x.action = 'transfer'
      AND x.outer_executing_account = '{sys}' AND x.amount_display >= {edge_min}
      AND x.from_owner <> x.to_owner
),
s_edges AS (
    /* S：一端是种子的边，在截点之前先过滤、再按地址对汇总（10-14，GPT 04） */
    SELECT from_owner, to_owner, count(*) AS n, sum(amt) AS amt, min(block_time) AS t0, max(block_time) AS t1,
           min_by(tx_id, block_time) AS tx0
    FROM nat
    WHERE from_owner IN (SELECT usr FROM seed) OR to_owner IN (SELECT usr FROM seed)
    GROUP BY 1, 2
),
f_fan AS (
    /* F：向种子转过钱、自己不是种子的来源地址，在同一窗口内的扇出（不同接收方数；>200 视为服务节点） */
    SELECT n.from_owner, count(DISTINCT n.to_owner) AS fanout
    FROM nat n
    WHERE n.from_owner IN (SELECT from_owner FROM s_edges WHERE to_owner IN (SELECT usr FROM seed))
      AND n.from_owner NOT IN (SELECT usr FROM seed)
    GROUP BY 1
),
c_edges AS (
    /* C：创建者关联体——每个币创建前 7 天内与创建者的直接 SOL 往来，逐币窗口先过滤再汇总（不设 0.05 下限） */
    SELECT k.mint, x.from_owner, x.to_owner, count(*) AS n, sum(x.amount_display) AS amt,
           min(x.block_time) AS t0, max(x.block_time) AS t1, min_by(x.tx_id, x.block_time) AS tx0
    FROM tokens_solana.transfers x
    JOIN kc k ON (x.from_owner = k.creator OR x.to_owner = k.creator)
    WHERE x.block_date BETWEEN DATE '{cd0}' AND DATE '{c1}'
      AND x.block_time >= k.created_at - INTERVAL '7' DAY AND x.block_time < k.created_at
      AND x.token_version = 'native' AND x.action = 'transfer'
      AND x.outer_executing_account = '{sys}' AND x.from_owner <> x.to_owner
    GROUP BY 1, 2, 3
),
t_edges AS (
    /* T：母体币的直接代币转移（不含成交腿），逐币窗口内，截点之前 */
    SELECT x.token_mint_address AS mint, x.from_owner, x.to_owner, count(*) AS n, sum(x.amount_display) AS amt,
           min(x.block_time) AS t0, max(x.block_time) AS t1, min_by(x.tx_id, x.block_time) AS tx0
    FROM tokens_solana.transfers x
    JOIN kc k ON k.mint = x.token_mint_address
    WHERE x.block_date BETWEEN DATE '{e0}' AND DATE '{s1}'
      AND x.block_time >= k.created_at AND x.block_time < k.created_at + INTERVAL '{hz}' DAY
      AND x.block_time < TIMESTAMP '{xcut}' AND x.block_time < TIMESTAMP '{cutoff} 00:00:00'
      AND x.token_version <> 'native' AND x.action = 'transfer'
      AND x.outer_executing_account IN ({token_programs})
      AND x.from_owner <> x.to_owner
    GROUP BY 1, 2, 3
),
out AS (
    SELECT 'solana' AS chain, 'S' AS kind, CAST(NULL AS varchar) AS mint, from_owner, to_owner, n, CAST(amt AS varchar) AS amt,
           to_unixtime(t0) AS first_t, to_unixtime(t1) AS last_t, tx0 AS first_tx, CAST(NULL AS BIGINT) AS fanout,
           '{x0}' AS win_from, '{xcut}' AS win_cut, 1 AS n_key
    FROM s_edges
    UNION ALL
    SELECT 'solana', 'F', NULL, from_owner, NULL, NULL, NULL, NULL, NULL, NULL, fanout, '{x0}', '{xcut}', 1 FROM f_fan
    UNION ALL
    SELECT 'solana', 'C', mint, from_owner, to_owner, n, CAST(amt AS varchar), to_unixtime(t0), to_unixtime(t1), tx0, NULL,
           'created-7d', 'created', 1
    FROM c_edges
    UNION ALL
    SELECT 'solana', 'T', mint, from_owner, to_owner, n, CAST(amt AS varchar), to_unixtime(t0), to_unixtime(t1), tx0, NULL,
           'created', '{xcut}', 1
    FROM t_edges
)"""

# 冒烟：通用结构核对（每层的 out）
SMOKE = """
SELECT '{layer}' AS layer, count(*) AS n_rows, count_if(n_key > 1) AS n_dup_key{nulls}{extra},
       sum(length(concat_ws(',', {cols}))) + count(*) * {ncols} AS est_csv_bytes
FROM out
"""

COLS = {
    "COIN": "chain mint created_t n_create symbol creator create_user c_slot c_txi c_oix c_iix "
    "is_mayhem_mode is_cashback_enabled vsr0 vtr0 rtr0 supply completed_t n_complete "
    "comp_slot comp_txi comp_oix comp_iix comp_tx comp_user migrated_t pool n_mig window_complete n_key",
    "CTRADE": "chain mint created_t ts slot txi oix iix n_key tx_id signer usr is_buy sol tok vsr vtr rsr rtr f_pr f_cr f_cb f_bb "
    "fee_bps cfee_bps cb_bps bb_bps fee_recipient ev_creator mayhem ix_name track_volume q_mint q_amt vqr rqr hr_bps hr q_src xchk_ok",
    "MAY": "chain mint ts slot txi oix iix n_key tx_id vtr_old vsr_old vtr_new vsr_new rtr rsr",
    "ATRADE": "chain mint pool created_t pool_t ts slot txi oix iix n_key tx_id side usr q0 b0 q1 b1 q_pool b_amt q_user q_gross_out "
    "f_lp f_pr f_cr f_cb f_bb vq vq_src vq_ovf ovf xchk_ok bd qd",
    "TX": "chain tx_id ts slot txi signer success fee priority_fee required_signatures compute_units_consumed cu_limit n_legs n_users "
    "n_curve n_amm signer_is_user cash_v1 cash_v2 cash_v3 d_trader tip_jito d_fee_recip d_other d_all d_other_pos d_pool keys_aligned keys_ok scope_complete n_key "
    "res_v1 res_v2 res_v3",
    "FAIL": "chain tx_id ts slot txi signer fee priority_fee error n_mints mints n_key",
    "EDGE": "chain kind mint from_owner to_owner n amt first_t last_t first_tx fanout win_from win_cut n_key",
    "CYCC": AG.CYC_Y_COLS,
    "CYCA": AG.CYC_Y_COLS,
    "CYCCP": AG.CYC_P_COLS,
    "CYCAP": AG.CYC_P_COLS,
    "COSTF": AG.COSTF_COLS,
    "VQ": AG.VQ_COLS,
}
# 冒烟时要报缺失数的字段（承重字段）
NULL_CHECK = {
    "COIN": "creator symbol supply vtr0 rtr0",
    "CTRADE": "sol tok vsr vtr rsr rtr f_pr f_cr f_cb f_bb fee_recipient ev_creator signer vqr hr",
    "MAY": "vtr_new vsr_new",
    "ATRADE": "q0 b0 q_user f_lp f_pr f_cr f_cb f_bb vq",
    "TX": "fee priority_fee d_trader",
    "FAIL": "fee priority_fee",
    "EDGE": "from_owner",
    "CYCC": "m12 u16 in_cash out_cash",
    "CYCA": "m12 u16 in_cash out_cash",
    "CYCCP": "z_r1 z_r2",
    "CYCAP": "z_r1 z_r2",
    "COSTF": "s16 cost",
    "VQ": "pool_tx",
}
SMOKE_EXTRA = {
    "COIN": ", count(DISTINCT mint) AS n_coins, count_if(completed_t IS NOT NULL) AS n_completed, "
    "count_if(pool IS NOT NULL) AS n_migrated, count_if(is_mayhem_mode) AS n_mayhem, count_if(n_create > 1) AS n_multi_create",
    "CTRADE": ", count(DISTINCT mint) AS n_coins, count(DISTINCT tx_id) AS n_tx, count_if(q_src = 'missing') AS n_q_missing, "
    "count_if(q_src = 'raw') AS n_q_raw, count_if(xchk_ok = 0) AS n_xchk_fail, count_if(mayhem) AS n_mayhem_rows, "
    "count_if(signer <> usr) AS n_signer_ne_user, count_if(slot IS NULL OR txi IS NULL OR oix IS NULL) AS n_key_null",
    "MAY": ", count(DISTINCT mint) AS n_coins",
    "ATRADE": ", count(DISTINCT pool) AS n_pools, count(DISTINCT tx_id) AS n_tx, count_if(vq_src = 'missing') AS n_vq_missing, "
    "count_if(vq_src = 'unknown') AS n_vq_unknown, count_if(vq_ovf = 1) AS n_vq_ovf, count_if(ovf = 1) AS n_ord_ovf, "
    "count_if(xchk_ok = 0) AS n_xchk_fail, count_if(slot IS NULL OR txi IS NULL OR oix IS NULL) AS n_key_null",
    "FAIL": ", count(DISTINCT signer) AS n_signers, sum(n_mints) AS n_mint_links",
    "EDGE": ", count_if(kind = 'S') AS n_sol_edges, count_if(kind = 'F') AS n_funders, count_if(kind = 'F' AND fanout > 200) AS n_service, "
    "count_if(kind = 'C') AS n_creator_edges, count_if(kind = 'T') AS n_tok_edges, sum(n) AS n_transfers",
    "CYCC": ", count(DISTINCT u16) AS n_wallets, count(DISTINCT m12) AS n_m12, "
    "count_if(n_buy > 0 AND fb_slot IS NULL) AS n_fb_missing, "
    "count_if(fb_slot IS NOT NULL AND fb_k IS NULL) AS n_k_noprior, count_if(fb_k = 1) AS n_k, "
    "count_if(fb_comp = 1) AS n_fb_in_comp_tx, count_if(sb = 1) AS n_sell_before_buy, "
    "count_if(CAST(tok_sell AS DECIMAL(38,0)) > CAST(tok_buy AS DECIMAL(38,0))) AS n_sell_gt_buy, "
    "count_if(in_pre IS NULL) AS n_pre_null",
    "CYCCP": ", count(DISTINCT m12) AS n_m12, count_if(z_cut = 'S') AS n_p_snap, count_if(z_cut = 'E') AS n_p_end, "
    "count_if(z_bps1 IS NULL) AS n_bps1_null",
    "COSTF": ", count_if(kind = 'K') AS n_k, count_if(kind = 'F') AS n_f, count(DISTINCT signer) AS n_signers, "
    "sum(n_tx) AS n_leg_tx, sum(n_tx_clean) AS n_leg_tx_clean, sum(n_tx_unclean) AS n_leg_tx_unclean, "
    "count_if(CAST(cost_net AS DECIMAL(38,0)) + CAST(cost_tip AS DECIMAL(38,0)) > CAST(cost AS DECIMAL(38,0)) + 2) "
    "AS n_parts_gt_total, count_if(CAST(cost AS DECIMAL(38,0)) < 0 OR CAST(res_neg AS DECIMAL(38,0)) < 0) AS n_negative",
    "VQ": ", count_if(NOT layout0 AND n_init = 0) AS n_new_pool_no_init, count_if(n_init > 1) AS n_multi_init, "
    "sum(n_pool_mismatch) AS n_pool_mismatch, sum(n_ovf) AS n_vq_ovf, count_if(vq_min <> vq_max) AS n_vq_varies, "
    "count_if(layout0) AS n_layout0",
}
SMOKE_EXTRA["CYCA"] = SMOKE_EXTRA["CYCC"]
SMOKE_EXTRA["CYCAP"] = SMOKE_EXTRA["CYCCP"]


def edge_window(c0, c1, e1, edge_from=None, edge_cut=None):
    """建边窗口 [x0, 截点)：x0 默认＝创建起日前 7 天；截点默认＝事件止日次日 00:00（全窗版本，只作事后描述）。
    T3、S3 用的事前图把截点设为 W+1 周一 00:00 UTC（取数附录 §4）。
    创建范围不得跨过截点（10-14，GPT 窄范围复核 04）：W+1 创建的币，创建者关联按各币自己的创建时刻另调一次。"""
    x0 = edge_from or (c0 - dt.timedelta(days=7))
    xcut = edge_cut or (e1 + dt.timedelta(days=1))
    if xcut > CUTOFF or x0 >= xcut:
        raise SystemExit("建边窗口不对：起点须早于截点，截点不晚于止日")
    if c1 >= xcut:
        raise SystemExit("创建范围跨过截点：创建止日 %s 须早于截点 %s" % (c1, xcut))
    return x0, xcut


SAMPLE_SALT = "RT-DQ43-coin-sample-v1|"


def sample_where(p) -> str:
    """取数附录 §2：sha256(盐 ‖ mint) 前 8 字节取低 63 位，模 10000 小于 10000·p 的币纳入。p 为 None 时不抽样。"""
    if p is None:
        return ""
    m = round(p * 10000)
    if not (0 < m <= 10000) or abs(m - p * 10000) > 1e-9:
        raise SystemExit("抽样率须为 (0, 1] 内、精确到万分之一")
    if m == 10000:
        return ""
    return (
        "\n    WHERE mod(bitwise_and(from_big_endian_64(substr(sha256(to_utf8('%s' || mint)), 1, 8)), "
        "9223372036854775807), 10000) < %d" % (SAMPLE_SALT, m)
    )


def in_sample(mint: str, p: float) -> bool:
    """Python 参照实现（冒烟核对与测试用），与 sample_where 同一规则。"""
    import hashlib

    h = hashlib.sha256((SAMPLE_SALT + mint).encode()).digest()[:8]
    return (int.from_bytes(h, "big") & (2**63 - 1)) % 10000 < round(p * 10000)


def slice_where(col: str, part) -> str:
    """输出按钱包哈希分片（只为控制单条导出量；分片之前的计算用全部数据）。part＝(第几片, 共几片)。"""
    i, n = part
    if not (0 <= i < n):
        raise SystemExit("分片编号不对")
    if n == 1:
        return ""
    return (
        "\n    WHERE mod(bitwise_and(from_big_endian_64(xxhash64(to_utf8(%s))), 9223372036854775807), %d) = %d"
        % (col, n, i)
    )


def build(
    layer,
    c0,
    c1,
    e0,
    e1,
    smoke=False,
    edge_from=None,
    edge_cut=None,
    p=None,
    snap=None,
    part=(0, 1),
    tpart=(0, 1),
    with_pre=True,
):
    """snap：CYC 的快照截点（默认创建止日次日 00:00，即 W+1 周一）；with_pre：是否输出截点前合计（W+1 的币不用）；
    part：CYC 输出按钱包分片；
    tpart：COSTF 把一个事件日按小时等分（第几段, 共几段），只许单日。"""
    if layer not in LAYERS:
        raise SystemExit("层只能是 %s" % "、".join(LAYERS))
    check_dates(c0, c1, e0, e1)
    names = (G35.H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    f = dict(
        layer=layer,
        smoke_tag="（冒烟：只出结构核对）" if smoke else "",
        names=names,
        c0=c0.isoformat(),
        c1=c1.isoformat(),
        e0=e0.isoformat(),
        e1=e1.isoformat(),
        cutoff=CUTOFF.isoformat(),
        hz=HORIZON_DAYS,
        sys=SYS,
        pump=PUMP,
        amm=AMM,
        wsol=WSOL,
        jito=q(JITO),
        token_programs=q(TOKEN_PROGRAMS),
        edge_min=EDGE_MIN_SOL,
        samp=sample_where(p),
    )
    sql = POP.format(**f)
    if layer in ("CYCC", "CYCA", "CYCCP", "CYCAP"):
        snap = snap or (c1 + dt.timedelta(days=1))
        if snap <= c1:
            raise SystemExit("快照截点须晚于创建止日")
        stage = "curve" if layer.startswith("CYCC") else "amm"
        if layer.endswith("P"):
            out = AG.CYC_OUT_P
        else:
            out = AG.CYC_OUT_Y.format(
                pre_cols=AG.CYC_PRE if with_pre else AG.CYC_NO_PRE
            )
        g = dict(
            snap="%s 00:00:00" % snap.isoformat(),
            fb_state=AG.FB_STATE[stage],
            yslice=slice_where("a.usr", part),
            out=out,
            **f,
        )
        if stage == "curve":
            sql += AG.CYC_EV_CURVE.format(**g)
        else:
            sql += POOLS.format(**f) + AG.CYC_EV_AMM.format(**g)
        sql += AG.CYC_AGG.format(**g)
    elif layer == "COSTF":
        i, n = tpart
        if e0 != e1 or not (0 <= i < n) or 24 % n:
            raise SystemExit("COSTF 一次只取一个事件日；时段数须整除 24")
        h0 = dt.datetime.combine(e0, dt.time()) + dt.timedelta(hours=24 // n * i)
        h1 = h0 + dt.timedelta(hours=24 // n)
        sql += POOLS.format(**f) + AG.COSTF.format(
            t0=h0.strftime("%Y-%m-%d %H:%M:%S"),
            t1=h1.strftime("%Y-%m-%d %H:%M:%S"),
            **f,
        )
    elif layer == "VQ":
        v0 = max(c0, VQ_FROM)
        if v0 > e1:
            raise SystemExit("VQ：事件止日早于 07-15，所有池都是 layout0，不必取")
        sql += POOLS.format(**f) + AG.VQ.format(
            vq_from=VQ_FROM.isoformat(),
            v0=v0.isoformat(),
            v1=e1.isoformat(),
            d_init=D_INIT,
            **f,
        )
    elif layer == "COIN":
        sql += COIN.format(**f)
    elif layer == "CTRADE":
        r0 = max(e0, QUOTE_FIELDS_FROM)
        use_raw = e1 >= r0
        f37 = dict(
            r0=r0.isoformat(),
            t1=e1.isoformat(),
            program=PUMP,
            d_trade=C37.D_TRADE,
            u64_sol=C37.u64(49),
            u64_qa=C37.u64("base + 32"),
            u64_vqr=C37.u64("base + 40"),
            u64_rqr=C37.u64("base + 48"),
            u64_hrb=C37.u64("base + 56"),
            u64_hr=C37.u64("base + 64"),
        )
        raw = (
            _swap_ic(C37.RAW.format(**f37), CURVE_IC.format(**f37), ",\nicn AS (")
            if use_raw
            else ""
        )
        sql += CURVE.format(raw=raw, **f)
        sql += CURVE_OUT.format(
            raw_cols=RAW_COLS.format(**f37) if use_raw else NO_RAW_COLS,
            raw_join="\n    LEFT JOIN rv ON rv.tx_id = r.tx_id AND rv.oix = r.oix AND rv.iix IS NOT DISTINCT FROM r.iix0"
            if use_raw
            else "",
        )
    elif layer == "MAY":
        sql += MAY.format(**f)
    elif layer == "ATRADE":
        raw, ex, has = G35.raw_parts(e0, e1)
        sql += POOLS.format(**f)
        if has:
            r_start = max(e0, G35.VQ_START).isoformat()
            sql += AMM_KEYS.format(r_start=r_start, **f)
            raw = _swap_ic(
                raw,
                AMM_IC.format(
                    r_start=r_start, d_buy=G35.DISC["buy"], d_sell=G35.DISC["sell"], **f
                ),
                ",\nicp AS (",
            )
        sql += raw
        sql += G35.EVENTS.format(
            horizon=HORIZON_DAYS, ev_start=f["e0"], ev_end=f["e1"], **ex
        )
        sql += AMM_OUT.format(**f)
    elif layer == "TX":
        # 冒烟：10-13 全量展开 860 万笔交易的余额超时（30 分钟，104.19 credits），改为按交易号哈希抽 1/128 做结构核对
        ts = (
            "\n    WHERE bitwise_and(from_big_endian_64(xxhash64(to_utf8(tx_id))), 127) = 0"
            if smoke
            else ""
        )
        sql += POOLS.format(**f) + LEGS.format(tx_sample=ts, **f)
        if not smoke:
            return sql + "\nSELECT * FROM out\n"
        cols = COLS["TX"].split()
        return sql + TX_SMOKE.format(
            tx_cols=", ".join("CAST(%s AS varchar)" % c for c in cols),
            tx_ncols=len(cols),
            **f,
        )
    elif layer == "FAIL":
        sql += FAIL.format(**f)
    elif layer == "EDGE":
        x0, xcut = edge_window(c0, c1, e1, edge_from, edge_cut)
        s1 = min(e1, xcut - dt.timedelta(days=1))
        sql += POOLS.format(**f) + EDGE.format(
            x0="%s 00:00:00" % x0.isoformat(),
            xcut="%s 00:00:00" % xcut.isoformat(),
            xd0=x0.isoformat(),
            xd1=(xcut - dt.timedelta(days=1)).isoformat(),
            cd0=(c0 - dt.timedelta(days=7)).isoformat(),
            s1=s1.isoformat(),
            **f,
        )
    if not smoke:
        return sql + "\nSELECT * FROM out\n"
    cols = COLS[layer].split()
    nulls = "".join(
        ", count_if(%s IS NULL) AS null_%s" % (c, c) for c in NULL_CHECK[layer].split()
    )
    extra = SMOKE_EXTRA.get(layer, "")
    if layer == "COIN":
        extra += COIN_SMOKE_EXTRA.format(**f)
    if layer in ("CYCC", "CYCA", "CYCCP", "CYCAP", "COSTF", "VQ", "COIN", "EDGE"):
        # 双跑比对（冻结前清单第 9 条；取数附录 v2 §7）：每行规范化成文本求哈希，行数、哈希和、哈希异或三项都一致才算逐行一致
        extra += AG.CHECKSUM.format(
            ck_cols=", ".join("COALESCE(CAST(%s AS varchar), '~')" % c for c in cols)
        )
    return sql + SMOKE.format(
        layer=layer,
        nulls=nulls,
        extra=extra,
        cols=", ".join("CAST(%s AS varchar)" % c for c in cols),
        ncols=len(cols),
    )


def main():
    """python build_wm2_sql.py <层> <创建起> <创建止> <事件起> <事件止> <标签> [建边起 建边截]
    [--smoke] [--p=0.10] [--snap=YYYY-MM-DD] [--part=i/n] [--tpart=i/n]"""
    a = sys.argv[1:]
    opt = {x.split("=")[0]: (x.split("=") + [""])[1] for x in a if x.startswith("--")}
    a = [x for x in a if not x.startswith("--")]
    layer = a[0]
    c0, c1, e0, e1 = (dt.date.fromisoformat(x) for x in a[1:5])
    label = a[5]
    ew = [dt.date.fromisoformat(x) for x in a[6:8]] if len(a) >= 8 else [None, None]

    def frac(k):
        return tuple(int(x) for x in opt[k].split("/")) if k in opt else (0, 1)

    out = H / "sql" / ("%s.sql" % label)
    out.write_text(
        build(
            layer,
            c0,
            c1,
            e0,
            e1,
            "--smoke" in opt,
            ew[0],
            ew[1],
            p=float(opt["--p"]) if "--p" in opt else None,
            snap=dt.date.fromisoformat(opt["--snap"]) if "--snap" in opt else None,
            part=frac("--part"),
            tpart=frac("--tpart"),
        )
    )
    print(out.relative_to(H))


if __name__ == "__main__":
    main()

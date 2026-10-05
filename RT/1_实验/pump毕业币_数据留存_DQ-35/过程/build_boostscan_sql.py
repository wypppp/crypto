#!/usr/bin/env python3
"""DQ-35 InitBoost 全量扫描 SQL（10-06；总控第二十轮第二节，费用算在 vq 解码额度里）。

python 过程/build_boostscan_sql.py → sql/SCAN23_BOOST_{a,b,c,d}.sql
2026-07-15～10-04 分 4 段（每段约 20 天，探针一天 0.77 credits），每段输出两类行：
- rec='P'：每个有 boost 事件的池一行——InitBoost 次数、BoostBuyAndBurn 次数、首末时刻、两类事件里 vq 的极值、
  溢出计数；再连上建池事件（建池时刻、base／quote、发起程序、池序号）。只有计数、时刻与储备参数，没有成交价或收益。
- rec='D'：该段 PumpSwap 全部自调用事件按判别符计数，核对升级后有没有别的事件类型（可能改 vq 而没有被解码）。
读取由 过程/boostscan_report.py 做：先按建池与曲线创建时刻分类，检验周、封存周的池只出计数（同 dev_gate 的读法）。
vq 的 i128 解码与 build_grad_sql_v22.py 的 RAW 段相同：InitBoost 在 121～136，BoostBuyAndBurn 在 177～192。
"""

from pathlib import Path

H = Path(__file__).resolve().parent.parent
PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
D_INIT, D_BURN = "0xae7c4af90451f611", "0x3f451c16305cc2b9"
CHUNKS = [
    ("a", "2026-07-15", "2026-08-04"),
    ("b", "2026-08-05", "2026-08-25"),
    ("c", "2026-08-26", "2026-09-14"),
    ("d", "2026-09-15", "2026-10-04"),
]

VQ = """CASE WHEN abs(hi_s) < 4000000000000000000
                THEN CAST(hi_s AS DECIMAL(38,0)) * DECIMAL '18446744073709551616' + CAST(lo_s AS DECIMAL(38,0))
                     + CASE WHEN lo_s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END END"""

SQL = """/* DQ-35 InitBoost 全量扫描 {tag}（10-06，执行模型；总控第二十轮第二节）：{s}～{e} 的 PumpSwap 自调用事件。
   生成：过程/build_boostscan_sql.py。rec='P' 每个有 boost 的池一行（次数、时刻、vq 极值、建池信息）；
   rec='D' 全部事件按判别符计数。没有成交价或收益。 */
WITH ic AS (
    SELECT block_time AS ts, data AS b, bytearray_substring(data, 9, 8) AS disc
    FROM solana.instruction_calls
    WHERE block_date BETWEEN DATE '{s}' AND DATE '{e}'
      AND executing_account = '{program}'
      AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
),
bo AS (
    SELECT ts, disc, to_base58(bytearray_substring(b, 89, 32)) AS pool,
           bytearray_to_bigint(reverse(bytearray_substring(b, pv, 8))) AS lo_s,
           bytearray_to_bigint(reverse(bytearray_substring(b, pv + 8, 8))) AS hi_s
    FROM (SELECT ic.*, CASE WHEN disc = {d_init} THEN 121 ELSE 177 END AS pv
          FROM ic WHERE disc IN ({d_init}, {d_burn}) AND length(b) >= 192 - 56 * CAST(disc = {d_init} AS INTEGER))
),
bv AS (
    SELECT ts, disc, pool, {vq} AS vq,
           CASE WHEN abs(hi_s) >= 4000000000000000000 THEN 1 ELSE 0 END AS ovf
    FROM bo
),
pp AS (
    SELECT pool,
           count_if(disc = {d_init}) AS n_init, count_if(disc = {d_burn}) AS n_burn,
           to_unixtime(min(CASE WHEN disc = {d_init} THEN ts END)) AS first_init_t,
           to_unixtime(max(CASE WHEN disc = {d_init} THEN ts END)) AS last_init_t,
           to_unixtime(min(CASE WHEN disc = {d_burn} THEN ts END)) AS first_burn_t,
           min(CASE WHEN disc = {d_init} THEN vq END) AS vq_init_min, max(CASE WHEN disc = {d_init} THEN vq END) AS vq_init_max,
           min(CASE WHEN disc = {d_burn} THEN vq END) AS vq_burn_min, max(CASE WHEN disc = {d_burn} THEN vq END) AS vq_burn_max,
           sum(ovf) AS n_ovf
    FROM bv GROUP BY 1
),
cp AS (
    SELECT pool, to_unixtime(min(evt_block_time)) AS pool_created_t, min_by(base_mint, evt_block_time) AS base_mint,
           min_by(quote_mint, evt_block_time) AS quote_mint,
           min_by(evt_outer_executing_account, evt_block_time) AS creator_prog,
           min_by("index", evt_block_time) AS pool_index, count(*) AS n_create
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2025-03-01' AND DATE '{e}'
      AND pool IN (SELECT pool FROM pp)
    GROUP BY 1
)
SELECT 'P' AS rec, pp.pool, CAST(NULL AS VARCHAR) AS disc, pp.n_init, pp.n_burn, pp.first_init_t, pp.last_init_t, pp.first_burn_t,
       pp.vq_init_min, pp.vq_init_max, pp.vq_burn_min, pp.vq_burn_max, pp.n_ovf,
       cp.pool_created_t, cp.base_mint, cp.quote_mint, cp.creator_prog, cp.pool_index, cp.n_create
FROM pp LEFT JOIN cp ON cp.pool = pp.pool
UNION ALL
SELECT 'D', NULL, to_hex(disc), count(*), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM ic GROUP BY disc
"""


def main():
    for tag, s, e in CHUNKS:
        p = H / "sql" / ("SCAN23_BOOST_%s.sql" % tag)
        p.write_text(
            SQL.format(
                tag=tag,
                s=s,
                e=e,
                program=PROGRAM,
                d_init=D_INIT,
                d_burn=D_BURN,
                vq=VQ,
            )
        )
        print(p.name)


if __name__ == "__main__":
    main()

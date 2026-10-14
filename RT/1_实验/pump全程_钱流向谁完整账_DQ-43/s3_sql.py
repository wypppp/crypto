"""S3 在 SQL 里算到统计量（10-14，总控第七轮第二节；取数附录 v4）。

一条查询对应一个窗口对 (W, W+1)。只下载统计量，不下载逐行明细：
  C 行  W 的候选实体（得分 >0）：行数、命中数、得分（以 1/D 为单位的整数）、不精确项数、名次、是否入选、在 W+1 的行数与命中数
  G 行  W+1 中含入选实体行的层：(n, K, m, k)＝层内行数、层内命中数、入选实体行数、入选实体命中数
  N 行  汇总与核对：合格数、入选数、行数、分箱边界、应为 0 的核对计数
本机用 G 行算 T 与超几何零分布（a_riskset.set_test 的同一抽法），用 C 行核对入选是否确定。

规则照冻结卡 v4 §8 与 a_riskset（label、collapse、select_set）：
- 实体＝钱包经实体映射表（W 截点之前的边，本机并查集）归并；不在表里的钱包自成一个实体。
- 每个“实体 × 币”只留首笔成熟买入（顺序键 (slot, 交易序, 外层, 内层)）；曲线与 PumpSwap 一起排。
- 成熟：买入时刻＋30 分钟严格早于观察终点；观察终点＝min(创建＋30 天, 2026-10-05, 数据止点)，W 的币再截到截点。
- 命中与自身：窗内（顺序键在买入之后、时刻不晚于买入＋30 分钟）的毕业事件；触发者属于同一实体、或与买入同一笔交易＝自身。
- 层＝(阶段, 币, UTC 日, 进度十分位, 前 60 秒净买入三档, 本笔大小三档, UTC 小时四档, 自身)；PumpSwap 行不分箱（层内命中恒为 0）。
- 分箱边界只用 W 的曲线行（最近秩法）；同一对的 W+1 用同一组边界。
- 选集（CTE sel）只读 W 的行：合格＝行数 ≥5；得分＝命中 − 同层期望；得分 >0 的按得分降序、并列按 sha256(实体) 升序，
  取 ⌈合格数 × 10%⌉ 个。
- 得分以 1/D 为单位记整数，D＝lcm(1..60)：层大小 ≤60 时精确；否则向下取整，计入 m_inexact。
  C 行另出 s_exact（只含精确项）与 ix（不精确项的 n:K），本机由此算出每个候选的精确得分（分数），核对入选集合。
"""

from __future__ import annotations

import datetime as dt
import functools
import math

import a_riskset as A
import build_wm2_sql as B

H_SEC = 1800  # 结果窗 30 分钟
MIN_ROWS = A.MIN_ROWS
assert A.TOP_FRAC == 0.10  # SQL 里按 ⌈N/10⌉ 写死
D_UNITS = functools.reduce(
    lambda a, b: a * b // math.gcd(a, b), range(1, 61)
)  # lcm(1..60)
DECILES = 10
TERCILES = 3

S3_CORE = """,
emap(usr, ent) AS (
{emap}
),
cw AS (
    /* 窗口币：is_w＝W 的币（创建早于截点 {cut}）。观察终点＝min(创建＋30 天, 止日, 数据止点 {obs_cap})，
       W 的币再截到截点：选集只用截点之前的成交与事件 */
    SELECT k.mint, k.created_at, k.created_at < TIMESTAMP '{cut}' AS is_w,
           least(k.created_at + INTERVAL '{hz}' DAY, TIMESTAMP '{cutoff} 00:00:00', TIMESTAMP '{obs_cap}',
                 IF(k.created_at < TIMESTAMP '{cut}', TIMESTAMP '{cut}', TIMESTAMP '{obs_cap}')) AS obs_end
    FROM coins k
    WHERE k.created_at >= TIMESTAMP '{w0}' AND k.created_at < TIMESTAMP '{w1end}'
),
tr AS (
    /* 曲线成交（事件表），逐币 [创建, 观察终点)。pre＝成交前的真实代币储备（买入：成交后＋本笔代币）；
       cash_in＝买入付出的 SOL（含协议费与创建者费），即“本笔大小” */
    SELECT t.mint, c.is_w, c.obs_end, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           t.evt_outer_instruction_index AS oix, COALESCE(t.evt_inner_instruction_index, -1) AS iix,
           t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS amt,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) + COALESCE(CAST(t.fee AS DECIMAL(38,0)), 0)
               + COALESCE(CAST(t.creator_fee AS DECIMAL(38,0)), 0) AS cash_in,
           CAST(t.real_token_reserves AS DECIMAL(38,0)) AS r4
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN cw c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND t.evt_block_time >= c.created_at AND t.evt_block_time < c.obs_end
),
tw AS (
    /* 前 60 秒净买入（同汇总版 CYC）：顺序键在前的成交净额，减去时刻不晚于 t−60 秒的成交净额（进出池子的 SOL） */
    SELECT x.*,
           sum(sg) OVER (PARTITION BY mint ORDER BY slot, txi, oix, iix ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cum_x,
           sum(sg) OVER (PARTITION BY mint ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60' SECOND PRECEDING) AS cum_60
    FROM (SELECT tr.*, IF(is_buy, amt, -amt) AS sg FROM tr) x
),
ub AS (
    /* 全部成熟买入（曲线＋PumpSwap），钱包映射到实体 */
    SELECT 'c' AS stg, b.mint, b.is_w, COALESCE(m.ent, b.usr) AS ent, b.ts, b.slot, b.txi, b.oix, b.iix, b.tx_id,
           b.r4 + b.tok AS pre, COALESCE(b.cum_x, 0) - COALESCE(b.cum_60, 0) AS net60, b.cash_in AS sz
    FROM tw b
    LEFT JOIN emap m ON m.usr = b.usr
    WHERE b.is_buy AND to_unixtime(b.ts) + {h} < to_unixtime(b.obs_end)
    UNION ALL
    SELECT 'a', p.mint, c.is_w, COALESCE(m.ent, a.usr), a.ts, a.slot, a.txi, a.oix, a.iix, a.tx_id,
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0))
    FROM (SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
                 evt_outer_instruction_index AS oix, COALESCE(evt_inner_instruction_index, -1) AS iix,
                 evt_tx_id AS tx_id, CAST("user" AS varchar) AS usr
          FROM pumpdotfun_solana.pump_amm_evt_buyevent
          WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}') a
    JOIN pools p ON p.pool = a.pool
    JOIN cw c ON c.mint = p.mint
    LEFT JOIN emap m ON m.usr = a.usr
    WHERE a.ts >= p.created_at AND a.ts < c.obs_end AND to_unixtime(a.ts) + {h} < to_unixtime(c.obs_end)
),
fr AS (
    /* 每个“实体 × 币”只留首笔成熟买入（顺序键；GPT 增量 05） */
    SELECT * FROM (
        SELECT ub.*, row_number() OVER (PARTITION BY ent, mint ORDER BY slot, txi, oix, iix) AS rn FROM ub
    ) WHERE rn = 1
),
ce AS (
    /* 毕业事件（全部，逐币 [创建, 观察终点)；W 的币只有截点之前的）。触发者映射到实体 */
    SELECT e.mint, e.evt_block_time AS e_ts, e.evt_block_slot AS e_slot, e.evt_tx_index AS e_txi,
           e.evt_outer_instruction_index AS e_oix, COALESCE(e.evt_inner_instruction_index, -1) AS e_iix,
           e.evt_tx_id AS e_tx, COALESCE(m.ent, CAST(e."user" AS varchar)) AS e_ent
    FROM pumpdotfun_solana.pump_evt_completeevent e
    JOIN cw c ON c.mint = e.mint
    LEFT JOIN emap m ON m.usr = CAST(e."user" AS varchar)
    WHERE e.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND e.evt_block_time >= c.created_at AND e.evt_block_time < c.obs_end
),
lb AS (
    /* 逐事件自身排除（a_riskset.label）：窗内事件由同一实体触发、或与这笔买入同一笔交易，算自身；
       hit＝窗内有外部事件，slf＝窗内有自身事件 */
    SELECT f.stg, f.mint, f.is_w, f.ent, f.ts, f.pre, f.net60, f.sz,
           max(IF(e.mint IS NOT NULL AND e.e_ent <> f.ent AND e.e_tx <> f.tx_id, 1, 0)) AS hit,
           max(IF(e.mint IS NOT NULL AND (e.e_ent = f.ent OR e.e_tx = f.tx_id), 1, 0)) AS slf
    FROM fr f
    LEFT JOIN ce e ON e.mint = f.mint
        AND ARRAY[e.e_slot, e.e_txi, e.e_oix, e.e_iix] > ARRAY[f.slot, f.txi, f.oix, f.iix]
        AND to_unixtime(e.e_ts) <= to_unixtime(f.ts) + {h}
    GROUP BY f.stg, f.mint, f.is_w, f.ent, f.ts, f.pre, f.net60, f.sz
),
wq AS (
    /* 分箱边界只用 W 的曲线行（截点之前、形成期内）。最近秩法：第 q 个 n 分位边界＝升序第 ⌈q·N/n⌉ 个值 */
    SELECT pre, net60, sz, count(*) OVER () AS n,
           row_number() OVER (ORDER BY pre) AS r_pre, row_number() OVER (ORDER BY net60) AS r_net,
           row_number() OVER (ORDER BY sz) AS r_sz
    FROM lb WHERE is_w AND stg = 'c'
),
bd AS (
    SELECT {edge_aggs}
    FROM wq
),
sr AS (
    /* 层的键：PumpSwap 行的状态记 −1（层内命中恒为 0，见取数附录 v4 §3） */
    SELECT lb.*, CAST(lb.ts AS date) AS dy,
           IF(stg = 'c', {bin_pre}, -1) AS b_pre,
           IF(stg = 'c', {bin_net}, -1) AS b_net,
           IF(stg = 'c', {bin_sz}, -1) AS b_sz,
           IF(stg = 'c', CASE WHEN hour(ts) < 6 THEN 0 WHEN hour(ts) < 12 THEN 1 WHEN hour(ts) < 18 THEN 2 ELSE 3 END, -1) AS b_hr
    FROM lb CROSS JOIN bd
),
ss AS (
    SELECT is_w, stg, mint, dy, b_pre, b_net, b_sz, b_hr, slf, count(*) AS sn, sum(hit) AS sk
    FROM sr
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
),
rx AS (
    SELECT r.*, s.sn, s.sk, CAST(s.sk AS DECIMAL(38,0)) * {d_units} AS kd
    FROM sr r
    JOIN ss s ON s.is_w = r.is_w AND s.stg = r.stg AND s.mint = r.mint AND s.dy = r.dy AND s.b_pre = r.b_pre
         AND s.b_net = r.b_net AND s.b_sz = r.b_sz AND s.b_hr = r.b_hr AND s.slf = r.slf
),
sc AS (
    /* W 上每个实体：行数、命中、得分（单位 1/D：层的期望 K/n 向下取整到 1/D）、不精确项数（K·D 不能被 n 整除的行数）；
       s_exact＝只减去精确项的得分（单位 1/D），ix＝不精确项的 n:K 列表。本机据此算每个候选的精确得分（分数），核对入选集合 */
    SELECT ent, count(*) AS n_rows, sum(hit) AS hits,
           CAST(sum(hit) AS DECIMAL(38,0)) * {d_units} - sum((kd - mod(kd, sn)) / sn) AS s_units,
           CAST(sum(hit) AS DECIMAL(38,0)) * {d_units}
               - sum(IF(mod(kd, sn) = 0, (kd - mod(kd, sn)) / sn, CAST(0 AS DECIMAL(38,0)))) AS s_exact,
           count_if(mod(kd, sn) <> 0) AS m_inexact,
           array_join(array_sort(array_agg(CAST(sn AS varchar) || ':' || CAST(sk AS varchar))
               FILTER (WHERE mod(kd, sn) <> 0)), ';') AS ix
    FROM rx
    WHERE is_w
    GROUP BY ent
),
el AS (SELECT * FROM sc WHERE n_rows >= {min_rows}),
kq AS (SELECT count(*) AS n_el, CAST((count(*) + 9 - mod(count(*) + 9, 10)) / 10 AS bigint) AS k_sel FROM el),
cd AS (
    SELECT el.*, row_number() OVER (ORDER BY s_units DESC, lower(to_hex(sha256(to_utf8(ent))))) AS rk
    FROM el
    WHERE s_units > 0
),
sel AS (
    /* 入选集合：只读 W 的行（sc ← rx 的 is_w 行）与 W 的分箱边界，W+1 的任何数据都进不来 */
    SELECT cd.ent FROM cd CROSS JOIN kq WHERE cd.rk <= kq.k_sel
),
w1 AS (
    SELECT r.*, s.ent IS NOT NULL AS is_sel
    FROM rx r
    LEFT JOIN sel s ON s.ent = r.ent
    WHERE NOT r.is_w
),
a1 AS (SELECT ent, count(*) AS n1, sum(hit) AS h1 FROM w1 WHERE is_sel GROUP BY ent)"""

S3_STATS_OUT = """,
out AS (
    SELECT 'G' AS kind, CAST(NULL AS varchar) AS ent, max(sn) AS a, max(sk) AS b, count(*) AS c, sum(hit) AS d,
           stg AS s, CAST(NULL AS bigint) AS e, CAST(NULL AS bigint) AS f, CAST(NULL AS bigint) AS g,
           CAST(NULL AS varchar) AS x, CAST(NULL AS varchar) AS ix
    FROM w1
    WHERE is_sel
    GROUP BY stg, mint, dy, b_pre, b_net, b_sz, b_hr, slf
    UNION ALL
    SELECT 'C', cd.ent, cd.n_rows, cd.hits, cd.m_inexact, cd.rk, CAST(cd.s_units AS varchar),
           IF(cd.rk <= kq.k_sel, 1, 0), a1.n1, a1.h1, CAST(cd.s_exact AS varchar), cd.ix
    FROM cd CROSS JOIN kq LEFT JOIN a1 ON a1.ent = cd.ent
    UNION ALL
    SELECT 'N', x.name, x.v, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    FROM (
        SELECT 'n_el' AS name, n_el AS v FROM kq
        UNION ALL SELECT 'k_sel', k_sel FROM kq
        UNION ALL SELECT 'n_cand', count(*) FROM cd
        UNION ALL SELECT 'n_ent_w', count(*) FROM sc
        UNION ALL SELECT 'n_rows_w', count_if(is_w) FROM sr
        UNION ALL SELECT 'n_rows_w1', count_if(NOT is_w) FROM sr
        UNION ALL SELECT 'n_hit_w', sum(IF(is_w, hit, 0)) FROM sr
        UNION ALL SELECT 'n_hit_w1', sum(IF(is_w, 0, hit)) FROM sr
        UNION ALL SELECT 'n_slf', sum(slf) FROM sr
        UNION ALL SELECT 'n_amm_rows', count_if(stg = 'a') FROM sr
        UNION ALL SELECT 'chk_amm_event', count_if(stg = 'a' AND (hit = 1 OR slf = 1)) FROM sr
        UNION ALL SELECT 'chk_state_null', count_if(stg = 'c' AND (pre IS NULL OR net60 IS NULL OR sz IS NULL)) FROM sr
        UNION ALL SELECT 'chk_hit_and_slf', count_if(hit = 1 AND slf = 1) FROM sr
        UNION ALL SELECT 'n_coins_w', count_if(is_w) FROM cw
        UNION ALL SELECT 'n_coins_w1', count_if(NOT is_w) FROM cw
        UNION ALL SELECT 'n_events', count(*) FROM ce
        UNION ALL SELECT 'n_mapped_w', count(DISTINCT ent) FROM sr WHERE is_w AND ent IN (SELECT ent FROM emap){edge_rows}
    ) x
)"""

# 本机参照的明细（只在冒烟的小范围上导出）：曲线成交、PumpSwap 买入、毕业事件、窗口币
S3_DETAIL_OUT = """,
out AS (
    SELECT 'T' AS kind, mint, usr, CAST(to_unixtime(ts) AS bigint) AS t, CAST(slot AS bigint) AS slot, CAST(txi AS bigint) AS txi,
           CAST(oix AS bigint) AS oix, CAST(iix AS bigint) AS iix, substr(tx_id, 1, 16) AS tx,
           IF(is_buy, 1, 0) AS b, CAST(amt AS varchar) AS amt, CAST(tok AS varchar) AS tok,
           CAST(cash_in AS varchar) AS cash, CAST(r4 AS varchar) AS r4
    FROM tr
    UNION ALL
    SELECT 'A', p.mint, a.usr, CAST(to_unixtime(a.ts) AS bigint), CAST(a.slot AS bigint), CAST(a.txi AS bigint),
           CAST(a.oix AS bigint), CAST(a.iix AS bigint), substr(a.tx_id, 1, 16),
           1, NULL, NULL, NULL, NULL
    FROM (SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
                 evt_outer_instruction_index AS oix, COALESCE(evt_inner_instruction_index, -1) AS iix,
                 evt_tx_id AS tx_id, CAST("user" AS varchar) AS usr
          FROM pumpdotfun_solana.pump_amm_evt_buyevent
          WHERE evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}') a
    JOIN pools p ON p.pool = a.pool
    JOIN cw c ON c.mint = p.mint
    WHERE a.ts >= p.created_at AND a.ts < c.obs_end
    UNION ALL
    SELECT 'E', e.mint, CAST(e."user" AS varchar), CAST(to_unixtime(e.evt_block_time) AS bigint), CAST(e.evt_block_slot AS bigint),
           CAST(e.evt_tx_index AS bigint), CAST(e.evt_outer_instruction_index AS bigint),
           CAST(COALESCE(e.evt_inner_instruction_index, -1) AS bigint),
           substr(e.evt_tx_id, 1, 16), NULL, NULL, NULL, NULL, NULL
    FROM pumpdotfun_solana.pump_evt_completeevent e
    JOIN cw c ON c.mint = e.mint
    WHERE e.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND e.evt_block_time >= c.created_at AND e.evt_block_time < c.obs_end
    UNION ALL
    SELECT 'K', mint, NULL, CAST(to_unixtime(created_at) AS bigint), NULL, NULL, NULL, NULL, NULL,
           IF(is_w, 1, 0), NULL, NULL, NULL, NULL
    FROM cw
)"""

DETAIL_COLS = "kind mint usr t slot txi oix iix tx b amt tok cash r4".split()
OUT_COLS = "kind ent a b c d s e f g x ix".split()


def _nearest_rank(var: str, rank: str, n_q: int, label: str) -> list[str]:
    """第 q 个边界（q＝1..n_q−1）＝升序第 ⌈q·N/n_q⌉ 个值；整数算术。"""
    out = []
    for q in range(1, n_q):
        pos = "({q} * n + {m} - mod({q} * n + {m}, {nq})) / {nq}".format(
            q=q, m=n_q - 1, nq=n_q
        )
        out.append(
            "max(IF({r} = {pos}, {v})) AS {lb}{q}".format(
                r=rank, pos=pos, v=var, lb=label, q=q
            )
        )
    return out


def _bin(var: str, label: str, n_q: int) -> str:
    return " + ".join(
        "IF({v} > {lb}{q}, 1, 0)".format(v=var, lb=label, q=q) for q in range(1, n_q)
    )


def emap_values(mapping: dict) -> str:
    """实体映射表的内联写法（冒烟用；全量用上传的表）。mapping：钱包 → 实体代表（只含多钱包实体）。"""
    if not mapping:
        return "    SELECT CAST(NULL AS varchar), CAST(NULL AS varchar) WHERE false"
    for u, e in mapping.items():
        _check_addr(u)
        _check_addr(e)
    rows = ",\n".join(
        "        ('%s', '%s')" % (u, e) for u, e in sorted(mapping.items())
    )
    return "    SELECT * FROM (VALUES\n%s\n    ) AS v(usr, ent)" % rows


def _check_addr(x: str) -> None:
    if not x.isalnum():
        raise SystemExit("地址只能是字母数字：%r" % x)


def build_s3(w0, cut, w1end, p, emap_sql, detail=False, obs_cap=None):
    """w0、cut、w1end：W 起、截点（W+1 起）、W+1 止（不含），都是 UTC 零点的日期。
    obs_cap：数据止点（默认＝事件止日次日零点）；冒烟用短的事件窗时给出。emap_sql：实体映射表的 SELECT（usr, ent）。"""
    if not (w0 < cut < w1end):
        raise SystemExit("日期次序不对：W 起 < 截点 < W+1 止")
    c1 = w1end - dt.timedelta(days=1)
    e1 = min(c1 + dt.timedelta(days=B.HORIZON_DAYS), B.LAST_EVENT_DAY)
    if obs_cap is not None:
        e1 = min(e1, obs_cap - dt.timedelta(days=1))
    cap = obs_cap or (e1 + dt.timedelta(days=1))
    f = B.fields("S3D" if detail else "S3", w0, c1, w0, e1, False, p)
    g = dict(
        f,
        w0="%s 00:00:00" % w0.isoformat(),
        cut="%s 00:00:00" % cut.isoformat(),
        w1end="%s 00:00:00" % w1end.isoformat(),
        obs_cap="%s 00:00:00" % cap.isoformat(),
        h=H_SEC,
        emap=emap_sql,
        min_rows=MIN_ROWS,
        d_units="CAST('%d' AS DECIMAL(38,0))" % D_UNITS,
        edge_aggs=",\n           ".join(
            _nearest_rank("pre", "r_pre", DECILES, "p")
            + _nearest_rank("net60", "r_net", TERCILES, "q")
            + _nearest_rank("sz", "r_sz", TERCILES, "z")
        ),
        bin_pre=_bin("pre", "p", DECILES),
        bin_net=_bin("net60", "q", TERCILES),
        bin_sz=_bin("sz", "z", TERCILES),
        edge_rows="".join(
            "\n        UNION ALL SELECT '%s%d', CAST(%s%d AS bigint) FROM bd"
            % (lb, q, lb, q)
            for lb, nq in (("p", DECILES), ("q", TERCILES), ("z", TERCILES))
            for q in range(1, nq)
        ),
    )
    sql = B.POP.format(**f) + B.POOLS.format(**f) + S3_CORE.format(**g)
    # 明细只引用 cw、tr 与池子；S3_CORE 里其余 CTE 不被引用，Trino 不会执行
    sql += (S3_DETAIL_OUT if detail else S3_STATS_OUT).format(**g)
    return sql + "\nSELECT * FROM out\n"

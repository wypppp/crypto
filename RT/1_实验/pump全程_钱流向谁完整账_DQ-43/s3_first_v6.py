"""取数附录 v6：确定性首笔 B/A、毕业 E、母体 K；K.q 是拒绝条件。

成熟先筛；完整钱包、交易号和链上键保留。金额与秒数只用整数。
时间 RANGE 的并列同行故意同权，整数求和无顺序依赖。
"""

import datetime as dt

import wm2_deterministic_v6 as D  # isort: skip -- restore builder path before legacy imports

import s3_first_extract as OLD
import s3_first_local as L
import s3_sql as S

B = D.B

COLS = OLD.COLS + ["q"]
OUT = """,
ar AS (
    SELECT p.mint,CAST(a."user" AS varchar) AS usr,a.evt_block_time AS ts,a.evt_block_slot AS slot,
           a.evt_tx_index AS txi,a.evt_outer_instruction_index AS oix,COALESCE(a.evt_inner_instruction_index,-1) AS iix,
           a.evt_tx_id AS tx_id,c.obs_end
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a JOIN pools p ON p.pool=a.pool JOIN cw c ON c.mint=p.mint
    WHERE a.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND a.evt_block_time >= p.created_at AND a.evt_block_time < c.obs_end
),
fc AS (
    SELECT * FROM (SELECT tw.*,row_number() OVER (PARTITION BY usr,mint ORDER BY slot,txi,oix,iix,tx_id) AS rn
    FROM tw WHERE is_buy AND ts+INTERVAL '1800' SECOND < obs_end) WHERE rn=1
),
fa AS (
    SELECT * FROM (SELECT ar.*,row_number() OVER (PARTITION BY usr,mint ORDER BY slot,txi,oix,iix,tx_id) AS rn
    FROM ar WHERE ts+INTERVAL '1800' SECOND < obs_end) WHERE rn=1
),
ge AS (
    SELECT e.mint,CAST(e."user" AS varchar) AS usr,e.evt_block_time AS ts,e.evt_block_slot AS slot,
           e.evt_tx_index AS txi,e.evt_outer_instruction_index AS oix,COALESCE(e.evt_inner_instruction_index,-1) AS iix,
           e.evt_tx_id AS tx_id
    FROM pumpdotfun_solana.pump_evt_completeevent e JOIN cw c ON c.mint=e.mint
    WHERE e.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND e.evt_block_time >= c.created_at AND e.evt_block_time < c.obs_end
),
cq AS (SELECT mint,count(*)-count(DISTINCT ARRAY[slot,txi,oix,iix]) AS dup,
       count_if(slot IS NULL OR txi IS NULL OR oix IS NULL OR usr IS NULL OR NOT regexp_like(usr,'{nonspace}') OR tx_id IS NULL OR NOT regexp_like(tx_id,'{nonspace}')) AS bad FROM tr GROUP BY mint),
aq AS (SELECT mint,count(*)-count(DISTINCT ARRAY[slot,txi,oix,iix]) AS dup,
       count_if(slot IS NULL OR txi IS NULL OR oix IS NULL OR usr IS NULL OR NOT regexp_like(usr,'{nonspace}') OR tx_id IS NULL OR NOT regexp_like(tx_id,'{nonspace}')) AS bad FROM ar GROUP BY mint),
eq AS (SELECT mint,count(*)-count(DISTINCT ARRAY[slot,txi,oix,iix]) AS dup,
       count_if(slot IS NULL OR txi IS NULL OR oix IS NULL OR usr IS NULL OR NOT regexp_like(usr,'{nonspace}') OR tx_id IS NULL OR NOT regexp_like(tx_id,'{nonspace}')) AS bad FROM ge GROUP BY mint),
source_keys AS (
    SELECT 'c' AS stg,mint,slot,txi,oix,iix FROM tr
    UNION ALL SELECT 'a',mint,slot,txi,oix,iix FROM ar
),
cross_keys AS (
    SELECT slot,txi,oix,iix FROM source_keys
    GROUP BY slot,txi,oix,iix HAVING count(DISTINCT stg)>1
),
xq AS (
    SELECT k.mint,count(*) AS bad FROM source_keys k JOIN cross_keys x
    ON k.slot=x.slot AND k.txi=x.txi AND k.oix=x.oix AND k.iix=x.iix GROUP BY k.mint
),
pq AS (
    SELECT p.mint,count_if(c.n_cp<>1 OR c.n_mints<>1 OR c.n_quotes<>1 OR c.n_bad<>0) AS bad
    FROM cp_candidates p JOIN cp c ON c.pool=p.pool GROUP BY p.mint
),
out AS (
    SELECT 'B' AS kind,mint,usr,date_diff('second',TIMESTAMP '1970-01-01 00:00:00',ts) AS t,
           CAST(slot AS bigint) AS slot,CAST(txi AS bigint) AS txi,CAST(oix AS bigint) AS oix,CAST(iix AS bigint) AS iix,
           tx_id AS tx,CAST(r4+tok AS varchar) AS pre,CAST(COALESCE(cum_x,0)-COALESCE(cum_60,0) AS varchar) AS net60,
           CAST(cash_in AS varchar) AS sz,CAST(NULL AS varchar) AS q FROM fc
    UNION ALL
    SELECT 'A',mint,usr,date_diff('second',TIMESTAMP '1970-01-01 00:00:00',ts),CAST(slot AS bigint),CAST(txi AS bigint),
           CAST(oix AS bigint),CAST(iix AS bigint),tx_id,NULL,NULL,NULL,NULL FROM fa
    UNION ALL
    SELECT 'E',mint,usr,date_diff('second',TIMESTAMP '1970-01-01 00:00:00',ts),CAST(slot AS bigint),CAST(txi AS bigint),
           CAST(oix AS bigint),CAST(iix AS bigint),tx_id,NULL,NULL,NULL,NULL FROM ge
    UNION ALL
    SELECT 'K',c.mint,NULL,date_diff('second',TIMESTAMP '1970-01-01 00:00:00',c.created_at),NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
           array_join(ARRAY[CAST(c.n_create AS varchar),CAST(COALESCE(cq.dup,0) AS varchar),CAST(COALESCE(cq.bad,0) AS varchar),
               CAST(COALESCE(aq.dup,0) AS varchar),CAST(COALESCE(aq.bad,0) AS varchar),CAST(COALESCE(eq.dup,0) AS varchar),
               CAST(COALESCE(eq.bad,0) AS varchar),CAST(COALESCE(pq.bad,0) AS varchar),
               CAST(COALESCE(xq.bad,0) AS varchar),CAST(c.n_identity_bad AS varchar)],';')
    FROM cw c LEFT JOIN cq ON cq.mint=c.mint LEFT JOIN aq ON aq.mint=c.mint LEFT JOIN eq ON eq.mint=c.mint LEFT JOIN pq ON pq.mint=c.mint LEFT JOIN xq ON xq.mint=c.mint
)
SELECT * FROM out
ORDER BY kind,mint,slot,txi,oix,iix,usr,tx
"""


def build(w0, cut, w1end, p=None, obs_cap=None):
    if not w0 < cut < w1end:
        raise SystemExit("日期次序不对")
    c1 = w1end - dt.timedelta(days=1)
    e1 = min(c1 + dt.timedelta(days=30), B.LAST_EVENT_DAY)
    if obs_cap is not None:
        e1 = min(e1, obs_cap - dt.timedelta(days=1))
    cap = obs_cap or e1 + dt.timedelta(days=1)
    f = B.fields("S3D_v6", w0, c1, w0, e1, False, p)
    g = dict(
        f,
        w0=str(w0) + " 00:00:00",
        cut=str(cut) + " 00:00:00",
        w1end=str(w1end) + " 00:00:00",
        obs_cap=str(cap) + " 00:00:00",
        emap="SELECT NULL,NULL WHERE FALSE",
    )
    core = ",\ncw AS (" + S.S3_CORE.split(",\ncw AS (", 1)[1].split(",\nub AS (", 1)[0]
    core = core.replace(
        "SELECT k.mint, k.created_at,",
        "SELECT k.mint, k.created_at, k.n_create, k.n_identity_bad,",
    )
    core = core.replace(
        "ORDER BY slot, txi, oix, iix ROWS", "ORDER BY slot, txi, oix, iix, tx_id ROWS"
    )
    return (
        D.population(f)
        + D.pools(f)
        + core.format(**g)
        + OUT.format(nonspace=D.NONSPACE, **f)
    )


def validate(rows):
    for r in rows:
        if r["kind"] == "K":
            values = [int(v) for v in r["q"].split(";")]
            if len(values) != 10 or values[0] != 1 or any(values[1:]):
                raise ValueError("K.q 的唯一键、缺失、跨阶段或池检查失败")
    seen = set()
    for r in rows:
        if r["kind"] == "K":
            values = [int(v) for v in r["q"].split(";")]
            if len(values) != 10 or values[0] != 1 or any(values[1:]):
                raise ValueError("K.q 的唯一键、缺失或创建检查失败")
        elif r["kind"] in ("B", "A", "E"):
            if any(
                r.get(k) is None or not str(r[k]).strip()
                for k in ("mint", "usr", "slot", "txi", "oix", "iix", "tx")
            ):
                raise ValueError("完整键或身份缺失")
            if r["kind"] in ("B", "A"):
                key = tuple(int(r[k]) for k in ("slot", "txi", "oix", "iix"))
                if key in seen:
                    raise ValueError("跨阶段的买入键重复")
                seen.add(key)
        else:
            raise ValueError("行类型越出 B/A/E/K")


def reference(rows, emap, w0, cut, w1end, cap):
    validate(rows)
    result = L.reference(rows, emap, w0, cut, w1end, cap)
    if not result["frozen_check"]["select_set_same"]:
        raise ValueError("冻结选集与精确核对不同，停下")
    return result

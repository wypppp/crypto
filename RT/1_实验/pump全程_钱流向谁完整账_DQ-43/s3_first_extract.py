"""第八轮 0 credits 路线草稿：首笔成熟钱包买入及状态、全部毕业、母体。

未获全量执行批准。原 S3 统计量 SQL 不改、不跑。
成熟先过滤再按链上键取首笔，保持冻结 collapse 的准确行为。
曲线仍读全部买卖来算 net60；压缩的是输出，不能凭此缩短扫描窗。
完整钱包与交易号保留，供本机归并、哈希并列、自身判断。
"""

import datetime as dt

import build_wm2_sql as B
import s3_sql as S

COLS = "kind mint usr t slot txi oix iix tx pre net60 sz".split()

FIRST_OUT = """,
fc AS (
    SELECT * FROM (
        SELECT tw.*, row_number() OVER (PARTITION BY usr,mint ORDER BY slot,txi,oix,iix) AS rn
        FROM tw WHERE is_buy AND to_unixtime(ts)+1800 < to_unixtime(obs_end)
    ) WHERE rn=1
),
fa AS (
    SELECT * FROM (
        SELECT p.mint, CAST(a."user" AS varchar) AS usr, a.evt_block_time AS ts,
               a.evt_block_slot AS slot, a.evt_tx_index AS txi,
               a.evt_outer_instruction_index AS oix, COALESCE(a.evt_inner_instruction_index,-1) AS iix,
               a.evt_tx_id AS tx_id,
               row_number() OVER (PARTITION BY a."user",p.mint ORDER BY a.evt_block_slot,a.evt_tx_index,
                   a.evt_outer_instruction_index,COALESCE(a.evt_inner_instruction_index,-1)) AS rn
        FROM pumpdotfun_solana.pump_amm_evt_buyevent a
        JOIN pools p ON p.pool=a.pool JOIN cw c ON c.mint=p.mint
        WHERE a.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
          AND a.evt_block_time >= p.created_at AND a.evt_block_time < c.obs_end
          AND to_unixtime(a.evt_block_time)+1800 < to_unixtime(c.obs_end)
    ) WHERE rn=1
),
out AS (
    SELECT 'B' AS kind,mint,usr,CAST(to_unixtime(ts) AS bigint) AS t,
           CAST(slot AS bigint) AS slot,CAST(txi AS bigint) AS txi,CAST(oix AS bigint) AS oix,CAST(iix AS bigint) AS iix,
           tx_id AS tx,CAST(r4+tok AS varchar) AS pre,
           CAST(COALESCE(cum_x,0)-COALESCE(cum_60,0) AS varchar) AS net60,CAST(cash_in AS varchar) AS sz
    FROM fc
    UNION ALL
    SELECT 'A',mint,usr,CAST(to_unixtime(ts) AS bigint),CAST(slot AS bigint),CAST(txi AS bigint),CAST(oix AS bigint),
           CAST(iix AS bigint),tx_id,NULL,NULL,NULL FROM fa
    UNION ALL
    SELECT 'E',e.mint,CAST(e."user" AS varchar),CAST(to_unixtime(e.evt_block_time) AS bigint),
           CAST(e.evt_block_slot AS bigint),CAST(e.evt_tx_index AS bigint),CAST(e.evt_outer_instruction_index AS bigint),
           CAST(COALESCE(e.evt_inner_instruction_index,-1) AS bigint),e.evt_tx_id,NULL,NULL,NULL
    FROM pumpdotfun_solana.pump_evt_completeevent e JOIN cw c ON c.mint=e.mint
    WHERE e.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND e.evt_block_time >= c.created_at AND e.evt_block_time < c.obs_end
    UNION ALL
    SELECT 'K',mint,NULL,CAST(to_unixtime(created_at) AS bigint),NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL FROM cw
)
SELECT * FROM out
"""


def build(w0, cut, w1end, p=None, obs_cap=None):
    source = S.build_s3(
        w0, cut, w1end, p, S.emap_values({}), detail=True, obs_cap=obs_cap
    )
    prefix = source.split(",\nub AS (", 1)[0]
    e1 = min(
        w1end - dt.timedelta(days=1) + dt.timedelta(days=B.HORIZON_DAYS),
        B.LAST_EVENT_DAY,
    )
    if obs_cap is not None:
        e1 = min(e1, obs_cap - dt.timedelta(days=1))
    return prefix + FIRST_OUT.format(e0=w0.isoformat(), e1=e1.isoformat())


if __name__ == "__main__":
    (B.H / "sql/A8DRAFT_S3_FIRST_0811_p002.sql").write_text(
        build(
            dt.date(2026, 8, 11),
            dt.date(2026, 8, 12),
            dt.date(2026, 8, 13),
            p=0.002,
            obs_cap=dt.date(2026, 8, 13),
        )
    )

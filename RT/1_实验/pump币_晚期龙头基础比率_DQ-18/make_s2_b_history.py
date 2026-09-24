"""Render one DQ-18 B-stage history query from frozen A-stage results.

Usage:
  python make_s2_b_history.py FROM_MONTH THROUGH_MONTH COHORT_MONTH [COHORT_MONTH ...]

Each cohort result must exist at raw/s2/A_YYYYMM.json. This generates SQL only;
it never executes Dune or downloads signal-after data. A chunk may span multiple
month partitions, but each dex month is referenced only once within the query.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MINT_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}\Z")
MONTH_RE = re.compile(r"20\d\d-(0[1-9]|1[0-2])\Z")


def month_start(label: str) -> date:
    if MONTH_RE.fullmatch(label) is None:
        raise ValueError(f"bad month {label!r}")
    y, m = map(int, label.split("-"))
    return date(y, m, 1)


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def parse_created(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" UTC", "+00:00"))


def candidate_values(labels: list[str], from_month: date, end_month: date) -> list[str]:
    rows = set()
    for label in labels:
        cohort = month_start(label)
        path = ROOT / "raw" / "s2" / f"A_{cohort:%Y%m}.json"
        data = json.loads(path.read_text())
        for item in data["rows"]:
            mint = item["mint"]
            if MINT_RE.fullmatch(mint) is None:
                raise ValueError(f"invalid mint in {path}: {mint!r}")
            created = parse_created(item["created_at"])
            # There is no prehistory in or after the signal month. Excluding
            # future-created tokens here avoids a large redundant VALUES list.
            if created.date() >= end_month or cohort <= from_month:
                continue
            rows.add((str(cohort), mint, created.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]))
    return [
        f"        (DATE '{cohort}', '{mint}', TIMESTAMP '{created}')"
        for cohort, mint, created in sorted(rows)
    ]


def render(from_label: str, through_label: str, cohorts: list[str]) -> Path | None:
    start = month_start(from_label)
    through = month_start(through_label)
    end = next_month(through)
    if end <= start:
        raise ValueError("THROUGH_MONTH must not precede FROM_MONTH")
    values = candidate_values(cohorts, start, end)
    if not values:
        print("no candidate mint created before this history chunk; no Dune scan needed")
        return None
    cohort_list = ",".join(sorted(set(cohorts)))
    value_lines = ",\n".join(values)
    sql = f"""-- DQ-18 第 2 步 B 段：{from_label}..{through_label} 完整前史的一块。
-- Cohort: {cohort_list}. 候选 mint 来自已落盘的 A 段月内首达标结果。
-- 本查询只求历史小时市值最大值；本块最大值 >= 某门槛即证明此前已穿越。
-- 必须把每个候选从创建月到信号月前一月的所有块跑完，才可判历史首次。
-- 一块 SQL 同时核所有候选和四档门槛，dex 月分区只写一次。
-- 单次 Dune 上限 50 credits；预计费用未经实测。不要导出大表。

WITH candidates(cohort_start, mint, created_at) AS (
    VALUES
{value_lines}
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd
    FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '{start} 00:00:00'
      AND minute < TIMESTAMP '{end} 00:00:00'
    GROUP BY minute
), historical_trades AS (
    SELECT block_time, token_bought_mint_address, token_sold_mint_address,
           token_bought_amount, token_sold_amount
    FROM dex_solana.trades
    WHERE block_month >= DATE '{start}'
      AND block_month < DATE '{end}'
      AND block_time >= TIMESTAMP '{start} 00:00:00'
      AND block_time < TIMESTAMP '{end} 00:00:00'
      AND token_bought_mint_address <> token_sold_mint_address
), candidate_legs AS (
    SELECT c.cohort_start, c.mint, t.block_time,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = c.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM historical_trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address,
                            t.token_sold_mint_address]) AS leg(mint)
    JOIN candidates c ON c.mint = leg.mint
    WHERE t.block_time >= c.created_at
      AND t.block_time < CAST(c.cohort_start AS timestamp)
), valued AS (
    SELECT l.*,
           CASE
             WHEN l.quote_mint = 'So11111111111111111111111111111111111111112'
                  THEN l.quote_amount * s.sol_usd
             WHEN l.quote_mint IN (
                 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
             ) THEN l.quote_amount
             ELSE NULL
           END AS quote_usd
    FROM candidate_legs l
    LEFT JOIN sol_minute s
      ON l.quote_mint = 'So11111111111111111111111111111111111111112'
     AND s.minute = date_trunc('minute', l.block_time)
), hourly AS (
    SELECT cohort_start, mint, date_trunc('hour', block_time) AS hour_start,
           COUNT(*) AS n_all_trades,
           COUNT_IF(token_amount > 0 AND quote_usd > 0) AS n_price_trades,
           SUM(IF(token_amount > 0 AND quote_usd > 0, token_amount, 0))
               AS valid_token_volume,
           SUM(IF(token_amount > 0 AND quote_usd > 0, quote_usd, 0))
               AS valid_usd_volume
    FROM valued
    GROUP BY cohort_start, mint, date_trunc('hour', block_time)
), by_mint AS (
    SELECT cohort_start, mint,
           MAX(1000000000.0 * valid_usd_volume /
               NULLIF(valid_token_volume, 0)) AS prior_max_marketcap_usd,
           COUNT_IF(valid_token_volume > 0) AS n_priced_hours,
           SUM(n_all_trades) AS n_all_trades,
           SUM(n_price_trades) AS n_price_trades
    FROM hourly
    GROUP BY cohort_start, mint
)
SELECT c.cohort_start, c.mint, c.created_at,
       b.prior_max_marketcap_usd,
       COALESCE(b.n_priced_hours, 0) AS n_priced_hours,
       COALESCE(b.n_all_trades, 0) AS n_all_trades,
       COALESCE(b.n_price_trades, 0) AS n_price_trades
FROM candidates c
LEFT JOIN by_mint b ON b.cohort_start = c.cohort_start AND b.mint = c.mint
ORDER BY c.cohort_start, c.mint
"""
    target = ROOT / "sql" / f"S2_B_{from_label.replace('-', '')}_{through_label.replace('-', '')}_前史合并.sql"
    target.write_text(sql)
    print(f"{len(values)} candidate/cohort pairs; SQL bytes {len(sql.encode())}")
    print(target)
    return target


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit("usage: make_s2_b_history.py FROM THROUGH COHORT [COHORT ...]")
    render(sys.argv[1], sys.argv[2], sys.argv[3:])

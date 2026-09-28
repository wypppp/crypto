#!/usr/bin/env python3
"""Build corrected S1 queries on the exact, already-frozen S0 output mints.

This is a computational optimization only. It must not derive inclusion from S1
returns and must not query any sealed cohort. The S0 CSV is local and read-only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
S0 = HERE / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
SQL_DIR = HERE / "sql"
S1_FULL = SQL_DIR / "S1_AB_固定退出基础回收_旧卖出公式_未执行_勿复用.sql"
S1_SMOKE = SQL_DIR / "S1_SMOKE_20260601_旧卖出公式_全量后过滤_已执行_勿复用.sql"
OUT_FULL = SQL_DIR / "S1_AB_固定退出基础回收_曲线卖出修正_待验.sql"
OUT_SMOKE = SQL_DIR / "S1_SMOKE_20260601_固定退出基础回收_曲线卖出修正_待验.sql"
OUT_A = SQL_DIR / "S1_A_固定退出基础回收_曲线卖出修正_待验.sql"
OUT_B = SQL_DIR / "S1_B_固定退出基础回收_曲线卖出修正_待验.sql"


def correct_curve_sell(sql: str) -> str:
    # Pump curve sells ADD tokens to virtual-token reserves and REMOVE quote
    # from virtual-SOL reserves; same constant-product direction as PumpSwap.
    # The old (y - tokens) expression computed a buy-side inverse and was wrong.
    for suffix in ("", "_e30", "_e120"):
        tok = "entry_tokens" + suffix
        old = (
            f"CASE\n                WHEN venue = 0 AND y > {tok} THEN "
            f"(x * y / (y - {tok}) - x) * (1 - fee_bps / 1e4)\n"
            "                WHEN venue = 0 THEN NULL\n"
            f"                ELSE (x - x * y / (y + {tok})) * (1 - fee_bps / 1e4)\n"
            "            END"
        )
        if sql.count(old) != 1:
            raise AssertionError(f"sell formula anchor changed: {tok}")
        new = (
            "CASE\n"
            f"                WHEN venue = 0 THEN (x * {tok} / (y + {tok})) * (1 - fee_bps / 1e4)\n"
            f"                ELSE (x - x * y / (y + {tok})) * (1 - fee_bps / 1e4)\n"
            "            END"
        )
        sql = sql.replace(old, new, 1)
    return sql


def make(source: Path, rows: list[dict[str, str]], output: Path,
         creation_end: str | None = None, scan_end: str | None = None,
         creation_start: str | None = None) -> None:
    sql = source.read_text()
    sql = correct_curve_sell(sql)
    if creation_start is not None:
        old = "WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'"
        if sql.count(old) != 1:
            raise AssertionError("full creation window changed")
        sql = sql.replace(old, f"WHERE evt_block_date BETWEEN DATE '{creation_start}' AND DATE '{creation_end}'", 1)
        old_scan = "BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'"
        if sql.count(old_scan) != 5:
            raise AssertionError("full scan window changed")
        sql = sql.replace(old_scan, f"BETWEEN DATE '{creation_start}' AND DATE '{scan_end}'")
    creation_pred = (
        f"    WHERE evt_block_date BETWEEN DATE '{creation_start}' AND DATE '{creation_end}'\n"
        if creation_start is not None else
        ("    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'\n"
         if source == S1_FULL else
         "    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'\n")
    )
    if sql.count(creation_pred) != 1:
        raise AssertionError("creation predicate not unique")
    mints = sorted(r["mint"] for r in rows)
    if len(mints) != len(set(mints)):
        raise AssertionError("duplicate S0 mints")
    if any("'" in mint for mint in mints):
        raise AssertionError("unexpected mint text")
    literal = ",\n            ".join(f"'{mint}'" for mint in mints)
    sql = sql.replace(
        creation_pred,
        creation_pred + "      AND mint IN (\n            " + literal + "\n      )\n",
        1,
    )
    old_select = (
        "SELECT\n    CASE\n        WHEN r0_seen THEN 'r0_qa'\n"
        "        WHEN eligible AND (tail420_candidate OR tail10_exec) THEN 'tail420_all'\n"
        "        ELSE 'random_2pct'\n    END AS inclusion_class,\n"
        "    CASE\n        WHEN eligible AND (tail420_candidate OR tail10_exec) THEN 1.0\n"
        "        WHEN eligible AND mod(mint_hash, 10000) < 200 THEN 0.02\n"
        "    END AS objective_inclusion_probability,\n"
        "    CAST(mint_hash AS varchar) AS mint_hash_exact,\n"
    )
    if sql.count(old_select) != 1:
        raise AssertionError("output select changed")
    sql = sql.replace(old_select, "SELECT\n    CAST(mint_hash AS varchar) AS mint_hash_exact,\n", 1)
    old_tail = (
        "    n_all, n_eligible, n_tail420_candidate, n_random_2pct\n"
        "FROM with_counts\nWHERE r0_seen\n"
        "   OR (eligible AND (tail420_candidate OR tail10_exec))\n"
        "   OR (eligible AND mod(mint_hash, 10000) < 200)\n"
        "ORDER BY created_at, mint"
    )
    if sql.count(old_tail) != 1:
        raise AssertionError("output tail not unique")
    sql = sql.replace(old_tail, "    1 AS sample_preselected\nFROM all_coins\nORDER BY created_at, mint", 1)
    sql = (
        "/* S1 CORRECTED SELL DIRECTION + SAMPLE-FIRST OPTIMIZATION.\n"
        "   Exact frozen S0 mint list; no S1-outcome reselection. Sample weights\n"
        "   and total denominators MUST come from S0, not recomputed outcomes.\n"
        "   Verify mint set and independent sell quotes before interpreting returns. */\n"
        + sql
    )
    for table in ("pump_evt_tradeevent", "pump_amm_evt_buyevent", "pump_amm_evt_sellevent"):
        if sql.count("FROM pumpdotfun_solana." + table) != 1:
            raise AssertionError(f"unexpected scan count: {table}")
    output.write_text(sql)
    print(output.name, "mints", len(mints), "bytes", output.stat().st_size,
          "sha256", hashlib.sha256(sql.encode()).hexdigest())


def main() -> None:
    with gzip.open(S0, "rt", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 10565:
        raise AssertionError("S0 frozen output count changed")
    if any(not r["created_at"].startswith("2026-06-") for r in rows):
        raise AssertionError("S0 contains unexpected date")
    make(S1_FULL, rows, OUT_FULL)
    day = [r for r in rows if r["created_at"][:10] == "2026-06-01"]
    if len(day) != 695:
        raise AssertionError("S0 June 1 count changed")
    make(S1_SMOKE, day, OUT_SMOKE)
    a = [r for r in rows if r["created_at"][:10] <= "2026-06-07"]
    b = [r for r in rows if r["created_at"][:10] >= "2026-06-08"]
    if len(a) + len(b) != len(rows) or set(r["mint"] for r in a) & set(r["mint"] for r in b):
        raise AssertionError("A/B sample split is not a partition")
    make(S1_FULL, a, OUT_A, creation_start="2026-06-01", creation_end="2026-06-07",
         scan_end="2026-07-08")
    make(S1_FULL, b, OUT_B, creation_start="2026-06-08", creation_end="2026-06-14",
         scan_end="2026-07-15")


if __name__ == "__main__":
    main()

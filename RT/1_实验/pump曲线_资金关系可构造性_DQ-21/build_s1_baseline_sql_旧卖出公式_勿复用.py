#!/usr/bin/env python3
"""HISTORICAL GENERATOR WITH WRONG CURVE-SELL DIRECTION. DO NOT REUSE.

Derive a narrow S1 fixed-exit SQL from the frozen S0 path implementation.

Never overwrites S0. This is a local build and structural check, not a Dune run.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sql/S0_AB_事件时点机会普查_v1_3_运行版.sql"
OUT = HERE / "sql/S1_AB_固定退出基础回收_旧卖出公式_未执行_勿复用.sql"
SMOKE_OUT = HERE / "sql/S1_SMOKE_20260601_旧卖出公式_全量后过滤_已执行_勿复用.sql"


def once(s: str, old: str, new: str) -> str:
    if s.count(old) != 1:
        raise AssertionError(f"expected one anchor, found {s.count(old)}: {old[:60]}")
    return s.replace(old, new, 1)


def main() -> None:
    s = SOURCE.read_text()
    s = "/* S1 DRAFT: fixed-exit baseline, development cohort only.\n" \
        "   Derived mechanically from frozen S0 v1.3. Do not run before\n" \
        "   source audit, one-day QA, and actual Dune balance reconciliation. */\n" + s
    s = once(s,
        "        price / NULLIF(e5_x / e5_y, 0) AS pm\n",
        "        price / NULLIF(e5_x / e5_y, 0) AS pm,\n"
        "        price / NULLIF(e30_x / e30_y, 0) AS pm_e30,\n"
        "        price / NULLIF(e120_x / e120_y, 0) AS pm_e120\n")
    s = once(s,
        "        ) AS runmax_pm,\n        min(CASE\n",
        "        ) AS runmax_pm,\n"
        "        max(CASE WHEN rn >= e30_rn THEN pm_e30 END) OVER (\n"
        "            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n"
        "        ) AS runmax_pm_e30,\n"
        "        max(CASE WHEN rn >= e120_rn THEN pm_e120 END) OVER (\n"
        "            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n"
        "        ) AS runmax_pm_e120,\n"
        "        min(CASE\n")

    fixed_cols = []
    agg_cols = []
    out_cols = []
    for delay, suffix in [(5, ""), (30, "_e30"), (120, "_e120")]:
        v = f"sell_multiple{suffix}"
        for hold, label in [(30, "30s"), (120, "2m"), (600, "10m"), (3600, "1h")]:
            key = f"d{delay}_{label}"
            cutoff = delay + hold
            agg_cols.append(
                f"        NULLIF(max_by(COALESCE({v}, -1.0), rn) FILTER (WHERE rn >= e{delay}_rn "
                f"AND clock_ts <= t3_ts + INTERVAL '{cutoff}' SECOND), -1.0) AS ret_{key},"
            )
            agg_cols.append(
                f"        max_by(date_diff('second', clock_ts, t3_ts + INTERVAL '{cutoff}' SECOND), rn) "
                f"FILTER (WHERE rn >= e{delay}_rn AND clock_ts <= t3_ts + INTERVAL '{cutoff}' SECOND) "
                f"AS state_age_{key},"
            )
            fixed_cols += [f"p.ret_{key}", f"p.state_age_{key}"]
            out_cols += [f"ret_{key}", f"state_age_{key}"]
        cond = f"rn >= e{delay}_rn AND pm{suffix} <= 0.5 * greatest(1.0, runmax_pm{suffix})"
        agg_cols.extend([
            f"        NULLIF(min_by(COALESCE({v}, -1.0), rn) FILTER (WHERE {cond}), -1.0) AS stop_ret_d{delay},",
            f"        min_by(date_diff('second', t3_ts, clock_ts), rn) "
            f"FILTER (WHERE {cond}) AS stop_time_d{delay},",
            f"        NULLIF(max_by(COALESCE({v}, -1.0), rn) FILTER (WHERE rn >= e{delay}_rn), -1.0) AS horizon_ret_d{delay},",
        ])
        fixed_cols += [f"p.stop_ret_d{delay}", f"p.stop_time_d{delay}", f"p.horizon_ret_d{delay}"]
        out_cols += [f"CASE WHEN stop_time_d{delay} IS NOT NULL THEN stop_ret_d{delay} "
                     f"ELSE horizon_ret_d{delay} END AS b50_ret_d{delay}",
                     f"stop_time_d{delay}"]

    s = once(s,
        "        max(pm) FILTER (WHERE rn >= e5_rn) AS max_price_pm_30d,\n",
        "\n".join(agg_cols) + "\n"
        "        max(pm) FILTER (WHERE rn >= e5_rn) AS max_price_pm_30d,\n")
    s = once(s,
        "        p.max_price_pm_30d, p.tail420_candidate,\n",
        "        p.max_price_pm_30d, p.tail420_candidate,\n"
        "        " + ", ".join(fixed_cols) + ",\n")
    s = once(s,
        "    CAST(mint_hash AS varchar) AS mint_hash_exact,\n    *\nFROM with_counts\n",
        "    CAST(mint_hash AS varchar) AS mint_hash_exact,\n"
        "    mint, created_at, cohort_week, t3_s, t3_bucket, eligible,\n"
        "    tail420_candidate, tail10_exec, r0_seen, has_migration_event, amm_mapped,\n"
        "    e5_x, e5_y, e5_xr, e5_fee_bps, e5_venue, e5_ts, e30_ts, e120_ts,\n"
        "    " + ",\n    ".join(out_cols) + ",\n"
        "    n_all, n_eligible, n_tail420_candidate, n_random_2pct\n"
        "FROM with_counts\n")
    OUT.write_text(s)
    assert s.count("FROM pumpdotfun_solana.pump_evt_tradeevent") == 1
    assert s.count("FROM pumpdotfun_solana.pump_amm_evt_buyevent") == 1
    assert s.count("FROM pumpdotfun_solana.pump_amm_evt_sellevent") == 1
    smoke = once(s,
        "WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'",
        "WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'")
    long_window = "BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'"
    if smoke.count(long_window) != 5:
        raise AssertionError("unexpected number of 30-day scan predicates")
    smoke = smoke.replace(long_window, "BETWEEN DATE '2026-06-01' AND DATE '2026-07-02'")
    smoke = "/* S1 ONE-DAY QA ONLY: June 1 creations and full 30-day path; " \
            "no population or return inference. Execution cap <=100 credits. */\n" + smoke
    SMOKE_OUT.write_text(smoke)
    print(f"wrote {OUT}, {len(s.splitlines())} lines, 12 fixed exits, 3 b50 exits")
    print(f"wrote {SMOKE_OUT}, {len(smoke.splitlines())} lines")


if __name__ == "__main__":
    main()

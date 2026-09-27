#!/usr/bin/env python3
"""Check v1.3 case-selection identity and generated SQL before Dune execution."""
from itertools import product
from pathlib import Path
import re

H = Path(__file__).resolve().parent


def direct(prices, t3_index, last_early_index):
    return any(
        max(prices[i:]) >= 8 * prices[i]
        for i in range(t3_index, min(last_early_index + 1, len(prices)))
    )


def forward(prices, t3_index, last_early_index):
    running_min = None
    for j, price in enumerate(prices):
        if t3_index <= j <= last_early_index:
            running_min = price if running_min is None else min(running_min, price)
        if running_min is not None and price >= 8 * running_min:
            return True
    return False


def main():
    # Includes a peak before the qualifying low, and events sharing one second.
    values = (0.25, 0.5, 1, 2, 4, 8, 16)
    checked = 0
    for length in range(1, 6):
        for prices in product(values, repeat=length):
            for t3_index in range(length):
                for last_early_index in (t3_index, length - 1):
                    assert direct(prices, t3_index, last_early_index) == forward(
                        prices, t3_index, last_early_index
                    ), (prices, t3_index, last_early_index)
                    checked += 1

    template = (H / "sql/S0_AB_事件时点机会普查_v1_3.sql").read_text()
    runtime = (H / "sql/S0_AB_事件时点机会普查_v1_3_运行版.sql").read_text()
    smoke = (H / "sql/S0_SMOKE_v1_3_20260601.sql").read_text()
    assert template.count("('__R0_MINT_PLACEHOLDER__')") == 1
    assert "('__R0_MINT_PLACEHOLDER__')" not in runtime
    assert "s9_future" not in template and "future_max_price" not in template
    assert "rn >= t3_rn AND clock_ts <= created_at + INTERVAL '420' SECOND" in template
    assert "price / NULLIF(runmin_early_price, 0) >= 8" in template
    assert template.count("ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW") >= 2
    assert "tail420_candidate OR tail10_exec" in template
    assert "CAST(mint_hash AS varchar) AS mint_hash_exact" in template
    assert not re.search(r"FILTER\s*\([^)]*\)\s*OVER", template, re.S | re.I)
    assert smoke.count("BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'") == 1
    assert smoke.count("BETWEEN DATE '2026-06-01' AND DATE '2026-06-02'") == 5
    assert "INTERVAL '1' DAY" in smoke
    assert "Platform execution cap: 10 credits" in smoke
    print(f"S0 v1.3 identity cases: {checked}; SQL invariants: OK")


if __name__ == "__main__":
    main()

"""Render the same DQ-18 A-stage SQL for another calendar month.

Usage: python make_s2_a_month.py YYYY-MM
The reference query is the 2025-12 file. Rendering creates a reviewable SQL
file; it does not submit a Dune query or touch credentials.
"""

from datetime import date
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "sql" / "S2_A_202512_四档候选合并.sql"


def render(year_month: str) -> Path:
    if re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", year_month) is None:
        raise ValueError("expected YYYY-MM")
    year, month = map(int, year_month.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    source = REFERENCE.read_text()
    assert source.count("2025-12-01") >= 3
    assert source.count("2026-01-01") >= 3
    source = source.replace("2025-12-01", "__START__")
    source = source.replace("2026-01-01", "__END__")
    source = source.replace("2025-12", "__LABEL__")
    source = source.replace("12 月", "__MONTH_ZH__")
    output = (source.replace("__START__", start.isoformat())
                    .replace("__END__", end.isoformat())
                    .replace("__LABEL__", year_month)
                    .replace("__MONTH_ZH__", f"{month} 月"))
    target = ROOT / "sql" / f"S2_A_{year}{month:02d}_四档候选合并.sql"
    if target == REFERENCE:
        raise ValueError("reference month already exists")
    target.write_text(output)
    return target


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python make_s2_a_month.py YYYY-MM")
    print(render(sys.argv[1]))

"""Blind inputs for DQ-15 retrieval: mint lists and trigger times only (no returns, no winner labels)."""
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
EXP = HERE.parent
m2 = pd.read_csv(EXP / "pump曲线_右尾测量_DQ-1M/raw/M2_full.csv", usecols=["mint", "cday"])
m2 = m2[m2.mint.str.endswith("pump", na=False) | m2.mint.notna()]
(HERE / "raw/inputs/a_week_mints.txt").write_text("\n".join(m2.mint.astype(str)) + "\n")
ev = pd.read_csv(EXP / "pump曲线_案例时序与点火跟随_H1/h1_events_A.csv", usecols=["mint", "created_at", "signal_time"])
ev.to_csv(HERE / "raw/inputs/h1_triggers_blind.csv", index=False)
print(len(m2), "A-week mints;", len(ev), "H1 triggers (mint, created_at, signal_time only)")

"""DQ-15 step 1: coverage and timing of a message source against the blind event frame. No returns are read.

Input: a normalized CSV per source with columns
  source, msg_id, ts_utc (ISO or epoch seconds), url, text, author_kind ('human'|'bot'|'unknown'), edited (bool/None)
Usage: .venv/bin/python coverage.py raw/normalized/<source>.csv [more.csv ...]
Output: per-source summary + per-mention table in results/coverage_<source>.csv"""
import re, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
B58 = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")  # a token counts as a CA if it ends in "pump" or is an A-week mint (~10% of A-week mints lack the suffix)
A0, A1 = pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-06-08", tz="UTC")
amints = set((HERE / "raw/inputs/a_week_mints.txt").read_text().split())


def cas(text):
    return {t for t in B58.findall(text) if t.endswith("pump") or t in amints}
trig = pd.read_csv(HERE / "raw/inputs/h1_triggers_blind.csv")
trig["created_at"] = pd.to_datetime(trig.created_at, utc=True); trig["signal_time"] = pd.to_datetime(trig.signal_time, utc=True)
trig = trig.set_index("mint")
(HERE / "results").mkdir(exist_ok=True)


def ts(x):
    try:
        return pd.to_datetime(float(x), unit="s", utc=True)
    except (TypeError, ValueError):
        return pd.to_datetime(x, utc=True)


for path in sys.argv[1:]:
    m = pd.read_csv(path)
    m["text"] = m.text.fillna("")
    m["ts"] = m.ts_utc.map(ts)
    src = m.source.iloc[0]
    rows = []
    for r in m.itertuples():
        for ca in cas(str(r.text)):
            rows.append(dict(source=src, msg_id=r.msg_id, ts=r.ts, url=r.url, mint=ca, author_kind=r.author_kind, in_a_week=ca in amints))
    men = pd.DataFrame(rows)
    inwin = m[(m.ts >= A0) & (m.ts < A1)]
    print(f"\n== {src}: messages {len(m)} (A-week window {len(inwin)}), messages with CA {m.text.fillna("").astype(str).map(lambda t: bool(cas(t))).sum()}")
    if men.empty:
        print("   no pump CAs"); continue
    a = men[men.in_a_week]
    first = a.sort_values("ts").groupby("mint").first()
    print(f"   distinct CAs {men.mint.nunique()}; A-week coins mentioned {a.mint.nunique()} (human-authored {a[a.author_kind=='human'].mint.nunique()})")
    j = first.join(trig, how="inner")
    if len(j):
        j["h_from_create"] = (j.ts - j.created_at).dt.total_seconds() / 3600
        j["h_from_signal"] = (j.ts - j.signal_time).dt.total_seconds() / 3600
        print(f"   H1 triggers covered {len(j)}/{len(trig)}; first mention minus signal (h) quantiles "
              f"{j.h_from_signal.quantile([0, .25, .5, .75, 1]).round(2).tolist()}; before signal {int((j.h_from_signal < 0).sum())}")
    fa = first.copy()
    print("   per-day A-week coins first mentioned:", fa.ts.dt.date.value_counts().sort_index().to_dict())
    men.to_csv(HERE / "results" / f"coverage_{re.sub(r'[^0-9A-Za-z_-]+', '_', src)}.csv", index=False)

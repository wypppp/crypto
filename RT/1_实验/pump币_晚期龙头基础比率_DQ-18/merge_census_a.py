"""合并 A 段普查各月结果为“创建以来首次 P1 穿越”表（本地，不查 Dune）。

输入：raw/s2/C_A_*.json（普查，P1 主口径）与 raw/s2/P1_202512.json 的 p1 变体（2025-12，同口径）。
输出：raw/census/first_crossings.csv —— 每个 mint × 门槛一行，取所有已扫区间内最早的 P1 小时；
      missing_months 列出尚未扫到的月份，落在其后的穿越标 first_status=provisional。
人群下限：Dune pump 解码事件最早创建时间 2024-04-26（见普查结果），更早创建的币不在人群内。
"""
import csv
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "s2"
MISSING = []  # 2025-04、05 已单月补跑（09-24）


def rows():
    for f in sorted(glob.glob(str(RAW / "C_A_*.json"))):
        if f.endswith("_status.json") or "diag" in f:
            continue
        for r in json.load(open(f))["rows"]:
            yield Path(f).stem, r
    for r in json.load(open(RAW / "P1_202512.json"))["rows"]:
        if r["variant_name"] == "p1":
            yield "P1_202512", r


def main():
    best = {}
    for src, r in rows():
        k = (r["mint"], float(r["threshold_usd"]))
        if k not in best or r["hour_start"] < best[k][1]["hour_start"]:
            best[k] = (src, r)
    out = ROOT / "raw" / "census"
    out.mkdir(exist_ok=True)
    with open(out / "first_crossings.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mint", "threshold_usd", "created_at", "hour_start", "signal_time",
                    "n_p1_valid", "p1_usd_volume", "p1_vwap_cap_usd", "p1_median_cap_usd",
                    "source", "first_status"])
        for (mint, t), (src, r) in sorted(best.items(), key=lambda x: (x[0][1], x[1][1]["hour_start"])):
            month = r["hour_start"][:7]
            status = "provisional" if any(month > m for m in MISSING) else "first"
            w.writerow([mint, int(t), r["created_at"], r["hour_start"], r["signal_time"],
                        r["n_p1_valid"], r["p1_usd_volume"], r["p1_vwap_cap_usd"],
                        r["p1_median_cap_usd"], src, status])
    print("rows", len(best))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DQ-23 前向卡登记前的案头核查（用户 10-02 裁决〇-3）：COAI 的资金费能否收到、自动减仓的影响。0 credits。

COAI 是已看过的开发事件。只用 data.binance.vision 公开归档（资金费月文件、标记价 1 小时线），缓存与核对走冻结的 DQ-22 perp_replicate.py。
输出：资金费结算次数、间隔、触及上限次数；按结算时刻小时标记价重算的资金费；“若在持有期内任一小时末被自动减仓”的回收分布。
"""

import collections
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "币安新币_上线后做空_DQ-22"))
import perp_replicate as P  # noqa: E402

UTC = dt.timezone.utc
SYM, D = "COAIUSDT", dt.date(2025, 9, 26)  # 入场日＝永续上线后一日（DQ-23 events.csv）
FEE = 0.001


def main() -> None:
    p0 = P.daily("klines", SYM, D, D)[D]["c"]
    mk = P.daily("markPriceKlines", SYM, D, D + 30 * P.DAY)
    t1 = dt.datetime.combine(D + P.DAY, dt.time(), UTC)
    t2 = dt.datetime.combine(D + 31 * P.DAY, dt.time(), UTC)
    fr = P.funding(SYM, t1, t2)
    hours = {}
    for m in ("2025-09", "2025-10"):
        rel = f"monthly/markPriceKlines/{SYM}/1h/{SYM}-1h-{m}.zip"
        for r in P.D.parse_klines(P.fetch(rel)):
            hours[r["t"] // 1000] = r  # 2025 起归档时间戳为微秒

    def mark_at(t: dt.datetime) -> float:
        k = int(t.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
        return hours[k]["o"]

    gaps = collections.Counter(
        round((b[0] - a[0]).total_seconds() / 3600) for a, b in zip(fr, fr[1:])
    )
    f_daily = sum(-r * mk[t.date()]["c"] / p0 for t, r in fr if t.date() in mk)
    f_hour = sum(-r * mark_at(t) / p0 for t, r in fr)
    keys = sorted(
        k for k in hours if t1.timestamp() * 1000 <= k < t2.timestamp() * 1000
    )
    vals = []
    for k in keys:
        tau = dt.datetime.fromtimestamp(k / 1000, UTC) + dt.timedelta(hours=1)
        f = sum(-r * mark_at(t) / p0 for t, r in fr if t < tau)
        vals.append(hours[k]["c"] / p0 - 1 - FEE + f)
    s = sorted(vals)
    out = {
        "settlements": len(fr),
        "interval_hours": dict(gaps),
        "n_at_minus_2pct": sum(1 for _, r in fr if round(r, 5) == -0.02),
        "sum_rates": round(sum(r for _, r in fr), 4),
        "funding_daily_close_mark": round(f_daily, 2),
        "funding_hourly_mark_at_settlement": round(f_hour, 2),
        "price_part": round(
            P.daily("klines", SYM, D + 30 * P.DAY, D + 30 * P.DAY)[D + 30 * P.DAY]["c"]
            / p0
            - 1,
            2,
        ),
        "mark_max_over_entry": round(max(hours[k]["h"] for k in keys) / p0, 1),
        "if_adl_at_hour_end": {
            "min": round(s[0], 2),
            "p10": round(s[int(0.1 * (len(s) - 1))], 2),
            "median": round(statistics.median(s), 1),
            "p90": round(s[int(0.9 * (len(s) - 1))], 1),
            "max": round(s[-1], 1),
            "first_10_days_max": round(max(vals[: 10 * 24]), 2),
        },
    }
    (HERE / "coai_check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

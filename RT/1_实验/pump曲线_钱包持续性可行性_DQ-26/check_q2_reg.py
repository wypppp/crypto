#!/usr/bin/env python3
"""DQ-26 Q2 回归（卡片_Q2_执行_v1.md §7）：06-01 的 t3 触发与 S1 单日结果逐币对照。

python check_q2_reg.py → runs/check_q2_reg.json
对照 DQ-21 raw/s1/S1_A_dual.csv.gz 中 06-01 创建的币（S1 A 周双口径正式结果；口径 A 与 B 都比）。
不用 S1_SMOKE_20260601.csv.gz：那是旧卖出公式的单日结果，其审计文件标为 INVALID RETURNS。
  入场状态时钟  edt5        vs  e5_ts − created_at（秒）
  跟随退出      sell_{a,b}_d5/0.5 vs ret_d5_30s{,_b}（卖出信号 t3+30 秒，延迟 5 秒 → t3+35 秒前最后一个状态）
  b50（5 秒）   b50_stop_{a,b}/0.5 vs b50_ret_d5{,_b}，只比 S1 止损发生在 06-03 结束前的币（Q2 回归的数据截至 06-03）
容差：相对误差 ≤1e-6；含 PumpSwap 状态的单列（费率取法不同）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
S1 = (
    H.parents[0] / "pump曲线_资金关系可构造性_DQ-21" / "raw" / "s1" / "S1_A_dual.csv.gz"
)
TOL = 1e-6
CUT = pd.Timestamp("2026-06-04 00:00:00", tz="UTC")


def rel(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).abs() / b.abs().clip(lower=1e-12)


def main() -> None:
    q = pd.read_csv(H / "raw" / "dune" / "Q2_REG_20260601.csv.gz")
    s = pd.read_csv(S1)
    for d in (q, s):
        d["created_at"] = pd.to_datetime(d.created_at, utc=True)
    s = s[s.created_at.dt.strftime("%Y-%m-%d") == "2026-06-01"].copy()
    s["e5_ts"] = pd.to_datetime(s.e5_ts, utc=True)
    m = s.merge(q, on="mint", how="left", suffixes=("_s1", ""), validate="1:1")
    has_t3 = m.t3_s_s1.notna()
    out: dict = {
        "s1_coins": int(len(s)),
        "s1_with_t3": int(has_t3.sum()),
        "matched": int((has_t3 & m.b_dt.notna()).sum()),
        "t3_equal": int((m.t3_s_s1 == m.t3_s).sum()),
    }
    k = m[has_t3 & m.b_dt.notna()].copy()
    e5_dt = (k.e5_ts - k.created_at_s1).dt.total_seconds()
    out["entry_clock_equal"] = int((e5_dt == k.edt5).sum())
    amm = (k.xvenue5 == 1) | (k.e_venue_b == 1)
    stop_at = k.created_at_s1 + pd.to_timedelta(k.t3_s_s1 + k.stop_time_d5, unit="s")
    sb = k.stop_time_d5.notna() & (stop_at < CUT)
    curve_ok = True
    for c, sfx in (("a", ""), ("b", "_b")):
        r = rel(k[f"sell_{c}_d5"] / 0.5, k[f"ret_d5_30s{sfx}"])
        both = k[f"ret_d5_30s{sfx}"].notna() & k[f"sell_{c}_d5"].notna()
        out[f"follow_exit_{c}"] = {
            "compared": int(both.sum()),
            "within_tol": int((both & (r <= TOL)).sum()),
            "curve_only_within_tol": f"{int((both & ~amm & (r <= TOL)).sum())}/{int((both & ~amm).sum())}",
            "max_rel_err": float(r[both].max()),
            "max_rel_err_curve_only": float(r[both & ~amm].max()),
            "null_mismatch": int(
                (k[f"ret_d5_30s{sfx}"].isna() != k[f"sell_{c}_d5"].isna()).sum()
            ),
        }
        curve_ok &= (
            bool(np.all(r[both & ~amm] <= TOL))
            and out[f"follow_exit_{c}"]["null_mismatch"] == 0
        )
        rb = rel(k[f"b50_stop_{c}"] / 0.5, k[f"b50_ret_d5{sfx}"])
        bb = sb & k[f"b50_ret_d5{sfx}"].notna()
        mig = k.has_migration_event.astype(bool)
        out[f"b50_{c}"] = {
            "compared": int(bb.sum()),
            "within_tol": int((bb & (rb <= TOL)).sum()),
            "unmigrated_within_tol": f"{int((bb & ~mig & (rb <= TOL)).sum())}/{int((bb & ~mig).sum())}",
            "max_rel_err": float(rb[bb].max()) if bb.any() else None,
            "max_rel_err_migrated": float(rb[bb & mig].max())
            if (bb & mig).any()
            else None,
        }
        curve_ok &= bool(np.all(rb[bb & ~mig] <= TOL))
        if c == "a":
            bad = k[both & (r > TOL)][
                ["mint", "ret_d5_30s", "sell_a_d5", "xvenue5", "e_venue_b"]
            ]
    out["b50_stop_clock_equal"] = (
        f"{int((sb & (k.b50_stop_dt == k.t3_s_s1 + k.stop_time_d5)).sum())}/{int(sb.sum())}"
    )
    out["mismatch_examples"] = bad.head(10).to_dict("records")
    out["pass"] = bool(
        out["t3_equal"] == out["matched"]
        and out["entry_clock_equal"] == out["matched"]
        and curve_ok
    )
    out["pass_rule"] = (
        "曲线状态逐币相对误差 ≤1e-6；PumpSwap（迁移币）因费率取法不同单列（卡片 §7）"
    )
    (H / "runs" / "check_q2_reg.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

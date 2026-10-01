#!/usr/bin/env python3
"""DQ-26 Q2 外部跟随评分（卡片_Q2_执行_v1.md §4～§6；与卡片一起冻结，读检验窗口之前）。

python q2.py → runs/q2.json、runs/q2_triggers.csv
输入 raw/dune/Q2_T.csv.gz（sql/Q2_T.sql 的结果：每个（实体, 币）触发一行，卖出所得为 SOL）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RUNS = H / "runs"
STAKE, FEE_TX = 0.5, 0.002
HOLD = 7 * 86400
DATA_END = pd.Timestamp("2026-09-07 00:00:00", tz="UTC")
DELAYS = (2, 5, 15, 30)
SEED, NBOOT = 20261001, 10_000


def cells(t: pd.DataFrame) -> dict[str, pd.Series]:
    """每格的卖出所得（SOL）；b50：有止损即止损所得，否则持有到 H 的所得（S1 同一取法）。"""
    out = {"主格_d2_跟随_A": t.sell_a_d2}
    for d in DELAYS[1:]:
        out[f"d{d}_跟随_A"] = t[f"sell_a_d{d}"]
    for d in DELAYS:
        out[f"d{d}_跟随_B"] = t[f"sell_b_d{d}"]
    stop = t.b50_stop_dt.notna()
    out["b50_d2_A"] = t.b50_stop_a.where(stop, t.hor_a)
    out["b50_d2_B"] = t.b50_stop_b.where(stop, t.hor_b)
    return out


def recovery(sell: pd.Series) -> pd.Series:
    return (sell - FEE_TX) / (STAKE + FEE_TX)


def boot(v: pd.Series, day: pd.Series, rng: np.random.Generator) -> list[float]:
    """按创建日分块自助法：有放回抽日，统计量＝抽中各日全部触发的平均。"""
    g = (
        pd.DataFrame({"v": v, "day": day})
        .dropna()
        .groupby("day")
        .v.agg(["sum", "count"])
    )
    s, n = g["sum"].to_numpy(), g["count"].to_numpy()
    idx = rng.integers(0, len(g), size=(NBOOT, len(g)))
    stat = s[idx].sum(1) / n[idx].sum(1)
    return [
        round(float(np.quantile(stat, 0.025)), 4),
        round(float(np.quantile(stat, 0.975)), 4),
    ]


def summarize(r: pd.Series, day: pd.Series, rng: np.random.Generator) -> dict:
    ok = r.notna()
    rr, dd = r[ok], day[ok]
    z = rr.clip(upper=3)
    win, loss = rr[rr > 1], rr[rr <= 1]
    rw, rl = (float(win.mean()) if len(win) else np.nan), float(loss.mean())
    return {
        "n": int(ok.sum()),
        "n_undefined": int((~ok).sum()),
        "mean_Z": round(float(z.mean()), 4),
        "Z_ci95": boot(z, dd, rng),
        "mean_R": round(float(rr.mean()), 4),
        "R_ci95": boot(rr, dd, rng),
        "median_R": round(float(rr.median()), 4),
        "hit_rate": round(float((rr > 1).mean()), 4),
        "R_W": round(rw, 4),
        "R_L": round(rl, 4),
        "p_BE": round((1 - rl) / (rw - rl), 4) if np.isfinite(rw) else None,
        "net_sol": round(float(((rr - 1) * (STAKE + FEE_TX)).sum()), 2),
    }


def main() -> None:
    t = pd.read_csv(H / "raw" / "dune" / "Q2_T.csv.gz")
    t["created_at"] = pd.to_datetime(t.created_at, utc=True)
    t["day"] = t.created_at.dt.strftime("%Y-%m-%d")
    assert t.day.min() >= "2026-08-17" and t.day.max() <= "2026-08-30"
    assert not t.duplicated(["mint", "entity"]).any()
    prof = pd.read_csv(RUNS / "top50_profile.csv")
    prof["group"] = np.where(
        prof.same_slot_cells >= 0.9,
        "同槽为主",
        np.where((prof.hold_med_buyw >= 30) & (prof.after_t35 > 0.5), "可跟随", "其他"),
    )
    t = t.merge(prof[["entity", "group"]], on="entity", how="left", validate="m:1")
    assert t.group.notna().all()

    rng = np.random.default_rng(SEED)
    res: dict = {"cells": {}}
    rs = {}
    for name, sell in cells(t).items():
        rs[name] = recovery(sell)
        res["cells"][name] = summarize(rs[name], t.day, rng)
    m = res["cells"]["主格_d2_跟随_A"]
    if m["Z_ci95"][0] > 1:
        reading = "读法 1（支持）：主格平均 Z 下界 >1"
    elif m["R_ci95"][1] < 1:
        reading = "读法 2（关闭所测实现）：主格平均 R 上界 <1"
    else:
        reading = "读法 3（不定）"
    res["reading"] = reading

    r0 = rs["主格_d2_跟随_A"]
    t["R_main"], t["Z_main"] = r0, r0.clip(upper=3)
    t["net_main"] = (r0 - 1) * (STAKE + FEE_TX)
    trig_end = t.created_at + pd.to_timedelta(t.b_dt + HOLD, unit="s")
    by_ent = t.groupby("entity").Z_main.mean()
    by_coin = t.groupby("mint").net_main.sum().sort_values(ascending=False)
    by_day = t.groupby("day").net_main.sum().sort_values(ascending=False)
    pos = by_coin[by_coin > 0].sum()
    res["describe"] = {
        "n_triggers": int(len(t)),
        "n_entities_with_trigger": int(t.entity.nunique()),
        "entities_not_participating": int(50 - t.entity.nunique()),
        "triggers_per_entity": t.groupby("entity").size().describe().round(1).to_dict(),
        "by_group": {
            g: {
                "n_entities": int(x.entity.nunique()),
                "n": int(len(x)),
                "mean_Z": round(float(x.Z_main.mean()), 4),
                "mean_R": round(float(x.R_main.mean()), 4),
                "net_sol": round(float(x.net_main.sum()), 2),
            }
            for g, x in t.groupby("group")
        },
        "entity_equal_weight_mean_Z": round(float(by_ent.mean()), 4),
        "entities_mean_Z_gt1": int((by_ent > 1).sum()),
        "share_sell_signal_before_entry": {
            f"d{d}": round(float((t.s_dt <= t.b_dt + d).mean()), 4) for d in DELAYS
        },
        "share_exit_same_second_as_entry_d2": round(
            float((t.xdt2 == t.edt2).mean()), 4
        ),
        "share_no_sell_signal": round(float(t.s_dt.isna().mean()), 4),
        "concentration_main": {
            "net_total_sol": round(float(t.net_main.sum()), 2),
            "top10_coins_net_sol": round(float(by_coin.head(10).sum()), 2),
            "top10_coins_share_of_positive_net": round(
                float(by_coin.head(10).sum() / pos), 4
            )
            if pos > 0
            else None,
            "top_day": by_day.index[0],
            "top_day_net_sol": round(float(by_day.iloc[0]), 2),
        },
        "trigger_dt_s_quantiles": t.b_dt.quantile(
            [0.1, 0.25, 0.5, 0.75, 0.9]
        ).to_dict(),
        "share_same_slot_trigger": round(float(t.b_same_slot.mean()), 4),
        "share_trigger_before_t3_plus5": round(
            float(((t.t3_s <= 300) & (t.b_dt < t.t3_s + 5)).mean()), 4
        ),
        "share_entry_on_pumpswap_d2": round(float((t.e_venue_b == 1).mean()), 4),
        "n_horizon_cut_by_data_end": int((trig_end > DATA_END).sum()),
        "entry_state_age_s_d2_quantiles": (t.b_dt + 2 - t.edt2)
        .quantile([0.5, 0.9, 0.99])
        .to_dict(),
    }
    t.to_csv(RUNS / "q2_triggers.csv", index=False)
    (RUNS / "q2.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

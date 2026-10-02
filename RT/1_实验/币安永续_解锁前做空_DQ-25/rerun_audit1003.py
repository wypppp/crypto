#!/usr/bin/env python3
"""代码审计 10-03 第 9、13 处：F127（unlock_short.py）的新旧并列重跑。原脚本不改。

python rerun_audit1003.py <0|a|b>   → runs/audit1003/<版本>/（每个版本单独一个进程）
python rerun_audit1003.py compare   → runs/audit1003/compare.json，并打印并列表
  0：原版原样运行（核对复现）；a：只修第 9 处；b：第 9＋13 处（DQ-22 perp_v2.iso_path，做空腿）。
篮子腿不涉及资金费，不变。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "币安新币_上线后做空_DQ-22"))
import perp_replicate as P  # noqa: E402
import perp_v2 as V  # noqa: E402
import unlock_short as U  # noqa: E402

OUT = HERE / "runs" / "audit1003"


def short_leg_b(perp, d0, d1, orig=U.short_leg) -> dict:
    out = orig(perp, d0, d1)
    if out["status"] != "ok":
        return out
    res = V.iso_event(-1, perp, d0, d1)
    assert res is not None, (perp, d0)
    out["liq_v1"], out["r_v1"] = out["liq"], out["r"]
    out["liq"], out["r"], out["liq_day"], out["avail"] = (
        res["liq"],
        res["r"],
        res["liq_day"],
        res["A"],
    )
    if res["liq"]:
        out["r_px"] = -1.0
    else:
        assert not out["liq_v1"], (perp, d0)
    return out


def run(variant: str) -> None:
    U.RUNS = OUT / variant
    U.RUNS.mkdir(parents=True, exist_ok=True)
    if variant in ("a", "b"):
        P.funding = V.funding_v2
    if variant == "b":
        U.short_leg = short_leg_b
    U.main()


def compare() -> None:
    key = ["cell", "perp", "T"]
    orig_ev = pd.read_csv(HERE / "runs" / "events.csv")
    orig_an = json.loads((HERE / "runs" / "analysis.json").read_text())
    res: dict = {
        "原入库": {"cells": orig_an["cells"], "reading": orig_an.get("reading")}
    }
    for v in ("0", "a", "b"):
        d = OUT / v
        if not (d / "analysis.json").exists():
            continue
        an = json.loads((d / "analysis.json").read_text())
        e = pd.read_csv(d / "events.csv")
        m = orig_ev.merge(e, on=key, suffixes=("_o", "_n"))
        ch = m[m.status_o != m.status_n]
        both = m[(m.status_o == "ok") & (m.status_n == "ok")]
        diff = both[(both.H30_r_o - both.H30_r_n).abs() > 1e-12]
        res[v] = {
            "cells": an["cells"],
            "reading": an.get("reading"),
            "status_changed": ch[key + ["status_o", "status_n"]].to_dict("records"),
            "r_changed": diff[key + ["H30_r_o", "H30_r_n", "liq_o", "liq_n"]].to_dict(
                "records"
            ),
        }
    (OUT / "compare.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    for v, r in res.items():
        for c, x in r["cells"].items():
            if "mean" in x:
                ci = [round(q, 4) for q in x["ci95_block_month"]]
                print(v, c, x["n"], round(x["mean"], 4), ci)
        print("   reading", r["reading"])
        if v != "原入库":
            print(
                "   状态改变", len(r["status_changed"]), "回收改变", len(r["r_changed"])
            )


if __name__ == "__main__":
    compare() if sys.argv[1] == "compare" else run(sys.argv[1])

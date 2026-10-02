#!/usr/bin/env python3
"""代码审计 10-03 第 9、13 处：F125（long_squeeze.py）的新旧并列重跑。原脚本不改。

python rerun_audit1003.py <0|a|b>   → runs/audit1003/<版本>/（每个版本单独一个进程）
python rerun_audit1003.py compare   → runs/audit1003/compare.json，并打印并列表
  0：原版原样运行（核对复现）；a：只修第 9 处；b：第 9＋13 处（DQ-22 perp_v2.iso_path，做多一侧），止盈格同样重算。
公告快照（只用于“先上永续、后上现货”描述）写到各版本目录，不覆盖 raw/。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "币安新币_上线后做空_DQ-22"))
import long_squeeze as L  # noqa: E402
import perp_replicate as P  # noqa: E402
import perp_v2 as V  # noqa: E402

OUT = HERE / "runs" / "audit1003"
CELLS = (
    "M_H30",
    "S1_H7",
    "S2_H30_TP100",
    "S3_H30_TP50",
    "S4_perp_only_199",
    "S5_perp_first",
)


def long_event_b(rec: dict, orig=L.long_event) -> dict:
    out = orig(rec)
    if out.get("status") != "ok":
        return out
    sym, d = out["perp"], dt.date.fromisoformat(out["entry_day"])
    for h in L.HOLDS:
        tag = f"H{h}"
        if out.get(f"{tag}_status") != "ok":
            continue
        res = V.iso_event(+1, sym, d, d + h * P.DAY)
        assert res is not None, (sym, h)
        out[f"{tag}_liq_v1"], out[f"{tag}_r_v1"] = out[f"{tag}_liq"], out[f"{tag}_r"]
        out[f"{tag}_liq"], out[f"{tag}_r"] = res["liq"], res["r"]
        out[f"{tag}_liq_day"], out[f"{tag}_avail"] = res["liq_day"], res["A"]
        if res["liq"]:
            out[f"{tag}_r_px"] = -1.0
        else:
            assert not out[f"{tag}_liq_v1"], (sym, h)
    if out.get("H30_status") != "ok":
        return out
    p0 = P.daily("klines", sym, d, d)[d]["c"]
    for tag, k in L.TPS.items():
        out[f"{tag}_r_v1"] = out[f"{tag}_r"]
        if out[f"{tag}_hit_day"] is None or pd.isna(out[f"{tag}_hit_day"]):
            out[f"{tag}_r"], out[f"{tag}_liq"] = out["H30_r"], out["H30_liq"]
            continue
        hit = d + int(out[f"{tag}_hit_day"]) * P.DAY
        res = V.iso_event(+1, sym, d, hit, p_exit=p0 * (1 + k))
        out[f"{tag}_r"], out[f"{tag}_liq"] = res["r"], res["liq"]
    return out


def run(variant: str) -> None:
    L.RUNS = L.RAW = OUT / variant
    L.RUNS.mkdir(parents=True, exist_ok=True)
    if variant in ("a", "b"):
        P.funding = V.funding_v2
    if variant == "b":
        L.long_event = long_event_b
    L.main()


def compare() -> None:
    orig_ev = pd.read_csv(HERE / "runs" / "events.csv")
    orig_an = json.loads((HERE / "runs" / "analysis.json").read_text())
    res: dict = {"原入库": {c: orig_an["cells"].get(c) for c in CELLS}}
    for v in ("0", "a", "b"):
        d = OUT / v
        if not (d / "analysis.json").exists():
            continue
        an = json.loads((d / "analysis.json").read_text())
        e = pd.read_csv(d / "events.csv")
        m = orig_ev.merge(e, on="perp", suffixes=("_o", "_n"))
        r = {c: an["cells"].get(c) for c in CELLS}
        for h in L.HOLDS:
            so, sn = m[f"H{h}_status_o"], m[f"H{h}_status_n"]
            ch = m[(so != sn) & (so.notna() | sn.notna())]
            r[f"H{h}_status_changed"] = ch[
                ["perp", f"H{h}_status_o", f"H{h}_status_n"]
            ].to_dict("records")
            both = m[(so == "ok") & (sn == "ok")]
            diff = both[(both[f"H{h}_r_o"] - both[f"H{h}_r_n"]).abs() > 1e-12]
            r[f"H{h}_r_changed"] = diff[
                ["perp", f"H{h}_r_o", f"H{h}_r_n", f"H{h}_liq_o", f"H{h}_liq_n"]
            ].to_dict("records")
        res[v] = r
    (OUT / "compare.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    for v, r in res.items():
        for c in CELLS:
            x = r.get(c) or {}
            if "mean" in x:
                ci = [round(q, 4) for q in x["ci95_block_month"]]
                print(
                    v,
                    c,
                    x["n"],
                    round(x["mean"], 4),
                    ci,
                    "liq",
                    round(x["share_liquidated"], 4),
                )
        if v != "原入库":
            for h in L.HOLDS:
                print(
                    "   ",
                    f"H{h}",
                    "状态改变",
                    len(r[f"H{h}_status_changed"]),
                    "回收改变",
                    len(r[f"H{h}_r_changed"]),
                )


if __name__ == "__main__":
    compare() if sys.argv[1] == "compare" else run(sys.argv[1])

#!/usr/bin/env python3
"""代码审计 10-03 第 9、13 处：F123（perp_replicate.py）与 F124（oos_replicate.py）的新旧并列重跑。原脚本不改。

python rerun_audit1003.py <perp|oos> <0|a|b>   → runs/audit1003/<脚本>_<版本>/（每个组合单独一个进程）
python rerun_audit1003.py compare               → runs/audit1003/compare.json，并打印并列表
  0：原版原样运行（核对能逐字复现入库结果）；
  a：只修第 9 处（资金费月份，perp_v2.funding_v2）；
  b：第 9＋13 处（再用 perp_v2.iso_path 按逐仓保证金与可用余额重算强平与回收）。
只用原版已缓存或公开的币安归档；事件集合与原版相同（原版的留出断言照常执行）。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import perp_replicate as P  # noqa: E402
import perp_v2 as V  # noqa: E402

OUT = HERE / "runs" / "audit1003"


def patch_b(out: dict, sym: str | None, side: int) -> dict:
    """在原版事件结果上，把状态为 ok 的持有格按 iso_path 重算 r、liq、r_px。"""
    if sym is None:
        return out
    d = dt.date.fromisoformat(out["entry_day"])
    for h in P.HOLDS:
        tag = f"H{h}"
        if out.get(f"{tag}_status") != "ok":
            continue
        res = V.iso_event(side, sym, d, d + h * P.DAY)
        assert res is not None, (sym, h)
        px = out[f"{tag}_r_px"] if not out[f"{tag}_liq"] else None
        out[f"{tag}_liq_v1"] = out[f"{tag}_liq"]
        out[f"{tag}_r_v1"] = out[f"{tag}_r"]
        out[f"{tag}_liq"] = res["liq"]
        out[f"{tag}_liq_day"] = res["liq_day"]
        out[f"{tag}_avail"] = res["A"]
        out[f"{tag}_r"] = res["r"]
        if res["liq"]:
            out[f"{tag}_r_px"] = -1.0
        elif (
            px is None
        ):  # 原版强平、新版不强平：不会出现（新版强平不晚于原版），出现即停
            raise AssertionError((sym, h))
    return out


def run(script: str, variant: str) -> None:
    P.RUNS = OUT / f"{script}_{variant}"
    P.RUNS.mkdir(parents=True, exist_ok=True)
    if variant in ("a", "b"):
        P.funding = V.funding_v2
    if script == "perp":
        if variant == "b":
            orig = P.event

            def event_b(rec: dict) -> dict:
                out = orig(rec)
                return patch_b(out, out.get("perp"), -1)

            P.event = event_b
        P.main()
    else:
        import oos_replicate as O

        if variant == "b":
            orig_one = O.one

            def one_b(sym: str, t0: dt.date) -> dict:
                return patch_b(orig_one(sym, t0), sym, -1)

            O.one = one_b
        O.main()


def summary(path: Path, cell: str) -> dict:
    a = json.loads(path.read_text())
    c = a["cells"][cell]
    return {
        "n": c.get("n"),
        "mean": c.get("mean"),
        "ci95_block_month": c.get("ci95_block_month"),
        "median": c.get("median"),
        "share_liquidated": c.get("share_liquidated"),
        "reading": a.get("reading"),
    }


def compare() -> None:
    res: dict = {}
    files = {
        "perp": ("events.csv", "analysis.json"),
        "oos": ("oos_events.csv", "oos_analysis.json"),
    }
    for script, (ev, an) in files.items():
        orig_ev = pd.read_csv(HERE / "runs" / ev)
        r = {"原入库": {k: summary(HERE / "runs" / an, k) for k in ("H30_L1", "H7_L1")}}
        for v in ("0", "a", "b"):
            d = OUT / f"{script}_{v}"
            if not (d / an).exists():
                continue
            r[v] = {k: summary(d / an, k) for k in ("H30_L1", "H7_L1")}
            e = pd.read_csv(d / ev)
            key = "base" if script == "perp" else "perp"
            m = orig_ev.merge(e, on=key, suffixes=("_o", "_n"))
            for h in P.HOLDS:
                so, sn = m[f"H{h}_status_o"], m[f"H{h}_status_n"]
                ch = m[(so != sn) & (so.notna() | sn.notna())]
                r[v][f"H{h}_status_changed"] = [
                    {
                        key: x[key],
                        "old": x[f"H{h}_status_o"],
                        "new": x[f"H{h}_status_n"],
                        "r_new": x.get(f"H{h}_r_n"),
                    }
                    for _, x in ch.iterrows()
                ]
                both = m[(so == "ok") & (sn == "ok")]
                diff = both[(both[f"H{h}_r_o"] - both[f"H{h}_r_n"]).abs() > 1e-12]
                r[v][f"H{h}_r_changed"] = [
                    {
                        key: x[key],
                        "r_old": x[f"H{h}_r_o"],
                        "r_new": x[f"H{h}_r_n"],
                        "liq_old": bool(x[f"H{h}_liq_o"]),
                        "liq_new": bool(x[f"H{h}_liq_n"]),
                    }
                    for _, x in diff.iterrows()
                ]
        res[script] = r
    (OUT / "compare.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    for script, r in res.items():
        for v, x in r.items():
            for k in ("H30_L1", "H7_L1"):
                c = x[k]
                print(
                    script,
                    v,
                    k,
                    c["n"],
                    round(c["mean"], 4),
                    [round(q, 4) for q in c["ci95_block_month"]],
                    c["reading"],
                )
            if v in ("0", "a", "b"):
                for h in P.HOLDS:
                    print(
                        "   ",
                        f"H{h}",
                        "状态改变",
                        len(x[f"H{h}_status_changed"]),
                        "回收改变",
                        len(x[f"H{h}_r_changed"]),
                    )


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare()
    else:
        run(sys.argv[1], sys.argv[2])

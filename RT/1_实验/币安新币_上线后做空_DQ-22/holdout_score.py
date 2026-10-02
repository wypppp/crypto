#!/usr/bin/env python3
"""DQ-22 留出一次性评分（卡片_留出一次性评分_v1.md；与卡片一起冻结，门 1 复核通过之前不运行）。

python holdout_score.py --gate1 <记录门 1 通过的提交号>
→ runs/holdout_events.csv、runs/holdout_analysis.json（只运行一次；输出已存在即拒绝）

事件：Probe L 母表 `embargo_metadata` 的 55 条（sha256(baseAsset) 首字节 mod 5 == 0 的币安现货首发）。
规则：完全沿用冻结的 perp_replicate.py（卡片_永续复现_v1 §2～§3）的映射、入场、爆仓、资金费与费用，
只调用其取数函数；不取现货、不扩格。缓存写入 raw_holdout/，与开发期 raw/ 分开。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import perp_replicate as P  # noqa: E402

P.RAW = HERE / "raw_holdout"
MASTER = (
    HERE.parents[1] / "5_参考" / "旧债务" / "direction" / "v1.8.40" / "L_u_master.json"
)
OUT_EV = P.RUNS / "holdout_events.csv"
OUT_AN = P.RUNS / "holdout_analysis.json"
SEED = 20261002
DEV_MEAN = 0.139  # F123 主格点估计，“反证”门槛
FORWARD_START = dt.date(2026, 11, 1)
DAY = dt.timedelta(days=1)


def frame() -> list[dict]:
    e = json.loads(MASTER.read_text())["embargo_metadata"]
    assert len(e) == 55
    assert all(x["kind"] == "FIRST_SPOT_LISTING" for x in e)
    rows = []
    for x in e:
        b = x["base_asset"]
        assert hashlib.sha256(b.encode()).digest()[0] % 5 == 0
        assert dt.date.fromisoformat(x["T0_day"][:10]) < FORWARD_START
        rows.append({"base": b, "T0_day": x["T0_day"][:10]})
    return rows


def event(rec: dict) -> dict:
    """perp_replicate.event 去掉现货代理部分；其余逐行相同。"""
    base, t0 = rec["base"], dt.date.fromisoformat(rec["T0_day"])
    P.TOUCHED.add(base)
    d = t0 + DAY
    out = {"base": base, "t0": t0.isoformat(), "entry_day": d.isoformat()}
    firsts = {}
    for sym in (f"{base}USDT", f"1000{base}USDT", f"1000000{base}USDT"):
        fd = P.first_day(sym)
        if fd is not None:
            firsts[sym] = fd
    if not firsts:
        out["status"] = "no_perp"
        return out
    earliest = min(firsts.values())
    cands = [s for s, fd in firsts.items() if fd == earliest]
    if len(cands) > 1:
        out["status"] = "ambiguous"
        return out
    sym = cands[0]
    out.update(
        perp=sym,
        perp_first_day=earliest.isoformat(),
        perp_lag_days=(earliest - t0).days,
    )
    if earliest > d:
        out["status"] = "perp_later"
        return out
    out["status"] = "perp_at_entry"
    hmax = max(P.HOLDS)
    kl = P.daily("klines", sym, d, d + hmax * DAY)
    mk = P.daily("markPriceKlines", sym, d, d + hmax * DAY)
    if d in kl:
        out["entry_day_qv"] = kl[d]["qv"]
    for h in P.HOLDS:
        days = [d + k * DAY for k in range(h + 1)]
        tag = f"H{h}"
        if any(x not in kl or x not in mk for x in days):
            out[f"{tag}_status"] = "window_missing"
            continue
        t1 = dt.datetime.combine(d + DAY, dt.time(), P.UTC)
        t2 = dt.datetime.combine(d + (h + 1) * DAY, dt.time(), P.UTC)
        fr = P.funding(sym, t1, t2)
        if fr is None:
            out[f"{tag}_status"] = "window_missing"
            continue
        p0, p1 = kl[d]["c"], kl[days[-1]]["c"]
        liq = max(mk[x]["h"] for x in days[1:]) >= p0 * (1 + 0.9 / P.LEV)
        fund = P.LEV * sum(
            rate * mk[t.date()]["c"] / p0 for t, rate in fr if t.date() in mk
        )
        px = P.LEV * (1 - p1 / p0) - P.FEE * P.LEV
        out[f"{tag}_status"] = "ok"
        out[f"{tag}_liq"] = bool(liq)
        out[f"{tag}_funding"] = fund
        out[f"{tag}_n_funding"] = len(fr)
        out[f"{tag}_r"] = -1.0 if liq else px + fund
    return out


def boot_means(r: np.ndarray, blocks: np.ndarray, n: int = 10_000) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    groups = [r[blocks == b] for b in np.unique(blocks)]
    out = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        out[i] = np.concatenate([groups[j] for j in pick]).mean()
    return out


def describe(s: pd.DataFrame, h: int) -> dict:
    t = f"H{h}"
    r = s[f"{t}_r"].values.astype(float)
    yrs = s.t0.str[:4].values
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "median": float(np.median(r)),
        "sd": float(r.std(ddof=1)) if len(r) > 1 else None,
        "share_pos": float((r > 0).mean()),
        "share_liquidated": float(s[f"{t}_liq"].mean()),
        "funding_contrib_mean": float(s[f"{t}_funding"].mean()),
        "by_year": {
            y: {"n": int((yrs == y).sum()), "mean": float(r[yrs == y].mean())}
            for y in sorted(set(yrs))
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate1", required=True, help="记录门 1 通过的提交号")
    a = ap.parse_args()
    if OUT_EV.exists() or OUT_AN.exists():
        raise SystemExit("留出已评分过（输出已存在）；一次性评分不重跑")
    ev = frame()
    allowed = {x["base"] for x in ev}
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(event, ev))
    assert P.TOUCHED == allowed
    ok_syms = {f"{p}{b}USDT" for b in allowed for p in ("", "1000", "1000000")}
    assert P.SYMS <= ok_syms
    E = pd.DataFrame(rows)
    E.to_csv(OUT_EV, index=False)
    st = E.get("H30_status")
    s = E[st == "ok"] if st is not None else E.iloc[0:0]
    out: dict = {
        "card": "卡片_留出一次性评分_v1.md",
        "gate1_commit": a.gate1,
        "n_frame": int(len(E)),
        "status": E.status.value_counts().to_dict(),
        "H30_status": E.loc[E.status == "perp_at_entry", "H30_status"]
        .value_counts()
        .to_dict()
        if st is not None
        else {},
    }
    n = int(len(s))
    if n >= 2:
        r = s.H30_r.values.astype(float)
        blocks = pd.to_datetime(s.entry_day).dt.to_period("M").astype(str).values
        bm = boot_means(r, blocks)
        lo, hi = float(np.quantile(bm, 0.05)), float(np.quantile(bm, 0.95))
        out["main_H30_L1"] = {
            "n": n,
            "mean": float(r.mean()),
            "one_sided95_lower_block_month": lo,
            "one_sided95_upper_block_month": hi,
            "two_sided95_block_month_descriptive": [
                float(np.quantile(bm, 0.025)),
                float(np.quantile(bm, 0.975)),
            ],
            "n_blocks": int(len(np.unique(blocks))),
        }
    if n < 30:
        result = "未判定（样本不足，n<30）"
    elif out["main_H30_L1"]["one_sided95_lower_block_month"] > 0:
        result = "通过"
    elif out["main_H30_L1"]["one_sided95_upper_block_month"] < DEV_MEAN:
        result = "反证"
    else:
        result = "未判定"
    out["result"] = result
    desc: dict = {}
    if n >= 2:
        desc["H30_L1"] = describe(s, 30)
        q = s.entry_day_qv.rank(pct=True)
        desc["H30_by_entry_day_qv_tercile"] = {
            k: {"n": int(len(g)), "mean": float(g.H30_r.mean())}
            for k, g in s.assign(
                g=pd.cut(q, [0, 1 / 3, 2 / 3, 1], labels=["低", "中", "高"])
            ).groupby("g", observed=True)
        }
    s7 = E[E.get("H7_status") == "ok"] if "H7_status" in E else E.iloc[0:0]
    if len(s7) >= 2:
        desc["H7_L1"] = describe(s7, 7)
    later = E.loc[E.status == "perp_later", "perp_lag_days"]
    desc["perp_later_lag_days"] = later.describe().to_dict() if len(later) else {}
    out["descriptive"] = desc
    OUT_AN.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n")
    print(json.dumps({k: out[k] for k in ("status", "result")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

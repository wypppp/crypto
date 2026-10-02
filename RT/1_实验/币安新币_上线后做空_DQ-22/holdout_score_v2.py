#!/usr/bin/env python3
"""DQ-22 留出一次性评分 v2（卡片_留出一次性评分_v2.md；按门 1 复核的五项修改，与卡片一起冻结）。

python holdout_score_v2.py → runs/holdout_v2_events.csv、runs/holdout_v2_analysis.json、
    runs/holdout_v2_inputs_manifest.csv；每次尝试追加到 runs/holdout_attempts.csv（入库）

运行前核验（任一不满足即拒绝）：
- 已提交、无本地改动的批准记录 过程/门1_批准记录_v2.md，其中逐字含有卡片、本脚本、依赖与母表的 sha256；
- 本实验文件夹没有未提交的改动；
- runs/holdout_attempts.csv 没有任何尝试记录（修错重跑须带 --retry-approved，见卡片 §7）；
- 原子锁 runs/holdout_v2.lock 不存在（创建后不自动删除）。
相对 v1 的改动：母表哈希、起止日与唯一性核验；资金费月份按排他终点取（v1 在终点恰为月初时多要一个月文件）；
缺失原因与疑似下架单报；结果标签与优先级按卡片 §4。逐事件的入场、爆仓、资金费与费用规则不变。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import perp_replicate as P  # noqa: E402

P.RAW = HERE / "raw_holdout"
RT = HERE.parents[1]
MASTER = RT / "5_参考" / "旧债务" / "direction" / "v1.8.40" / "L_u_master.json"
MASTER_SHA = "8a26e6f7d983461ba2557f0be6333d0a26ac9c23e7ea8d98c1bf66d0ba8dd440"
CARD = HERE / "卡片_留出一次性评分_v2.md"
APPROVAL = HERE / "过程" / "门1_批准记录_v2.md"
DEPS = [
    HERE / "perp_replicate.py",
    RT / "1_实验" / "币安上市_上市后价格右尾_DQ-2" / "dq2_listing_tail.py",
    MASTER,
]
RUNS = P.RUNS
OUT_EV = RUNS / "holdout_v2_events.csv"
OUT_AN = RUNS / "holdout_v2_analysis.json"
OUT_MF = RUNS / "holdout_v2_inputs_manifest.csv"
ATTEMPTS = RUNS / "holdout_attempts.csv"
LOCK = RUNS / "holdout_v2.lock"
SEED = 20261002
DEV_MEAN = 0.139  # F123 主格点估计：固定幅度基准
T0_MIN, T0_MAX = dt.date(2021, 1, 1), dt.date(2026, 7, 31)
DAY = dt.timedelta(days=1)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=HERE, capture_output=True, text=True, check=True
    ).stdout


def preflight(retry: str | None) -> dict:
    hashes = {p.name: sha(p) for p in [CARD, Path(__file__).resolve(), *DEPS]}
    if hashes["L_u_master.json"] != MASTER_SHA:
        raise SystemExit("母表哈希不符")
    if not APPROVAL.exists():
        raise SystemExit("没有门 1 批准记录")
    git("ls-files", "--error-unmatch", str(APPROVAL))
    if git("status", "--porcelain", "--", ".").strip():
        raise SystemExit("本实验文件夹有未提交的改动")
    text = APPROVAL.read_text()
    miss = [k for k, v in hashes.items() if v not in text]
    if miss:
        raise SystemExit(f"批准记录中缺少这些文件的 sha256：{miss}")
    rows = list(csv.DictReader(ATTEMPTS.open())) if ATTEMPTS.exists() else []
    if rows:
        if not retry:
            raise SystemExit("已有尝试记录；修错重跑须按卡片 §7 带 --retry-approved")
        rp = Path(retry).resolve()
        git("ls-files", "--error-unmatch", str(rp))
        if rows[-1]["attempt_id"] not in rp.read_text():
            raise SystemExit("重跑批准记录未写明上一次尝试编号")
    for out in (OUT_EV, OUT_AN, OUT_MF):
        if out.exists():
            raise SystemExit(f"输出已存在：{out.name}")
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, dt.datetime.now(dt.timezone.utc).isoformat().encode())
    os.close(fd)
    return {"head": git("rev-parse", "HEAD").strip(), "hashes": hashes}


def attempt(row: dict) -> None:
    new = not ATTEMPTS.exists()
    with ATTEMPTS.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["attempt_id", "stage", "head", "detail"])
        if new:
            w.writeheader()
        w.writerow(row)


def frame() -> list[dict]:
    e = json.loads(MASTER.read_text())["embargo_metadata"]
    bases = [x["base_asset"] for x in e]
    assert len(e) == 55 and len(set(bases)) == 55
    rows = []
    for x in e:
        b, t0 = x["base_asset"], dt.date.fromisoformat(x["T0_day"][:10])
        assert x["kind"] == "FIRST_SPOT_LISTING"
        assert hashlib.sha256(b.encode()).digest()[0] % 5 == 0
        assert T0_MIN <= t0 <= T0_MAX
        rows.append({"base": b, "T0_day": t0.isoformat()})
    return rows


def funding(sym: str, t1: dt.datetime, t2: dt.datetime) -> list[tuple] | None:
    """[t1, t2) 内的结算；月份只取到 t2 前一刻所在的月（v1 在 t2 为月初时多要一个月）。"""
    out = []
    last = t2 - dt.timedelta(milliseconds=1)
    y, m = t1.year, t1.month
    while (y, m) <= (last.year, last.month):
        data = P.fetch(
            f"monthly/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"
        )
        if data is None:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt = z.read(z.namelist()[0]).decode()
        for row in csv.reader(io.StringIO(txt)):
            if not row or not row[0].isdigit():
                continue
            t = dt.datetime.fromtimestamp(int(row[0]) / 1000, P.UTC)
            if t1 <= t < t2:
                out.append((t, float(row[2])))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def event(rec: dict) -> dict:
    """入场、爆仓、资金费、费用与 perp_replicate.event 相同；另记缺失原因。"""
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
    return window(out, sym, d)


def window(out: dict, sym: str, d: dt.date) -> dict:
    """持有窗口内的回收：入场、爆仓、资金费、费用与 perp_replicate.event 相同；另记缺失原因。"""
    hmax = max(P.HOLDS)
    kl = P.daily("klines", sym, d, d + hmax * DAY)
    mk = P.daily("markPriceKlines", sym, d, d + hmax * DAY)
    if d in kl:
        out["entry_day_qv"] = kl[d]["qv"]
    for h in P.HOLDS:
        days = [d + k * DAY for k in range(h + 1)]
        tag = f"H{h}"
        miss_k = [x for x in days if x not in kl]
        miss_m = [x for x in days if x not in mk]
        if miss_k or miss_m:
            out[f"{tag}_status"] = "window_missing"
            out[f"{tag}_miss_klines"] = len(miss_k)
            out[f"{tag}_miss_mark"] = len(miss_m)
            present = [x for x in days if x in kl]
            # 疑似下架：日线在窗口内中止、之后再无数据
            out[f"{tag}_ended_in_window"] = bool(present) and max(present) < days[-1]
            continue
        t1 = dt.datetime.combine(d + DAY, dt.time(), P.UTC)
        t2 = dt.datetime.combine(d + (h + 1) * DAY, dt.time(), P.UTC)
        fr = funding(sym, t1, t2)
        if fr is None:
            out[f"{tag}_status"] = "window_missing"
            out[f"{tag}_miss_funding_file"] = True
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


def judge(n: int, lo: float | None, hi: float | None) -> dict:
    """卡片 §4：先看样本是否足够，再看“通过”，再看“开发期效应量被排除”；两个标志都单报。"""
    if n < 30:
        label = "未判定（样本不足）"
    elif lo > 0:
        label = "通过"
    elif hi < DEV_MEAN:
        label = "开发期效应量被排除"
    else:
        label = "未判定"
    return {
        "label": label,
        "flag_lower_gt_0": None if lo is None else bool(lo > 0),
        "flag_dev_effect_excluded": None if hi is None else bool(hi < DEV_MEAN),
    }


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


def missing_reasons(pe: pd.DataFrame, tag: str) -> dict:
    def col(name: str, default: object) -> pd.Series:
        c = f"{tag}_{name}"
        return pe[c].fillna(default) if c in pe else pd.Series(default, index=pe.index)

    gap = (col("miss_klines", 0) > 0) | (col("miss_mark", 0) > 0)
    return {
        "klines_or_mark_gap": int(gap.sum()),
        "suspected_delisting_ended_in_window": int(
            col("ended_in_window", False).astype(bool).sum()
        ),
        "funding_file_missing": int(col("miss_funding_file", False).astype(bool).sum()),
    }


def manifest() -> None:
    with OUT_MF.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "sha256", "bytes"])
        for p in sorted(P.RAW.rglob("*")):
            if p.is_file():
                w.writerow([p.relative_to(P.RAW), sha(p), p.stat().st_size])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry-approved", default=None)
    a = ap.parse_args()
    pre = preflight(a.retry_approved)
    aid = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    attempt(
        {
            "attempt_id": aid,
            "stage": "started",
            "head": pre["head"],
            "detail": json.dumps(pre["hashes"]),
        }
    )
    ev = frame()
    allowed = {x["base"] for x in ev}
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(event, ev))
    assert P.TOUCHED == allowed
    ok_syms = {f"{p}{b}USDT" for b in allowed for p in ("", "1000", "1000000")}
    assert P.SYMS <= ok_syms
    manifest()
    E = pd.DataFrame(rows)
    E.to_csv(OUT_EV, index=False)
    st = E.get("H30_status")
    s = E[st == "ok"] if st is not None else E.iloc[0:0]
    pe = E[E.status == "perp_at_entry"]
    out: dict = {
        "card": CARD.name,
        "attempt_id": aid,
        "head": pre["head"],
        "hashes": pre["hashes"],
        "n_frame": int(len(E)),
        "status": E.status.value_counts().to_dict(),
        "H30_status": pe["H30_status"].value_counts().to_dict() if len(pe) else {},
        "H30_window_missing_reasons": missing_reasons(pe, "H30"),
    }
    n = int(len(s))
    lo = hi = None
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
    out["result"] = judge(n, lo, hi)
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
    attempt(
        {
            "attempt_id": aid,
            "stage": "finished",
            "head": pre["head"],
            "detail": json.dumps(out["result"], ensure_ascii=False),
        }
    )
    print(json.dumps({"status": out["status"], **out["result"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

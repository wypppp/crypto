"""生成代码审计用的小型开发期样本（10-02，执行模型；只生成一次，结果入库）。

两份样本：
1. perp/：永续逐事件回收与成本模型（`perp_replicate.py:event`：入场、爆仓、资金费、手续费）。
   4 个开发期事件（ARB、TIA、AEVO、FLOKI，2023～2024），把它们用到的 data.binance.vision
   公开归档原文件（逐文件 CHECKSUM 已在原缓存时核对）与当时的 S3 目录列表存下来，审计方离线运行。
   预期输出取自冻结结果 `runs/events.csv`（不是重新计算的）；本脚本另外离线重跑一遍核对一致。
2. valuation/：pump 曲线 / 池卖出估值（`analyze_dq8a.py:sell_ratio` 与 `buy_tok`）。
   A 周（06-01～07）检查点面板里按固定种子抽 16 个状态，预期输出由冻结函数计算，
   并与本脚本里独立写的逐行标量实现核对。
不含 55 条留出（逐条断言哈希规则）、封存周 06-15～07-12、DQ-22 前向窗口的任何数据。
"""

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RT = H.parent.parent
DQ22 = RT / "1_实验" / "币安新币_上线后做空_DQ-22"
DQ8A = RT / "1_实验" / "pump曲线_检查点动态决策_DQ-8A"
EVENTS = ("ARB", "TIA", "AEVO", "FLOKI")
FIELDS = ("status", "liq", "funding", "n_funding", "r_px", "r")


def build_perp() -> None:
    sys.path.insert(0, str(DQ22))
    import perp_replicate as P

    out = H / "perp"
    arch = out / "archive"
    used, listing = set(), {}
    fetch0, keys0 = P.fetch, P.s3_keys

    def fetch(rel: str):
        data = fetch0(rel)
        if data is not None:
            used.add(rel)
        return data

    def s3_keys(prefix: str):
        k = keys0(prefix)
        listing[prefix] = k
        return k

    def no_net(url: str):
        raise RuntimeError(f"样本生成不应下载归档文件：{url}")

    get0 = P.get
    P.fetch, P.s3_keys = fetch, s3_keys
    # s3_keys 本身用 get 列目录：列目录允许联网，取归档文件不允许（必须来自原缓存）
    P.get = lambda url: get0(url) if "?delimiter=" in url else no_net(url)
    P.D.daily_rows = lambda sym, d1, d2: {}  # 现货对照只作描述，样本不含

    ev = pd.read_csv(DQ22 / "runs" / "events.csv").set_index("base")
    rows = []
    for b in EVENTS:
        assert hashlib.sha256(b.encode()).digest()[0] % 5 != 0, b  # 非留出
        e = ev.loc[b]
        rec = {"base": b, "symbol": e["spot"], "T0_day": e["t0"]}
        got = P.event(rec)
        for h in (30, 7):
            for f in FIELDS:
                k = f"H{h}_{f}"
                exp = e[k]
                g = got.get(k)
                if f == "status":
                    assert g == exp, (b, k, g, exp)
                elif f == "liq":
                    assert bool(g) == (str(exp) == "True"), (b, k, g, exp)
                else:
                    assert abs(float(g) - float(exp)) <= 1e-12, (b, k, g, exp)
        row = {"base": b, "symbol": e["spot"], "T0_day": e["t0"], "perp": e["perp"]}
        row.update({f"H{h}_{f}": e[f"H{h}_{f}"] for h in (30, 7) for f in FIELDS})
        rows.append(row)
    if out.exists():
        shutil.rmtree(out)
    for rel in sorted(used):
        dst = arch / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DQ22 / "raw" / rel, dst)
    (out / "s3_listing.json").write_text(json.dumps(listing, indent=1, sort_keys=True))
    with open(out / "expected.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(out / "archive_manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "sha256", "bytes"])
        for rel in sorted(used):
            b = (arch / rel).read_bytes()
            w.writerow([rel, hashlib.sha256(b).hexdigest(), len(b)])
    print("perp", len(rows), "events,", len(used), "archive files")


def sell_scalar(x, y, xr, v, fee, tok, feeb) -> float:
    """独立的逐行实现（不调用被审计代码），用来核对冻结函数。"""
    if v == 0:
        if not y > tok:
            return float("nan")
        c = (x * y / (y - tok) - x) * (1 - fee / 1e4)
        cap = (0.0 if xr != xr else xr) + 0.5 * (1 - feeb / 1e4)
        return min(c, cap) / 0.5
    return (x - x * y / (y + tok)) * (1 - fee / 1e4) / 0.5


def build_valuation() -> None:
    sys.path.insert(0, str(DQ8A))
    import analyze_dq8a as A

    cols = ["mint", "iv", "l_x", "l_y", "l_xr", "l_venue", "l_fee_bps"]
    p = pd.read_csv(DQ8A / "raw" / "F3_devA.csv", usecols=cols, low_memory=False)
    e0 = p[p.iv == 0].set_index("mint")
    rng = np.random.default_rng(20261002)
    later = p[p.iv > 0]
    pick = pd.concat(
        [
            later[later.l_venue == 0].iloc[
                rng.choice(int((later.l_venue == 0).sum()), 10, replace=False)
            ],
            later[later.l_venue == 1].iloc[
                rng.choice(int((later.l_venue == 1).sum()), 6, replace=False)
            ],
        ]
    )
    rows = []
    for r in pick.itertuples(index=False):
        s0 = e0.loc[r.mint]
        tok = float(A.buy_tok(s0.l_x, s0.l_y, s0.l_fee_bps))
        args = (r.l_x, r.l_y, r.l_xr, r.l_venue, r.l_fee_bps, tok, s0.l_fee_bps)
        got = float(A.sell_ratio(*args))
        ind = sell_scalar(*(float(a) for a in args))
        assert (got != got and ind != ind) or abs(got - ind) <= 1e-12 * max(
            1, abs(ind)
        ), (r.mint, got, ind)
        rows.append(
            {
                "mint": r.mint,
                "iv": r.iv,
                "entry_x": s0.l_x,
                "entry_y": s0.l_y,
                "entry_fee_bps": s0.l_fee_bps,
                "x": r.l_x,
                "y": r.l_y,
                "xr": r.l_xr,
                "venue": r.l_venue,
                "fee_bps": r.l_fee_bps,
                "expected_tok": repr(tok),
                "expected_sell_ratio": repr(got),
            }
        )
    out = H / "valuation"
    out.mkdir(exist_ok=True)
    with open(out / "expected.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("valuation", len(rows), "rows")


if __name__ == "__main__":
    build_perp()
    build_valuation()

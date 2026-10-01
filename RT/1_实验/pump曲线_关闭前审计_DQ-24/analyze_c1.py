#!/usr/bin/env python3
"""DQ-24（C1）分析：读 raw/dune/C1_W*.csv.gz，按卡片 §4 的读法判定。

python analyze_c1.py → runs/c1_analysis.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "dune"
RUNS = H / "runs"
SEED = 20261001
X_MIN, DEV_MAX = 59.1866, 11
RULES = ("rb50", "b50", "x50_1h")


def block_ci(r: np.ndarray, blocks: np.ndarray, n: int = 10_000) -> list[float]:
    rng = np.random.default_rng(SEED)
    groups = [r[blocks == b] for b in np.unique(blocks)]
    sums = np.array([g.sum() for g in groups])
    cnts = np.array([len(g) for g in groups])
    k = len(groups)
    means = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, k, k)
        means[i] = sums[pick].sum() / cnts[pick].sum()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def desc(x: pd.Series) -> dict:
    v = np.sort(x.values.astype(float))[::-1]
    return {
        "n": int(len(v)),
        "mean": float(v.mean()) if len(v) else None,
        "median": float(np.median(v)) if len(v) else None,
        "drop_top1": float(v[1:].mean()) if len(v) > 1 else None,
        "drop_top3": float(v[3:].mean()) if len(v) > 3 else None,
    }


def load() -> tuple[pd.DataFrame, dict]:
    frames, summ = [], {}
    for f in sorted(RAW.glob("C1_W*.csv.gz")):
        w = f.name[4:12]
        d = pd.read_csv(f)
        s = d[d.mint == "__SUMMARY__"].iloc[0]
        summ[w] = {"n_created_sol": int(s.cday), "n_non_sol": int(s["flags"])}
        d = d[d.mint != "__SUMMARY__"].copy()
        d["week"] = w
        d["block"] = w + "_" + d.cday.astype(int).astype(str)
        frames.append(d)
    return pd.concat(frames, ignore_index=True), summ


def main() -> None:
    D, summ = load()
    fl = D["flags"].astype(int)
    D["main"] = (D.entry_x_sol >= X_MIN) & (D.dev_prior_launches <= DEV_MAX)
    M = D[D.main]
    out: dict = {
        "weeks": sorted(D.week.unique()),
        "n_pool": int(len(D)),
        "n_main": int(len(M)),
    }
    cells = {}
    for rule in RULES:
        for k in ("a", "b"):
            col = f"{rule}_{k}"
            r = M[col].values.astype(float)
            cells[f"main_{col}"] = {
                **desc(M[col]),
                "ci95_block_day": block_ci(r, M.block.values),
            }
    out["cells_main"] = cells
    p = cells["main_rb50_a"], cells["main_rb50_b"]
    if p[0]["ci95_block_day"][0] > 1:
        reading = "1_复活候选"
    elif p[1]["ci95_block_day"][1] < 1:
        reading = "2_支持关闭（须先过第二模型门 3）"
    else:
        reading = "3_未判定"
    out["reading"] = reading
    weekly = {}
    for w, g in D.groupby("week"):
        m = g[g.main]
        fw = g["flags"].astype(int)
        weekly[w] = {
            **summ[w],
            "n_pool": int(len(g)),
            "n_main": int(len(m)),
            "grad_share_pool": float((fw & 4).gt(0).mean()),
            "fee_imputed_share": float((fw & 2048).gt(0).mean()),
            "pool_fullbuy": {
                c: float(g[c].mean()) for c in ("b50_a", "b50_b", "rb50_a", "rb50_b")
            },
            "main": {
                c: float(m[c].mean())
                for c in ("rb50_a", "rb50_b", "b50_a", "b50_b", "x50_1h_a", "x50_1h_b")
            },
            "main_drop_top1_x50_1h_b": desc(m.x50_1h_b)["drop_top1"],
        }
    out["weekly"] = weekly
    out["pool_fullbuy_all"] = {
        c: desc(D[c]) for c in ("b50_a", "b50_b", "rb50_a", "rb50_b")
    }
    win = M[M.ms_30d >= 10]
    out["winners_main"] = {
        "n": int(len(win)),
        "rb50_b": float(win.rb50_b.mean()) if len(win) else None,
        "b50_b": float(win.b50_b.mean()) if len(win) else None,
        "rb_state": win.rb_state.value_counts().to_dict(),
    }
    out["rb_state_main"] = M.rb_state.value_counts().to_dict()
    out["rebuy_effect_main"] = {
        "rebought_n": int((M.rb_state == 2).sum()),
        "rebought_mean_gain_b": float((M.rb50_b - M.b50_b)[M.rb_state == 2].mean()),
        "rebought_mean_gain_a": float((M.rb50_a - M.b50_a)[M.rb_state == 2].mean()),
    }
    out["fee_imputed_share_all"] = float((fl & 2048).gt(0).mean())
    RUNS.mkdir(exist_ok=True)
    (RUNS / "c1_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(
        json.dumps(
            {k: out[k] for k in ("n_pool", "n_main", "reading")}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()

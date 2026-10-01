#!/usr/bin/env python3
"""DQ-26 排名查询的技术核对（不看收益，只核管线）。

python check_rank.py REG_20260601 → runs/check_REG_20260601.json
  ① t3：与 DQ-21 S1 A 周文件中同日创建的币逐币比较（S0 v1.3 定义）；
  ② 曲线现金闭合：未迁移币 曲线买入 − 卖出 ＝ 最后 real_sol_reserves（同 WM C1）；
  ③ 规模：币数、合格钱包数、有 t3（≤300 秒）的币占比。
python check_rank.py SMOKE_20260803 → 只做 ②③（新时期无 S1 对照）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
S1 = H.parent / "pump曲线_资金关系可构造性_DQ-21" / "raw" / "s1" / "S1_A_dual.csv.gz"


def main() -> None:
    label = sys.argv[1]
    c = pd.read_csv(H / "raw" / "dune" / f"RANK_C_{label}.csv.gz")
    w = pd.read_csv(H / "raw" / "dune" / f"RANK_W_{label}.csv.gz")
    out: dict = {
        "label": label,
        "n_coins": int(len(c)),
        "n_coins_t3_le300": int((c.t3_s <= 300).sum()),
        "share_t3_le300": round(float((c.t3_s <= 300).mean()), 4),
        "n_migrated": int((c.n_amm > 0).sum()),
        "n_wallets_eligible": int(len(w)),
    }
    un = c[(c.n_amm == 0) & (c.v_end == 0) & c.xr_end.notna()]
    err = (un.curve_in - un.curve_out - un.xr_end).abs() / un.curve_in.clip(lower=1e-9)
    out["closure_unmigrated"] = {
        "n": int(len(un)),
        "rel_err_median": float(err.median()),
        "rel_err_p99": float(err.quantile(0.99)),
        "n_gt_1pct": int((err > 0.01).sum()),
    }
    if label.startswith("REG"):
        s1 = pd.read_csv(S1, usecols=["mint", "created_at", "t3_s"])
        s1 = s1[
            s1.created_at.str[:10]
            == label[-8:-4] + "-" + label[-4:-2] + "-" + label[-2:]
        ]
        m = s1.merge(c[["mint", "t3_s"]], on="mint", how="left", suffixes=("_s1", ""))
        out["t3_vs_s1"] = {
            "n_s1": int(len(s1)),
            "found": int(m.t3_s.notna().sum()),
            "equal": int(
                ((m.t3_s == m.t3_s_s1) | (m.t3_s.isna() & m.t3_s_s1.isna())).sum()
            ),
            "abs_diff_max": float(np.nanmax((m.t3_s - m.t3_s_s1).abs()))
            if len(m)
            else None,
            "diff_examples": m[
                (m.t3_s != m.t3_s_s1) & ~(m.t3_s.isna() & m.t3_s_s1.isna())
            ]
            .head(5)
            .to_dict("records"),
        }
    (H / "runs").mkdir(exist_ok=True)
    (H / "runs" / f"check_{label}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

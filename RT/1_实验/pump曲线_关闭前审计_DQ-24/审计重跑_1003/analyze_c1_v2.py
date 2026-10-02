#!/usr/bin/env python3
"""C1 审计重跑 v2 的评分：原 analyze_c1.py 逐字调用，只把输入换成 raw/dune/C1_W*.csv.gz（v2 SQL 的结果）、输出换到 runs/。
另报新旧对照：python analyze_c1_v2.py → runs/c1_analysis.json（与原版同格式）、runs/c1_v1_v2_compare.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import analyze_c1 as A  # noqa: E402

V1_RAW = A.RAW
A.RAW, A.RUNS = HERE / "raw" / "dune", HERE / "runs"


def load(raw: Path) -> pd.DataFrame:
    fs = sorted(raw.glob("C1_W*.csv.gz"))
    d = pd.concat(
        [pd.read_csv(f).assign(week=f.name[4:12]) for f in fs], ignore_index=True
    )
    return d[d.mint != "__SUMMARY__"]


def main() -> None:
    A.main()
    o, n = load(V1_RAW), load(A.RAW)
    m = o.merge(
        n, on=["week", "mint"], how="outer", suffixes=("_v1", "_v2"), indicator=True
    )
    fl = n["flags"].astype(int)
    new = m[m._merge == "right_only"]
    newfl = new.flags_v2.astype(int)
    both = m[m._merge == "both"]
    main_v2 = (n.entry_x_sol >= A.X_MIN) & (n.dev_prior_launches <= A.DEV_MAX)
    out = {
        "rows_v1": int(len(o)),
        "rows_v2": int(len(n)),
        "only_v1": int((m._merge == "left_only").sum()),
        "only_v2": int(len(new)),
        "only_v2_flag4096_post_entry_anomaly": int((newfl & 4096 > 0).sum()),
        "only_v2_flag128_mayhem": int((newfl & 128 > 0).sum()),
        "v2_flag4096_rows": int((fl & 4096 > 0).sum()),
        "v2_flag4096_main": int(((fl & 4096 > 0) & main_v2).sum()),
        "v2_flag4096_main_ms30d_ge10": int(
            ((fl & 4096 > 0) & main_v2 & (n.ms_30d >= 10)).sum()
        ),
        "v2_flag4096_main_mean_rb50_b": float(
            n[(fl & 4096 > 0) & main_v2].rb50_b.mean()
        )
        if ((fl & 4096 > 0) & main_v2).any()
        else None,
        "v2_flag8192_rows_completed_but_last_state_curve": int((fl & 8192 > 0).sum()),
        "both_rows_rb50_b_changed_gt_1e6": int(
            ((both.rb50_b_v1 - both.rb50_b_v2).abs() > 1e-6).sum()
        ),
        "both_rows_b50_b_changed_gt_1e6": int(
            ((both.b50_b_v1 - both.b50_b_v2).abs() > 1e-6).sum()
        ),
        "both_rows_entry_x_changed": int(
            ((both.entry_x_sol_v1 - both.entry_x_sol_v2).abs() > 1e-3).sum()
        ),
        "by_week_flag4096": n[fl & 4096 > 0].groupby("week").size().to_dict(),
    }
    v1 = json.loads((HERE.parent / "runs" / "c1_analysis.json").read_text())
    v2 = json.loads((A.RUNS / "c1_analysis.json").read_text())
    out["cells_main"] = {
        k: {"v1": [round(v1["cells_main"][k]["mean"], 4), [round(x, 4) for x in v1["cells_main"][k]["ci95_block_day"]]],
            "v2": [round(v2["cells_main"][k]["mean"], 4), [round(x, 4) for x in v2["cells_main"][k]["ci95_block_day"]]]}
        for k in v1["cells_main"]
    }  # fmt: skip
    out["reading"] = {"v1": v1["reading"], "v2": v2["reading"]}
    out["n_main"] = {"v1": v1["n_main"], "v2": v2["n_main"]}
    out["n_pool"] = {"v1": v1["n_pool"], "v2": v2["n_pool"]}
    out["pool_fullbuy_all_mean"] = {
        c: {
            "v1": round(v1["pool_fullbuy_all"][c]["mean"], 4),
            "v2": round(v2["pool_fullbuy_all"][c]["mean"], 4),
        }
        for c in v1["pool_fullbuy_all"]
    }
    (A.RUNS / "c1_v1_v2_compare.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

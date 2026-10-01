"""WM 集中度两个口径对齐（10-01，用户指令；看过结果后的复算，只作口径说明）。

在 DQ-21 文件夹下运行：python 过程/wm_concentration_1001.py → 过程/wm_concentration_1001.json
口径①（冻结诊断，analyze_wm.diagnostics）：每格最大单钱包含持仓净额 max_net_w×w 的最大 10 个之和 ÷ 组含持仓净额。
口径②（第二模型）：按格现金净额 w×(OUT−IN) 排序，最大 10 格之和 ÷ 组现金净额。
另报：去掉口径②最大 10 格后的按金额加权与按币等权现金回收。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import analyze_s1_dual as m  # noqa: E402
import analyze_wm as W  # noqa: E402

GROUPS = ["creator", "sameslot", "open10", "pre", "e5", "e30"]


def main() -> None:
    _, s1 = m.load()
    g, coin = W.load(["A", "B"], W.main_sample(s1))
    res = {}
    for grp in GROUPS:
        sub = g[g.grp == grp].reset_index(drop=True)
        w = 1 / sub.p0
        cash = w * (sub.out_sol - sub.in_sol)
        mr = w * (sub.out_sol + sub.held_sol - sub.in_sol)
        top = cash.nlargest(10).index
        keep = ~sub.index.isin(top)
        k, wk = sub[keep], w[keep]
        r = sub.out_sol / sub.in_sol.where(sub.in_sol > 0)
        ok = keep & r.notna()
        res[grp] = {
            "n_cells": len(sub),
            "cash_net": round(float(cash.sum())),
            "mr_net": round(float(mr.sum())),
            "frozen_top10_maxwallet_over_mr": round(
                float((sub.max_net_w * w).nlargest(10).sum() / mr.sum()), 4
            ),
            "top10_cash_cells_over_cash": round(
                float(cash.nlargest(10).sum() / cash.sum()), 4
            ),
            "top10_mr_cells_over_mr": round(float(mr.nlargest(10).sum() / mr.sum()), 4),
            "cash_rr_money_ex_top10": round(
                float((wk * k.out_sol).sum() / (wk * k.in_sol).sum()), 4
            ),
            "cash_rr_coin_eq": round(
                float((r * w)[r.notna()].sum() / w[r.notna()].sum()), 4
            ),
            "cash_rr_coin_eq_ex_top10": round(
                float((r * w)[ok].sum() / w[ok].sum()), 4
            ),
        }
    out = HERE / "过程" / "wm_concentration_1001.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res["e5"], indent=1))


if __name__ == "__main__":
    main()

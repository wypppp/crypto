"""审核核算：S1 单日（2026-06-01）固定退出基础回收为何低于 1。0 credits，只读已取回的两份 S1 结果。

python 基础回收原因分解.py → checks/基础回收原因分解.json
- 同一批 695 个冻结币，两种曲线卖出估值：B = 旧 SQL（我方仓位留在曲线里，立即往返精确）；A = F116“修正”（卖进不含我方仓位的状态，
  重复计入自身冲击）。有他人成交的路径上真值介于两者之间，A <= B 逐币成立。
- 主样本：适用、排除 R0 已看币；权重：420 秒病例超集 1，其他 50（冻结 2% 子队列）；比率均值 = sum(w*r)/sum(w)。
- 分解（曲线入场）：mid = sqrt(A*B) 近似按中间价估的退出价值；漂移 = mid / ((1-f)^2 * 入场冲击因子)。
- 预言机上限：事后剔除全部回收 <0.5 的币后的均值；E_needed：非赢家均值不变时，≥2 倍币要富集多少倍才能到 1.03。
单日数据，只作机制诊断，不是 A/B 结论。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
S1 = H.parents[1] / "1_实验" / "pump曲线_资金关系可构造性_DQ-21" / "raw" / "s1"
RULES = [f"ret_{d}_{h}" for d in ("d5", "d30", "d120") for h in ("30s", "2m", "10m", "1h")] + \
        [f"b50_ret_{d}" for d in ("d5", "d30", "d120")]


def main():
    O = pd.read_csv(S1 / "S1_SMOKE_20260601.csv.gz")
    N = pd.read_csv(S1 / "S1_SMOKE_20260601_corrected.csv.gz")
    D = O.merge(N[["mint"] + RULES], on="mint", suffixes=("_B", "_A"))
    D = D[(D.eligible == True) & (D.r0_seen != True)].copy()  # noqa: E712
    D["w"] = np.where(D.tail420_candidate == True, 1.0, 50.0)  # noqa: E712
    f = D.e5_fee_bps / 1e4
    fee2 = (1 - f) ** 2
    imp = D.e5_x / (D.e5_x + 0.5 * (1 - f))

    def wm(s, m=None):
        m = s.notna() if m is None else (m & s.notna())
        return float((s[m] * D.w[m]).sum() / D.w[m].sum())

    out = {"n_rows": len(D), "sum_w": float(D.w.sum()), "fee_bps_mean": wm(D.e5_fee_bps),
           "fee_drag_roundtrip": 1 - wm(fee2), "entry_impact_0p5sol": 1 - wm(imp), "rules": {}}
    for r in RULES:
        a, b = D[f"{r}_A"], D[f"{r}_B"]
        rec = {"A": wm(a), "B": wm(b), "loss_share_A": wm((a < 1).astype(float))}
        if not r.startswith("b50"):
            rec["drift_mean"] = wm(np.sqrt(a * b) / (fee2 * imp))
        for cv, s in (("A", a), ("B", b)):
            m = s.notna()
            rec[f"oracle_drop_lt0p5_{cv}"] = wm(s, m & (s >= 0.5))
            hi = m & (s >= 2)
            sh = float(D.w[hi].sum() / D.w[m].sum())
            mh, ml = wm(s, hi), wm(s, m & (s < 2))
            rec[f"share_ge2x_{cv}"] = sh
            rec[f"E_needed_1p03_{cv}"] = ((1.03 - ml) / (mh - ml)) / sh
        out["rules"][r] = rec
    r = D.ret_d5_1h_A
    bands = pd.cut(r, [-1, 0.25, 0.5, 0.9, 1.1, 2, 10, 1e9], labels=["<0.25", "0.25-0.5", "0.5-0.9", "0.9-1.1", "1.1-2", "2-10", ">=10"])
    out["d5_1h_A_bands"] = {str(k): {"share": float(D.w[bands == k].sum() / D.w.sum()),
                                     "contrib_to_mean_minus_1": float(((r - 1) * D.w)[bands == k].sum() / D.w.sum())}
                            for k in bands.cat.categories}
    (H / "checks" / "基础回收原因分解.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for k, v in out["rules"].items():
        print(k, {kk: round(vv, 3) for kk, vv in v.items()})


if __name__ == "__main__":
    main()

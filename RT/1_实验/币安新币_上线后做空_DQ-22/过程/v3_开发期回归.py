#!/usr/bin/env python3
"""留出评分 v3 的开发期回归（10-02）：holdout_score_v3.window 在开发期 145 条入场日已有永续的事件上，
与代码审计重跑的 F123 v2 口径结果（runs/audit1003/perp_b/events.csv，第 9＋13 处）逐项比较；只读开发期缓存 raw/，不碰留出。
python 过程/v3_开发期回归.py → 过程/v3_开发期回归_1002.txt
"""

import datetime as dt
import hashlib
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import holdout_score_v3 as H  # noqa: E402

H.P.RAW = HERE / "raw"  # 开发期缓存；导入时被设成 raw_holdout，这里改回
ref = pd.read_csv(HERE / "runs" / "audit1003" / "perp_b" / "events.csv")
ev = ref[ref.status == "perp_at_entry"]
n_cmp, diffs = 0, []
for r in ev.itertuples():
    out = H.window({}, r.perp, dt.date.fromisoformat(r.entry_day))
    for h in (30, 7):
        for k in ("status", "liq", "r"):
            col = f"H{h}_{k}"
            a, b = out.get(col), getattr(r, col)
            n_cmp += 1
            same = (
                (pd.isna(a) and pd.isna(b))
                if (a is None or pd.isna(b))
                else (
                    abs(float(a) - float(b)) < 1e-12 if k == "r" else str(a) == str(b)
                )
            )
            if not same:
                diffs.append((r.base, col, a, b))
lines = [
    f"holdout_score_v3.py sha256 {hashlib.sha256((HERE / 'holdout_score_v3.py').read_bytes()).hexdigest()}",
    f"perp_v2.py sha256 {hashlib.sha256((HERE / 'perp_v2.py').read_bytes()).hexdigest()}",
    f"对照 runs/audit1003/perp_b/events.csv sha256 {hashlib.sha256((HERE / 'runs/audit1003/perp_b/events.csv').read_bytes()).hexdigest()}",
    f"开发期入场日已有永续的事件 {len(ev)} 比较项 {n_cmp} 差异 {len(diffs)}",
    *[f"  差异 {d}" for d in diffs[:20]],
    f"DEV_MEAN {H.DEV_MEAN}",
    f"judge (33, 0.01, 0.12) {H.judge(33, 0.01, 0.12)}",
    f"judge (33, -0.1, 0.12) {H.judge(33, -0.1, 0.12)}",
    f"judge (33, -0.1, 0.13) {H.judge(33, -0.1, 0.13)}",
    f"触及留出币名? {bool(H.P.TOUCHED)}；raw_holdout 存在? {(HERE / 'raw_holdout').exists()}",
]
try:
    H.preflight(None)
    lines.append("preflight 通过（不应发生）")
except (SystemExit, FileNotFoundError) as e:
    lines.append(f"preflight 拒绝: {e}")
lines.append(f"锁文件存在? {H.LOCK.exists()}")
(HERE / "过程" / "v3_开发期回归_1002.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))

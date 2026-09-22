"""H1 S1 result package (spec §4) from the Dune S1 output. Development data (A week); not a confirmation.

Usage: .venv/bin/python RT/case_timing/h1_s1_analyze.py [RT/case_timing/raw/dune/H1_S1_A.csv]
Net recovery = recovery - 0.004 (the old model's fixed deduction; it does not cover priority fees/MEV/failures).
Main delay 120 s; 30 s / 300 s are sensitivity rows, all reported."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).parent
path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "raw" / "dune" / "H1_S1_A.csv"
res = pd.read_csv(path)
ev = pd.read_csv(HERE / "h1_events_A.csv")
df = res.merge(ev[["mint", "cday", "is_seed", "is_mayhem", "in_F2_pool", "signal_venue", "signal_buy_lamports", "age_h"]], on="mint", how="left")
df["net"] = df.recovery - 0.004
df["pnl_sol"] = 0.5 * (df.net - 1)
out = []
P = out.append

P(f"# H1 S1 结果包（{path.name}）\n")
P(f"事件 {df.mint.nunique()} 个 × 延迟 {sorted(df.d.unique())}；S0 事件清单 {len(ev)} 个。缺少 S1 行的事件：{len(set(ev.mint) - set(df.mint))}。\n")

# data-quality gates first
dq = df.groupby("d").agg(n=("mint", "size"), exit_value_missing=("exit_value_missing", "sum"), null_sm_rows=("n_null_sm", "sum"),
                         ts_regress_rows=("n_ts_regress", "sum"), curve_cut_risk=("curve_cut_risk", "sum"),
                         extra_fee_nonzero=("max_extra_fee_bps", lambda s: int((s.fillna(0) > 0).sum())))
P("## 数据质量\n\n" + dq.to_markdown() + "\n")

rng = np.random.default_rng(20260921)
def boot(x, n=20000):
    x = np.asarray(x); idx = rng.integers(0, len(x), (n, len(x)))
    m = x[idx].mean(1); return np.percentile(m, [5, 50, 95])

rows = []
for d, g in df.groupby("d"):
    lo, mid, hi = boot(g.net)
    srt = g.net.sort_values(ascending=False)
    rows.append(dict(delay_s=d, n=len(g), mean_net=g.net.mean(), boot_p5=lo, boot_p95=hi, median=g.net.median(),
                     share_gt1=(g.net > 1).mean(), share_lt05=(g.net < 0.5).mean(),
                     mean_ex_seeds=g[~g.is_seed].net.mean(), mean_ex_top1=srt.iloc[1:].mean(), mean_ex_top3=srt.iloc[3:].mean(),
                     top5_share_of_gains=(g.pnl_sol.clip(lower=0).nlargest(5).sum() / max(g.pnl_sol.clip(lower=0).sum(), 1e-12)),
                     sum_pnl_sol=g.pnl_sol.sum(), median_hold_h=g.hold_h.median()))
P("## 净回收（回收 − 0.004；每笔 0.5 SOL）\n\n" + pd.DataFrame(rows).round(4).to_markdown(index=False) + "\n")
P("`boot_p5/p95` 为事件层面自助法均值的 5/95 分位（事件视为独立，忽略同日相关，偏乐观）。\n")

m = df[df.d == 120].copy()
P("## 主延迟 120 s 的分解\n")
P("退出方式：" + str(m.exit_kind.value_counts().to_dict()) + "\n")
for col in ["signal_venue", "is_mayhem", "in_F2_pool", "cday"]:
    t = m.groupby(col).agg(n=("net", "size"), mean_net=("net", "mean"), median=("net", "median"), share_gt1=("net", lambda s: (s > 1).mean()))
    P(f"\n按 `{col}`：\n\n" + t.round(4).to_markdown() + "\n")
m["buy_bucket"] = pd.cut(m.signal_buy_lamports / 1e9, [4, 5, 8, 15, 1e9], right=False)
t = m.groupby("buy_bucket", observed=True).agg(n=("net", "size"), mean_net=("net", "mean"), share_gt1=("net", lambda s: (s > 1).mean()))
P("\n按触发买入额（SOL）：\n\n" + t.round(4).to_markdown() + "\n")
top = m.sort_values("pnl_sol", ascending=False).head(10)[["mint", "cday", "is_seed", "net", "pnl_sol", "exit_kind", "hold_h", "runmax_at_exit", "max_pm_30d"]]
P("\n贡献最大的 10 个（120 s）：\n\n" + top.round(3).to_markdown(index=False) + "\n")

# capital: concurrent open positions at 120 s
iv = pd.DataFrame({"t0": pd.to_datetime(m.t_entry, utc=True), "t1": pd.to_datetime(m.exit_ts, utc=True)})
evts = pd.concat([pd.DataFrame({"t": iv.t0, "k": 1}), pd.DataFrame({"t": iv.t1, "k": -1})]).sort_values(["t", "k"])
conc = evts.k.cumsum()
P(f"\n资金占用（120 s）：同时持仓最多 {int(conc.max())} 笔（{0.5 * conc.max():.1f} SOL）；持有期中位 {m.hold_h.median():.2f} h，90 分位 {m.hold_h.quantile(.9):.1f} h。\n")
P(f"频率：A 周 7 天 {m.mint.nunique()} 个事件，约 {m.mint.nunique() / 7:.1f} 个/天。\n")

txt = "\n".join(out)
target = HERE / "sql" / f"S1_结果包_{path.stem}.md"
target.write_text(txt)
print(txt)

"""DQ-1M v2：按卡 v1.2 判据分析 M2_full.csv，并与 v1 逐项对照。"""
import hashlib, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"; OUT.mkdir(exist_ok=True)
SOL = 69.76
CAP_BUY, CAP_SELL = np.sqrt(1.05) - 1, 1 - 1 / np.sqrt(1.05)
TH = [2, 5, 10, 50, 100]
bit = lambda d, b: (d["flags"] & b) > 0

def main_sample(d):
    return d[~bit(d, 1) & ~bit(d, 2) & ~bit(d, 64)]

def share_table(df, cols, label):
    out = [f"| {label} | n | " + " | ".join(f"≥{t}×" for t in TH) + " |", "|---|---:|" + "---:|" * len(TH)]
    for c in cols:
        s = df[c]
        out.append(f"| {c} | {s.notna().sum():,} | " + " | ".join(f"{(s >= t).sum():,}（{100 * (s >= t).mean():.3f}%）" for t in TH) + " |")
    return "\n".join(out)

v2 = pd.read_csv(HERE / "raw/M2_full.csv")
v1 = pd.read_csv(HERE / "raw/M1_full.csv")
S = {"v2_csv_sha256": hashlib.sha256((HERE / "raw/M2_full.csv").read_bytes()).hexdigest(),
     "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
     "rows_v2": len(v2), "rows_v1": len(v1), "sol_usd": SOL}

m2, m1 = main_sample(v2), main_sample(v1)
sol2 = v2[~bit(v2, 1)]
S["denominator_same_as_v1"] = {
    "总发行": [len(v2), len(v1)], "非 SOL": [int(bit(v2, 1).sum()), int(bit(v1, 1).sum())],
    "无法入场": [int(bit(sol2, 2).sum()), int(bit(v1[~bit(v1, 1)], 2).sum())],
    "异常": [int(bit(v2, 64).sum()), int(bit(v1, 64).sum())],
    "主样本": [len(m2), len(m1)], "毕业": [int(bit(m2, 4).sum()), int(bit(m1, 4).sum())]}

# 判据
w2, w1 = m2[m2.mpi_t50 >= 10], m1[m1.mpi_t50 >= 10]
bad = int(bit(sol2, 2).sum()) + int(bit(sol2, 512).sum()) + int(bit(v2, 64).sum())
S["criteria_v2"] = {"c1_winners": len(w2), "c1_pass": len(w2) >= 5,
                    "c2_cdays": int(w2.cday.nunique()), "c2_pass": w2.cday.nunique() >= 2,
                    "c3_bad_share": round(bad / len(sol2), 4), "c3_pass": bad / len(sol2) <= .30,
                    "continue": len(w2) >= 5 and w2.cday.nunique() >= 2 and bad / len(sol2) <= .30}
# 赢家名单变化
s2, s1 = set(w2.mint), set(w1.mint)
S["winners_change"] = {"v1": len(s1), "v2": len(w2), "both": len(s1 & s2), "only_v1": sorted(s1 - s2), "only_v2": sorted(s2 - s1)}
cmp = m1[["mint", "mpi_t50", "hv_60d", "ms_60d"]].merge(m2[["mint", "mpi_t50", "hv_60d", "ms_60d"]], on="mint", suffixes=("_v1", "_v2"))
S["mpi_t50_shift"] = {"相关系数": round(float(cmp.mpi_t50_v1.corr(cmp.mpi_t50_v2)), 4),
                      "中位数 v1→v2": [round(float(cmp.mpi_t50_v1.median()), 4), round(float(cmp.mpi_t50_v2.median()), 4)],
                      "均值 v1→v2": [round(float(cmp.mpi_t50_v1.mean()), 4), round(float(cmp.mpi_t50_v2.mean()), 4)],
                      "v1<0.5 而 v2≥0.9 的数量": int(((cmp.mpi_t50_v1 < .5) & (cmp.mpi_t50_v2 >= .9)).sum())}
# 门槛
nw, ww = m2[m2.mpi_t50 < 10].mpi_t50.mean(), w2.mpi_t50.mean()
S["selection_bar_v2"] = {"非赢家平均": round(float(nw), 4), "赢家平均": round(float(ww), 2),
                         "基础比例": round(float((m2.mpi_t50 >= 10).mean()), 6),
                         **{f"达到{t}倍所需赢家占比%": round(float(100 * (t - nw) / (ww - nw)), 3) for t in [1.0, 1.5, 2.0]}}
S["selection_bar_v2"]["相对基础比例"] = {f"{t}": round(((t - nw) / (ww - nw)) / float((m2.mpi_t50 >= 10).mean()), 1) for t in [1.0, 1.5, 2.0]}
# 容量
m2 = m2.assign(entry_cap=m2.entry_x_sol * CAP_BUY * SOL, exit_cap=m2.exit_x_sol * CAP_SELL * SOL)
w2c = m2[m2.mpi_t50 >= 10]
S["capacity_v2"] = {"赢家入场容量_usd": w2c.entry_cap.describe().round(1).to_dict(),
                    "赢家退出容量_usd": w2c.exit_cap.describe().round(1).to_dict(),
                    **{f"≥10×且入场容量≥${s}": int(((m2.mpi_t50 >= 10) & (m2.entry_cap >= s)).sum()) for s in [1400, 14000]},
                    "上帝视角_投入_usd": round(float(w2c.entry_cap.sum()), 0),
                    "上帝视角_毛利_usd": round(float((w2c.entry_cap * (w2c.mpi_t50 - 1)).sum()), 0)}
# 多口径与新列
post = m2[m2.last_dt.notna()]
S["multi_horizon_v2"] = {"spearman_ms2h_ms60d": round(float(post.ms_2h.rank().corr(post.ms_60d.rank())), 3),
                         "spearman_hv2h_hv60d": round(float(post.hv_2h.rank().corr(post.hv_60d.rank())), 3),
                         "ms_2h≥2 的数量": int((m2.ms_2h >= 2).sum()),
                         "其中 mpi_t50≥10 占比%": round(float(100 * (m2[m2.ms_2h >= 2].mpi_t50 >= 10).mean()), 3),
                         "其平均 mpi_t50": round(float(m2[m2.ms_2h >= 2].mpi_t50.mean()), 4)}
S["timing"] = {"见顶耗时_小时_中位数_全样本": round(float(m2.peak_dt.median() / 3600), 2),
               "见顶耗时_小时_中位数_赢家": round(float(w2c.peak_dt.median() / 3600), 2),
               "毕业耗时_小时_中位数_毕业币": round(float(m2.grad_dt.median() / 3600), 2),
               "毕业耗时_小时_中位数_赢家": round(float(w2c.grad_dt.median() / 3600), 2),
               "赢家中入场前已毕业": int((w2c.grad_dt <= 0).sum())}
S["equal_weight_v2"] = {"平均 mpi_t50": round(float(m2.mpi_t50.mean()), 4), "平均 hv_60d": round(float(m2.hv_60d.mean()), 4)}

md = [f"# DQ-1M v2 结果表\n\nCSV sha256 `{S['v2_csv_sha256']}`；SOL 均价 ${SOL}\n",
      "## 主样本分布（v2）\n\n" + share_table(m2, ["ms_2h", "ms_24h", "ms_60d"], "M*"),
      share_table(m2, ["hv_2h", "hv_24h", "hv_60d", "mpi_t50"], "Mπ"),
      "## 赢家明细（v2）\n\n" + w2c.sort_values("mpi_t50", ascending=False)[
          ["mint", "cday", "flags", "entry_x_sol", "entry_cap", "ms_60d", "hv_60d", "mpi_t50", "t50_day", "exit_cap", "peak_dt", "grad_dt"]].round(3).to_markdown(index=False)]
(OUT / "tables_v2.md").write_text("\n\n".join(md), encoding="utf-8")
(OUT / "summary_v2.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(S, ensure_ascii=False, indent=1, default=str))

"""DQ-1M：按卡 v1.2 判据分析 M1_full.csv。输出 results/summary.json 与 results/tables.md。"""
import csv, hashlib, io, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "results"
CSV = RAW / "M1_full.csv"
CAP5_BUY = np.sqrt(1.05) - 1          # 恒定乘积下使价格上升 5% 的买入额 / 报价侧储备
CAP5_SELL = 1 - 1 / np.sqrt(1.05)     # 使价格下降 5% 的卖出所得 / 报价侧储备
STAKE_USD = [1400, 14000]             # 1 万元本金、10 万元本金
TH = [2, 5, 10, 50, 100]


def sol_close():
    rows = []
    for z in sorted((RAW / "solusdt").glob("SOLUSDT-1d-*.zip")):
        with zipfile.ZipFile(z) as f:
            for r in csv.reader(io.TextIOWrapper(f.open(f.namelist()[0]))):
                ts = int(r[0]); ts = ts // 1000 if ts > 1e14 else ts
                rows.append((pd.to_datetime(ts, unit="ms").date(), float(r[4])))
    return pd.Series(dict(rows))


def bit(d, b):
    return (d["flags"] & b) > 0


def share_table(df, cols, label):
    lines = [f"| {label} | n | " + " | ".join(f"≥{t}×" for t in TH) + " |",
             "|---|---:|" + "---:|" * len(TH)]
    for c in cols:
        s = df[c]
        cells = [f"{(s >= t).sum():,}（{100 * (s >= t).mean():.3f}%）" for t in TH]
        lines.append(f"| {c} | {s.notna().sum():,} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    OUT.mkdir(exist_ok=True)
    d = pd.read_csv(CSV)
    px = sol_close()
    cohort_days = pd.date_range("2026-06-01", "2026-06-07").date
    sol_px = float(np.mean([px[x] for x in cohort_days]))
    S = {"csv_sha256": hashlib.sha256(CSV.read_bytes()).hexdigest(),
         "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         "sol_usd_mean_0601_0607": round(sol_px, 2), "rows": len(d)}

    # ---- 一、分母分解（互斥）----
    non_sol = bit(d, 1)
    sol = d[~non_sol]
    no_entry = bit(sol, 2)
    ent = sol[~no_entry]
    anomaly = bit(ent, 64)
    main_ = ent[~anomaly]
    no_post = main_["last_dt"].isna()
    grad = bit(main_, 4)
    part = {
        "总发行": len(d),
        "非 SOL 计价（排除）": int(non_sol.sum()),
        "SOL 计价": len(sol),
        "  无法入场（30 分钟内无成交）": int(no_entry.sum()),
        "  已入场·异常（虚拟 SOL >120，单列）": int(anomaly.sum()),
        "  已入场·主样本": len(main_),
        "    其中入场后再无成交": int(no_post.sum()),
        "    其中 60 天内毕业": int(grad.sum()),
        "    其中入场时已在池上": int(bit(main_, 1024).sum()),
    }
    assert part["非 SOL 计价（排除）"] + part["SOL 计价"] == part["总发行"]
    assert part["  无法入场（30 分钟内无成交）"] + part["  已入场·异常（虚拟 SOL >120，单列）"] + part["  已入场·主样本"] == part["SOL 计价"]
    S["denominator"] = part
    S["flags_other"] = {"mayhem（SOL 计价）": int(bit(sol, 128).sum()),
                        "异常且 mayhem": int((bit(ent, 64) & bit(ent, 128)).sum()),
                        "退出不可行": int(bit(sol, 512).sum()),
                        "池来自建池兜底": int(bit(sol, 16).sum()),
                        "小数位未知": int(bit(sol, 32).sum()),
                        "费率缺失": int(bit(sol, 256).sum())}

    # ---- 二、判据 ----
    win = main_[main_["mpi_t50"] >= 10]
    bad = int(no_entry.sum()) + int(bit(sol, 512).sum()) + int(anomaly.sum())
    crit = {
        "c1_mpi_t50_ge10_excl_anomaly": len(win),
        "c1_pass": len(win) >= 5,
        "c2_distinct_cdays": int(win["cday"].nunique()),
        "c2_pass": win["cday"].nunique() >= 2,
        "c3_bad_share_of_sol": round(bad / len(sol), 4),
        "c3_pass": bad / len(sol) <= 0.30,
    }
    crit["continue"] = crit["c1_pass"] and crit["c2_pass"] and crit["c3_pass"]
    S["criteria"] = crit

    # ---- 三、容量 ----
    def cap_usd(x, k): return x * k * sol_px
    m = main_.assign(entry_cap_usd=cap_usd(main_["entry_x_sol"], CAP5_BUY),
                     exit_cap_usd=cap_usd(main_["exit_x_sol"], CAP5_SELL))
    capinfo = {"entry_cap_usd_p50_all": round(float(m["entry_cap_usd"].median()), 1),
               "q_over_entry_x_p50": round(float((0.5 / m["entry_x_sol"]).median()), 4)}
    for stake in STAKE_USD:
        capinfo[f"mpi_t50_ge10_and_entry_cap_ge_{stake}"] = int(((m["mpi_t50"] >= 10) & (m["entry_cap_usd"] >= stake)).sum())
        capinfo[f"hv_60d_ge10_and_entry_cap_ge_{stake}"] = int(((m["hv_60d"] >= 10) & (m["entry_cap_usd"] >= stake)).sum())
        capinfo[f"ms_60d_ge10_and_entry_cap_ge_{stake}"] = int(((m["ms_60d"] >= 10) & (m["entry_cap_usd"] >= stake)).sum())
    w = m[m["mpi_t50"] >= 10]
    capinfo["winners_entry_cap_usd"] = w["entry_cap_usd"].describe().round(1).to_dict()
    capinfo["winners_exit_cap_usd"] = w["exit_cap_usd"].describe().round(1).to_dict()
    S["capacity"] = capinfo

    # ---- 四、多口径 ----
    post = m[m["last_dt"].notna()]
    mh = {}
    for a, b in [("ms_2h", "ms_60d"), ("hv_2h", "hv_60d"), ("hv_24h", "hv_60d"), ("hv_2h", "mpi_t50")]:
        mh[f"spearman_{a}_{b}"] = round(float(post[a].rank().corr(post[b].rank())), 3)
    g2 = m[m["ms_2h"] >= 2]
    mh["ms_2h_ge2_n"] = len(g2)
    mh["ms_2h_ge2_hv60_quantiles"] = g2["hv_60d"].quantile([.1, .25, .5, .75, .9]).round(3).to_dict()
    mh["ms_2h_ge2_mpi_t50_quantiles"] = g2["mpi_t50"].quantile([.1, .25, .5, .75, .9]).round(3).to_dict()
    mh["ms_2h_ge2_share_mpi_t50_ge10"] = round(float((g2["mpi_t50"] >= 10).mean()), 4)
    mh["all_share_mpi_t50_ge10"] = round(float((m["mpi_t50"] >= 10).mean()), 5)
    S["multi_horizon"] = mh

    # ---- 五、机械全买（描述）与资金需求 ----
    S["equal_weight_all_entered"] = {"mean_mpi_t50": round(float(m["mpi_t50"].mean()), 4),
                                     "mean_hv_60d": round(float(m["hv_60d"].mean()), 4),
                                     "capital_sol_per_day": round(len(sol) / 7 * 0.5, 0),
                                     "capital_usd_per_day": round(len(sol) / 7 * 0.5 * sol_px, 0)}

    # ---- 六、卖出封顶口径偏差诊断 ----
    capbind = post[(post["ms_60d"] <= 1.05) & (post["hv_60d"] < 0.5)]
    S["sell_cap_bias"] = {"post_rows_price_never_above_1.05_but_hv60_lt_0.5": len(capbind),
                          "share_of_main": round(len(capbind) / len(m), 4)}

    # ---- 分组表 ----
    md = [f"# DQ-1M 结果表（脚本生成）\n\nCSV sha256 `{S['csv_sha256']}`；SOL 均价（06-01～06-07 日收盘）${sol_px:.2f}\n"]
    md.append("## 分母分解\n\n| 类别 | 数量 |\n|---|---:|\n" + "\n".join(f"| {k} | {v:,} |" for k, v in part.items()))
    md.append("## 主样本分布\n\n" + share_table(m, ["ms_2h", "ms_24h", "ms_7d", "ms_30d", "ms_60d"], "M*（事后最高价）"))
    md.append(share_table(m, ["hv_2h", "hv_24h", "hv_7d", "hv_30d", "hv_60d", "mpi_t50"], "Mπ（固定 0.5 SOL 可退出）"))
    for name, sub in [("非 mayhem", m[~bit(m, 128)]), ("mayhem", m[bit(m, 128)]),
                      ("60 天内毕业子集（对照，不替代分母）", m[bit(m, 4)]), ("未毕业", m[~bit(m, 4)])]:
        md.append(f"### {name}\n\n" + share_table(sub, ["ms_60d", "hv_60d", "mpi_t50"], name))
    md.append("## 异常组（单列，不计入判据）\n\n" + share_table(ent[anomaly], ["ms_60d", "hv_60d", "mpi_t50"], "异常"))
    wtab = w.sort_values("mpi_t50", ascending=False)[["mint", "cday", "flags", "entry_x_sol", "entry_cap_usd", "ms_2h", "ms_24h", "ms_60d", "hv_60d", "mpi_t50", "t50_day", "exit_x_sol", "exit_cap_usd"]]
    md.append("## Mπ_T50 ≥ 10 明细\n\n" + wtab.round(3).to_markdown(index=False))
    (OUT / "tables.md").write_text("\n\n".join(md), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(S, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

"""K1 汇总：按 S2_筛选.md §3 K1 的事先判据判定。输入 results/K1_paths.csv，输出 results/K1_summary.json 并打印。

判据（首次组，L=5 s、300 s 退出）：均值扣 0.3% 往返成本 ≥ +2%；>0 的事件过半；每年 ≥ 10 个；
三年上限 = 3 × Σ(每个事件扣成本后收益 × 容量代理) ≥ 100 万元（容量代理 = [t0+5 s, t0+300 s] 成交额的 2%，1 美元 = 7.1 元）。
样本窗口正好一年，所以“每年个数”就是有价格数据的事件数。
"""
import csv, json, statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / "results" / "K1_paths.csv", encoding="utf-8")))
COST, CAP_SHARE, FX, TARGET = 0.003, 0.02, 7.1, 1_000_000


def f(x):
    return float(x) if x not in ("", None) else None


def cell(sub, L, X):
    v = [f(r[f"r_L{L}_X{X}"]) for r in sub if f(r.get(f"r_L{L}_X{X}", ""))is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "mean": st.mean(v), "median": st.median(v),
            "pos": sum(x > 0 for x in v) / len(v), "gt5": sum(x > 0.05 for x in v) / len(v),
            "p10": sorted(v)[int(0.1 * (len(v) - 1))], "p90": sorted(v)[int(0.9 * (len(v) - 1))]}


out = {"n_rows": len(rows), "by_src": {}, "groups": {}}
for r in rows:
    out["by_src"][r["src"]] = out["by_src"].get(r["src"], 0) + 1
has = [r for r in rows if r["src"] != "none" and r.get("r_L5_X300", "") != ""]
for g in ("first", "repeat", "unknown"):
    for ex in ("all", "upbit", "bithumb"):
        sub = [r for r in has if r["group"] == g and (ex == "all" or r["exchange"] == ex)]
        out["groups"][f"{g}/{ex}"] = {f"L{L}_X{X}": cell(sub, L, X) for L in (2, 5, 10) for X in (60, 300, 600)}

first = [r for r in has if r["group"] == "first"]
net = [f(r["r_L5_X300"]) - COST for r in first]
cap = [CAP_SHARE * f(r["qvol_L5_X300"]) for r in first]
ceiling_usd = 3 * sum(n * c for n, c in zip(net, cap))
out["criterion"] = {
    "n_first_per_year": len(first),
    "mean_net": st.mean(net) if net else None,
    "share_pos_gross": (sum(f(r["r_L5_X300"]) > 0 for r in first) / len(first)) if first else None,
    "median_capacity_usd": st.median(cap) if cap else None,
    "ceiling_3y_rmb": ceiling_usd * FX,
}
c = out["criterion"]
c["pass"] = bool(first) and c["mean_net"] >= 0.02 and c["share_pos_gross"] > 0.5 and c["n_first_per_year"] >= 10 and c["ceiling_3y_rmb"] >= TARGET

# 时刻核对：价格首次偏离 t0−60 s 水平 ≥1% 的时刻（相对 t0 的秒数）
fm = [(r["exchange"], r["group"], f(r["first_move_s"])) for r in rows if r.get("first_move_s", "") not in ("", None)]
out["first_move"] = {}
for ex in ("upbit", "bithumb"):
    v = sorted(x for e, g, x in fm if e == ex)
    if v:
        out["first_move"][ex] = {"n_moved_within_600s": len(v), "median_s": st.median(v),
                                 "share_before_t0_minus2": sum(x <= -2 for x in v) / len(v),
                                 "share_le_2s": sum(x <= 2 for x in v) / len(v),
                                 "share_le_5s": sum(x <= 5 for x in v) / len(v)}
pre = [f(r["pre60"]) for r in rows if r.get("pre60", "") not in ("", None)]
out["pre60_median"] = st.median(pre) if pre else None

json.dump(out, open(HERE / "results" / "K1_summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({"by_src": out["by_src"], "criterion": c, "first_move": out["first_move"], "pre60_median": out["pre60_median"]}, ensure_ascii=False, indent=1))
for k in ("first/all", "first/upbit", "first/bithumb", "repeat/all", "unknown/all"):
    g = out["groups"][k]
    print(k, " ".join(f"{cell_k}:n{v['n']} m{v.get('mean', 0)*100:+.1f}% md{v.get('median', 0)*100:+.1f}% pos{v.get('pos', 0):.0%}" for cell_k, v in g.items() if cell_k.startswith("L5") or cell_k == "L2_X300" or cell_k == "L10_X300"))

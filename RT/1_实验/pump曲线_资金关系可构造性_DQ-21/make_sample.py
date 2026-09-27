"""DQ-21 §6 抽样名单（v1.2）。在任何付费调用之前运行并提交 sample.csv。

主样本 random：A+B 两周 F3 面板（iv=0 的币）合并、按（week, mint）排序后，种子 20260928 随机排列，取前 40；R0a 用前 10。
压力样本 winner：30 天 max f_maxpm >= 10 的币（不含已入主样本者），同一随机数发生器无放回抽 30。
压力样本 matched：对每个 winner，在同周、同入场场所、max f_maxpm < 10、未入样的币中，
  按 F3 入场状态（与 DQ-20 analyze_q1.f3_entry 相同的 6 个变量，A+B 合并标准化）取欧氏距离最近的 1 个。
F101 的 3 个赢家与 3 个对照（A 周）只作 R0a 字段核对，stratum = f101。
结果标签只用于分层，不比较收益。

python make_sample.py → sample.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
D8 = H.parents[1] / "1_实验" / "pump曲线_检查点动态决策_DQ-8A" / "raw"
SEED = 20260928
F101 = {"B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump": "f101_winner",
        "5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump": "f101_winner",
        "BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump": "f101_winner",
        "YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump": "f101_control",
        "6vpjdKC8EAHdqXgX3gry3voXnQYGuRR6RJkH7hMxpump": "f101_control",
        "FbZbeMQGonXiUKK5QGDWXTGvraY2A3fRvwBZTbYRpump": "f101_control"}
VARS = ["lx", "tr30", "bshare", "vol30", "nb30", "ins"]


def panel(w):
    P = pd.read_csv(D8 / f"F3_dev{w}.csv", low_memory=False,
                    usecols=["mint", "iv", "l_venue", "l_x", "f_trades30", "f_buy30", "f_sell30", "f_newb30",
                             "f_ins_exit", "f_maxpm"])
    lab = P.groupby("mint").f_maxpm.max()
    e = P[P.iv == 0].set_index("mint")
    tot = e.f_buy30.fillna(0) + e.f_sell30.fillna(0)
    return pd.DataFrame({
        "week": w, "venue": e.l_venue, "lx": np.log(e.l_x), "tr30": np.log1p(e.f_trades30.fillna(0)),
        "bshare": np.where(tot > 0, e.f_buy30.fillna(0) / tot.where(tot > 0, 1), 0.5),
        "vol30": np.log1p(tot), "nb30": np.log1p(e.f_newb30.fillna(0)), "ins": e.f_ins_exit.fillna(0).clip(-1, 2),
        "ge10x": lab.reindex(e.index) >= 10})


def main():
    U = pd.concat([panel("A"), panel("B")]).reset_index().sort_values(["week", "mint"]).reset_index(drop=True)
    assert U.mint.is_unique
    print("panel", U.groupby("week").size().to_dict(), "ge10x", U[U.ge10x].groupby("week").size().to_dict())
    missing = [m for m in F101 if m not in set(U.mint)]
    assert not missing, missing
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(U))
    rand = U.iloc[order[:40]].assign(stratum="random", order=range(1, 41))
    taken = set(rand.mint)
    wpool = U[U.ge10x & ~U.mint.isin(taken)].reset_index(drop=True)
    win = wpool.iloc[np.sort(rng.choice(len(wpool), 30, replace=False))].assign(stratum="winner", order=range(1, 31))
    taken |= set(win.mint)
    Z = U[VARS].to_numpy(float)
    Z = (Z - Z.mean(0)) / np.where(Z.std(0) > 0, Z.std(0), 1)
    matched = []
    for k, (_, r) in enumerate(win.iterrows(), 1):
        i = U.index[U.mint == r.mint][0]
        cand = U.index[(U.week == r.week) & (U.venue == r.venue) & ~U.ge10x & ~U.mint.isin(taken)]
        j = cand[np.argmin(((Z[cand] - Z[i]) ** 2).sum(1))]
        taken.add(U.mint.iat[j])
        matched.append(U.loc[[j]].assign(stratum="matched", order=k, matched_to=r.mint))
    f101 = U[U.mint.isin(F101)].assign(stratum=lambda d: d.mint.map(F101), order=0)
    S = pd.concat([rand, win, pd.concat(matched), f101], ignore_index=True)
    S["r0a"] = ((S.stratum == "random") & (S.order <= 10)) | S.stratum.str.startswith("f101")
    S = S[["mint", "week", "venue", "stratum", "order", "r0a", "matched_to"]]
    S.to_csv(H / "sample.csv", index=False)
    print(S.groupby(["stratum", "week"]).size().to_string(), "\nR0a", int(S.r0a.sum()), "unique", S.mint.nunique(), "rows", len(S))


if __name__ == "__main__":
    main()

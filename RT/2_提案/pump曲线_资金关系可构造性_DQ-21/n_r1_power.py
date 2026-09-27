"""DQ-21 v1.2 §8 附：R1 需要的触发币数 N_R1。

数据：A+B 全部 F3 面板币的 R_0（DQ-19 口径：创建后 30 分钟入场、b50、扣 0.004），与关系变量无关。
门槛：E[R_0] >= 1.00，且去掉最大 1 币后仍 >= 1.00（R1 第 1、2 条）。
null  = 从全体随机抽 N 个（有放回）；uniform_scale = 同一批抽样把每个币同比例抬高到均值 1.10（对照用）；
富集 = 把 R >= thr 的币按倍数 lam 加权抽样，使加权均值 = 目标 E（尾部富集，F83/F113 的模式）。

python n_r1_power.py → n_r1_power.json（首次运行载入 DQ-19 面板约 10 分钟，缓存 r0_AB.npy，不提交）
"""
import json
import sys
from pathlib import Path

import numpy as np

H = Path(__file__).resolve().parent
SEED = 20260927


def load_r0():
    f = H / "r0_AB.npy"
    if not f.exists():
        sys.path.insert(0, str(H.parents[1] / "1_实验" / "pump曲线_状态转变领先性_DQ-19"))
        import dq19 as Q
        np.save(f, np.concatenate([Q.load("A")["R"][:, 0], Q.load("B")["R"][:, 0]]))
    return np.load(f)


def passes(S):
    N = S.shape[1]
    m = S.mean(1)
    d = (S.sum(1) - S.max(1)) / (N - 1)
    return float(((m >= 1) & (d >= 1)).mean())


def null_rates(r):
    rng = np.random.default_rng(SEED)
    out = {}
    for N in (100, 200, 300, 500, 1000, 1500, 2000, 3000):
        S = r[rng.integers(0, len(r), (3000, N))]
        out[N] = {"null": round(passes(S), 4), "E1.10_uniform_scale": round(passes(S * (1.10 / r.mean())), 4)}
    return out


def enrichment_power(r):
    rng = np.random.default_rng(SEED)
    base = r.mean()
    rows = []
    for thr in (2.0, 5.0):
        tail = r >= thr
        for target in (1.10, 1.20):
            a, b, na, nb = r[tail].sum(), r[~tail].sum(), tail.sum(), (~tail).sum()
            lam = (target * nb - b) / (a - target * na)
            p = np.where(tail, lam, 1.0)
            p /= p.sum()
            for N in (100, 300, 500, 1000, 2000, 3000):
                S = r[rng.choice(len(r), (2000, N), p=p)]
                rows.append({"tail": f"R>={thr}", "E": target, "lift": round(float(lam), 2), "N": N,
                             "power": round(passes(S), 3)})
    return {"mean": round(float(base), 4), "rows": rows}


if __name__ == "__main__":
    r = load_r0()
    res = {"n": int(len(r)), "null_pass_rate": null_rates(r), "tail_enrichment": enrichment_power(r)}
    (H / "n_r1_power.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["null_pass_rate"]), [(x["tail"], x["E"], x["N"], x["power"]) for x in res["tail_enrichment"]["rows"] if x["E"] == 1.10])

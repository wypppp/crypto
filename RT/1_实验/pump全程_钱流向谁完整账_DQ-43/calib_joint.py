#!/usr/bin/env python3
"""DQ-43 §9.1 联合校准（10-13，总控第三轮、GPT 增量 07、08）。合成数据，不读真实数据。

在同一个合成世界里同时算 S3 集合检验与 R2，直接统计最终 keep_main_line＝keep 的比例。
三种无信号场景（任何实体都没有事件信息，收益是公平的）：
- null：随机实体在随机时刻买入；事件时刻独立随机；币级收益冲击。
- freq：GPT 增量 05 的固定频率场景：每个币上 20 个实体按固定时间表买 5 次，其余实体只买一次；首笔状态相同。
- shock：GPT 增量 06 的共同冲击场景：同一创建日的币共享一个公平冲击（×0.5 或 ×1.5 等概率），
  30 个实体每天同买当天的“热门币”，前十分位实体集中在少数共同冲击上。
目标：每种场景 keep 比例不超过 5%。报 Clopper-Pearson 95% 区间。
另跑两个有信号的对照（只报功效，不是目标）：
- pow_s3：8 个知情实体在每个将毕业的币毕业前 600 秒买入；
- pow_r2：30 个实体每周各买 10 个随机币，回收是公平的 1.5 倍。

用法：python3 calib_joint.py [每场景次数，默认 400]  → runs/calib_joint.json
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import a_riskset as A
import t3_persist as P

H = Path(__file__).resolve().parent
DAY = 86400
N_COINS = 60  # 每周
UNIT = 100_000_000  # 每笔买入 0.1 SOL（lamports）
FEE = 5_000  # 每笔签名费


NULLS = ("null", "freq", "shock")
SCENARIOS = NULLS + ("pow_s3", "pow_r2")


def _lognorm_mean1(rng, sigma):
    return math.exp(rng.gauss(-sigma * sigma / 2, sigma))


def make_week(rng, week, scenario, day_shock):
    """返回 (buys, events, cash)。cash：每笔买入一行 {entity, day, in_cost, out_held}。"""
    buys, events, cash = [], [], []
    bid = 0
    for c in range(N_COINS):
        coin = f"w{week}c{c}"
        day = week * 7 + c % 7
        t0 = day * DAY + (c // 7) * 600
        if rng.random() < 0.5:
            tg = t0 + rng.uniform(2000, 8000)
            events.append(
                A.Event(coin, "grad", tg, (int(tg), 9, 0, -1), f"g{coin}", "x")
            )
        m_coin = _lognorm_mean1(rng, 0.8) * (
            day_shock[day] if scenario == "shock" else 1
        )
        plan = []  # (实体, 买入时刻)
        if scenario == "freq":
            for k in range(20):
                first = t0 + rng.uniform(0, 9000)
                plan += [(f"f{k}", first + j * 600) for j in range(5)]
            plan += [
                (f"o{rng.randrange(180)}", t0 + rng.uniform(0, 9000)) for _ in range(25)
            ]
        else:
            plan += [
                (f"e{rng.randrange(300)}", t0 + rng.uniform(0, 9000)) for _ in range(30)
            ]
            if scenario == "shock" and c < 7:  # 每天第一个币是热门币，30 个实体同买
                plan += [(f"h{k}", t0 + rng.uniform(0, 3000)) for k in range(30)]
            if scenario == "pow_s3" and events and events[-1].coin == coin:
                plan += [(f"i{k}", events[-1].ts - 600) for k in range(8)]
            if scenario == "pow_r2":
                plan += [
                    (f"s{k}", t0 + rng.uniform(0, 9000))
                    for k in range(30)
                    if rng.random() < 10 / N_COINS
                ]
        for ent, t in plan:
            bid += 1
            buys.append(
                A.Buy(
                    bid,
                    ent,
                    coin,
                    t,
                    (int(t), bid % 1000, 0, -1),
                    f"t{coin}{bid}",
                    ("s",),
                    1e15,
                )
            )
            edge = 1.5 if ent.startswith("s") else 1.0
            out = int(UNIT * m_coin * edge * _lognorm_mean1(rng, 0.3))
            cash.append(
                {"entity": ent, "day": day, "in_cost": UNIT + FEE, "out_held": out}
            )
    return buys, events, cash


def simulate(args):
    scenario, seed = args
    rng = random.Random(f"{scenario}-{seed}")
    day_shock = defaultdict(lambda: 0.5 if rng.random() < 0.5 else 1.5)
    pairs_s3, members, flows = [], [], []
    for p in range(3):
        bw, ew, cw = make_week(rng, 2 * p, scenario, day_shock)
        bw1, ew1, cw1 = make_week(rng, 2 * p + 1, scenario, day_shock)
        # S3
        sel = A.select_set(A.collapse(A.label(bw, ew, "grad")))
        pairs_s3.append((A.collapse(A.label(bw1, ew1, "grad")), sel))
        # R2
        net_w, net_w1 = defaultdict(int), defaultdict(int)
        for r in cw:
            net_w[r["entity"]] += r["out_held"] - r["in_cost"]
        for r in cw1:
            net_w1[r["entity"]] += r["out_held"] - r["in_cost"]
        top = P.top_decile(dict(net_w))
        for e in top:
            act = e in net_w1
            members.append(
                {
                    "pair": p,
                    "entity": e,
                    "active": act,
                    "p_class": act and net_w[e] > 0 and net_w1[e] > 0,
                }
            )
        tops = set(top)
        agg = defaultdict(lambda: [0, 0])
        for r in cw1:
            if r["entity"] in tops:
                a = agg[(r["entity"], r["day"])]
                a[0] += r["in_cost"]
                a[1] += r["out_held"]
        flows += [
            {"pair": p, "entity": e, "day": d, "in_cost": v[0], "out_held": v[1]}
            for (e, d), v in agg.items()
        ]
    s3 = A.set_test(pairs_s3, n_perm=999, seed=seed)
    r2 = P.r2_pooled(members, flows, seed=seed)
    return {
        "scenario": scenario,
        "seed": seed,
        "s3": s3["result"],
        "s3_active": s3["active"],
        "r2_computable": r2["computable"],
        "r2_holds": r2["holds"],
        "r2_n_active": r2["n_active"],
        "r2_n_days": r2["n_days"],
        "keep": P.keep_main_line(s3, r2) == "keep",
    }


def clopper_pearson(k, n, a=0.05):
    from scipy.stats import beta

    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return lo, hi


def summarize(res):
    out = {}
    for sc in SCENARIOS:
        rs = [r for r in res if r["scenario"] == sc]
        n = len(rs)
        k = sum(r["keep"] for r in rs)
        out[sc] = {
            "n": n,
            "keep": k,
            "keep_rate": k / n,
            "keep_ci95": clopper_pearson(k, n),
            "s3_positive": sum(r["s3"] == "positive" for r in rs),
            "s3_not_computable": sum(r["s3"] == "not_computable" for r in rs),
            "r2_holds": sum(r["r2_holds"] for r in rs),
            "r2_not_computable": sum(not r["r2_computable"] for r in rs),
            "median_s3_active": sorted(r["s3_active"] for r in rs)[n // 2],
            "median_r2_active": sorted(r["r2_n_active"] for r in rs)[n // 2],
        }
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    jobs = [(sc, s) for sc in SCENARIOS for s in range(n if sc in NULLS else n // 4)]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(simulate, jobs, chunksize=8))
    summ = summarize(res)
    (H / "runs").mkdir(exist_ok=True)
    (H / "runs" / "calib_joint.json").write_text(
        json.dumps({"n_per_scenario": n, "summary": summ}, ensure_ascii=False, indent=1)
    )
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

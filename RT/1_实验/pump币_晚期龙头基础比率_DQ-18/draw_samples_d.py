"""冻结 D 段样本（在任何 D 段查询之前运行一次）。

验证样本（预登记，种子 20260924，排序 md5(mint || ':20260924') 升序，与执行方 09-24 登记一致）：
  2025-12 首次过 100 万美元（创建以来首次）取 20 个；2024-11 取 10 个；另加 5 个知名币。
估计样本（分层，种子 dq18d，排序 md5(mint || ':dq18d') 升序），按币在窗口内到达的最高档分层：
  S100 全取；S20 全取；S5 取 250；S1 取 250。窗口：首次穿越小时在 2024-06-01～2026-03-15。
输出 raw/census/sample_D.csv：每个入选币一行（层、权重、验证标记）。
"""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWN = ["CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump", "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
         "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump", "a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump",
         "8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump"]


def h(m, seed):
    return hashlib.md5((m + ":" + seed).encode()).hexdigest()


def main():
    rows = list(csv.DictReader(open(ROOT / "raw" / "census" / "first_crossings.csv")))
    win = lambda r: "2024-06-01" <= r["hour_start"][:10] <= "2026-03-15"
    top = defaultdict(int)
    inwin = set()
    for r in rows:
        if win(r):
            inwin.add(r["mint"])
            top[r["mint"]] = max(top[r["mint"]], int(r["threshold_usd"]))
    first1m = {r["mint"]: r["hour_start"][:7] for r in rows if r["threshold_usd"] == "1000000"}
    val = {}
    for month, k in (("2025-12", 20), ("2024-11", 10)):
        frame = sorted((m for m, mo in first1m.items() if mo == month), key=lambda m: h(m, "20260924"))
        for m in frame[:k]:
            val[m] = "V" + month
    for m in KNOWN:
        val[m] = "known"
    strata = defaultdict(list)
    for m in inwin:
        strata[{100000000: "S100", 20000000: "S20", 5000000: "S5", 1000000: "S1"}[top[m]]].append(m)
    take = {"S100": None, "S20": None, "S5": 250, "S1": 250}
    out = []
    for s, ms in strata.items():
        ms = sorted(ms, key=lambda m: h(m, "dq18d"))
        k = len(ms) if take[s] is None else take[s]
        for m in ms[:k]:
            out.append((m, s, len(ms) / k, val.get(m, "")))
    chosen = {m for m, *_ in out}
    for m, v in val.items():
        if m not in chosen:
            out.append((m, "V_only", 0.0, v))
    out.sort()
    p = ROOT / "raw" / "census" / "sample_D.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mint", "stratum", "weight", "validation"])
        w.writerows(out)
    sizes = {s: len(ms) for s, ms in strata.items()}
    print(json.dumps({"strata_sizes": sizes, "n_sample": len(out), "n_validation": len(val)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

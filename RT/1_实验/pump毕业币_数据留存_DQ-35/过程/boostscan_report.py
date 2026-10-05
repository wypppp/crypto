#!/usr/bin/env python3
"""DQ-35 InitBoost 全量扫描的读取与报告（10-06；总控第二十轮第二节）。

python 过程/boostscan_report.py a b c [d]  → runs/SCAN23_BOOST_report.md
- 合并各段的 rec='P' 行（同一个池跨段：次数相加，首次取最早、末次取最晚，vq 取极值）。
- 按建池时刻分：升级前（老池，早于 2026-07-15 18:07:19 UTC）、升级窗口（18:07:19～18:07:32）、升级后（新池）、查不到建池事件。
- 老池再按建池日期所在周分类（weeks.week_class：开发、检验、封存、范围外）。只有开发周建的老池列出明细；
  检验周、封存周、范围外的老池只出计数（同 dev_gate 的读法：先分类，被排除的不进入明细）。
  注：DQ-37 的周按曲线创建时刻定；这里用建池日期，是结构核对的近似，不用于开发读取。
- rec='D' 行：各段事件判别符的合计，与已知的 14 种事件比对，出现未知判别符就在报告里标出。
"""

import csv
import datetime as dt
import gzip
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

H = Path(__file__).resolve().parent.parent
sys.path.append(str(H.parent / "发射台_前期右尾评测底座_DQ-37"))
import weeks  # noqa: E402

RAW = H / "raw" / "dune"
EPOCH = dt.datetime(1970, 1, 1)
T_UP0 = (dt.datetime(2026, 7, 15, 18, 7, 19) - EPOCH).total_seconds()
T_UP1 = (dt.datetime(2026, 7, 15, 18, 7, 32) - EPOCH).total_seconds()
KNOWN = {
    "67F4521F2CF57777": "BuyEvent",
    "3E2F370AA503DC2A": "SellEvent",
    "B1310CD2A076A774": "CreatePoolEvent",
    "78F83D531F8E6B90": "DepositEvent",
    "1609851AA02C47C0": "WithdrawEvent",
    "6161D7905D92167C": "ExtendAccountEvent",
    "E8F5C2EEEADA3A59": "CollectCoinCreatorFeeEvent",
    "86240D48E86582D8": "InitUserVolumeAccumulatorEvent",
    "929FBDAC925838F4": "CloseUserVolumeAccumulatorEvent",
    "2DDC5D181961AC68": "AdminSetCoinCreatorEvent",
    "E2D6F62107F293E5": "ClaimCashbackEvent",
    "AE7C4AF90451F611": "InitBoostEvent",
    "3F451C16305CC2B9": "BoostBuyAndBurnEvent",
    "AADD52C793A5F72E": "MigratePoolCoinCreatorEvent",
}


def num(x):
    return None if x in ("", None) else Decimal(x)


def utc(t):
    return EPOCH + dt.timedelta(seconds=float(t))


def load(tags):
    pools, disc = {}, Counter()
    for tag in tags:
        with gzip.open(RAW / ("SCAN23_BOOST_%s.csv.gz" % tag), "rt", newline="") as f:
            for r in csv.DictReader(f):
                if r["rec"] == "D":
                    disc[r["disc"].upper().replace("0X", "")] += int(num(r["n_init"]))
                    continue
                p = pools.get(r["pool"])
                if p is None:
                    pools[r["pool"]] = dict(r)
                    continue
                for k in ("n_init", "n_burn", "n_ovf"):
                    p[k] = str(int(num(p[k]) or 0) + int(num(r[k]) or 0))
                for k, f2 in (
                    ("first_init_t", min),
                    ("first_burn_t", min),
                    ("last_init_t", max),
                    ("vq_init_min", min),
                    ("vq_burn_min", min),
                    ("vq_init_max", max),
                    ("vq_burn_max", max),
                ):
                    xs = [num(v) for v in (p[k], r[k]) if v not in ("", None)]
                    p[k] = str(f2(xs)) if xs else ""
    return pools, disc


def age_class(p):
    t = p["pool_created_t"]
    if t in ("", None):
        return "no_create"
    t = float(t)
    if t < T_UP0:
        return "old"
    if t < T_UP1:
        return "boundary"
    return "new"


def main():
    tags = sys.argv[1:]
    pools, disc = load(tags)
    by_age = defaultdict(list)
    for p in pools.values():
        by_age[age_class(p)].append(p)
    L = ["# DQ-35 InitBoost 全量扫描（10-06；总控第二十轮第二节）", ""]
    L.append(
        "- 段：%s（`sql/SCAN23_BOOST_*.sql`，生成 `过程/build_boostscan_sql.py`）；升级时刻取 2026-07-15 18:07:19～18:07:32 UTC。"
        % "、".join(tags)
    )
    L.append(
        "- 只含计数、时刻与 vq 参数，没有成交价或收益。检验周、封存周、范围外建的老池只出计数。"
    )
    L.append("")
    L.append("## 1. 按建池时刻分组")
    L.append("")
    L.append(
        "| 组 | 有 boost 的池 | InitBoost 次数 | 有 InitBoost 的池 | BoostBuyAndBurn 次数 | 一个池多次 InitBoost |"
    )
    L.append("|---|---|---|---|---|---|")
    for k, lab in (
        ("old", "升级前建池（老池）"),
        ("boundary", "升级窗口内建池"),
        ("new", "升级后建池（新池）"),
        ("no_create", "查不到建池事件"),
    ):
        ps = by_age.get(k, [])
        L.append(
            "| %s | %d | %d | %d | %d | %d |"
            % (
                lab,
                len(ps),
                sum(int(num(p["n_init"])) for p in ps),
                sum(int(num(p["n_init"])) > 0 for p in ps),
                sum(int(num(p["n_burn"])) for p in ps),
                sum(int(num(p["n_init"])) > 1 for p in ps),
            )
        )
    L.append("")
    old = by_age.get("old", [])
    L.append("## 2. 老池")
    L.append("")
    if not old:
        L.append("**升级前建的池在扫描期内 InitBoost 0 次、BoostBuyAndBurn 0 次。**")
    else:
        wc = Counter()
        dev_rows = []
        for p in old:
            c = weeks.week_class(utc(p["pool_created_t"]).date().isoformat())
            wc[c] += 1
            if c == weeks.DEV:
                dev_rows.append(p)
        L.append("按建池日期所在周：%s" % dict(wc))
        L.append("")
        L.append(
            "| 池 | 建池（UTC） | 发起程序 | InitBoost | 首次 InitBoost | BoostBuyAndBurn | InitBoost 的 vq |"
        )
        L.append("|---|---|---|---|---|---|---|")
        for p in sorted(dev_rows, key=lambda p: float(p["pool_created_t"])):
            L.append(
                "| `%s` | %s | `%s` | %s | %s | %s | %s～%s |"
                % (
                    p["pool"],
                    utc(p["pool_created_t"]).strftime("%Y-%m-%d %H:%M:%S"),
                    p["creator_prog"][:8],
                    p["n_init"],
                    utc(p["first_init_t"]).strftime("%Y-%m-%d %H:%M:%S")
                    if p["first_init_t"]
                    else "—",
                    p["n_burn"],
                    p["vq_init_min"],
                    p["vq_init_max"],
                )
            )
    L.append("")
    new = by_age.get("new", [])
    L.append("## 3. 新池（核对）")
    L.append("")
    lag = []
    for p in new:
        if p["first_init_t"]:
            lag.append(float(p["first_init_t"]) - float(p["pool_created_t"]))
    lag.sort()
    if lag:
        L.append(
            "- 首次 InitBoost 距建池（秒）：%d 个池，中位 %.0f，p99 %.0f，最大 %.0f；同秒或之后 %d"
            % (
                len(lag),
                lag[len(lag) // 2],
                lag[min(len(lag) - 1, int(0.99 * len(lag)))],
                lag[-1],
                sum(x >= 0 for x in lag),
            )
        )
    vq = Counter(p["vq_init_min"] == p["vq_init_max"] for p in new if p["vq_init_min"])
    L.append("- 同一个池各次 InitBoost 的 vq 相同：%s" % dict(vq))
    L.append(
        "- 有 BoostBuyAndBurn 而没有 InitBoost 的新池：%d（InitBoost 可能早于扫描起点，或在 d 段之后）"
        % sum(1 for p in new if int(num(p["n_init"])) == 0)
    )
    ovf = sum(int(num(p["n_ovf"]) or 0) for p in pools.values())
    L.append("- vq 溢出（高 8 字节超 ±4e18）：%d" % ovf)
    progs = Counter(p["creator_prog"][:8] for p in new)
    L.append("- 新池的建池发起程序（前 8 位）：%s" % dict(progs.most_common(6)))
    L.append("")
    L.append("## 4. 扫描期内全部事件类型")
    L.append("")
    L.append("| 判别符 | 事件 | 次数 |")
    L.append("|---|---|---|")
    for d, n in disc.most_common():
        L.append("| `%s` | %s | %d |" % (d.lower(), KNOWN.get(d, "**未知**"), n))
    unk = [d for d in disc if d not in KNOWN]
    L.append("")
    L.append(
        "- 未知判别符：%s" % ("无" if not unk else "、".join(u.lower() for u in unk))
    )
    out = H / "runs" / "SCAN23_BOOST_report.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DQ-35 v2.1 小样本对照（10-04）：用逐笔原始事件（精确整数）重算 B 层分桶与 P 层快照，逐项比对。

python compare_sample_v21.py <B 层标签> <P 层标签> <逐笔原始标签> [<B 层第二次运行标签> <P 层第二次运行标签>]
  → runs/<B 层标签>_compare.md
逐笔原始文件来自 build_sample_raw_v2.py（金额是精确整数）。只核对齐全、精度与一致性，不看价格或收益分布。
快照只比对“时点＋1 秒仍在逐笔原始文件覆盖日内”的时点（原始文件只有一天的事件）。
"""

import csv
import gzip
import sys
from collections import defaultdict

from dune_get import H

RAW = H / "raw" / "dune"
OFFSETS = (2, 10, 45, 60, 75, 900, 3600, 86400)
NUM_FIELDS = (
    "q_buy_user",
    "q_sell_user",
    "q_buy_pool",
    "q_sell_pool",
    "b_buy",
    "b_sell",
    "f_lp",
    "f_pr",
    "f_cr",
)


def read(label):
    with gzip.open(RAW / ("%s.csv.gz" % label), "rt", newline="") as f:
        return list(csv.DictReader(f))


def epoch(ts):
    """'2025-10-07 01:35:00.000 UTC' → epoch 秒（整数毫秒精度，返回毫秒）。"""
    import datetime as dt

    d = dt.datetime.strptime(ts.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S.%f")
    return int(round((d - dt.datetime(1970, 1, 1)).total_seconds() * 1000))


def bucket(age_ms):
    """v2.1 分桶：[0,300 s) 5 秒 S；[300 s,1 h) 1 分钟 M；[1 h,7 d) 1 小时 H；之后 1 天 D。"""
    if age_ms < 300_000:
        return "S", age_ms // 5_000
    if age_ms < 3_600_000:
        return "M", age_ms // 60_000
    if age_ms < 604_800_000:
        return "H", age_ms // 3_600_000
    return "D", age_ms // 86_400_000


def post_state(side, q0, b0, q_pool, b_amt):
    """成交后储备（整数）：买＝前＋含 LP 费的报价入池、减代币出池；卖＝前−（报价出池−LP 费）、加代币入池。"""
    if side == "B":
        return q0 + q_pool, b0 - b_amt
    return q0 - q_pool, b0 + b_amt


def events(raw, pools):
    """逐笔原始 → 每池按事件键排序的列表；只取 B／S，金额转 Python 整数。"""
    out = defaultdict(list)
    for r in raw:
        if r["pool"] not in pools or r["ev"] not in ("B", "S"):
            continue
        q_amt, q_lp, lp = int(r["q_amt"]), int(r["q_amt_lp"] or 0), int(r["f_lp"] or 0)
        q_pool = q_lp if r["ev"] == "B" else q_amt - lp
        e = dict(
            side=r["ev"],
            key=(int(r["slot"]), int(r["txi"]), int(r["oix"]), int(r["iix"] or -1)),
            t=epoch(r["ts"]),
            usr=r["usr"],
            q0=int(r["q0"]),
            b0=int(r["b0"]),
            q_pool=q_pool,
            b_amt=int(r["b_amt"]),
            q_user=int(r["q_user"]),
            f_lp=lp,
            f_pr=int(r["f_pr"] or 0),
            f_cr=int(r["f_cr"] or 0),
        )
        e["q1"], e["b1"] = post_state(
            e["side"], e["q0"], e["b0"], e["q_pool"], e["b_amt"]
        )
        out[r["pool"]].append(e)
    for v in out.values():
        v.sort(key=lambda e: e["key"])
    return out


def expected_buckets(ev, created_ms):
    agg = {}
    for pool, es in ev.items():
        for e in es:
            kind, bkey = bucket(e["t"] - created_ms[pool])
            a = agg.setdefault(
                (kind, pool, bkey), dict(n=0, n_buy=0, users=set(), ev=[])
            )
            a["n"] += 1
            a["n_buy"] += e["side"] == "B"
            a["users"].add(e["usr"])
            a["ev"].append(e)
    rows = {}
    for k, a in agg.items():
        es = a["ev"]
        f, last = es[0], es[-1]
        s = defaultdict(int)
        for e in es:
            sd = "buy" if e["side"] == "B" else "sell"
            s["q_%s_user" % sd] += e["q_user"]
            s["q_%s_pool" % sd] += e["q_pool"]
            s["b_%s" % sd] += e["b_amt"]
            for c in ("f_lp", "f_pr", "f_cr"):
                s[c] += e[c]
        rows[k] = dict(
            n=a["n"],
            n_buy=a["n_buy"],
            n_users_exact=len(a["users"]),
            key_f=f["key"],
            key_l=last["key"],
            q0_open=f["q0"],
            b0_open=f["b0"],
            side_first=f["side"],
            q1_close=last["q1"],
            b1_close=last["b1"],
            side_last=last["side"],
            q_pool_last=last["q_pool"],
            b_amt_last=last["b_amt"],
            t_first=f["t"],
            t_last=last["t"],
            **{c: s[c] for c in NUM_FIELDS},
        )
    return rows


def expected_snapshot(es, created_ms, o):
    """时点 created+o 秒：之前最后一笔（成交后状态）与之后第一笔（成交前状态）。es 已按事件键排序。"""
    lim = created_ms + o * 1000
    before = [e for e in es if e["t"] < lim]
    after = [e for e in es if e["t"] >= lim]
    a = before[-1] if before else None
    b = after[0] if after else None
    return a, b


def same_rows(r1, r2):
    """两次运行逐行一致（按全部列排序后比较）。"""
    k = sorted(r1[0].keys()) if r1 else []
    f = sorted(tuple(r[c] for c in k) for r in r1)
    g = sorted(tuple(r[c] for c in k) for r in r2)
    return f == g


def main():
    a = sys.argv[1:]
    blab, plab, rawlab = a[0], a[1], a[2]
    B, P, raw = read(blab), read(plab), read(rawlab)
    pools = {r["pool"]: r for r in P}
    created_ms = {p: int(round(float(r["created_t"]) * 1000)) for p, r in pools.items()}
    ev = events(raw, set(pools))
    day_end_ms = (
        max(e["t"] for es in ev.values() for e in es) // 86_400_000 * 86_400_000
        + 86_400_000
    )
    lines = ["# DQ-35 v2.1 小样本对照：%s / %s 对 %s" % (blab, plab, rawlab), ""]

    # 1. 储备逐笔守恒（池内无加撤池时，下一笔成交前＝上一笔成交后）
    cont = tot = 0
    for es in ev.values():
        for p, q in zip(es, es[1:]):
            tot += 1
            cont += (q["q0"], q["b0"]) == (p["q1"], p["b1"])
    lines.append("- 储备逐笔守恒：%d / %d" % (cont, tot))

    # 2. 事件键唯一
    keys = [(pl, e["key"]) for pl, es in ev.items() for e in es]
    lines.append("- 事件键唯一：%d 个事件，%d 个不同键" % (len(keys), len(set(keys))))

    # 3. B 层逐项
    exp = expected_buckets(ev, created_ms)
    got = {(r["kind"], r["pool"], int(r["bkey"])): r for r in B}
    lines.append(
        "- 分桶数：SQL %d，逐笔重算 %d，键集合相同：%s"
        % (len(got), len(exp), set(got) == set(exp))
    )
    bad = defaultdict(int)
    users_diff = 0
    for k in set(got) & set(exp):
        g, e = got[k], exp[k]
        for c in ("n", "n_buy", "t_first", "t_last"):
            gv = float(g[c]) * (1000 if c.startswith("t_") else 1)
            bad[c] += int(round(gv)) != e[c]
        for c in NUM_FIELDS + (
            "q0_open",
            "b0_open",
            "q1_close",
            "b1_close",
            "q_pool_last",
            "b_amt_last",
        ):
            bad[c] += int(g[c]) != e[c]
        for c in ("side_first", "side_last"):
            bad[c] += g[c] != e[c]
        kf = tuple(int(g[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))
        kl = tuple(int(g[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))
        bad["key_f"] += kf != e["key_f"]
        bad["key_l"] += kl != e["key_l"]
        users_diff += int(g["n_users"]) != e["n_users_exact"]
    lines.append(
        "- 分桶逐项不一致：" + ("全部为 0" if not any(bad.values()) else str(dict(bad)))
    )
    lines.append("- n_users（approx_distinct）与精确去重不同的桶：%d" % users_diff)
    lines.append(
        "- 越界计数合计：%d；费用空值计数合计：%d"
        % (
            sum(int(r["n_ord_overflow"]) for r in B),
            sum(int(r["n_fee_null"]) for r in B),
        )
    )

    # 4. P 层快照
    snap_bad, snap_n, inner_bad = defaultdict(int), 0, 0
    for pool, r in pools.items():
        es = ev.get(pool, [])
        for o in OFFSETS:
            if (
                r["a%d_q1" % o]
                and r["b%d_q0" % o]
                and r["a%d_q1" % o] != r["b%d_q0" % o]
            ):
                inner_bad += 1
            if created_ms[pool] + o * 1000 + 1000 > day_end_ms:
                continue
            snap_n += 1
            ea, eb = expected_snapshot(es, created_ms[pool], o)
            for pre, e, fs in (("a", ea, ("q1", "b1")), ("b", eb, ("q0", "b0"))):
                if e is None:
                    snap_bad["%s_missing" % pre] += r["%s%d_slot" % (pre, o)] != ""
                    continue
                key = tuple(
                    int(r["%s%d_%s" % (pre, o, x)])
                    for x in ("slot", "txi", "oix", "iix")
                )
                snap_bad["%s_key" % pre] += key != e["key"]
                for fld in fs:
                    snap_bad["%s_%s" % (pre, fld)] += (
                        int(r["%s%d_%s" % (pre, o, fld)]) != e[fld]
                    )
    lines.append(
        "- 快照：比对 %d 个（池×时点），不一致：%s"
        % (snap_n, "全部为 0" if not any(snap_bad.values()) else dict(snap_bad))
    )
    lines.append(
        "- 快照内部一致（时点前最后一笔成交后＝时点后第一笔成交前，全部时点）：不一致 %d"
        % inner_bad
    )

    # 5. 同一 SQL 两次运行
    if len(a) >= 5:
        lines.append("- B 层两次运行逐行一致：%s" % same_rows(B, read(a[3])))
        lines.append("- P 层两次运行逐行一致：%s" % same_rows(P, read(a[4])))
    out = H / "runs" / ("%s_compare.md" % blab)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""0 credits：紧凑首笔提取的本机风险集，直接调用冻结 label/collapse。

用于路线验证；不产生新的全量结果。评分仍检查冻结算法的一致性。
保留完整身份的正式 SQL；已下载样本仅有交易前缀，原有覆盖限制保留。
"""

from collections import defaultdict

import a_riskset as A
import s3_first_extract as F
import s3_ref as R
import s3_sql as S


def observation(created, cut, cap):
    end = min(created + 30 * 86400, R.CUTOFF_T, R.epoch(cap))
    return min(end, R.epoch(cut)) if created < R.epoch(cut) else end


def compress_detail(detail, w0, cut, w1end, cap):
    """对已有原始样本做 0 credits 压缩，用于验证与量体积。"""
    coins = {
        r["mint"]: int(r["t"])
        for r in detail
        if r["kind"] == "K" and R.epoch(w0) <= int(r["t"]) < R.epoch(w1end)
    }
    by_coin = defaultdict(list)
    for r in detail:
        if (
            r["kind"] == "T"
            and r["mint"] in coins
            and coins[r["mint"]]
            <= int(r["t"])
            < observation(coins[r["mint"]], cut, cap)
        ):
            by_coin[r["mint"]].append(r)
    out = []
    for r in detail:
        if r["kind"] in ("E", "K"):
            out.append({c: r.get(c) for c in F.COLS})
    candidates = []
    for mint, rs in by_coin.items():
        rs.sort(key=R._key)
        amounts = [int(r["amt"]) * (1 if int(r["b"]) else -1) for r in rs]
        cum = 0
        for i, r in enumerate(rs):
            if int(r["b"]):
                t = int(r["t"])
                old = sum(a for a, x in zip(amounts, rs) if int(x["t"]) <= t - 60)
                b = {c: r.get(c) for c in F.COLS}
                b.update(
                    kind="B",
                    pre=int(r["r4"]) + int(r["tok"]),
                    net60=cum - old,
                    sz=int(r["cash"]),
                )
                candidates.append(b)
            cum += amounts[i]
    candidates.extend({c: r.get(c) for c in F.COLS} for r in detail if r["kind"] == "A")
    first = {}
    for b in sorted(candidates, key=R._key):
        mint = b["mint"]
        if mint not in coins or int(b["t"]) + S.H_SEC >= observation(
            coins[mint], cut, cap
        ):
            continue
        key = (b["kind"], b["usr"], mint)
        first.setdefault(key, b)
    return out + list(first.values())


def reference(first, emap, w0, cut, w1end, cap):
    created = {
        r["mint"]: int(r["t"])
        for r in first
        if r["kind"] == "K" and R.epoch(w0) <= int(r["t"]) < R.epoch(w1end)
    }
    is_w = {m: c < R.epoch(cut) for m, c in created.items()}

    def entity(u):
        return emap.get(u, u)

    buys = []
    events = []
    for r in first:
        m = r["mint"]
        if m not in created:
            continue
        t = int(r["t"])
        end = observation(created[m], cut, cap)
        if r["kind"] in ("B", "A"):
            if not created[m] <= t < end:
                raise ValueError("买入越出逐币观察窗")
            st = (
                ("c", int(r["pre"]), int(r["net60"]), int(r["sz"]))
                if r["kind"] == "B"
                else ("a",)
            )
            buys.append(
                A.Buy(len(buys), entity(r["usr"]), m, t, R._key(r), r["tx"], st, end)
            )
        elif r["kind"] == "E" and created[m] <= t < end:
            events.append(A.Event(m, "grad", t, R._key(r), r["tx"], entity(r["usr"])))
    rows = A.collapse(A.label(buys, events, "grad", float(S.H_SEC)))
    times = {b.bid: b.ts for b in buys}
    for r in rows:
        r.update(is_w=is_w[r["coin"]], ts=times[r["bid"]])
    wc = [r for r in rows if r["is_w"] and r["state"][0] == "c"]
    edges = {
        lb: R._edges([r["state"][i] for r in wc], n)
        for lb, i, n in [("p", 1, 10), ("q", 2, 3), ("z", 3, 3)]
    }
    for r in rows:
        st = r["state"]
        r["state"] = (
            (
                "c",
                R._bin(st[1], edges["p"]),
                R._bin(st[2], edges["q"]),
                R._bin(st[3], edges["z"]),
                R._hour_bin(r["ts"]),
            )
            if st[0] == "c"
            else ("a", -1, -1, -1, -1)
        )
        r["stratum"] = (r["coin"], r["day"], r["state"], r["self"])
    result = R._summarize(rows, edges, created, is_w, events, emap)
    result["frozen_check"] = R.frozen_check(result)
    return result

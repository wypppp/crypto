#!/usr/bin/env python3
"""DQ-35 v2.2 毕业后小样本对照（10-05；GPT 批 1a-i 第 1～5 条）：用独立母体的逐笔原始事件（精确整数）与 Python 解码的 vq，
重算 B 层分桶、P 层快照（五个字段）、L 层加撤池与 boost、M 层母体计数，逐个字段比对。

python compare_sample_v22.py <B 层标签[,第二片,...]> <P 层标签或 -> <逐笔原始标签> [--b2 <B 第二次>] [--p2 <P 第二次>]
    [--m <M 层>] [--l <L 层>] [--raw-start YYYY-MM-DD] [--raw-end YYYY-MM-DD] [--out 输出名]
  → runs/<输出名>_compare.md

读取一律经 dev_gate：先读逐笔样本的 'C'／'X' 行定出开发池，再流式读数值文件，非开发池与 10-05 起的行在解析时丢弃。
所有键先查重复再建索引；报告逐项列出比对的字段名。只核对齐全、精度与一致性，不看价格或收益分布。
"""

import datetime as dt
import gzip
import csv
import math
import sys
from collections import Counter, defaultdict

import dev_gate as g
import rawdecode_v22 as rd
from compare_sample_v21 import (
    bucket,
    epoch,
    is_true,
    kint,
    post_state,
    same_rows,
    vq_interval_sell,
)
from dune_get import H

OFFSETS = (2, 10, 45, 60, 75, 900, 3600, 86400)
VQ_START = dt.datetime(2026, 7, 15)
VQ_START_MS = int((VQ_START - dt.datetime(1970, 1, 1)).total_seconds() * 1000)
END_MS = int(
    (dt.datetime(2026, 10, 5) - dt.datetime(1970, 1, 1)).total_seconds() * 1000
)
B_INT = (
    "q_buy_user",
    "q_sell_user",
    "q_buy_pool",
    "q_sell_pool",
    "b_buy",
    "b_sell",
    "f_lp",
    "f_pr",
    "f_cr",
    "q0_open",
    "b0_open",
    "q1_close",
    "b1_close",
    "q_pool_last",
    "b_amt_last",
)
B_OPT = (
    "f_cb_buy",
    "f_bb_buy",
    "f_cb_sell",
    "f_bb_sell",
    "vq_open",
    "vq_close",
    "vq_min",
    "vq_max",
)
B_CNT = (
    "n",
    "n_buy",
    "n_fee_null",
    "n_cb_null",
    "n_bb_null",
    "n_vq_null",
    "n_vq_ovf",
    "n_xchk",
    "n_xchk_fail",
    "n_xchk_skip",
    "n_px_null",
    "n_ord_overflow",
)
B_STR = ("side_first", "side_last", "tx_f", "tx_l", "vq_src")
SIDE = {"B": "B", "S": "S"}


def opt_int(s):
    return None if s in ("", None) else kint(s)


def key_of(r):
    return (
        kint(r["slot"]),
        kint(r["txi"]),
        kint(r["oix"]),
        kint(r["iix"]) if r["iix"] not in ("", None) else -1,
    )


def dups(items):
    c = Counter(items)
    return sum(v - 1 for v in c.values() if v > 1)


def guard_ok(b0, b_in, q_out):
    """与 SQL 相同的量级限制：b0＋b_in＜1e19、quote_out＋1＜1e18 才做区间核对。"""
    return b_in > 0 and b0 + b_in < 10**19 and q_out + 1 < 10**18


def px(q1, vq, b1, qd, bd):
    if vq is None or b1 == 0:
        return None
    return ((float(q1) + float(vq)) / 10**qd) / (float(b1) / 10**bd)


def build_events(rows, rrows, created_ms):
    """原始行 → 每池按事件键排序的成交、加撤池、boost；vq 由 Python 解析 'R' 行（07-15 之前按布局记 0）。"""
    rmap, rk = {}, []
    for r in rrows:
        k = (r["tx_id"], kint(r["oix"]), kint(r["iix"]), r["usr"])
        rk.append(k)
        rmap[k] = r
    out, lp, boost = defaultdict(list), defaultdict(list), defaultdict(list)
    keys = []
    for r in rows:
        ev = r["ev"]
        if ev in ("B", "S"):
            q_amt, q_lp, lpf = (
                int(r["q_amt"]),
                int(r["q_amt_lp"] or 0),
                int(r["f_lp"] or 0),
            )
            q_pool = q_lp if ev == "B" else q_amt - lpf
            t = epoch(r["ts"])
            k = key_of(r)
            keys.append((r["pool"], k, ev))
            e = dict(
                side=ev,
                key=k,
                t=t,
                usr=r["usr"],
                tx=r["tx_id"],
                q0=int(r["q0"]),
                b0=int(r["b0"]),
                q_pool=q_pool,
                b_amt=int(r["b_amt"]),
                q_user=int(r["q_user"]),
                f_lp=lpf,
                f_pr=opt_int(r["f_pr"]),
                f_cr=opt_int(r["f_cr"]),
                q_gross=q_amt,
                f_cb=opt_int(r["f_cb"]) if ev == "S" else None,
                f_bb=opt_int(r["f_bb"]) if ev == "S" else None,
            )
            if t < VQ_START_MS:
                e["vq"], e["vq_src"] = 0, "layout0"
            else:
                rr = rmap.get((r["tx_id"], k[2], k[3], ev))
                if rr is None:
                    e["vq"], e["vq_src"] = None, "missing"
                else:
                    d = rd.parse(ev, rr["q0"])
                    # 布局里没有 vq 字段（升级前的事件）：按协议为 0
                    e["vq"], e["vq_src"] = (
                        (d["vq"], "raw") if d["vq"] is not None else (0, "layout0")
                    )
                    if ev == "B":
                        e["f_cb"], e["f_bb"] = d["cb"], d["bb"]
            e["q1"], e["b1"] = post_state(ev, e["q0"], e["b0"], e["q_pool"], e["b_amt"])
            e["xchk"] = None
            if ev == "S" and guard_ok(e["b0"], e["b_amt"], e["q_gross"]):
                lo, hi = vq_interval_sell(e["q0"], e["b0"], e["b_amt"], e["q_gross"])
                e["xchk"] = (lo, hi)
            out[r["pool"]].append(e)
        elif ev in ("D", "W"):
            k = key_of(r)
            sg = 1 if ev == "D" else -1
            q0, b0 = int(r["q0"]), int(r["b0"])
            dq, db = sg * int(r["q_amt"]), sg * int(r["b_amt"])
            lp[r["pool"]].append(
                dict(
                    kind=ev,
                    key=k,
                    t=epoch(r["ts"]),
                    tx=r["tx_id"],
                    q0=q0,
                    b0=b0,
                    q1=q0 + dq,
                    b1=b0 + db,
                    dq=dq,
                    db=db,
                    vq=None,
                )
            )
    for r in rrows:
        if r["usr"] in ("I", "U"):
            d = rd.parse(r["usr"], r["q0"])
            boost[r["pool"]].append(
                dict(
                    kind=r["usr"],
                    key=key_of(r),
                    t=epoch(r["ts"]),
                    tx=r["tx_id"],
                    q0=None,
                    b0=None,
                    q1=d["q1"],
                    b1=d["b1"],
                    vq=d["vq"],
                )
            )
    for d_ in (out, lp, boost):
        for v in d_.values():
            v.sort(key=lambda e: e["key"])
    return out, lp, boost, dups(keys), dups(rk)


def expected_buckets(ev, created_ms, meta):
    agg = defaultdict(list)
    for pool, es in ev.items():
        for e in es:
            kind, bkey = bucket(e["t"] - created_ms[pool])
            agg[(kind, pool, bkey)].append(e)
    rows = {}
    for (kind, pool, bkey), es in agg.items():
        f, last = es[0], es[-1]
        qd, bd = meta[pool]
        s = defaultdict(int)
        for e in es:
            sd = "buy" if e["side"] == "B" else "sell"
            s["q_%s_user" % sd] += e["q_user"]
            s["q_%s_pool" % sd] += e["q_pool"]
            s["b_%s" % sd] += e["b_amt"]
            s["f_lp"] += e["f_lp"]
            s["f_pr"] += e["f_pr"] or 0
            s["f_cr"] += e["f_cr"] or 0

        def osum(side, f_):
            v = [e[f_] for e in es if e["side"] == side and e[f_] is not None]
            return sum(v) if v else None

        vqs = [e["vq"] for e in es if e["vq"] is not None]
        xs = [e for e in es if e["xchk"] is not None]
        pxs = [
            p
            for p in (px(e["q1"], e["vq"], e["b1"], qd, bd) for e in es)
            if p is not None
        ]
        rows[(kind, pool, bkey)] = dict(
            n=len(es),
            n_buy=sum(e["side"] == "B" for e in es),
            users=set(e["usr"] for e in es),
            n_fee_null=sum(e["f_pr"] is None or e["f_cr"] is None for e in es),
            n_cb_null=sum(e["f_cb"] is None for e in es),
            n_bb_null=sum(e["f_bb"] is None for e in es),
            n_vq_null=sum(e["vq"] is None for e in es),
            n_vq_ovf=0,
            n_xchk=len(xs),
            n_xchk_fail=sum(
                1
                for e in xs
                if e["vq"] is not None and not (e["xchk"][0] <= e["vq"] <= e["xchk"][1])
            ),
            n_xchk_skip=sum(1 for e in es if e["side"] == "S" and e["xchk"] is None),
            n_px_null=len(es) - len(pxs),
            n_ord_overflow=0,
            q0_open=f["q0"],
            b0_open=f["b0"],
            q1_close=last["q1"],
            b1_close=last["b1"],
            q_pool_last=last["q_pool"],
            b_amt_last=last["b_amt"],
            side_first=f["side"],
            side_last=last["side"],
            tx_f=f["tx"],
            tx_l=last["tx"],
            vq_src=f["vq_src"],
            key_f=f["key"],
            key_l=last["key"],
            t_first=f["t"],
            t_last=last["t"],
            f_cb_buy=osum("B", "f_cb"),
            f_bb_buy=osum("B", "f_bb"),
            f_cb_sell=osum("S", "f_cb"),
            f_bb_sell=osum("S", "f_bb"),
            vq_open=f["vq"],
            vq_close=last["vq"],
            vq_min=min(vqs) if vqs else None,
            vq_max=max(vqs) if vqs else None,
            px_high=max(pxs) if pxs else None,
            px_low=min(pxs) if pxs else None,
            **{
                c: s[c]
                for c in (
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
            },
        )
    return rows


def merge_v22(rows):
    """跨片合并（v2.2 字段）：计数与金额相加；首末取事件键最小／最大的行；vq、价格取极值；用户名单并集。"""
    by = defaultdict(list)
    for r in rows:
        by[(r["kind"], r["pool"], kint(r["bkey"]))].append(r)
    out = {}
    for k, rs in by.items():
        if len(rs) == 1:
            out[k] = dict(rs[0], n_merged=1)
            continue
        kf = lambda r: tuple(kint(r[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))  # noqa: E731
        kl = lambda r: tuple(kint(r[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))  # noqa: E731
        f, last = min(rs, key=kf), max(rs, key=kl)
        m = dict(f)
        for c in B_CNT + (
            "q_buy_user",
            "q_sell_user",
            "q_buy_pool",
            "q_sell_pool",
            "b_buy",
            "b_sell",
            "f_lp",
            "f_pr",
            "f_cr",
        ):
            m[c] = str(sum(kint(r[c]) for r in rs if r[c] != ""))
        for c in ("f_cb_buy", "f_bb_buy", "f_cb_sell", "f_bb_sell"):
            v = [kint(r[c]) for r in rs if r[c] != ""]
            m[c] = str(sum(v)) if v else ""
        for c in (
            "slot_l",
            "txi_l",
            "oix_l",
            "iix_l",
            "tx_l",
            "q1_close",
            "b1_close",
            "side_last",
            "q_pool_last",
            "b_amt_last",
            "vq_close",
        ):
            m[c] = last[c]
        for c, fn in (("vq_min", min), ("vq_max", max)):
            v = [kint(r[c]) for r in rs if r[c] != ""]
            m[c] = str(fn(v)) if v else ""
        for c, fn in (("px_high", max), ("px_low", min)):
            v = [float(r[c]) for r in rs if r[c] != ""]
            m[c] = str(fn(v)) if v else ""
        m["t_first"] = str(min(float(r["t_first"]) for r in rs))
        m["t_last"] = str(max(float(r["t_last"]) for r in rs))
        users = set()
        for r in rs:
            users |= set(u for u in r["users_straddle"].split(",") if u)
        m["users_straddle"] = ",".join(sorted(users))
        m["straddle"] = "true" if all(is_true(r["straddle"]) for r in rs) else "false"
        m["n_users"] = str(len(users)) if is_true(m["straddle"]) else m["n_users"]
        m["n_merged"] = len(rs)
        out[k] = m
    return out


def expected_snapshots(stream, created_ms, o, cover_end_ms):
    """时点 T＝建池＋o 秒（毫秒取整到秒，与 SQL 的 created_at＋INTERVAL 一致）：之前最后一个事件、之后第一个事件、五个字段。"""
    tt = created_ms + o * 1000
    before = [e for e in stream if e["t"] < tt]
    after = [e for e in stream if e["t"] >= tt]
    a = before[-1] if before else None
    b = after[0] if after else None
    vqs = [e for e in before if e.get("vq") is not None]
    nboost = sum(1 for e in before if e["kind"] in ("I", "U"))
    if tt >= END_MS:
        cov = "immature"
    elif a is not None and a["kind"] == "I":
        cov = "partial"
    elif b is None:
        cov = "no_next"
    elif None in (a["q1"], a["b1"], b["q0"], b["b0"]):
        cov = "unverified"
    elif (a["q1"], a["b1"]) != (b["q0"], b["b0"]):
        cov = "gap"
    else:
        cov = "ok"
    return dict(
        a=a,
        b=b,
        vq=vqs[-1]["vq"] if vqs else None,
        nboost=nboost,
        cov=cov,
        tt=tt,
        b_beyond=b is None and tt < cover_end_ms,
    )


def opt(a, name, default=None):
    if name in a:
        k = a.index(name)
        v = a[k + 1]
        del a[k : k + 2]
        return v
    return default


def main():
    a = sys.argv[1:]
    b2, p2, mlab, llab = opt(a, "--b2"), opt(a, "--p2"), opt(a, "--m"), opt(a, "--l")
    raw_start, raw_end, out_name = (
        opt(a, "--raw-start"),
        opt(a, "--raw-end"),
        opt(a, "--out"),
    )
    blabs, plab, rawlab = a[0].split(","), a[1], a[2]
    lines = [
        "# DQ-35 v2.2 小样本对照：%s / %s 对 %s" % ("+".join(blabs), plab, rawlab),
        "",
    ]

    # 0. 入口：只读 'C'／'X' 行定开发池；再流式读数值
    crow_all, xrow = g.read_meta(rawlab, "ev", "pool")
    keep, n_drop = g.dev_ids_from_meta(crow_all, "pool", "q_user")
    crow = {r["pool"]: r for r in crow_all if r["pool"] in keep}
    xcnt = {r["pool"]: kint(r["q0"]) for r in xrow}
    raw, raw_drop = g.stream(rawlab, "pool", keep, time_col="ts")
    rows = [r for r in raw if r["ev"] not in ("C", "X", "R")]
    rrows = [r for r in raw if r["ev"] == "R"]
    created_ms = {p: epoch(r["ts"]) for p, r in crow.items()}
    # 建池时刻取整到秒（SQL 的 created_at 是秒级时间戳）
    lines.append(
        "- 入口（dev_gate）：独立母体 %d 个池，其中开发池 %d 个、剔除 %d 个（检验周或前向批次），数值文件解析时丢弃 %d 行"
        % (len(crow_all), len(keep), n_drop, raw_drop)
    )

    # 1. 母体：P 层池集合（只读池名列）与独立候选；M 层计数恒等
    if plab != "-":
        # 只读池名一列（元数据），不按候选过滤，P 层多出的池也能查出
        with gzip.open(g.RAW / ("%s.csv.gz" % plab), "rt", newline="") as f:
            p_all = [r["pool"] for r in csv.DictReader(f)]
        lines.append(
            "- 母体：独立候选 %d 个池，P 层 %d 个，集合相同：%s；P 层池键重复 %d"
            % (
                len(crow_all),
                len(p_all),
                set(p_all) == set(r["pool"] for r in crow_all),
                dups(p_all),
            )
        )
    if mlab:
        m = next(
            iter(
                csv.DictReader(
                    gzip.open(g.RAW / ("%s.csv.gz" % mlab), "rt", newline="")
                )
            )
        )
        exp_m = dict(
            n_included=len(crow_all),
            n_sealed=xcnt.get("sealed", 0),
            n_holdout_name=xcnt.get("holdout_name", 0),
            n_no_curve_create=xcnt.get("no_create", 0),
            n_no_symbol=xcnt.get("no_symbol", 0),
            identity_gap=0,
        )
        mbad = {k: (kint(m[k]), v) for k, v in exp_m.items() if kint(m[k]) != v}
        tot = sum(
            kint(m[c])
            for c in (
                "n_no_curve_create",
                "n_sealed",
                "n_no_symbol",
                "n_holdout_name",
                "n_included",
            )
        )
        lines.append(
            "- M 层（字段 n_included、n_sealed、n_holdout_name、n_no_curve_create、n_no_symbol、identity_gap）与独立候选：%s；类别合计 %d＝候选 %d：%s；计价分层 SOL %s／USDC %s／其他 %s"
            % (
                "一致" if not mbad else "不一致 %s" % mbad,
                tot,
                kint(m["n_candidate"]),
                tot == kint(m["n_candidate"]),
                m["n_included_sol"],
                m["n_included_usdc"],
                m["n_included_other"],
            )
        )

    # 2. 事件、重复、守恒、vq
    ev, lp, boost, dup_ev, dup_r = build_events(rows, rrows, created_ms)
    lines.append("- 事件键重复：成交 %d，原始字节 'R' 行 %d" % (dup_ev, dup_r))
    src = Counter(e["vq_src"] for es in ev.values() for e in es)
    lines.append("- vq 来源（Python 解析 'R' 行）：%s" % dict(src))
    cont = tot = lpb = 0
    for pool, es in ev.items():
        ks = [e["key"] for e in lp.get(pool, []) + boost.get(pool, [])]
        for p_, q_ in zip(es, es[1:]):
            if any(p_["key"] < k < q_["key"] for k in ks):
                lpb += 1
                continue
            tot += 1
            cont += (q_["q0"], q_["b0"]) == (p_["q1"], p_["b1"])
    lines.append(
        "- 储备逐笔守恒：%d / %d（另 %d 对之间夹着加撤池或 boost，不计）"
        % (cont, tot, lpb)
    )
    first_ok = sum(
        1
        for p, es in ev.items()
        if es
        and (es[0]["q0"], es[0]["b0"])
        == (kint(crow[p]["b_amt"]), kint(crow[p]["f_lp"]))
        and not lp.get(p)
    )
    lines.append(
        "- 建池后储备（C 行 pool_*_amount）＝首笔成交前储备：%d / %d 个有成交且无加撤池的池"
        % (first_ok, sum(1 for p, es in ev.items() if es and not lp.get(p)))
    )

    # 3. B 层
    meta_qd = {p: (kint(r["b0"]), kint(r["q_amt_lp"])) for p, r in crow.items()}
    B, dup_in_slice = [], 0
    for lab in blabs:
        part = g.stream(lab, "pool", keep)[0]
        dup_in_slice += dups([(r["kind"], r["pool"], kint(r["bkey"])) for r in part])
        B += part
    got = merge_v22(B)
    exp = expected_buckets(ev, created_ms, meta_qd)
    lines.append(
        "- B 层：%d 行（%d 片，片内键重复 %d），合并后 %d（跨片合并 %d），逐笔重算 %d，键集合相同：%s"
        % (
            len(B),
            len(blabs),
            dup_in_slice,
            len(got),
            sum(1 for r in got.values() if r["n_merged"] > 1),
            len(exp),
            set(got) == set(exp),
        )
    )
    bad = defaultdict(int)
    users_diff = smem = 0
    for k in set(got) & set(exp):
        gr, e = got[k], exp[k]
        for c in B_CNT:
            bad[c] += kint(gr[c]) != e[c]
        for c in B_INT:
            bad[c] += kint(gr[c]) != e[c]
        for c in B_OPT:
            bad[c] += opt_int(gr[c]) != e[c]
        for c in B_STR:
            bad[c] += gr[c] != e[c]
        for c in ("t_first", "t_last"):
            bad[c] += int(round(float(gr[c]) * 1000)) != e[c]
        for c in ("px_high", "px_low"):
            gv = float(gr[c]) if gr[c] != "" else None
            ev_ = e[c]
            bad[c] += not (
                (gv is None and ev_ is None)
                or (
                    gv is not None
                    and ev_ is not None
                    and math.isclose(gv, ev_, rel_tol=1e-9)
                )
            )
        bad["key_f"] += (
            tuple(kint(gr[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))
            != e["key_f"]
        )
        bad["key_l"] += (
            tuple(kint(gr[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))
            != e["key_l"]
        )
        if is_true(gr["straddle"]):
            smem += set(u for u in gr["users_straddle"].split(",") if u) != e["users"]
        users_diff += kint(gr["n_users"]) != len(e["users"])
    fields = (
        list(B_CNT)
        + list(B_INT)
        + list(B_OPT)
        + list(B_STR)
        + ["t_first", "t_last", "px_high", "px_low", "key_f", "key_l"]
    )
    lines.append(
        "- B 层逐字段（%d 个字段：%s）不一致：%s"
        % (
            len(fields),
            "、".join(fields),
            "全部为 0"
            if not any(bad.values())
            else dict((k, v) for k, v in bad.items() if v),
        )
    )
    lines.append(
        "- B 层跨片桶用户名单（逐成员）不一致：%d；n_users（approx_distinct）与精确去重不同的桶：%d"
        % (smem, users_diff)
    )
    lines.append(
        "- B 层合计：越界 %d、vq 缺失 %d、vq 溢出 %d、交叉核对越界 %d（共核 %d 笔、未核 %d 笔）、价格空 %d"
        % tuple(
            sum(kint(r[c]) for r in B)
            for c in (
                "n_ord_overflow",
                "n_vq_null",
                "n_vq_ovf",
                "n_xchk_fail",
                "n_xchk",
                "n_xchk_skip",
                "n_px_null",
            )
        )
    )

    # 4. L 层
    if llab:
        L, _ = g.stream(llab, "pool", keep)
        lk = [(r["pool"], key_of(r), r["kind"]) for r in L]
        got_l = {(r["pool"], key_of(r), r["kind"]): r for r in L}
        exp_l = {}
        for pool, es in lp.items():
            for e in es:
                exp_l[(pool, e["key"], e["kind"])] = (
                    e["dq"],
                    e["db"],
                    e["q0"],
                    e["tx"],
                    None,
                    None,
                    None,
                )
        for pool, es in boost.items():
            for e in es:
                exp_l[(pool, e["key"], e["kind"])] = (
                    None,
                    None,
                    None,
                    e["tx"],
                    e["q1"],
                    e["b1"],
                    e["vq"],
                )
        lbad = 0
        for k in set(got_l) & set(exp_l):
            r = got_l[k]
            gv = (
                opt_int(r["dq"]),
                opt_int(r["db"]),
                opt_int(r["q0"]),
                r["tx_id"],
                opt_int(r["q1_after"]),
                opt_int(r["b1_after"]),
                opt_int(r["vq"]),
            )
            lbad += gv != exp_l[k]
        lines.append(
            "- L 层（字段 kind、事件键、dq、db、q0、tx_id、q1_after、b1_after、vq）：SQL %d 行（键重复 %d），逐笔 %d（加撤池 %d、boost %d），键集合相同：%s，逐项不一致 %d，越界 %d"
            % (
                len(L),
                dups(lk),
                len(exp_l),
                sum(len(v) for v in lp.values()),
                sum(len(v) for v in boost.values()),
                set(got_l) == set(exp_l),
                lbad,
                sum(kint(r["ovf"]) for r in L),
            )
        )

    # 5. P 层快照（五个字段）与 7 天字段
    if plab != "-":
        cover_end = (
            (dt.date.fromisoformat(raw_end) - dt.date(1970, 1, 1)).days * 86_400_000
            + 86_400_000
            if raw_end
            else END_MS
        )
        cover_start = (
            (dt.date.fromisoformat(raw_start) - dt.date(1970, 1, 1)).days * 86_400_000
            if raw_start
            else 0
        )
        P, _ = g.stream(plab, "pool", keep)
        sb = defaultdict(int)
        n_cmp = n_beyond = p7n = p7b = 0
        for r in P:
            pool = r["pool"]
            cms = int(round(float(r["created_t"]) * 1000))
            sb["created_t"] += cms != created_ms[pool]
            sb["c_q"] += kint(r["c_q"]) != kint(crow[pool]["b_amt"])
            sb["c_b"] += kint(r["c_b"]) != kint(crow[pool]["f_lp"])
            if cms < cover_start:
                continue
            c = crow[pool]
            cr = dict(
                kind="C",
                key=key_of(c),
                t=cms,
                tx=c["tx_id"],
                q0=None,
                b0=None,
                q1=kint(c["b_amt"]),
                b1=kint(c["f_lp"]),
                vq=None,
            )
            horizon = cms + 7 * 86_400_000
            st = sorted(
                [cr]
                + [
                    dict(e, kind=e["side"])
                    for e in ev.get(pool, [])
                    if e["t"] < horizon
                ]
                + [e for e in lp.get(pool, []) if e["t"] < horizon]
                + [e for e in boost.get(pool, []) if e["t"] < horizon],
                key=lambda e: e["key"],
            )
            if horizon <= cover_end:
                p7n += 1
                tr = [e for e in st if e["kind"] in ("B", "S")]
                vq7 = [e["vq"] for e in st if e.get("vq") is not None]
                got7 = (
                    kint(r["n_7d"]),
                    kint(r["n_lp_7d"]),
                    kint(r["n_boost_7d"]),
                    opt_int(r["vq_min_7d"]),
                    opt_int(r["vq_max_7d"]),
                )
                p7b += got7 != (
                    len(tr),
                    sum(e["kind"] in ("D", "W") for e in st),
                    sum(e["kind"] in ("I", "U") for e in st),
                    min(vq7) if vq7 else None,
                    max(vq7) if vq7 else None,
                )
            for o in OFFSETS:
                if cms + o * 1000 >= cover_end:
                    continue
                n_cmp += 1
                x = expected_snapshots(st, cms, o, cover_end)
                sb["target_time"] += (
                    int(round(float(r["target%d_time" % o]) * 1000)) != x["tt"]
                )
                a_, b_ = x["a"], x["b"]
                sb["a_key"] += (
                    tuple(
                        kint(r["a%d_%s" % (o, f)])
                        for f in ("slot", "txi", "oix", "iix")
                    )
                    if r["a%d_slot" % o] != ""
                    else None
                ) != (a_["key"] if a_ else None)
                for f, ef in (("kind", "kind"), ("tx", "tx")):
                    sb["a_" + f] += (r["a%d_%s" % (o, f)] or None) != (
                        a_[ef] if a_ else None
                    )
                for f in ("q1", "b1"):
                    sb["a_" + f] += opt_int(r["a%d_%s" % (o, f)]) != (
                        a_[f] if a_ else None
                    )
                st_t = (
                    int(round(float(r["state%d_time" % o]) * 1000))
                    if r["state%d_time" % o] != ""
                    else None
                )
                sb["state_time"] += st_t != (a_["t"] if a_ else None)
                sb["known_at"] += r["known%d_at" % o] != r["state%d_time" % o]
                sb["vq"] += opt_int(r["vq%d" % o]) != x["vq"]
                sb["nboost"] += kint(r["nboost%d" % o]) != x["nboost"]
                if (
                    b_ is None
                    and r["b%d_slot" % o] != ""
                    and float(r["b%d_t" % o]) * 1000 >= cover_end
                ):
                    n_beyond += (
                        1  # 时点后第一个事件在原始文件覆盖期之后：b 侧与 coverage 不比
                    )
                    continue
                sb["b_key"] += (
                    tuple(
                        kint(r["b%d_%s" % (o, f)])
                        for f in ("slot", "txi", "oix", "iix")
                    )
                    if r["b%d_slot" % o] != ""
                    else None
                ) != (b_["key"] if b_ else None)
                for f in ("kind", "tx"):
                    sb["b_" + f] += (r["b%d_%s" % (o, f)] or None) != (
                        b_[f] if b_ else None
                    )
                for f in ("q0", "b0"):
                    sb["b_" + f] += opt_int(r["b%d_%s" % (o, f)]) != (
                        b_[f] if b_ else None
                    )
                sb["coverage"] += r["coverage%d" % o] != x["cov"]
                sb["gap_flag"] += is_true(r["gap%d_flag" % o]) != (x["cov"] != "ok")
        sfields = [
            "created_t",
            "c_q",
            "c_b",
            "target_time",
            "state_time",
            "known_at",
            "coverage",
            "gap_flag",
            "vq",
            "nboost",
            "a_key",
            "a_kind",
            "a_tx",
            "a_q1",
            "a_b1",
            "b_key",
            "b_kind",
            "b_tx",
            "b_q0",
            "b_b0",
        ]
        cov_cnt = Counter(r["coverage%d" % o] for r in P for o in OFFSETS)
        lines.append(
            "- P 层快照：比对 %d 个（池×时点）；逐字段（%s）不一致：%s；时点后第一个事件在覆盖期之后（b 侧与 coverage 不比）%d"
            % (
                n_cmp,
                "、".join(sfields),
                "全部为 0"
                if not any(sb.values())
                else dict((k, v) for k, v in sb.items() if v),
                n_beyond,
            )
        )
        lines.append("- P 层 coverage 分布（全部池×时点，SQL 值）：%s" % dict(cov_cnt))
        lines.append(
            "- P 层 7 天字段（n_7d、n_lp_7d、n_boost_7d、vq_min_7d、vq_max_7d）：比对 %d 个池，不一致 %d"
            % (p7n, p7b)
        )

    # 6. 同一 SQL 两次运行
    if b2:
        lines.append(
            "- B 层两次运行逐行一致（全部行、全部列）：%s"
            % same_rows(
                g.stream(blabs[0], "pool", keep)[0], g.stream(b2, "pool", keep)[0]
            )
        )
    if p2:
        lines.append(
            "- P 层两次运行逐行一致（全部行、全部列）：%s"
            % same_rows(g.stream(plab, "pool", keep)[0], g.stream(p2, "pool", keep)[0])
        )
    out = H / "runs" / ("%s_compare.md" % (out_name or blabs[0]))
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

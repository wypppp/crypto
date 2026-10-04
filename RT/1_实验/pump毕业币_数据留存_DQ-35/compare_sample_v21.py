#!/usr/bin/env python3
"""DQ-35 v2.1 小样本对照（10-04）：用逐笔原始事件（精确整数）重算 B 层分桶与 P 层快照，逐项比对。

python compare_sample_v21.py <B 层标签[,第二片,...]> <P 层标签> <逐笔原始标签> [<B 第二次运行标签> <P 第二次运行标签>]
    [--raw-end YYYY-MM-DD] [--out 输出名]
  → runs/<输出名或 B 层第一个标签>_compare.md
- 逐笔原始文件来自 build_sample_raw_v21.py（独立母体，有 'C' 行）或 build_sample_raw_v2.py（无 'C' 行，退回以 P 层为母体并注明）。
- B 层给多个标签（逗号分隔）时，先按跨片合并规则（merge_buckets）合并，再与逐笔重算比对。
- --raw-end：逐笔原始文件覆盖的最后一个事件日（缺省取原始事件最晚日期）；快照与 7 天池级字段只比对完全落在覆盖期内的。
只核对齐全、精度与一致性，不看价格或收益分布。
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


def dev_week(epoch_s):
    """曲线创建 epoch 秒是否在 DQ-37 开发周（weeks.py 冻结，只调用不修改）。"""
    import datetime as dt

    sys.path.insert(0, str(H.parent / "发射台_前期右尾评测底座_DQ-37"))
    import weeks

    d = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=epoch_s)
    return weeks.is_dev(d.date().isoformat())


def is_true(s):
    """布尔列：下载脚本经 pandas 写成 True／False，Dune 网页导出为 true／false，两种都认。"""
    return str(s).strip().lower() == "true"


def kint(s):
    """整数列：同一列含 NULL 时 Dune 以浮点文本返回（如 "7.0"），按十进制精确解析。"""
    from decimal import Decimal

    return int(Decimal(s))


def epoch(ts):
    """'2025-10-07 01:35:00.000 UTC' → epoch 秒（整数毫秒精度，返回毫秒）。"""
    import datetime as dt

    d = dt.datetime.strptime(ts.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S.%f")
    return int(round((d - dt.datetime(1970, 1, 1)).total_seconds() * 1000))


def vq_interval_sell(q0, b0, b_in, q_out):
    """卖出反解虚拟报价储备 vq 的整数区间：q_out＝floor((q0＋vq)·b_in／(b0＋b_in)) 成立的全部 vq。"""
    d = b0 + b_in
    lo = -(-q_out * d // b_in) - q0
    hi = -(-(q_out + 1) * d // b_in) - 1 - q0
    return lo, hi


def merge_buckets(rows):
    """跨片合并：同一 (kind, pool, bkey) 的多行合成一行（README §1c 的合并规则）。
    笔数、金额、费用、计数相加；首笔取事件键最小的一行，末笔取最大的一行；高低取极值；
    vq 取下界最大、上界最小；跨片桶的用户数取名单并集（只有全部行都是跨片桶时才精确）。"""
    by = defaultdict(list)
    for r in rows:
        by[(r["kind"], r["pool"], int(r["bkey"]))].append(r)
    out = {}
    for k, rs in by.items():
        if len(rs) == 1:
            out[k] = dict(rs[0])
            continue
        kf = lambda r: tuple(int(r[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))  # noqa: E731
        kl = lambda r: tuple(int(r[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))  # noqa: E731
        f, last = min(rs, key=kf), max(rs, key=kl)
        m = dict(f)
        for c in (
            "n",
            "n_buy",
            "n_fee_null",
            "n_vq_obs",
            "n_px_unknown",
            "n_ord_overflow",
        ) + NUM_FIELDS:
            m[c] = str(sum(int(r[c]) for r in rs))
        for c in ("f_cb_sell", "f_bb_sell"):
            v = [int(r[c]) for r in rs if r[c] != ""]
            m[c] = str(sum(v)) if v else ""
        for c in (
            "slot_l",
            "txi_l",
            "oix_l",
            "iix_l",
            "q1_close",
            "b1_close",
            "side_last",
            "q_pool_last",
            "b_amt_last",
        ):
            m[c] = last[c]
        m["t_first"] = str(min(float(r["t_first"]) for r in rs))
        m["t_last"] = str(max(float(r["t_last"]) for r in rs))
        lo = [int(r["vq_lo"]) for r in rs if r["vq_lo"] != ""]
        hi = [int(r["vq_hi"]) for r in rs if r["vq_hi"] != ""]
        m["vq_lo"] = str(max(lo)) if lo else ""
        m["vq_hi"] = str(min(hi)) if hi else ""
        ph = [float(r["px_high"]) for r in rs if r["px_high"] != ""]
        pl = [float(r["px_low"]) for r in rs if r["px_low"] != ""]
        m["px_high"] = str(max(ph)) if ph else ""
        m["px_low"] = str(min(pl)) if pl else ""
        users = set()
        for r in rs:
            users |= set(u for u in r["users_straddle"].split(",") if u)
        m["users_straddle"] = ",".join(sorted(users))
        m["straddle"] = "true" if all(is_true(r["straddle"]) for r in rs) else "false"
        m["n_users"] = str(len(users)) if is_true(m["straddle"]) else m["n_users"]
        m["n_merged"] = len(rs)
        out[k] = m
    return out


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
            key=(kint(r["slot"]), kint(r["txi"]), kint(r["oix"]), kint(r["iix"] or -1)),
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
        e["f_cb"] = int(r["f_cb"]) if r["ev"] == "S" and r["f_cb"] else None
        e["f_bb"] = int(r["f_bb"]) if r["ev"] == "S" and r["f_bb"] else None
        e["vq"] = (
            vq_interval_sell(e["q0"], e["b0"], e["b_amt"], q_amt)
            if r["ev"] == "S" and e["b_amt"] > 0
            else None
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
        vs = [e["vq"] for e in es if e["vq"] is not None]
        cb = [e["f_cb"] for e in es if e["f_cb"] is not None]
        bb = [e["f_bb"] for e in es if e["f_bb"] is not None]
        rows[k] = dict(
            vq_lo=max(v[0] for v in vs) if vs else None,
            vq_hi=min(v[1] for v in vs) if vs else None,
            n_vq_obs=len(vs),
            f_cb_sell=sum(cb) if cb else None,
            f_bb_sell=sum(bb) if bb else None,
            users=a["users"],
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


def opt(a, name, default=None):
    if name in a:
        k = a.index(name)
        v = a[k + 1]
        del a[k : k + 2]
        return v
    return default


def main():
    import datetime as dt

    a = sys.argv[1:]
    raw_end = opt(a, "--raw-end")
    out_name = opt(a, "--out")
    mlab = opt(a, "--m")
    llab = opt(a, "--l")
    blabs, plab, rawlab = a[0].split(","), a[1], a[2]
    B = [r for lab in blabs for r in read(lab)]
    P, raw = (
        ([] if plab == "-" else read(plab)),
        read(rawlab),
    )  # "-"：该样本没有 P 层（老池单日）
    pools = {r["pool"]: r for r in P}
    crow = {r["pool"]: r for r in raw if r["ev"] == "C"}
    xrow = {r["pool"]: int(r["q0"]) for r in raw if r["ev"] == "X"}
    # 入口过滤：曲线创建在 DQ-37 检验周的池不进入任何比对计算（只参与池集合核对）
    test_drop = {p for p, r in crow.items() if not dev_week(float(r["q_user"]))}
    base = (set(crow) - test_drop) if crow else set(pools)
    if crow:
        # 建池时刻以独立候选为准，另核 P 层的 created_t
        created_ms = {p: epoch(r["ts"]) for p, r in crow.items()}
        ct_bad = sum(
            1
            for p in set(crow) & set(pools)
            if int(round(float(pools[p]["created_t"]) * 1000)) != created_ms[p]
        )
    else:
        created_ms = {
            p: int(round(float(r["created_t"]) * 1000)) for p, r in pools.items()
        }
        ct_bad = 0
    B = [r for r in B if r["pool"] in base]
    ev = events(raw, base)
    if raw_end:
        cover_end_ms = (
            int((dt.date.fromisoformat(raw_end) - dt.date(1970, 1, 1)).days)
            * 86_400_000
            + 86_400_000
        )
    else:
        cover_end_ms = (
            max(e["t"] for es in ev.values() for e in es) // 86_400_000 * 86_400_000
            + 86_400_000
        )
    lines = [
        "# DQ-35 v2.1 小样本对照：%s / %s 对 %s" % ("+".join(blabs), plab, rawlab),
        "",
    ]

    # 0. 母体：独立候选集合与 P 层池集合
    if crow and plab == "-":
        lines.append(
            "- 母体（独立候选 'C' 行）%d 个池；本样本无 P 层（池不在本片建池日期内），只比分桶"
            % len(crow)
        )
    elif crow:
        lines.append(
            "- 母体（独立候选 'C' 行）%d 个池，P 层 %d 个，集合相同：%s；原始文件的排除计数：%s"
            % (len(crow), len(pools), set(crow) == set(pools), xrow or "无")
        )
        lines.append(
            "- 入口过滤：曲线创建在检验周的池 %d 个，不进入以下任何比对"
            % len(test_drop)
        )
        qbad = sum(
            1
            for p in set(crow) & set(pools)
            if crow[p]["q0"] != pools[p]["quote_mint"]
            or crow[p]["b0"] != pools[p]["qd"]
            or crow[p]["q_amt"] != pools[p]["mint"]
        )
        qc = defaultdict(int)
        for r in P:
            qc[r["quote_class"]] += 1
        lines.append(
            "- P 层计价资产、decimals、mint 与独立候选不一致的池：%d；计价分层：%s"
            % (qbad, dict(qc))
        )
    else:
        lines.append(
            "- 母体：原始文件无 'C' 行（v2 格式），以 P 层池集合为母体（整池缺失查不出）"
        )
    lines.append("- P 层建池时刻与独立候选不一致的池：%d" % ct_bad)

    if mlab and crow:
        m = read(mlab)[0]
        exp_m = dict(
            n_included=len(crow),
            n_sealed=xrow.get("sealed", 0),
            n_holdout_name=xrow.get("holdout_name", 0),
            n_no_curve_create=xrow.get("no_create", 0),
        )
        mbad = {k: (int(m[k]), v) for k, v in exp_m.items() if int(m[k]) != v}
        lines.append(
            "- M 层计数与独立候选：%s（纳入 %d、封存 %d、留出同名 %d、无曲线创建 %d；M 层计价分层 SOL %s／USDC %s／其他 %s）"
            % (
                "一致" if not mbad else "不一致 %s" % mbad,
                exp_m["n_included"],
                exp_m["n_sealed"],
                exp_m["n_holdout_name"],
                exp_m["n_no_curve_create"],
                m["n_included_sol"],
                m["n_included_usdc"],
                m["n_included_other"],
            )
        )
    if llab:
        lpath = H / "raw" / "dune" / ("%s.csv.gz" % llab)
        L = [r for r in read(llab) if r["pool"] in base] if lpath.exists() else []
        got_l = {
            (r["pool"], tuple(kint(r[x]) for x in ("slot", "txi", "oix", "iix"))): r
            for r in L
        }
        exp_l = {}
        for r in raw:
            if r["ev"] in ("D", "W") and r["pool"] in base:
                k = (
                    r["pool"],
                    (
                        kint(r["slot"]),
                        kint(r["txi"]),
                        kint(r["oix"]),
                        kint(r["iix"] or -1),
                    ),
                )
                sg = 1 if r["ev"] == "D" else -1
                exp_l[k] = (
                    r["ev"],
                    sg * int(r["q_amt"]),
                    sg * int(r["b_amt"]),
                    int(r["q0"]),
                )
        lbad = sum(
            1
            for k in set(got_l) & set(exp_l)
            if (
                got_l[k]["kind"],
                int(got_l[k]["dq"]),
                int(got_l[k]["db"]),
                int(got_l[k]["q0"]),
            )
            != exp_l[k]
        )
        lines.append(
            "- L 层加撤池逐笔：SQL %d，逐笔 %d，键集合相同：%s，逐项不一致 %d，越界计数 %d"
            % (
                len(got_l),
                len(exp_l),
                set(got_l) == set(exp_l),
                lbad,
                sum(int(r["ovf"]) for r in L),
            )
        )

    # 1. 储备逐笔守恒（池内无加撤池时，下一笔成交前＝上一笔成交后）
    lpk = defaultdict(list)
    for r in raw:
        if r["ev"] in ("D", "W") and r["pool"] in base:
            lpk[r["pool"]].append(
                (kint(r["slot"]), kint(r["txi"]), kint(r["oix"]), kint(r["iix"] or -1))
            )
    cont = tot = lp_between = 0
    for pool, es in ev.items():
        ks = lpk.get(pool, [])
        for p, q in zip(es, es[1:]):
            if any(p["key"] < k < q["key"] for k in ks):
                lp_between += 1  # 中间有加撤池，储备本来就会变
                continue
            tot += 1
            cont += (q["q0"], q["b0"]) == (p["q1"], p["b1"])
    lines.append(
        "- 储备逐笔守恒：%d / %d（另有 %d 对相邻成交之间夹着加撤池，不计）"
        % (cont, tot, lp_between)
    )

    # 2. 事件键唯一
    keys = [(pl, e["key"]) for pl, es in ev.items() for e in es]
    lines.append("- 事件键唯一：%d 个事件，%d 个不同键" % (len(keys), len(set(keys))))

    # 3. B 层逐项（多片先合并）
    got = merge_buckets(B)
    n_merged = sum(1 for r in got.values() if r.get("n_merged", 1) > 1)
    exp = expected_buckets(ev, created_ms)
    lines.append(
        "- 分桶数：SQL %d 行（%d 片），合并后 %d（其中跨片合并 %d 个），逐笔重算 %d，键集合相同：%s"
        % (len(B), len(blabs), len(got), n_merged, len(exp), set(got) == set(exp))
    )
    bad = defaultdict(int)
    users_diff = straddle_members_bad = 0
    for k in set(got) & set(exp):
        g, e = got[k], exp[k]
        for c in ("n", "n_buy", "t_first", "t_last", "n_vq_obs"):
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
        for c in ("vq_lo", "vq_hi", "f_cb_sell", "f_bb_sell"):
            gv = int(g[c]) if g[c] != "" else None
            bad[c] += gv != e[c]
        for c in ("side_first", "side_last"):
            bad[c] += g[c] != e[c]
        kf = tuple(int(g[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))
        kl = tuple(int(g[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))
        bad["key_f"] += kf != e["key_f"]
        bad["key_l"] += kl != e["key_l"]
        if is_true(g["straddle"]):
            straddle_members_bad += set(
                u for u in g["users_straddle"].split(",") if u
            ) != set(e["users"])
        users_diff += int(g["n_users"]) != e["n_users_exact"]
    lines.append(
        "- 分桶逐项不一致（含 vq 区间、卖出 cashback／回购费）："
        + ("全部为 0" if not any(bad.values()) else str(dict(bad)))
    )
    lines.append(
        "- 跨片桶的用户名单与逐笔精确名单（逐个成员）不一致：%d" % straddle_members_bad
    )
    lines.append("- n_users（approx_distinct）与精确去重不同的桶：%d" % users_diff)
    lines.append(
        "- 越界计数合计：%d；费用空值计数合计：%d；价格未知的事件合计：%d"
        % (
            sum(int(r["n_ord_overflow"]) for r in B),
            sum(int(r["n_fee_null"]) for r in B),
            sum(int(r["n_px_unknown"]) for r in B),
        )
    )
    vq_conf = sum(
        1
        for r in got.values()
        if r["vq_lo"] != "" and r["vq_hi"] != "" and int(r["vq_lo"]) > int(r["vq_hi"])
    )
    lines.append("- vq 区间交集为空（片内 vq 变过）的桶：%d" % vq_conf)

    # 4. P 层快照与 7 天池级字段
    snap_bad, snap_n, inner_bad, p7_n, p7_bad = defaultdict(int), 0, 0, 0, 0
    snap_beyond = 0
    for pool, r in pools.items():
        if pool not in base:
            continue
        es = ev.get(pool, [])
        if created_ms[pool] + 7 * 86_400_000 <= cover_end_ms:
            p7_n += 1
            e7 = [e for e in es if e["t"] < created_ms[pool] + 7 * 86_400_000]
            vs = [e["vq"] for e in e7 if e["vq"] is not None]
            lo = max(v[0] for v in vs) if vs else None
            hi = min(v[1] for v in vs) if vs else None
            got7 = (
                int(r["n_7d"] or 0),
                int(r["vq_lo_7d"]) if r["vq_lo_7d"] else None,
                int(r["vq_hi_7d"]) if r["vq_hi_7d"] else None,
            )
            p7_bad += got7 != (len(e7), lo, hi)
        for o in OFFSETS:
            if (
                r["a%d_q1" % o]
                and r["b%d_q0" % o]
                and r["a%d_q1" % o] != r["b%d_q0" % o]
            ):
                inner_bad += 1
            if created_ms[pool] + o * 1000 + 1000 > cover_end_ms:
                continue
            snap_n += 1
            ea, eb = expected_snapshot(es, created_ms[pool], o)
            for pre, e, fs in (("a", ea, ("q1", "b1")), ("b", eb, ("q0", "b0"))):
                if e is None:
                    # 时点后第一笔落在原始文件覆盖期之后：SQL 有值是对的，不算不一致
                    t_sql = r["%s%d_t" % (pre, o)]
                    beyond = (
                        pre == "b"
                        and t_sql != ""
                        and float(t_sql) * 1000 >= cover_end_ms
                    )
                    if beyond:
                        snap_beyond += 1
                    else:
                        snap_bad["%s_missing" % pre] += r["%s%d_slot" % (pre, o)] != ""
                    continue
                key = tuple(
                    kint(r["%s%d_%s" % (pre, o, x)])
                    for x in ("slot", "txi", "oix", "iix")
                )
                snap_bad["%s_key" % pre] += key != e["key"]
                for fld in fs:
                    snap_bad["%s_%s" % (pre, fld)] += (
                        int(r["%s%d_%s" % (pre, o, fld)]) != e[fld]
                    )
    lines.append(
        "- 快照：比对 %d 个（池×时点），不一致：%s；时点后第一笔在原始文件覆盖期之后（SQL 有值，不算不一致）：%d"
        % (
            snap_n,
            "全部为 0" if not any(snap_bad.values()) else dict(snap_bad),
            snap_beyond,
        )
    )
    lines.append(
        "- 快照内部一致（时点前最后一笔成交后＝时点后第一笔成交前，全部时点）：不一致 %d"
        % inner_bad
    )
    lines.append(
        "- 7 天池级字段（n_7d、vq_lo_7d、vq_hi_7d）：比对 %d 个池，不一致 %d"
        % (p7_n, p7_bad)
    )

    # 5. 同一 SQL 两次运行
    if len(a) >= 5:
        lines.append(
            "- B 层两次运行逐行一致：%s" % same_rows(read(blabs[0]), read(a[3]))
        )
        lines.append("- P 层两次运行逐行一致：%s" % same_rows(P, read(a[4])))
    out = H / "runs" / ("%s_compare.md" % (out_name or blabs[0]))
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

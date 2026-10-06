#!/usr/bin/env python3
"""DQ-35 v2.2 毕业前小样本对照（10-05）：用逐笔原始曲线成交（精确整数）重算 GRADPRE v2.2 的 5 秒桶，逐个字段比对。
v2.2：读取经 dev_gate（先读 'C'／'X' 行定开发币，数值行解析时丢弃）；M 层加 n_no_symbol 与 identity_gap；
B 层加 tx_f／tx_l、n_cb_null／n_bb_null；键先查重复；报告列出比对字段。

python compare_pre_v22.py <B 层标签> <M 层标签> <逐笔原始标签> [<B 层第二次运行标签>]  → runs/<B 层标签>_compare.md
逐笔原始文件来自 build_sample_raw_v22.py pre（独立母体：'C' 行为纳入的币，'X' 行为排除计数）。
只核对齐全、精度与一致性，不看价格或收益分布。
"""

import sys
from collections import defaultdict

import dev_gate as g
from compare_sample_v21 import epoch, is_true, kint, same_rows
from dune_get import H

SUMS = ("sol_buy", "sol_sell", "tok_buy", "tok_sell")
FEES = ("f_pr", "f_cr", "f_cb", "f_bb")


def ival(s):
    return int(s) if s not in ("", None) else None


def curve_pre(is_buy, x_post, y_post, sol, tok):
    """曲线成交前储备（非 mayhem、SOL 计价）：买＝后−sol、后＋tok；卖＝后＋sol、后−tok。"""
    if is_buy:
        return x_post - sol, y_post + tok
    return x_post + sol, y_post - tok


def trades(raw):
    out = defaultdict(list)
    for r in raw:
        if r["kind"] != "T":
            continue
        e = dict(
            key=(
                kint(r["slot"]),
                kint(r["txi"]),
                kint(r["oix"]),
                kint(r["iix"]) if r["iix"] != "" else -1,
            ),
            t=epoch(r["ts"]),
            buy=is_true(r["is_buy"]),
            usr=r["usr"],
            sol=int(r["sol"]),
            tok=int(r["tok"]),
            x=int(r["x"]),
            y=int(r["y"]),
            xr=ival(r["xr"]),
            qa=ival(r["qa"]),
            mayhem=is_true(r["mayhem_mode"]),
            tx=r["tx_id"],
            **{f: ival(r[f]) for f in FEES},
        )
        out[r["mint"]].append(e)
    for v in out.values():
        v.sort(key=lambda e: e["key"])
    return out


def sum_or_none(vals):
    v = [x for x in vals if x is not None]
    return sum(v) if v else None


def expected(tr, completed_ms, sol_quote):
    rows = {}
    for mint, es in tr.items():
        by = defaultdict(list)
        for e in es:
            by[(completed_ms[mint] - e["t"]) // 5000].append(e)
        for bkey, b in by.items():
            f, last = b[0], b[-1]
            mayhem = any(e["mayhem"] for e in b)
            valid = sol_quote[mint] and not mayhem
            xp, yp = curve_pre(f["buy"], f["x"], f["y"], f["sol"], f["tok"])
            rows[(mint, bkey)] = dict(
                n=len(b),
                n_buy=sum(e["buy"] for e in b),
                n_users_exact=len(set(e["usr"] for e in b)),
                sol_buy=sum(e["sol"] for e in b if e["buy"]),
                sol_sell=sum(e["sol"] for e in b if not e["buy"]),
                tok_buy=sum(e["tok"] for e in b if e["buy"]),
                tok_sell=sum(e["tok"] for e in b if not e["buy"]),
                qa_buy=sum_or_none(e["qa"] for e in b if e["buy"]),
                qa_sell=sum_or_none(e["qa"] for e in b if not e["buy"]),
                max_buy_sol=max((e["sol"] for e in b if e["buy"]), default=None),
                n_fee_null=sum(e["f_pr"] is None or e["f_cr"] is None for e in b),
                n_cb_null=sum(e["f_cb"] is None for e in b),
                n_bb_null=sum(e["f_bb"] is None for e in b),
                tx_f=f["tx"],
                tx_l=last["tx"],
                key_f=f["key"],
                key_l=last["key"],
                buy_first=f["buy"],
                sol_first=f["sol"],
                tok_first=f["tok"],
                x_post_first=f["x"],
                y_post_first=f["y"],
                pre_valid=valid,
                x_pre_first=xp if valid else None,
                y_pre_first=yp if valid else None,
                buy_last=last["buy"],
                x_last=last["x"],
                y_last=last["y"],
                xr_last=last["xr"],
                t_first=f["t"],
                t_last=last["t"],
                mayhem=int(mayhem),
                **{c: sum_or_none(e[c] for e in b) for c in FEES},
            )
    return rows


def dups(items):
    from collections import Counter

    return sum(v - 1 for v in Counter(items).values() if v > 1)


def main():
    a = sys.argv[1:]
    blab, mlab, rawlab = a[0], a[1], a[2]
    crow_all, xrow = g.read_meta(rawlab, "kind", "mint")
    keep, n_drop = g.dev_ids_from_meta(crow_all, "mint", "qa")
    crow = {r["mint"]: r for r in crow_all}
    xrow = {r["mint"]: kint(r["usr"]) for r in xrow}
    raw, raw_drop = g.stream(rawlab, "mint", keep, time_col="ts")
    raw = [r for r in raw if r["kind"] == "T"]
    B, _ = g.stream(blab, "mint", keep)
    with __import__("gzip").open(g.RAW / ("%s.csv.gz" % mlab), "rt", newline="") as f:
        M = list(__import__("csv").DictReader(f))
    completed_ms = {m: epoch(r["ts"]) for m, r in crow.items()}
    sol_quote = {
        m: r["quote_mint"]
        in (
            "",
            "So11111111111111111111111111111111111111112",
            "11111111111111111111111111111111",
        )
        for m, r in crow.items()
    }
    tr = trades(raw)
    lines = ["# DQ-35 v2.2 毕业前小样本对照：%s / %s 对 %s" % (blab, mlab, rawlab), ""]
    lines.append(
        "- 入口（dev_gate）：独立母体 %d 个币，其中开发币 %d 个、剔除 %d 个；数值文件解析时丢弃 %d 行"
        % (len(crow_all), len(keep), n_drop, raw_drop)
    )

    # 0. 母体与计数
    m = M[0]
    exp_m = dict(
        n_included=len(crow),
        n_sealed=xrow.get("sealed", 0),
        n_holdout_name=xrow.get("holdout_name", 0),
        n_no_curve_create=xrow.get("no_create", 0),
        n_no_symbol=xrow.get("no_symbol", 0),
        identity_gap=0,
        n_included_sol=sum(sol_quote.values()),
    )
    mbad = {k: (kint(m[k]), v) for k, v in exp_m.items() if kint(m[k]) != v}
    lines.append(
        "- M 层（字段 n_included、n_sealed、n_holdout_name、n_no_curve_create、n_no_symbol、identity_gap、n_included_sol）与独立候选：%s；纳入 %d（SOL %d、USDC %s、其他 %s）"
        % (
            "一致" if not mbad else "不一致 %s" % mbad,
            len(crow),
            exp_m["n_included_sol"],
            m["n_included_usdc"],
            m["n_included_other"],
        )
    )
    bmints = set(r["mint"] for r in B)
    lines.append(
        "- 有成交的币：逐笔 %d，SQL %d，集合相同：%s；不在独立母体里的 SQL 币：%d"
        % (len(tr), len(bmints), set(tr) == bmints, len(bmints - set(crow)))
    )

    # 1. 曲线连续性（非 mayhem、SOL 计价）
    cont = tot = 0
    for mint, es in tr.items():
        if not sol_quote[mint]:
            continue
        for p, q in zip(es, es[1:]):
            if p["mayhem"] or q["mayhem"]:
                continue
            tot += 1
            cont += curve_pre(q["buy"], q["x"], q["y"], q["sol"], q["tok"]) == (
                p["x"],
                p["y"],
            )
    lines.append("- 曲线逐笔连续（非 mayhem、SOL 计价）：%d / %d" % (cont, tot))
    keys = [(mint, e["key"]) for mint, es in tr.items() for e in es]
    lines.append(
        "- 事件键唯一：%d 个事件，%d 个不同键；B 层键重复 %d"
        % (len(keys), len(set(keys)), dups([(r["mint"], kint(r["bkey"])) for r in B]))
    )

    # 2. 分桶逐项
    exp = expected(tr, completed_ms, sol_quote)
    got = {(r["mint"], kint(r["bkey"])): r for r in B}
    lines.append(
        "- 分桶数：SQL %d，逐笔重算 %d，键集合相同：%s"
        % (len(got), len(exp), set(got) == set(exp))
    )
    bad = defaultdict(int)
    users_diff = 0
    for k in set(got) & set(exp):
        gr, e = got[k], exp[k]
        for c in ("n", "n_buy", "n_fee_null", "n_cb_null", "n_bb_null", "mayhem"):
            bad[c] += kint(gr[c]) != e[c]
        for c in ("tx_f", "tx_l"):
            bad[c] += gr[c] != e[c]
        for c in (
            SUMS
            + FEES
            + (
                "qa_buy",
                "qa_sell",
                "max_buy_sol",
                "sol_first",
                "tok_first",
                "x_post_first",
                "y_post_first",
                "x_pre_first",
                "y_pre_first",
                "x_last",
                "y_last",
                "xr_last",
            )
        ):
            bad[c] += ival(gr[c]) != e[c]
        for c in ("buy_first", "buy_last", "pre_valid"):
            bad[c] += is_true(gr[c]) != e[c]
        for c in ("t_first", "t_last"):
            bad[c] += int(round(float(gr[c]) * 1000)) != e[c]
        bad["key_f"] += (
            tuple(kint(gr[x]) for x in ("slot_f", "txi_f", "oix_f", "iix_f"))
            != e["key_f"]
        )
        bad["key_l"] += (
            tuple(kint(gr[x]) for x in ("slot_l", "txi_l", "oix_l", "iix_l"))
            != e["key_l"]
        )
        users_diff += kint(gr["n_users"]) != e["n_users_exact"]
    lines.append(
        "- 分桶逐字段（%s）不一致：%s"
        % (
            "、".join(sorted(bad)),
            "全部为 0"
            if not any(bad.values())
            else str({k: v for k, v in bad.items() if v}),
        )
    )
    lines.append(
        "- n_users 与精确去重不同的桶（10-06 起 SQL 用精确去重，应为 0）：%d"
        % users_diff
    )
    lines.append(
        "- 越界计数合计：%d；mayhem 桶 %d、pre_valid＝false 的桶 %d（x_pre_first 已置空）"
        % (
            sum(kint(r["n_ord_overflow"]) for r in B),
            sum(kint(r["mayhem"]) for r in B),
            sum(not is_true(r["pre_valid"]) for r in B),
        )
    )
    if len(a) >= 4:
        lines.append(
            "- 同一 SQL 两次运行逐行一致（全部行、全部列）：%s"
            % same_rows(
                g.stream(blab, "mint", keep)[0], g.stream(a[3], "mint", keep)[0]
            )
        )
    out = H / "runs" / ("%s_compare.md" % blab)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

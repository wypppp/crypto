#!/usr/bin/env python3
"""DQ-35 v2 小样本对照（10-03，总控第十三轮第二节第 2 条）。

python compare_sample_v2.py <日期标签 如 20251007> [GRAD 分桶的标签前缀，默认 SMP2c] [GRADPRE 前缀，默认 SMP2b]  → runs/SMP2_compare_<标签>.md
输入（raw/dune/）：<前缀>_GRAD_<T>_r1/_r2（GRAD v2 定稿两次运行；10-03 改结构后重跑，前缀 SMP2c）、SMP2b_PRE_<T>_r1/_r2（v2 分桶 SQL 两次运行）、
SMP2b_GRADRAW_<T>、SMP2b_PRERAW_<T>（同一母体的逐笔原始事件）。
核对四件事：
 1. 同一 SQL 两次运行逐行一致（冻结前清单第 9 条）；
 2. 逐笔储备连续性：按 ord 排序后，本笔成交后储备（v2 公式）＝下一笔报告的交易前储备；
 3. 由逐笔重算的每个桶与 SQL 输出逐项一致（笔数、金额、费用、首末、开高低收、首末 ord、跨界桶用户名单）；
 4. ord 唯一、不越界。用户数 n_users 是 approx_distinct，只报告与精确去重的差。
只看数据是否被正确提取，不看任何收益。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "dune"


def ord_key(slot, txi, oix, iix):
    """与 SQL 相同的排序键：slot·1e10＋tx·1e5＋外层·1e3＋内层。"""
    return (
        np.int64(slot) * 10_000_000_000
        + np.int64(txi) * 100_000
        + np.int64(oix) * 1_000
        + np.int64(iix)
    )


def amm_post(ev, q0, b0, q_amt, q_amt_lp, b_amt, f_lp):
    """PumpSwap 事件后的池储备（v2 公式）。ev: B 买、S 卖、D 加池、W 撤池。
    买：quote ＋ quote_amount_in_with_lp_fee，base − base_amount_out；
    卖：quote −（quote_amount_out − lp_fee），base ＋ base_amount_in；
    加池：两边加；撤池：两边减。"""
    if ev == "B":
        return q0 + q_amt_lp, b0 - b_amt
    if ev == "S":
        return q0 - (q_amt - f_lp), b0 + b_amt
    if ev == "D":
        return q0 + q_amt, b0 + b_amt
    if ev == "W":
        return q0 - q_amt, b0 - b_amt
    raise ValueError(ev)


def curve_pre(is_buy, x_post, y_post, sol, tok):
    """曲线成交前的虚拟储备：TradeEvent 报告的是成交后状态。"""
    if is_buy:
        return x_post - sol, y_post + tok
    return x_post + sol, y_post - tok


def grad_bucket(age):
    """毕业后分桶：返回 (kind, bkey, 桶宽秒)。"""
    if age < 300:
        return "S", float(age // 5), 5
    if age < 604800:
        return "H", float(age // 3600), 3600
    return "D", float(age // 86400), 86400


def _num(s):
    return pd.to_numeric(s, errors="coerce").astype(float)


def _ts(s):
    return pd.to_datetime(s.str.replace(" UTC", "", regex=False), utc=True)


def same_rows(a, b, keys):
    """两次运行逐行一致：排序后逐格比字符串。"""
    if len(a) != len(b) or list(a.columns) != list(b.columns):
        return False, "行数或列不同 %d vs %d" % (len(a), len(b))
    a2 = a.sort_values(keys).astype(str).reset_index(drop=True)
    b2 = b.sort_values(keys).astype(str).reset_index(drop=True)
    diff = (a2 != b2).any(axis=1).sum()
    return diff == 0, "不同的行 %d / %d" % (diff, len(a))


def exact_ord(raw_int, sql_str):
    """ord 逐位比较：SQL 输出的是 varchar（Dune API 会把超过 2^53 的 BIGINT 当浮点丢低位）。"""
    return raw_int.astype("int64").astype(str).values == sql_str.astype(str).values


def close(a, b, rel=1e-9, absol=1e-6):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    both_nan = np.isnan(a) & np.isnan(b)
    return both_nan | (np.abs(a - b) <= np.maximum(absol, rel * np.abs(b)))


def check_grad(tag, out, pre="SMP2c"):
    r1 = pd.read_csv(RAW / ("%s_GRAD_%s_r1.csv.gz" % (pre, tag)), dtype=str)
    r2 = pd.read_csv(RAW / ("%s_GRAD_%s_r2.csv.gz" % (pre, tag)), dtype=str)
    ok, msg = same_rows(r1, r2, ["kind", "pool", "bkey", "ord_first"])
    out.append("- 两次运行逐行一致：**%s**（%s）" % ("是" if ok else "否", msg))
    raw = pd.read_csv(RAW / ("SMP2b_GRADRAW_%s.csv.gz" % tag), dtype=str)
    raw["ts"] = _ts(raw["ts"])
    for c in [
        "q0",
        "b0",
        "q_amt",
        "q_amt_lp",
        "q_user",
        "b_amt",
        "f_lp",
        "f_pr",
        "f_cr",
        "f_cb",
        "f_bb",
    ]:
        raw[c] = _num(raw[c])
    for c in ["slot", "txi", "oix", "iix"]:
        raw[c] = pd.to_numeric(raw[c]).fillna(0).astype(np.int64)
    raw["ord"] = ord_key(raw["slot"], raw["txi"], raw["oix"], raw["iix"])
    ovf = ((raw["txi"] >= 100000) | (raw["oix"] >= 100) | (raw["iix"] >= 1000)).sum()
    dup = raw.duplicated(["pool", "ord"]).sum()
    out.append(
        "- 逐笔 %d 笔（%s）；ord 越界 %d、重复 %d"
        % (len(raw), raw["ev"].value_counts().to_dict(), ovf, dup)
    )
    raw = raw.sort_values(["pool", "ord"]).reset_index(drop=True)
    post = [
        amm_post(
            r.ev,
            r.q0,
            r.b0,
            r.q_amt,
            r.q_amt_lp,
            r.b_amt,
            r.f_lp if not np.isnan(r.f_lp) else 0.0,
        )
        for r in raw.itertuples()
    ]
    raw["q1"] = [p[0] for p in post]
    raw["b1"] = [p[1] for p in post]
    nxt = raw.groupby("pool")[["q0", "b0"]].shift(-1)
    has = nxt["q0"].notna()
    mq = (np.abs(raw["q1"] - nxt["q0"]) <= 1) & has
    mb = (np.abs(raw["b1"] - nxt["b0"]) <= 1) & has
    out.append("- 储备连续性（本笔后＝下一笔前，误差 ≤1 原始单位），按事件类型：")
    for ev, g in raw[has].groupby("ev"):
        out.append(
            "  - %s：quote %d/%d，base %d/%d"
            % (ev, mq[g.index].sum(), len(g), mb[g.index].sum(), len(g))
        )
    sells = raw[raw["ev"] == "S"]
    if len(sells):
        eq = close(sells["q_amt"] - sells["f_lp"], sells["q_amt_lp"], 0, 1).sum()
        out.append(
            "  - 卖出 quote_amount_out − lp_fee ＝ quote_amount_out_without_lp_fee：%d/%d；cashback>0 的 %d 笔，buyback_fee>0 的 %d 笔"
            % (eq, len(sells), (sells["f_cb"] > 0).sum(), (sells["f_bb"] > 0).sum())
        )
    # 重算分桶（只用交易事件；L 行另核）
    meta = r1[r1["kind"] != "L"][["pool", "created_at", "bd", "qd"]].drop_duplicates(
        "pool"
    )
    meta["created_at"] = _ts(meta["created_at"])
    tr = raw[raw["ev"].isin(["B", "S"])].merge(meta, on="pool", how="inner")
    tr["bd"] = tr["bd"].astype(int)
    tr["qd"] = tr["qd"].astype(int)
    age = ((tr["ts"] - tr["created_at"]).dt.total_seconds()).astype(np.int64)
    kb = [grad_bucket(a) for a in age]
    tr["kind"] = [k[0] for k in kb]
    tr["bkey"] = [k[1] for k in kb]
    tr["px"] = (tr["q1"] / 10.0 ** tr["qd"]) / (tr["b1"] / 10.0 ** tr["bd"])
    tr["px_pre"] = (tr["q0"] / 10.0 ** tr["qd"]) / (tr["b0"] / 10.0 ** tr["bd"])
    tr["q_pool"] = np.where(
        tr["ev"] == "B", tr["q_amt_lp"], tr["q_amt"] - tr["f_lp"].fillna(0)
    )
    tr = tr.sort_values(["pool", "ord"])
    g = tr.groupby(["kind", "pool", "bkey"], sort=False)
    mine = pd.DataFrame(
        {
            "n": g.size(),
            "n_buy": g["ev"].apply(lambda s: (s == "B").sum()),
            "n_users_exact": g["usr"].nunique(),
            "q_buy_user": g.apply(lambda d: d.loc[d.ev == "B", "q_user"].sum()),
            "q_sell_user": g.apply(lambda d: d.loc[d.ev == "S", "q_user"].sum()),
            "q_buy_pool": g.apply(lambda d: d.loc[d.ev == "B", "q_pool"].sum()),
            "q_sell_pool": g.apply(lambda d: d.loc[d.ev == "S", "q_pool"].sum()),
            "b_buy": g.apply(lambda d: d.loc[d.ev == "B", "b_amt"].sum()),
            "b_sell": g.apply(lambda d: d.loc[d.ev == "S", "b_amt"].sum()),
            "f_lp": g["f_lp"].sum(),
            "f_pr": g["f_pr"].sum(),
            "f_cr": g["f_cr"].sum(),
            "ord_first": g["ord"].min(),
            "ord_last": g["ord"].max(),
            "q0_open": g["q0"].first(),
            "b0_open": g["b0"].first(),
            "side_first": g["ev"].first(),
            "q1_close": g["q1"].last(),
            "b1_close": g["b1"].last(),
            "side_last": g["ev"].last(),
            "px_pre_open": g["px_pre"].first(),
            "px_open": g["px"].first(),
            "px_close": g["px"].last(),
            "px_high": g["px"].max(),
            "px_low": g["px"].min(),
        }
    ).reset_index()
    sql = r1[r1["kind"] != "L"].copy()
    sql["bkey"] = _num(sql["bkey"])
    m = mine.merge(
        sql,
        on=["kind", "pool", "bkey"],
        how="outer",
        suffixes=("_raw", "_sql"),
        indicator=True,
    )
    out.append(
        "- 分桶对齐：两边都有 %d，只在逐笔 %d，只在 SQL %d"
        % (
            (m["_merge"] == "both").sum(),
            (m["_merge"] == "left_only").sum(),
            (m["_merge"] == "right_only").sum(),
        )
    )
    b = m[m["_merge"] == "both"]
    bad = []
    for c in [
        "n",
        "n_buy",
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
        "px_pre_open",
        "px_open",
        "px_close",
        "px_high",
        "px_low",
    ]:
        okc = close(b[c + "_raw"], _num(b[c + "_sql"])).sum()
        if okc != len(b):
            bad.append("%s %d/%d" % (c, okc, len(b)))
    for c in ["side_first", "side_last"]:
        okc = (b[c + "_raw"].astype(str) == b[c + "_sql"].astype(str)).sum()
        if okc != len(b):
            bad.append("%s %d/%d" % (c, okc, len(b)))
    for c in ["ord_first", "ord_last"]:
        okc = exact_ord(b[c + "_raw"], b[c + "_sql"]).sum()
        if okc != len(b):
            bad.append("%s（逐位）%d/%d" % (c, okc, len(b)))
    out.append("- 逐项一致：%s" % ("全部一致" if not bad else "；".join(bad)))
    du = (b["n_users_exact"].astype(float) - _num(b["n_users"])).abs()
    out.append(
        "- n_users（approx_distinct）与精确去重：相同 %d/%d，最大差 %d"
        % ((du == 0).sum(), len(b), du.max() if len(b) else 0)
    )
    st = sql[sql["straddle"].str.lower() == "true"]
    out.append(
        "- 跨分片边界的桶 %d 个，带用户名单 %d 个"
        % (len(st), st["users_straddle"].notna().sum())
    )
    lrows = r1[r1["kind"] == "L"].copy()
    lraw = raw[raw["ev"].isin(["D", "W"])].copy()
    out.append("- 加撤池：SQL L 行 %d，逐笔 D/W %d" % (len(lrows), len(lraw)))
    if len(lrows) or len(lraw):
        sign = np.where(lraw["ev"] == "D", 1.0, -1.0)
        lraw["dq"] = sign * lraw["q_amt"]
        lraw["db"] = sign * lraw["b_amt"]
        lraw["ord_s"] = lraw["ord"].astype(str)
        lrows["ord_first"] = lrows["ord_first"].astype(str)
        lm = lraw.merge(
            lrows,
            left_on=["pool", "ord_s"],
            right_on=["pool", "ord_first"],
            how="outer",
            indicator=True,
        )
        both = lm[lm["_merge"] == "both"]
        okl = (
            close(both["q0"], _num(both["q0_open"]))
            & close(both["b0"], _num(both["b0_open"]))
            & close(both["dq"], _num(both["q_pool_last"]))
            & close(both["db"], _num(both["b_amt_last"]))
            & close(both["q0"] + both["dq"], _num(both["q1_close"]))
            & (both["ev"] == both["side_first"])
        )
        out.append(
            "  - L 行逐项一致 %d/%d（只在一边 %d）"
            % (okl.sum(), len(both), (lm["_merge"] != "both").sum())
        )
    out.append(
        "- SQL 输出 n_ord_overflow 合计 %d" % _num(r1["n_ord_overflow"]).fillna(0).sum()
    )


def check_pre(tag, out, pre="SMP2b"):
    r1 = pd.read_csv(RAW / ("%s_PRE_%s_r1.csv.gz" % (pre, tag)), dtype=str)
    r2 = pd.read_csv(RAW / ("%s_PRE_%s_r2.csv.gz" % (pre, tag)), dtype=str)
    ok, msg = same_rows(r1, r2, ["mint", "bkey"])
    out.append("- 两次运行逐行一致：**%s**（%s）" % ("是" if ok else "否", msg))
    raw = pd.read_csv(RAW / ("SMP2b_PRERAW_%s.csv.gz" % tag), dtype=str)
    raw["ts"] = _ts(raw["ts"])
    raw["completed_at"] = _ts(raw["completed_at"])
    raw["is_buy"] = raw["is_buy"].str.lower() == "true"
    raw["sol"] = _num(raw["sol"]) / 1e9
    raw["tok"] = _num(raw["tok"]) / 1e6
    raw["x"] = _num(raw["x"]) / 1e9
    raw["y"] = _num(raw["y"]) / 1e6
    for c in ["slot", "txi", "oix", "iix"]:
        raw[c] = pd.to_numeric(raw[c]).fillna(0).astype(np.int64)
    raw["ord"] = ord_key(raw["slot"], raw["txi"], raw["oix"], raw["iix"])
    dup = raw.duplicated(["mint", "ord"]).sum()
    qm = raw["quote_mint"].fillna("(空)").value_counts().to_dict()
    out.append(
        "- 逐笔 %d 笔，币 %d 个；ord 重复 %d；quote_mint 分布 %s；mayhem %d 笔"
        % (
            len(raw),
            raw["mint"].nunique(),
            dup,
            qm,
            (raw["mayhem_mode"].str.lower() == "true").sum(),
        )
    )
    raw = raw.sort_values(["mint", "ord"]).reset_index(drop=True)
    pre = [curve_pre(r.is_buy, r.x, r.y, r.sol, r.tok) for r in raw.itertuples()]
    raw["x_pre"] = [p[0] for p in pre]
    raw["y_pre"] = [p[1] for p in pre]
    prev = raw.groupby("mint")[["x", "y"]].shift(1)
    has = prev["x"].notna()
    mx = (np.abs(raw["x_pre"] - prev["x"]) <= 1e-9) & has
    my = (np.abs(raw["y_pre"] - prev["y"]) <= 1e-6) & has
    out.append(
        "- 曲线连续性（本笔前＝上一笔后）：x %d/%d，y %d/%d"
        % (mx.sum(), has.sum(), my.sum(), has.sum())
    )
    mh = raw["mayhem_mode"].str.lower() == "true"
    for lab, m in [("非 mayhem", ~mh), ("mayhem", mh)]:
        hm = has & m
        if hm.sum():
            out.append(
                "  - %s：x %d/%d，y %d/%d"
                % (lab, (mx & m).sum(), hm.sum(), (my & m).sum(), hm.sum())
            )
    raw["bkey"] = np.floor(
        (raw["completed_at"] - raw["ts"]).dt.total_seconds() * 1000 // 5000
    ).astype(float)
    g = raw.groupby(["mint", "bkey"], sort=False)
    mine = pd.DataFrame(
        {
            "n": g.size(),
            "n_buy": g["is_buy"].sum(),
            "n_users_exact": g["usr"].nunique(),
            "sol_buy": g.apply(lambda d: d.loc[d.is_buy, "sol"].sum()),
            "sol_sell": g.apply(lambda d: d.loc[~d.is_buy, "sol"].sum()),
            "tok_buy": g.apply(lambda d: d.loc[d.is_buy, "tok"].sum()),
            "tok_sell": g.apply(lambda d: d.loc[~d.is_buy, "tok"].sum()),
            "ord_first": g["ord"].min(),
            "ord_last": g["ord"].max(),
            "x_post_first": g["x"].first(),
            "y_post_first": g["y"].first(),
            "x_pre_first": g["x_pre"].first(),
            "y_pre_first": g["y_pre"].first(),
            "x_last": g["x"].last(),
            "y_last": g["y"].last(),
        }
    ).reset_index()
    sql = r1.copy()
    sql["bkey"] = _num(sql["bkey"])
    m = mine.merge(
        sql, on=["mint", "bkey"], how="outer", suffixes=("_raw", "_sql"), indicator=True
    )
    out.append(
        "- 分桶对齐：两边都有 %d，只在逐笔 %d，只在 SQL %d"
        % (
            (m["_merge"] == "both").sum(),
            (m["_merge"] == "left_only").sum(),
            (m["_merge"] == "right_only").sum(),
        )
    )
    b = m[m["_merge"] == "both"]
    bad = []
    for c in [
        "n",
        "n_buy",
        "sol_buy",
        "sol_sell",
        "tok_buy",
        "tok_sell",
        "x_post_first",
        "y_post_first",
        "x_pre_first",
        "y_pre_first",
        "x_last",
        "y_last",
    ]:
        okc = close(b[c + "_raw"], _num(b[c + "_sql"])).sum()
        if okc != len(b):
            bad.append("%s %d/%d" % (c, okc, len(b)))
    for c in ["ord_first", "ord_last"]:
        okc = exact_ord(b[c + "_raw"], b[c + "_sql"]).sum()
        if okc != len(b):
            bad.append("%s（逐位）%d/%d" % (c, okc, len(b)))
    out.append("- 逐项一致：%s" % ("全部一致" if not bad else "；".join(bad)))
    du = (b["n_users_exact"].astype(float) - _num(b["n_users"])).abs()
    out.append(
        "- n_users（approx_distinct）与精确去重：相同 %d/%d，最大差 %d"
        % ((du == 0).sum(), len(b), du.max() if len(b) else 0)
    )


def main():
    tag = sys.argv[1]
    pre = sys.argv[2] if len(sys.argv) > 2 else "SMP2c"
    ppre = sys.argv[3] if len(sys.argv) > 3 else "SMP2b"
    out = [
        "# DQ-35 v2 小样本对照 %s（compare_sample_v2.py 生成）" % tag,
        "",
        "## 毕业后（GRAD v2）",
        "",
    ]
    check_grad(tag, out, pre)
    out += ["", "## 毕业前（GRADPRE v2）", ""]
    if (RAW / ("%s_PRE_%s_r1.csv.gz" % (ppre, tag))).exists():
        check_pre(tag, out, ppre)
    else:
        out.append("- 本组没有毕业前样本")
    p = H / "runs" / ("SMP2_compare_%s.md" % tag)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()

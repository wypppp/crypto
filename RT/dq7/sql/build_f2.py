"""DQ-7 · F2：在 DQ-1F F1 模板上做定点修改（每处替换都断言命中次数），渲染冒烟、开发与 4 个验证周 SQL。"""
import hashlib, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "dq1f" / "sql"))
import build_f1 as F1  # noqa: E402

TR50 = "(p AND pm <= 0.50 * greatest(1.0, runmax_post))"
TR70 = "(p AND pm <= 0.30 * greatest(1.0, runmax_post))"
DUMP = "(p AND ins_hold > 0 AND ins_exit >= 0.5)"
DEAD = "(rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)"


def cond(n, i):
    return f"({TR50} AND (ins_exit >= {i} OR newb30 < {n}))"


# 全额退出规则：价格类触发（按 5 秒抢跑假设取下一笔）+ 24 小时沉寂
FULL = {
    "b50": [TR50],
    "ins50_h70": [DUMP, TR70],
    "c30_i02": [cond(30, 0.2), TR70, DUMP],
    "c30_i05": [cond(30, 0.5), TR70, DUMP],
    "c100_i02": [cond(100, 0.2), TR70, DUMP],
    "c100_i05": [cond(100, 0.5), TR70, DUMP],
}
# 分批止盈：pm ≥ k 时卖一半；止盈前按 pre 触发全额退出，止盈后剩余一半按 post 触发退出
TP = {
    "tp2_r70": (2, [TR50], [TR70]),
    "tp2_rNA": (2, [TR50], []),
    "tp3_r70": (3, [TR50], [TR70]),
    "tp3_rNA": (3, [TR50], []),
    "tp2_c30_i02_r70": (2, [cond(30, 0.2), TR70, DUMP], [TR70]),
    "tp2_c100_i05_r70": (2, [cond(100, 0.5), TR70, DUMP], [TR70]),
}
RULE_NAMES = list(FULL) + list(TP)


def any_of(xs):
    return "(" + " OR ".join(xs) + ")" if xs else "false"


def val(price, s, lead):
    return (f"CASE WHEN {price} THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 "
            f"THEN {lead} ELSE {s} END) ELSE {s} END")


def edt(price):
    return f"CASE WHEN {price} THEN dt ELSE greatest(dt, 0) + 86400 END"


def agg_sql():
    L = ["        max(tp2_rn) AS tp2_rn,", "        max(tp3_rn) AS tp3_rn,",
         "        max_by(smh, rn) FILTER (WHERE p) AS smh_last,"]
    for tag, trig in FULL.items():
        pr = any_of(trig)
        L.append(f"        min_by({val(pr, 'sm', 'lead_sm')}, rn) FILTER (WHERE {pr} OR {DEAD}) AS {tag}_v,")
        L.append(f"        min_by({edt(pr)}, rn) FILTER (WHERE {pr} OR {DEAD}) AS {tag}_t,")
    for tag, (k, pre, post) in TP.items():
        pr, po, tp = any_of(pre), any_of(post), f"tp{k}_rn"
        L.append(f"        min_by({val(pr, 'sm', 'lead_sm')}, rn) FILTER (WHERE ({pr} OR {DEAD}) AND ({tp} IS NULL OR rn < {tp})) AS {tag}_pv,")
        L.append(f"        min_by({edt(pr)}, rn) FILTER (WHERE ({pr} OR {DEAD}) AND ({tp} IS NULL OR rn < {tp})) AS {tag}_pt,")
        L.append(f"        min_by(smh, rn) FILTER (WHERE rn = {tp}) AS {tag}_hv,")
        L.append(f"        min_by({val(po, 'smh', 'lead_smh')}, rn) FILTER (WHERE rn > {tp} AND ({po} OR {DEAD})) AS {tag}_qv,")
        L.append(f"        min_by({edt(po)}, rn) FILTER (WHERE rn > {tp} AND ({po} OR {DEAD})) AS {tag}_qt,")
    # 首次 50% 回撤时刻的解剖（描述用，不进入规则选择之外的任何判定）
    for col, expr in [("dd_dt", "dt"), ("dd_runmax", "runmax_post"), ("dd_pm", "pm"), ("dd_venue", "venue"),
                      ("dd_ins_exit", "ins_exit"), ("dd_newb30", "newb30"), ("dd_sell30", "sell30"),
                      ("dd_buy30", "buy30"), ("dd_ins_sell30", "ins_sell30"), ("dd_sm", "sm"),
                      ("dd_nb_sell30", "nb_sell30"), ("dd_trades30", "trades30"), ("dd_trades30_prev", "trades30_prev")]:
        L.append(f"        min_by({expr}, rn) FILTER (WHERE rn = dd_rn) AS {col},")
    L += ["        max(pm) FILTER (WHERE rn > dd_rn) AS dd_post_max_pm,",
          "        max(ins_hold) AS ins_hold,", "        max(pos_hold) AS pos_hold,",
          "        count_if(p AND is_newb) AS n_newb_post,"]
    return "\n".join(L)


def final_sql():
    fee = "power(1 - a.efee / 1e4, 2)"
    L = []
    for tag in FULL:
        L.append(f"        round(COALESCE(a.{tag}_v, a.sm_last, {fee}), 6) AS {tag},")
        L.append(f"        COALESCE(a.{tag}_t, a.last_dt, 0) AS {tag}_dt,")
    for tag, (k, _, _) in TP.items():
        tp = f"a.tp{k}_rn"
        L.append(f"        round(CASE WHEN a.{tag}_pv IS NOT NULL THEN a.{tag}_pv WHEN {tp} IS NOT NULL "
                 f"THEN COALESCE(a.{tag}_hv, 0) + COALESCE(a.{tag}_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, {fee}) END, 6) AS {tag},")
        L.append(f"        CASE WHEN a.{tag}_pv IS NOT NULL THEN a.{tag}_pt WHEN {tp} IS NOT NULL "
                 f"THEN COALESCE(a.{tag}_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS {tag}_dt,")
    L += ["        round(COALESCE(a.ins_hold, 0) / nullif(a.pos_hold, 0), 4) AS ins_hold_share,",
          "        a.dd_dt, round(a.dd_runmax, 4) AS dd_runmax, a.dd_venue,",
          "        round(a.dd_ins_exit, 4) AS dd_ins_exit, a.dd_newb30,",
          "        round(a.dd_sell30, 4) AS dd_sell30, round(a.dd_buy30, 4) AS dd_buy30, round(a.dd_ins_sell30, 4) AS dd_ins_sell30,",
          "        round(a.dd_sm, 6) AS dd_sm, round(a.dd_post_max_pm / nullif(a.dd_pm, 0), 4) AS dd_rebound,",
          "        round(a.dd_nb_sell30, 4) AS dd_nb_sell30, a.dd_trades30, a.dd_trades30_prev,",
          "        a.n_newb_post,"]
    return "\n".join(L)


EDITS = [  # (旧, 新, 期望命中次数)
    ("-- DQ-1F · F1（", "-- [模板来源 DQ-1F · F1，经 dq7/sql/build_f2.py 定点修改]（", 1),
    ("INTERVAL '60' DAY", "INTERVAL '30' DAY", 2),
    ("                   lp_fee_basis_points IS NULL AS fee_missing\n            FROM pumpdotfun_solana.pump_amm_evt_buyevent",
     "                   lp_fee_basis_points IS NULL AS fee_missing,\n"
     "                   \"user\" AS usr, true AS is_buy, CAST(quote_amount_in AS DOUBLE) AS sraw, CAST(base_amount_out AS DOUBLE) AS traw\n"
     "            FROM pumpdotfun_solana.pump_amm_evt_buyevent", 1),
    ("                   lp_fee_basis_points IS NULL AS fee_missing\n            FROM pumpdotfun_solana.pump_amm_evt_sellevent",
     "                   lp_fee_basis_points IS NULL AS fee_missing,\n"
     "                   \"user\" AS usr, false AS is_buy, CAST(quote_amount_out AS DOUBLE) AS sraw, CAST(base_amount_in AS DOUBLE) AS traw\n"
     "            FROM pumpdotfun_solana.pump_amm_evt_sellevent", 1),
    ("        SELECT pool, ts, slot, txi, iix, fee_bps, fee_missing,\n",
     "        SELECT pool, ts, slot, txi, iix, fee_bps, fee_missing, usr, is_buy, sraw, traw,\n", 1),
    ("        CAST(NULL AS varchar) AS usr, CAST(NULL AS boolean) AS is_buy,\n"
     "        CAST(NULL AS DOUBLE) AS sol_amt, CAST(NULL AS DOUBLE) AS tok_amt, CAST(NULL AS boolean) AS outer_pump",
     "        p.usr, p.is_buy,\n"
     "        p.sraw / power(10, mp.qd) AS sol_amt, p.traw / power(10, mp.bd) AS tok_amt, CAST(NULL AS boolean) AS outer_pump", 1),
    ("        row_number() OVER (PARTITION BY mint, usr ORDER BY rn) AS u_rn1\n    FROM s2",
     "        row_number() OVER (PARTITION BY mint, usr ORDER BY rn) AS u_rn1,\n"
     "        min(CASE WHEN is_buy THEN rn END) OVER (PARTITION BY mint, usr) AS u_first_buy_rn\n    FROM s2", 1),
    ("AS u_rank\n    FROM s3",
     "AS u_rank,\n"
     "        usr IS NOT NULL AND (usr = dev OR u_first_buy_slot = created_slot) AS ins,\n"
     "        usr IS NOT NULL AND COALESCE(is_buy, false) AND rn = u_first_buy_rn AS is_newb,\n"
     "        usr IS NOT NULL AND NOT COALESCE(is_buy, true) AND (u_first_buy_rn IS NULL OR u_first_buy_rn > rn) AS is_nb_sell\n    FROM s3", 1),
    ("AS is_close\n    FROM s4",
     "AS is_close,\n"
     "        LEAST(\n"
     "            CASE WHEN venue = 0 AND y > tok / 2 THEN (x * y / (y - tok / 2) - x) * (1 - fee_bps / 1e4)\n"
     "                 WHEN venue = 0 THEN NULL\n"
     "                 ELSE (x - x * y / (y + tok / 2)) * (1 - fee_bps / 1e4) END,\n"
     "            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS smh,\n"
     "        sum(CASE WHEN u_first AND ins AND u_net_pre > 0 THEN u_net_pre END) OVER (PARTITION BY mint) AS ins_hold,\n"
     "        sum(CASE WHEN u_first AND u_net_pre > 0 THEN u_net_pre END) OVER (PARTITION BY mint) AS pos_hold,\n"
     "        sum(CASE WHEN p AND ins AND tok_amt IS NOT NULL THEN IF(is_buy, -tok_amt, tok_amt) END)\n"
     "            OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ins_cum_sold\n"
     "    FROM s4", 1),
    ("AS lead_ts\n    FROM s5",
     "AS lead_ts,\n"
     "        lead(smh) OVER (PARTITION BY mint ORDER BY rn) AS lead_smh,\n"
     "        COALESCE(ins_cum_sold / nullif(ins_hold, 0), 0) AS ins_exit,\n"
     "        sum(IF(is_newb, 1, 0)) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS newb30,\n"
     "        sum(CASE WHEN NOT is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS sell30,\n"
     "        sum(CASE WHEN is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS buy30,\n"
     "        sum(CASE WHEN ins AND NOT is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS ins_sell30,\n"
     "        sum(CASE WHEN is_nb_sell THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS nb_sell30,\n"
     "        count(*) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS trades30,\n"
     "        count(*) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 3600 PRECEDING AND 1801 PRECEDING) AS trades30_prev\n"
     "    FROM s5", 1),
    ("AS d_trig\n    FROM s6",
     "AS d_trig,\n"
     "        min(CASE WHEN p AND pm >= 2 THEN rn END) OVER (PARTITION BY mint) AS tp2_rn,\n"
     "        min(CASE WHEN p AND pm >= 3 THEN rn END) OVER (PARTITION BY mint) AS tp3_rn,\n"
     f"        min(CASE WHEN {TR50} THEN rn END) OVER (PARTITION BY mint) AS dd_rn\n"
     "    FROM s6", 1),
    ("6) AS ms_60d,", "6) AS ms_30d,", 1),
    ("6) AS hv_60d,", "6) AS hv_30d,", 1),
]

HEADER = """-- DQ-7 · F2（{variant}）：回撤时区分洗盘与砸盘 + 分批止盈。依据 dq7/DQ7_卡.md。
-- cohort 创建日 {c_start} ~ {c_end}；行情扫描至 {s_end}（入场后 30 天封顶）。
-- 相对 F1 的改动：持有期 60→30 天；PumpSwap 事件补入 user/方向/数量（毕业后也能追踪卖方）；
-- 新增 内部人集合（创建者 + 创建区块内买入者）持仓与入场后累计净卖出比例、30 分钟窗口新买家数与买卖额、半仓卖出价值；
-- 12 条退出规则（6 条全额 + 6 条分批止盈）与首次 50% 回撤时刻的解剖列（v1.1 增加：从未买过的钱包卖出额、30 分钟成交数及其前一个 30 分钟的成交数）。
-- 注意：已毕业后入场的币，入场前特征现在包含 PumpSwap 成交（F1 中不含），与 F1 的该部分特征不完全可比。
{warning}
"""


def render(v):
    base = F1.TEMPLATE.format(rules=agg_sql(), rule_final=final_sql(), pump=F1.PUMP, tail="__TAIL__",
                              variant=v["variant"], c_start=v["c_start"], c_end=v["c_end"], s_start=v["c_start"],
                              s_end=v["s_end"], h_start=v["h_start"], warning="")
    for old, new, n in EDITS:
        got = base.count(old)
        assert got == n, (old[:60], got, n)
        base = base.replace(old, new)
    ncols = len(F1.final_columns(base))
    if v["smoke"]:
        rules = ",\n".join(f"    round(avg({r}), 4) AS avg_{r},\n    count_if({r} > 1.5 * ms_30d + 0.1) AS bad_{r}" for r in RULE_NAMES)
        tail = ("-- 冒烟输出：一行汇总。bad_* 为回收超过事后最高价 1.5 倍的币数（应为 0）。\n"
                "SELECT\n    count(*) AS n_active,\n    count_if(dd_dt IS NOT NULL) AS n_dd,\n"
                "    approx_percentile(dd_newb30, 0.5) AS dd_newb30_p50,\n    approx_percentile(dd_ins_exit, 0.5) AS dd_ins_exit_p50,\n"
                "    count_if(dd_ins_exit > 1.5 OR dd_ins_exit < -1.5) AS bad_ins_exit,\n"
                "    approx_percentile(ins_hold_share, 0.5) AS ins_hold_share_p50,\n"
                "    count_if(ins_hold_share > 1.0001) AS bad_ins_share,\n"
                f"{rules}\nFROM final")
    else:
        tail = ("-- 正式输出：活跃池每个 mint 一行，外加一行 mint='__SUMMARY__'（cday = SOL 计价 cohort 数；flags = 非 SOL 计价数）。请在网页下载 CSV。\n"
                "SELECT * FROM final\nUNION ALL\nSELECT\n    '__SUMMARY__' AS mint,\n    (SELECT count(*) FROM sol_cohort) AS cday,\n"
                "    (SELECT count(*) FROM cohort) - (SELECT count(*) FROM sol_cohort) AS flags,\n"
                + ",\n".join(["    NULL"] * (ncols - 3)) + "\nORDER BY cday, mint")
    body = base.replace("__TAIL__", tail)
    warn = "-- 开发样本（已被 DQ-1M、DQ-1F 看过）。" if v["variant"] == "开发版" else (
        "-- 验证样本：从未打开过。只运行一次；分析脚本须在打开前冻结。" if v["variant"].startswith("验证") else "-- 冒烟：只看汇总与自检。")
    return HEADER.format(warning=warn, **v) + body, ncols


VARIANTS = {
    "F2_smoke": dict(variant="冒烟版", c_start="2026-06-07", c_end="2026-06-07", s_end="2026-06-10", h_start="2026-05-08", smoke=True),
    "F2_dev": dict(variant="开发版", c_start="2026-06-01", c_end="2026-06-07", s_end="2026-07-08", h_start="2026-05-02", smoke=False),
    "F2_val_w1": dict(variant="验证版 w1", c_start="2026-06-15", c_end="2026-06-21", s_end="2026-07-22", h_start="2026-05-16", smoke=False),
    "F2_val_w2": dict(variant="验证版 w2", c_start="2026-06-22", c_end="2026-06-28", s_end="2026-07-29", h_start="2026-05-23", smoke=False),
    "F2_val_w3": dict(variant="验证版 w3", c_start="2026-06-29", c_end="2026-07-05", s_end="2026-08-05", h_start="2026-05-30", smoke=False),
    "F2_val_w4": dict(variant="验证版 w4", c_start="2026-07-06", c_end="2026-07-12", s_end="2026-08-12", h_start="2026-06-06", smoke=False),
}


def main():
    out = {}
    for name, v in VARIANTS.items():
        sql, ncols = render(v)
        (HERE / f"{name}.sql").write_text(sql, encoding="utf-8")
        h = hashlib.sha256(sql.encode()).hexdigest()
        out[name] = h
        print(name, h, len(sql.splitlines()), "行", ncols, "列")
    (HERE / "sha256.txt").write_text("".join(f"{h}  {n}.sql\n" for n, h in out.items()))


if __name__ == "__main__":
    main()

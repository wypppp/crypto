"""DQ-8A · F3：检查点面板（按最终冻结版卡）。复用 DQ-7 F2 重扫描链至 s7，之后：
b1/b2/b3 为每个买入检查点 k=0..10 预计算本次持仓的买入状态、running peak、逐笔 50%/70% 移动止损触发与成交价值；
grp 按 (mint, 区间) 聚合；final 过滤活跃池并把新仓位触发与沉寂行打包成字符串列（减少下载数据点）。"""
import hashlib, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "dq7" / "sql"))
import build_f2 as F2  # noqa: E402

TAUS = [0, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 259200, 604800]
K = range(len(TAUS))  # 买入检查点 0..10；k=0 为原始入场（与原始仓位逻辑逐笔核对）
NIV = len(TAUS)       # 区间 0..11
DEAD = "(rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)"
LEAD5 = "(lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5)"
ST = ["x", "y", "xr", "venue", "fee_bps"]


def sv(k, p=""):
    """持仓 k 在某状态（p='' 为本行，p='lead_' 为下一笔）的卖出回收（÷0.5），口径同 F1 sm。"""
    X, Y, XR, V, F = (f"{p}{c}" for c in ST)
    t = f"tok_{k}"
    return (f"LEAST(CASE WHEN {V} = 0 AND {Y} > {t} THEN ({X} * {Y} / ({Y} - {t}) - {X}) * (1 - {F} / 1e4) "
            f"WHEN {V} = 0 THEN NULL ELSE ({X} - {X} * {Y} / ({Y} + {t})) * (1 - {F} / 1e4) END, "
            f"COALESCE(IF({V} = 0, {XR} + 0.5 * (1 - feeb_{k} / 1e4)), 1e18)) / 0.5")


def trig(k, s):
    keep = {50: "0.50", 70: "0.30"}[s]
    return f"(rn > rnk_{k} AND pm <= {keep} * greatest(pmb_{k}, COALESCE(pkr_{k}, pmb_{k})))"


def chain_sql():
    iv = "CASE WHEN dt <= 0 THEN 0 " + " ".join(f"WHEN dt <= {t} THEN {i}" for i, t in enumerate(TAUS) if i) + f" ELSE {NIV} END"
    lo = "CASE iv " + " ".join(f"WHEN {i} THEN {TAUS[i - 1]}" for i in range(1, NIV + 1)) + " END"
    rnk = ",\n".join(["        entry_rn AS rnk_0"] + [f"        max(CASE WHEN dt <= {TAUS[k]} + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_{k}" for k in K if k])
    b2 = []
    for k in K:
        for c, alias in (("pm", "pmb"), ("x", "xb"), ("y", "yb"), ("fee_bps", "feeb")):
            b2.append(f"        max(CASE WHEN rn = rnk_{k} THEN {c} END) OVER (PARTITION BY mint) AS {alias}_{k}")
        b2.append(f"        max(CASE WHEN rn > rnk_{k} THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_{k}")
    b3 = [f"        yb_{k} - xb_{k} * yb_{k} / (xb_{k} + 0.5 * (1 - feeb_{k} / 1e4)) AS tok_{k}" for k in K]
    return (",\nb1 AS (\n    SELECT *, " + lo + " AS lo\n    FROM (\n        SELECT *,\n" + rnk + ",\n        " + iv + " AS iv\n        FROM s7\n    ) z\n)"
            ",\nb2 AS (\n    SELECT *,\n" + ",\n".join(b2) + "\n    FROM b1\n)"
            ",\nb3 AS (\n    SELECT *,\n" + ",\n".join(b3) + "\n    FROM b2\n)")


def grp_sql():
    g = ["        mint", "        iv", "        count(*) AS n", "        min(dt) AS first_dt",
         "        min(dt) FILTER (WHERE dt > lo + 5) AS first_after5_dt", "        max(dt) AS last_dt",
         "        bool_or(venue = 0 AND x > 120) AS anom"]
    r = lambda c, e: {"x": f"round({e}, 6)", "xr": f"round({e}, 6)", "y": f"round({e}, 0)"}.get(c, e)
    for c in ST:
        g.append(f"        {r(c, f'max_by({c}, rn)')} AS l_{c}")
    g.append("        round(max_by(sm, rn) FILTER (WHERE rn >= entry_rn), 6) AS l_sm")
    for c in ST:
        g.append(f"        {r(c, f'max_by({c}, rn) FILTER (WHERE dt <= lo + 5)')} AS e_{c}")
    g.append("        round(max_by(sm, rn) FILTER (WHERE dt <= lo + 5 AND rn >= entry_rn), 6) AS e_sm")
    for n, e in [("pm", "round(max_by(pm, rn), 6)"), ("runmax", "round(max_by(runmax_post, rn), 6)"),
                 ("maxpm", "round(max(pm) FILTER (WHERE rn >= entry_rn), 6)"),
                 ("newb30", "max_by(newb30, rn)"), ("trades30", "max_by(trades30, rn)"), ("trades30_prev", "max_by(trades30_prev, rn)"),
                 ("buy30", "round(max_by(buy30, rn), 4)"), ("sell30", "round(max_by(sell30, rn), 4)"),
                 ("nb_sell30", "round(max_by(nb_sell30, rn), 4)"), ("ins_exit", "round(max_by(ins_exit, rn), 4)")]:
        g.append(f"        {e} AS f_{n}")
    # 原始仓位（F2 口径）的区间内首次触发
    for s, keep in ((50, "0.50"), (70, "0.30")):
        tr = f"(p AND pm <= {keep} * greatest(1.0, runmax_post))"
        g.append(f"        min(dt) FILTER (WHERE {tr}) AS t{s}_dt")
        g.append(f"        round(min_by(IF({LEAD5}, lead_sm, sm), rn) FILTER (WHERE {tr}), 6) AS t{s}_v")
    g.append(f"        min(dt) FILTER (WHERE {DEAD}) AS dead_dt")
    g.append(f"        round(min_by(sm, rn) FILTER (WHERE {DEAD}), 6) AS dead_sm")
    g.append(f"        array_join(array_agg(format('%d,%.6f,%.0f,%.6f,%d,%.2f', dt, x, y, COALESCE(xr, -1), venue, fee_bps)) FILTER (WHERE {DEAD}), ';') AS dead_rows")
    # 每个买入检查点 k 的新仓位触发（通用逻辑；k=0 用于与 t50/t70 核对）
    for k in K:
        for s in (50, 70):
            g.append(f"        min(dt) FILTER (WHERE {trig(k, s)}) AS k{k}_{s}_dt")
            g.append(f"        min_by(IF({LEAD5}, {sv(k, 'lead_')}, {sv(k)}), rn) FILTER (WHERE {trig(k, s)}) AS k{k}_{s}_v")
    return ",\ngrp AS (\n    SELECT\n" + ",\n".join(g) + "\n    FROM b3\n    GROUP BY 1, 2\n)"


def final_sql():
    items = [f"IF(k{k}_{s}_dt IS NULL, NULL, format('%d,%d,%d,%.6f', {k}, {s}, k{k}_{s}_dt, COALESCE(k{k}_{s}_v, -1)))" for k in K if k for s in (50, 70)]
    cols = (["mint", "iv", "n", "first_dt", "first_after5_dt", "last_dt"] + [f"l_{c}" for c in ST] + ["l_sm"] + [f"e_{c}" for c in ST] + ["e_sm"]
            + [f"f_{n}" for n in ["pm", "runmax", "maxpm", "newb30", "trades30", "trades30_prev", "buy30", "sell30", "nb_sell30", "ins_exit"]]
            + ["t50_dt", "t50_v", "t70_dt", "t70_v", "dead_dt", "dead_sm", "dead_rows"])
    packed = "array_join(filter(ARRAY[\n            " + ",\n            ".join(items) + "\n        ], z -> z IS NOT NULL), ';') AS trig_new"
    chk = ("(k0_50_dt IS DISTINCT FROM t50_dt OR k0_70_dt IS DISTINCT FROM t70_dt"
           " OR abs(COALESCE(k0_50_v, -9) - COALESCE(t50_v, -9)) > 1e-5 OR abs(COALESCE(k0_70_v, -9) - COALESCE(t70_v, -9)) > 1e-5) AS bad_k0")
    early = " OR ".join(f"k{k}_{s}_dt <= {TAUS[k]}" for k in K if k for s in (50, 70))
    return (",\nfin AS (\n    SELECT\n        " + ",\n        ".join(cols) + ",\n        " + packed + ",\n        " + chk
            + f",\n        ({early}) AS bad_early,\n        anom_any, x0, v0\n    FROM (\n        SELECT *,\n"
            "            max(CASE WHEN iv = 0 THEN l_x END) OVER (PARTITION BY mint) AS x0,\n"
            "            max(CASE WHEN iv = 0 THEN l_venue END) OVER (PARTITION BY mint) AS v0,\n"
            "            bool_or(anom) OVER (PARTITION BY mint) AS anom_any\n        FROM grp\n    ) q\n)"
            ",\nfinal AS (\n    SELECT * FROM fin WHERE x0 IS NOT NULL AND NOT anom_any AND (x0 >= 30.5 OR v0 = 1)\n)"), cols


LEAD_EDIT = ("        lead(smh) OVER (PARTITION BY mint ORDER BY rn) AS lead_smh,\n",
             "        lead(smh) OVER (PARTITION BY mint ORDER BY rn) AS lead_smh,\n"
             + "".join(f"        lead({c}) OVER (PARTITION BY mint ORDER BY rn) AS lead_{c},\n" for c in ST))

# 排序并列修复（冒烟 Gate 0 诊断，query 8753065 v7）：同一交易内不同外层指令的事件可能共享 inner_instruction_index，
# 原排序键 (slot, tx_index, inner_ix) 存在并列，Trino 每次扫描的并列次序可能不同。加入 outer_instruction_index 使次序确定。
ORDER_EDITS = [
    ("        t.evt_inner_instruction_index AS iix,\n", "        t.evt_inner_instruction_index AS iix,\n        t.evt_outer_instruction_index AS oix,\n", 1),
    ("p.txi, p.iix,", "p.txi, p.iix, p.oix,", 1),
    ("SELECT pool, ts, slot, txi, iix, fee_bps", "SELECT pool, ts, slot, txi, iix, oix, fee_bps", 1),
    ("ORDER BY slot, txi, iix)", "ORDER BY slot, txi, oix, iix)", 2),
    ("AS txi, evt_inner_instruction_index AS iix,", "AS txi, evt_inner_instruction_index AS iix, evt_outer_instruction_index AS oix,", 2),
    ("s.txi, s.iix)", "s.txi, s.oix, s.iix)", 1),
]

HEADER = """-- DQ-8A · F3（{variant}）：检查点面板。依据 dq8/DQ-8A 卡 · 决策价值地图（最终冻结版）.md。
-- cohort 创建日 {c_start} ~ {c_end}；行情扫描至 {s_end}（入场后 30 天封顶）。重扫描链与口径沿用 DQ-7 F2（build_f2.render 截至 s7）。
-- 行 = (mint, 区间 iv)。iv=0：入场及之前；iv=k (1..10)：(τ_{{k-1}}, τ_k]；iv=11：(7d, 30d]。τ = {taus} 秒。无成交区间不输出。
-- l_*：区间最后一笔后的状态（检查点决策信息）；e_*：区间开头 5 秒内最后一笔后的状态（上一检查点决策的成交状态）；*_sm：原始仓位卖出回收。
-- f_*：区间最后一笔处的特征（30 分钟窗口按该笔时间计）；f_maxpm：区间内最高价倍数。
-- t50/t70：原始仓位区间内首次触发 50%/70% 移动止损的时点与成交回收（5 秒抢跑规则）。dead_*：其后 24 小时无成交的行（dead_rows 打包全部：dt,x,y,xr,venue,fee）。
-- trig_new：检查点 k=1..10 新买入 0.5 SOL 的持仓（买入状态 = 截至 τ_k+5 秒最后一笔后；running peak 自买入起逐笔累积、跨区间延续）
--   在本区间首次触发 50%/70% 移动止损的 "k,s,dt,回收" 列表，以 ';' 分隔；回收 -1 表示无法估值。
-- 排序键含 outer_instruction_index（冒烟诊断后修复并列；DQ-1F/DQ-7 的旧 SQL 无此键）。
-- bad_k0：通用新仓位逻辑取 k=0 时与原始仓位 t50/t70 不一致（应恒为 false）；bad_early：新仓位触发早于买入（应恒为 false）。
{warning}
"""


def render(v):
    full, _ = F2.render(dict(v, smoke=False))
    body = full.split("\nWITH\n", 1)[1].split("\nagg AS (", 1)[0].rstrip().rstrip(",")
    assert body.count(LEAD_EDIT[0]) == 1
    body = body.replace(LEAD_EDIT[0], LEAD_EDIT[1])
    for old, new, n in ORDER_EDITS:
        assert body.count(old) == n, (old, body.count(old), n)
        body = body.replace(old, new)
    fin, cols = final_sql()
    sql = "WITH\n" + body + chain_sql() + grp_sql() + fin
    if v["smoke"]:
        b50_direct = ("min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN " + LEAD5 + " THEN lead_sm ELSE sm END) ELSE sm END, rn) "
                      "FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR " + DEAD + ")")
        sql += (",\ndirect AS (\n    SELECT mint, COALESCE(" + b50_direct + ", max_by(sm, rn) FILTER (WHERE p), power(1 - max(efee) / 1e4, 2)) AS b50_direct\n"
                "    FROM s7\n    GROUP BY 1\n)"
                ",\npb AS (\n    SELECT mint,\n"
                "        count(*) AS n_rows,\n        count_if(bad_k0) AS bad_k0,\n        count_if(bad_early) AS bad_early,\n"
                "        count_if(l_y <= 0 OR l_x <= 0) AS bad_state,\n        count_if(trig_new LIKE '%,-1.000000%') AS n_new_unvalued,\n"
                "        count_if(length(trig_new) > 0) AS n_rows_new_trig,\n        count_if(dead_dt IS NOT NULL) AS n_dead_rows,\n"
                "        max(length(trig_new)) AS max_trig_len,\n"
                "        COALESCE(min_by(CASE WHEN t50_dt IS NOT NULL AND (dead_dt IS NULL OR t50_dt <= dead_dt) THEN t50_v ELSE dead_sm END, iv)\n"
                "                 FILTER (WHERE t50_dt IS NOT NULL OR dead_dt IS NOT NULL),\n"
                "                 max_by(l_sm, iv) FILTER (WHERE l_sm IS NOT NULL)) AS b50_panel\n"
                "    FROM final\n    GROUP BY 1\n)\n"
                "-- 冒烟输出：一行汇总；bad_* 应为 0。重扫描链只被引用两次：面板路径（final→pb）与独立对照路径（direct）。\n"
                "SELECT\n    sum(n_rows) AS n_rows,\n    count(*) AS n_mints,\n    sum(bad_k0) AS bad_k0,\n    sum(bad_early) AS bad_early,\n"
                "    sum(bad_state) AS bad_state,\n    sum(n_new_unvalued) AS n_new_unvalued,\n    sum(n_rows_new_trig) AS n_rows_new_trig,\n"
                "    sum(n_dead_rows) AS n_dead_rows,\n    max(max_trig_len) AS max_trig_len,\n"
                "    count_if(abs(b50_panel - b50_direct) > 1e-5) AS bad_b50_mismatch,\n"
                "    round(avg(b50_panel), 6) AS b50_panel_mean,\n    round(avg(b50_direct), 6) AS b50_direct_mean\n"
                "FROM pb JOIN direct USING (mint)")
    else:
        sql += "\n-- 正式输出：请在网页下载 CSV。\nSELECT " + ", ".join(cols) + ", trig_new, bad_k0, bad_early\nFROM final\nORDER BY mint, iv"
    warn = {"冒烟版": "-- 冒烟：只看汇总与自检（含 b50 两路径对照、k=0 通用逻辑对照），会重复扫描一次，成本约为单路径的 2 倍。",
            "开发 A": "-- 开发 A（06-01～07，已被 DQ-1M/1F/7 看过）。",
            "开发 B": "-- 开发 B（06-08～14，DQ-1F 验证已打开并作废；仅作跨期检查，不是真正样本外）。"}[v["variant"]]
    return HEADER.format(warning=warn, taus=TAUS, **v) + sql


VARIANTS = {
    "F3_smoke": dict(variant="冒烟版", c_start="2026-06-07", c_end="2026-06-07", s_end="2026-06-10", h_start="2026-05-08", smoke=True),
    "F3_devA": dict(variant="开发 A", c_start="2026-06-01", c_end="2026-06-07", s_end="2026-07-08", h_start="2026-05-02", smoke=False),
    "F3_devB": dict(variant="开发 B", c_start="2026-06-08", c_end="2026-06-14", s_end="2026-07-15", h_start="2026-05-09", smoke=False),
}

if __name__ == "__main__":
    out = []
    for name, v in VARIANTS.items():
        sql = render(v)
        (HERE / f"{name}.sql").write_text(sql, encoding="utf-8")
        h = hashlib.sha256(sql.encode()).hexdigest(); out.append(f"{h}  {name}.sql\n")
        print(name, h[:16], len(sql.splitlines()), "行", len(sql), "字符")
    (HERE / "sha256.txt").write_text("".join(out))

"""第八轮 EDGE 标定：原始整数金额、完整地址核对、四列紧凑导出。

母体、种子、池与截点沿用现有生成器，旧批准 SQL 原样保留。
正式导出暂用完整地址：前缀会影响实体哈希并列与跨对去重。
冒烟同时估算 16 位前缀体积并检查窗口内碰撞，供路线报告选择。
"""

import datetime as dt
import re

import build_wm2_sql as B

SMOKE = """
SELECT count(*) AS n_rows,
       count_if(kind='S') AS n_s, count_if(kind='G') AS n_g, count_if(kind='T') AS n_t,
       sum(n_key-1) AS n_dup_key,
       count_if(a IS NULL OR b IS NULL) AS n_null_address,
       count_if(kind='G' AND x IS NULL) AS n_missing_fanout,
       /* 哈希覆盖压缩前全部字段与整数金额；以十六进制字符串保留所有位。 */
       lower(to_hex(checksum(array_join(ARRAY[
           kind, COALESCE(mint,'~'), a, b, CAST(n AS varchar), amt,
           CAST(first_t AS varchar), CAST(last_t AS varchar), COALESCE(CAST(x AS varchar),'~'),
           COALESCE(CAST(y AS varchar),'~'), CAST(n_key AS varchar)
       ], '|')))) AS ck_full_hex,
       lower(to_hex(checksum(array_join(ARRAY[kind,a,b,COALESCE(CAST(x AS varchar),'~')], '|')))) AS ck_compact_hex,
       sum(length(kind)+length(a)+length(b)+COALESCE(length(CAST(x AS varchar)),0)+4) AS est_compact_csv_bytes,
       sum(length(kind)+least(length(a),16)+least(length(b),16)+COALESCE(length(CAST(x AS varchar)),0)+4) AS est_prefix16_csv_bytes,
       sum(length(kind)+COALESCE(length(mint),0)+length(a)+length(b)+length(CAST(n AS varchar))+length(amt)
           +length(CAST(first_t AS varchar))+length(CAST(last_t AS varchar))
           +COALESCE(length(CAST(x AS varchar)),0)+COALESCE(length(CAST(y AS varchar)),0)+12) AS est_full_csv_bytes,
       /* 同一前缀对应两个完整端点才算碰撞；完整地址仍是实际身份。 */
       cardinality(array_distinct(concat(array_agg(a),array_agg(b))))
       - cardinality(array_distinct(transform(array_distinct(concat(array_agg(a),array_agg(b))), z -> substr(z,1,16))))
           AS n_prefix16_collisions
FROM out
"""


def build(c0, c1, event_end, edge_from, edge_cut, p=None, smoke=False):
    # 事件范围要覆盖 W 中所有创建日；不会按创建日拆成七条。
    sql = B.build(
        "EDGE",
        c0,
        c1,
        c0,
        event_end,
        edge_from=edge_from,
        edge_cut=edge_cut,
        p=p,
        edge_kinds="SGT",
    ).rsplit("\nSELECT * FROM out", 1)[0]
    sql = sql.replace("x.amount_display AS amt", "x.amount AS amt")
    sql = sql.replace("x.amount_display >= 0.05", "x.amount >= 50000000")
    sql = sql.replace("sum(x.amount_display)", "sum(x.amount)")
    # SGT 没有 C 边。去掉死 CTE，使审阅与静态扫描计数只含实际用途。
    sql = re.sub(
        r"\nc_edges AS \(.*?\n\),\nt_edges AS", "\nt_edges AS", sql, flags=re.S
    )
    sql = re.sub(r"\nc_keep AS \(.*?\n\),\nout AS", "\nout AS", sql, flags=re.S)
    # >200 是冻结规则。近似计数会在边界错分，采用精确不同收款方数。
    sql = sql.replace("approx_distinct(n.to_owner)", "count(DISTINCT n.to_owner)")
    sql = sql.replace(
        "用 approx_distinct（标准误约 2%，只用来和 200 比）",
        "用精确 count(DISTINCT)，按 >200 判定",
    )
    assert "amount_display" not in sql and "approx_distinct" not in sql
    assert "x.amount >= 50000000" in sql
    sql = "/* 第八轮：整数金额；完整身份；下载只需 kind,a,b,x。 */\n" + sql
    return sql + (SMOKE if smoke else "\nSELECT kind,a,b,x FROM out\n")


def calibration():
    return build(
        dt.date(2026, 8, 11),
        dt.date(2026, 8, 11),
        dt.date(2026, 8, 11),
        dt.date(2026, 8, 8),
        dt.date(2026, 8, 12),
        p=0.002,
        smoke=True,
    )


if __name__ == "__main__":
    (B.H / "sql/A8P_EDGE_SGT_0811_p002_4d_SMK.sql").write_text(calibration())

"""第十一轮零费用原型：MV关系、同步标签传播、压缩首笔上的S3统计。

这里只生成SQL。传播未收敛时Q检查拒绝；不把固定轮数当收敛。
MV1/MV2继续使用GPT已通过的v6原件。本文件不读取Dune密钥。
"""

import re

import wm2_deterministic_v6 as D  # isort: skip -- restores legacy import path

import s3_sql as S


def table(name):
    if not re.fullmatch(
        r"(?:[A-Za-z_][A-Za-z0-9_]*\.){0,2}[A-Za-z_][A-Za-z0-9_]*", name
    ):
        raise ValueError("表名须为一至三段固定标识符")
    return name


def links(edges, cex=()):
    """冻结entities的等价关系。G只连接种子，不把来源加入实体。"""
    for address in cex:
        if not re.fullmatch(r"[A-Za-z0-9]+", address):
            raise ValueError("交易所地址只能含字母数字")
    excluded = (
        "SELECT * FROM (VALUES "
        + ",".join("('" + address + "')" for address in sorted(cex))
        + ") AS t(u)"
        if cex
        else "SELECT CAST(NULL AS varchar) AS u WHERE FALSE"
    )
    return f"""WITH
e AS (SELECT * FROM {table(edges)}),
cex AS ({excluded}),
nb AS (
    SELECT kind,a AS u,b AS v FROM e WHERE kind IN ('S','T')
    UNION ALL SELECT kind,b,a FROM e WHERE kind IN ('S','T')
),
dg AS (SELECT kind,u,count(DISTINCT v) AS n FROM nb GROUP BY kind,u),
st AS (
    SELECT e.a,e.b FROM e JOIN dg a ON a.kind=e.kind AND a.u=e.a
    JOIN dg b ON b.kind=e.kind AND b.u=e.b
    WHERE e.kind IN ('S','T') AND a.n<=200 AND b.n<=200
      AND e.a NOT IN (SELECT u FROM cex) AND e.b NOT IN (SELECT u FROM cex)
),
g AS (
    SELECT DISTINCT a,b FROM e WHERE kind='G' AND x IS NOT NULL
      AND regexp_like(x,'^[0-9]+$') AND try_cast(x AS DECIMAL(38,0)) BETWEEN 0 AND 200
      AND a NOT IN (SELECT u FROM cex)
),
gr AS (SELECT a,min(b) AS root FROM g GROUP BY a),
ll AS (
    SELECT a,b FROM st
    UNION ALL SELECT r.root,g.b FROM g JOIN gr r ON r.a=g.a WHERE g.b<>r.root
),
out AS (
    SELECT DISTINCT 'L' AS kind,least(a,b) AS u,greatest(a,b) AS v,CAST(NULL AS bigint) AS q FROM ll
    UNION ALL
    SELECT 'Q',NULL,NULL,count_if(kind IS NULL OR kind NOT IN ('S','T','G') OR a IS NULL OR b IS NULL
      OR (kind='G' AND x IS NOT NULL AND (NOT regexp_like(x,'^[0-9]+$')
          OR try_cast(x AS DECIMAL(38,0)) IS NULL))) FROM e
)
SELECT * FROM out"""


def labels0(link_table):
    return f"""WITH nodes AS (
SELECT u FROM {table(link_table)} WHERE kind='L'
UNION SELECT v FROM {table(link_table)} WHERE kind='L')
SELECT u,u AS ent FROM nodes"""


def step(link_table, previous):
    return f"""WITH
nbr AS (
    SELECT u,v FROM {table(link_table)} WHERE kind='L'
    UNION ALL SELECT v,u FROM {table(link_table)} WHERE kind='L'
),
candidates AS (
    SELECT u,ent FROM {table(previous)}
    UNION ALL SELECT n.u,p.ent FROM nbr n JOIN {table(previous)} p ON p.u=n.v
)
SELECT u,min(ent) AS ent FROM candidates GROUP BY u"""


def convergence(link_table, labels):
    return f"""SELECT count_if(a.ent IS NULL OR b.ent IS NULL OR a.ent<>b.ent) AS n_unresolved
FROM {table(link_table)} l LEFT JOIN {table(labels)} a ON a.u=l.u
LEFT JOIN {table(labels)} b ON b.u=l.v WHERE l.kind='L'"""


def stats(first, link_table, labels, w0, cut, w1end, obs_cap):
    """已压缩B/A/E/K→原S3统计后半段；Q必须全部为0才能验收。"""
    if not w0 < cut < w1end or obs_cap < w1end:
        raise ValueError("日期次序不对")
    # 旧统计的后半段保持原算术。新的输入层只读已物化的允许输入。
    base = S.build_s3(w0, cut, w1end, None, S.emap_values({}), obs_cap=obs_cap)
    tail = ",\nlb AS (" + base.split(",\nlb AS (", 1)[1]
    tail = tail.replace("to_unixtime(e.e_ts)", "e.e_t").replace(
        "to_unixtime(f.ts)", "f.t"
    )
    prefix = f"""WITH
src AS (SELECT * FROM {table(first)}),
ml AS (SELECT u AS usr,ent,count(*) OVER (PARTITION BY ent) AS n FROM {table(labels)}),
emap AS (SELECT usr,ent FROM ml WHERE n>1),
cw0 AS (
    SELECT mint,t AS created_t,t<date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{cut}') AS is_w
    FROM src WHERE kind='K' AND t>=date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{w0}')
      AND t<date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{w1end}')
),
cw AS (
    SELECT *,least(created_t+2592000,date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '2026-10-05'),
      date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{obs_cap}'),
      IF(is_w,date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{cut}'),
         date_diff('second',TIMESTAMP '1970-01-01',TIMESTAMP '{obs_cap}'))) AS obs_end FROM cw0
),
ub AS (
    SELECT IF(s.kind='B','c','a') AS stg,s.mint,c.is_w,COALESCE(m.ent,s.usr) AS ent,s.t,
      TIMESTAMP '1970-01-01'+s.t*INTERVAL '1' SECOND AS ts,s.slot,s.txi,s.oix,s.iix,s.tx AS tx_id,
      CAST(s.pre AS DECIMAL(38,0)) AS pre,CAST(s.net60 AS DECIMAL(38,0)) AS net60,CAST(s.sz AS DECIMAL(38,0)) AS sz
    FROM src s JOIN cw c ON c.mint=s.mint LEFT JOIN emap m ON m.usr=s.usr
    WHERE s.kind IN ('B','A') AND s.t>=c.created_t AND s.t+1800<c.obs_end
),
fr AS (
    SELECT * FROM (SELECT ub.*,row_number() OVER (PARTITION BY ent,mint ORDER BY slot,txi,oix,iix,tx_id) AS rn FROM ub)
    WHERE rn=1
),
ce AS (
    SELECT s.mint,s.t AS e_t,s.slot AS e_slot,s.txi AS e_txi,s.oix AS e_oix,s.iix AS e_iix,
      s.tx AS e_tx,COALESCE(m.ent,s.usr) AS e_ent
    FROM src s JOIN cw c ON c.mint=s.mint LEFT JOIN emap m ON m.usr=s.usr
    WHERE s.kind='E' AND s.t>=c.created_t AND s.t<c.obs_end
)"""
    query = prefix + tail
    end = "\nSELECT * FROM out\n"
    assert query.endswith(end)
    query = (
        query[: -len(end)]
        + f""",
quality AS (
    SELECT 'source_bad' AS name,count_if(kind IS NULL OR kind NOT IN ('K','B','A','E')
      OR (kind='K' AND (q IS NULL OR q<>'1;0;0;0;0;0;0;0;0;0'))
      OR (kind IN ('B','A','E') AND (usr IS NULL OR NOT regexp_like(usr,'{D.NONSPACE}')
          OR tx IS NULL OR NOT regexp_like(tx,'{D.NONSPACE}') OR slot IS NULL OR txi IS NULL OR oix IS NULL OR iix IS NULL))) AS v FROM src
    UNION ALL SELECT 'link_bad',COALESCE(sum(q),0) FROM {table(link_table)} WHERE kind='Q'
    UNION ALL SELECT 'mapping_unresolved',n_unresolved FROM ({convergence(link_table, labels)})
    UNION ALL SELECT 'mapping_duplicate',count(*)-count(DISTINCT u) FROM {table(labels)}
),
final_out AS (
    SELECT * FROM out
    UNION ALL SELECT 'Q',name,v,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL FROM quality
)
SELECT * FROM final_out
"""
    )
    return query


def check_quality(rows):
    q = {r["ent"]: int(r["a"]) for r in rows if r["kind"] == "Q"}
    if set(q) != {
        "source_bad",
        "link_bad",
        "mapping_unresolved",
        "mapping_duplicate",
    } or any(q.values()):
        raise ValueError("MV源质量、映射或收敛检查失败")

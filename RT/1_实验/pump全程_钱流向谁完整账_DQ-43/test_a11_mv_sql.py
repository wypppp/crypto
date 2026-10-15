"""生成SQL到归并及S3统计的离线对照；无网络、无付费。"""

import random
import re

import duckdb
import pytest
import sqlglot

import a11_mv_sql as M
import s3_first_v6 as V
import s3_ref as R
from test_s3_sql import CAP, CUT, EMAP, W0, W1E, detail, gen, hand, run


def duck(sql):
    q = sql.replace("lower(to_hex(sha256(to_utf8(ent))))", "entsha__(ent)")
    q = sqlglot.transpile(q, read="trino", write="duckdb")[0]
    q = re.sub(r"(?i)entsha__\(ent\)", "sha256(ent)", q)
    return q.replace("DECIMAL(38, 0)", "HUGEINT").replace(
        "(kd - kd % sn) / sn", "(kd - kd % sn) // sn"
    )


def execute(con, sql):
    cur = con.execute(duck(sql))
    return [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()]


def load_graph(con, edges, cex=()):
    con.execute("CREATE TABLE edges(kind VARCHAR,a VARCHAR,b VARCHAR,x VARCHAR)")
    if edges:
        con.executemany(
            "INSERT INTO edges VALUES (?,?,?,?)",
            [(e["kind"], e["a"], e["b"], e.get("x")) for e in edges],
        )
    con.execute("CREATE TABLE links AS " + duck(M.links("edges", cex)))
    con.execute("CREATE TABLE labels AS " + duck(M.labels0("links")))


def finish(con):
    n = con.execute("SELECT count(*) FROM labels").fetchone()[0]
    for i in range(n + 1):
        unresolved = execute(con, M.convergence("links", "labels"))[0]["n_unresolved"]
        if unresolved == 0:
            return i
        con.execute("CREATE TABLE next_labels AS " + duck(M.step("links", "labels")))
        con.execute("DROP TABLE labels")
        con.execute("ALTER TABLE next_labels RENAME TO labels")
    raise AssertionError("标签未在顶点数界内收敛")


def mapping(con):
    rows = con.execute(
        "SELECT u,ent,count(*) OVER (PARTITION BY ent) AS n FROM labels"
    ).fetchall()
    return {u: ent for u, ent, n in rows if n > 1}


def load_first(con, short):
    numeric = {"t", "slot", "txi", "oix", "iix"}
    con.execute(
        "CREATE TABLE first_data("
        + ",".join(c + (" BIGINT" if c in numeric else " VARCHAR") for c in V.COLS)
        + ")"
    )
    if short:
        con.executemany(
            "INSERT INTO first_data VALUES (" + ",".join("?" for _ in V.COLS) + ")",
            [[r[c] for c in V.COLS] for r in short],
        )


def pairs_to_edges(emap):
    return [{"kind": "S", "a": u, "b": e} for u, e in emap.items() if u != e]


def test_generated_links_hubs_bridge_g_funder_and_type_specific_degrees():
    edges = [{"kind": "S", "a": "hub", "b": f"x{i}"} for i in range(201)]
    edges += [
        {"kind": "S", "a": "seed1", "b": "bridge"},
        {"kind": "S", "a": "seed2", "b": "bridge"},
        {"kind": "T", "a": "hub", "b": "token_peer"},
        {"kind": "G", "a": "0funder", "b": "g1", "x": "200"},
        {"kind": "G", "a": "0funder", "b": "g2", "x": "200"},
        {"kind": "G", "a": "0service", "b": "g3", "x": "201"},
        {"kind": "G", "a": "0service", "b": "g4", "x": "201"},
        {"kind": "G", "a": "single_funder", "b": "singleton", "x": "1"},
    ]
    con = duckdb.connect()
    load_graph(con, edges)
    finish(con)
    assert mapping(con) == R.entities(edges)[0]
    assert "0funder" not in mapping(con)


def test_cex_skips_st_endpoints_and_g_funder_but_keeps_g_seed():
    edges = [
        {"kind": "S", "a": "exchange", "b": "s"},
        {"kind": "T", "a": "exchange", "b": "t"},
        {"kind": "G", "a": "exchange", "b": "g1", "x": "2"},
        {"kind": "G", "a": "exchange", "b": "g2", "x": "2"},
        {"kind": "G", "a": "other", "b": "exchange", "x": "2"},
        {"kind": "G", "a": "other", "b": "normal", "x": "2"},
    ]
    con = duckdb.connect()
    load_graph(con, edges, {"exchange"})
    finish(con)
    assert mapping(con) == R.entities(edges, {"exchange"})[0]


@pytest.mark.parametrize("seed", range(12))
def test_random_graph_equals_frozen_dsu(seed):
    rng = random.Random(seed)
    edges = [
        {
            "kind": rng.choice(["S", "T", "G"]),
            "a": f"u{rng.randrange(12)}",
            "b": f"u{rng.randrange(12)}",
            "x": rng.choice([None, "1", "200", "201"]),
        }
        for _ in range(50)
    ]
    con = duckdb.connect()
    load_graph(con, edges)
    finish(con)
    assert mapping(con) == R.entities(edges)[0]


def test_no_fixed_round_count_can_be_treated_as_convergence():
    con = duckdb.connect()
    load_graph(
        con, [{"kind": "S", "a": f"u{i:03}", "b": f"u{i + 1:03}"} for i in range(20)]
    )
    assert execute(con, M.convergence("links", "labels"))[0]["n_unresolved"] == 20
    assert finish(con) == 20


@pytest.mark.parametrize("seed", range(12))
def test_compressed_mv_stats_equal_full_reference_and_w1_independence(seed):
    fx, emap = gen(seed)
    source = fx.con()
    short = run(source, V.build(W0, CUT, W1E, None, obs_cap=CAP))
    reference = R.reference(detail(source, emap), emap, W0, CUT, W1E, CAP)
    con = duckdb.connect()
    load_first(con, short)
    load_graph(con, pairs_to_edges(emap))
    finish(con)
    q = M.stats("first_data", "links", "labels", W0, CUT, W1E, CAP)
    out = execute(con, q)
    M.check_quality(out)
    got = R.parse_out(out)
    assert R.compare(got, reference) == []
    con.execute(
        "DELETE FROM first_data WHERE mint IN (SELECT mint FROM first_data WHERE kind='K' AND t>=?)",
        [R.epoch(CUT)],
    )
    only_w = R.parse_out(execute(con, q))
    assert {e for e, v in only_w["C"].items() if v[5]} == {
        e for e, v in got["C"].items() if v[5]
    }
    assert {k: v[:6] for k, v in only_w["C"].items()} == {
        k: v[:6] for k, v in got["C"].items()
    }


def test_quality_bad_source_and_unconverged_map_refused():
    short = run(hand().con(), V.build(W0, CUT, W1E, None, obs_cap=CAP))
    con = duckdb.connect()
    load_first(con, short)
    load_graph(con, pairs_to_edges(EMAP))
    q = M.stats("first_data", "links", "labels", W0, CUT, W1E, CAP)
    with pytest.raises(ValueError, match="收敛"):
        M.check_quality(execute(con, q))
    finish(con)
    con.execute("UPDATE first_data SET q='1;0;1;0;0;0;0;0;0;0' WHERE kind='K'")
    with pytest.raises(ValueError, match="源质量"):
        M.check_quality(execute(con, q))

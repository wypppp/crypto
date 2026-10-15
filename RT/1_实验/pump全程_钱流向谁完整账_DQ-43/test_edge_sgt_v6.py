"""从完整生成SQL起算：201服务节点与非种子桥接，不只测试手写边。"""

import datetime as dt
import re

import sqlglot

import edge_sgt_v5 as OLD
import edge_sgt_v6 as V
import s3_ref as R
import sql_determinism as SD
from test_edge_sgt_integer import integer_db
from test_wm2_semantic import coin, trade, xfer

D, T = dt.date, dt.datetime


def sql(module=V):
    return module.build(
        D(2026, 8, 10), D(2026, 8, 16), D(2026, 8, 16), D(2026, 8, 3), D(2026, 8, 17)
    )


def exported(con, q):
    # 同旧构造表适配：仅将保护名单改成虚构名；完整边CTE与最终导出均真跑。
    q = re.sub(
        r"bn\(base\) AS \(.*?\n\),\nexcl AS \(.*?\n\),",
        "bn(base) AS (SELECT 'HOLDX'),\nexcl AS (SELECT base FROM bn),",
        q,
        flags=re.DOTALL,
    )
    cur = con.execute(sqlglot.transpile(q, read="trino", write="duckdb")[0])
    cols = [x[0] for x in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def test_03_generated_service_node_201_rejects_old_false_merge():
    data = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", T(2026, 8, 11))],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            trade("m", u, 12) for u in ("h", "a", "b")
        ],
        "tokens_solana.transfers": [
            xfer("h", u, 12) for u in ["a", "b"] + [f"n{i}" for i in range(199)]
        ],
    }
    con = integer_db(data)
    new, old = exported(con, sql()), exported(con, sql(OLD))
    assert len([r for r in new if r["kind"] == "S"]) == 201
    assert R.entities(new)[0] == {}
    assert R.entities(old)[0] == {"a": "a", "b": "a", "h": "a"}
    # 独立逐笔构造完整关系，冻结归并器给同一答案。
    full = [
        {"kind": "S", "a": r["from_owner"], "b": r["to_owner"], "x": None}
        for r in data["tokens_solana.transfers"]
    ]
    assert R.entities(new)[0] == R.entities(full)[0]


def test_complete_degree_alone_would_miss_nonseed_bridge():
    early_a = xfer("ea", "a", 12)
    early_b = xfer("eb", "b", 12)
    early_a["block_time"] = T(2026, 8, 12, 11)
    early_b["block_time"] = T(2026, 8, 12, 11)
    data = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m", T(2026, 8, 11))],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            trade("m", u, 12) for u in ("a", "b")
        ],
        "tokens_solana.transfers": [
            early_a,
            early_b,
            xfer("bridge", "a", 12),
            xfer("bridge", "b", 12),
        ],
    }
    con = integer_db(data)
    new, old = exported(con, sql()), exported(con, sql(OLD))
    assert R.entities(old)[0] == {}
    full = [
        {"kind": "S", "a": r["from_owner"], "b": r["to_owner"], "x": None}
        for r in data["tokens_solana.transfers"]
    ]
    assert (
        R.entities(new)[0]
        == R.entities(full)[0]
        == {"a": "a", "b": "a", "bridge": "a", "ea": "a", "eb": "a"}
    )


def test_g200_201_and_future_cut_from_generated_sql():
    for receivers in (200, 201):
        data = {
            "pumpdotfun_solana.pump_evt_createevent": [coin("m", T(2026, 8, 11))],
            "pumpdotfun_solana.pump_evt_tradeevent": [
                trade("m", u, 12) for u in ("a", "b")
            ],
            "tokens_solana.transfers": [
                xfer("f", u, 12)
                for u in ["a", "b"] + [f"n{i}" for i in range(receivers - 2)]
            ],
        }
        data["tokens_solana.transfers"].append(xfer("f", "future", 18))
        rs = exported(integer_db(data), sql())
        assert "future" not in {r["b"] for r in rs}
        assert len([r for r in rs if r["kind"] == "G"]) == (
            2 if receivers == 200 else 0
        )
    SD.check(sql())

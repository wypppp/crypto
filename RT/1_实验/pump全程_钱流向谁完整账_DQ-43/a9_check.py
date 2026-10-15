"""第九轮零 credits 核对；只打印等价判断与结构计数。"""

import csv
import gzip
import json
from collections import Counter, defaultdict

import s3_first_v5 as V  # isort: skip -- establish local module path before legacy imports
import s3_first_local as L
import s3_real_replay as RP
import s3_ref as R
import s3_smoke as SM
from test_s3_sql import run

FIRST = "A9P_FIRST_0811_p002"
EDGE = "A9P_EDGE_MIN_0811_p002"


def raw(label):
    with gzip.open(SM.H / "raw/dune" / (label + ".csv.gz"), "rt", newline="") as f:
        return list(csv.DictReader(f))


def check_first(first, detail, emap):
    V.validate(first)
    got = V.reference(first, emap, SM.W0, SM.CUT, SM.W1E, SM.CAP)
    ref = R.reference(detail, emap, SM.W0, SM.CUT, SM.W1E, SM.CAP)
    compact = L.compress_detail(detail, SM.W0, SM.CUT, SM.W1E, SM.CAP)

    # 旧明细只带16字符前缀。逐列对账时，仅将新完整tx投影到旧列。
    def key(rows):
        return sorted(
            tuple(
                ""
                if r.get(c) in (None, "")
                else str(r[c])[:16]
                if c == "tx"
                else str(r[c])
                for c in L.F.COLS
            )
            for r in rows
        )

    prefixes = defaultdict(set)
    for r in first:
        if r.get("tx"):
            prefixes[r["tx"][:16]].add(r["tx"])
    w = {r["mint"] for r in first if r["kind"] == "K" and int(r["t"]) < R.epoch(SM.CUT)}
    only = V.reference(
        [r for r in first if r["mint"] in w], emap, SM.W0, SM.CUT, SM.W1E, SM.CAP
    )
    diffs = Counter(d[0] for d in R.compare(got, ref))
    return {
        "first_kinds": dict(Counter(r["kind"] for r in first)),
        "compressed_rows_equal_old_detail_projection": key(first) == key(compact),
        "full_tx_prefix_collisions": sum(len(s) > 1 for s in prefixes.values()),
        "diff_N_C_G": dict(diffs),
        "n_C": len(got["C"]),
        "n_G": len(got["G"]),
        "remove_W1_keeps_selection": only["sel_exact"] == got["sel_exact"],
        "frozen_selection_same": got["frozen_check"]["select_set_same"],
        "N_structure": {
            k: v
            for k, v in got["N"].items()
            if k.startswith(
                (
                    "n_coins",
                    "n_rows",
                    "n_ent",
                    "n_el",
                    "k_sel",
                    "chk_",
                    "n_amm",
                    "n_mapped",
                    "n_events",
                )
            )
        },
    }


def offline():
    detail = raw(SM.DETAIL)
    emap = json.loads((SM.H / "runs/s3_smoke_emap.json").read_text())["emap"]
    con, _ = RP.source_db(detail)
    con.execute(
        "CREATE OR REPLACE VIEW coins AS SELECT mint, CAST(to_timestamp(t) AS TIMESTAMP) AS created_at, 1 AS n_create FROM inp WHERE kind='K'"
    )
    con.execute(
        "CREATE OR REPLACE VIEW pools AS SELECT 'p_' || mint AS pool,mint,created_at,1 AS n_cp FROM coins"
    )
    sql = (
        "/* S3D_v5 already-filtered replay */ WITH cw AS ("
        + V.build(SM.W0, SM.CUT, SM.W1E, None, obs_cap=SM.CAP).split(",\ncw AS (", 1)[1]
    )
    first, second = run(con, sql), run(con, sql)
    out = check_first(first, detail, emap)
    out.update(
        scope="already filtered A7-06 detail, DuckDB first extraction core; source guards not re-tested here",
        local_double_identical=sorted(tuple(r[c] or "" for c in V.COLS) for r in first)
        == sorted(tuple(r[c] or "" for c in V.COLS) for r in second),
    )
    con.close()
    return out


def platform():
    first, second = raw(FIRST + "_r1"), raw(FIRST + "_r2")
    edges = raw(EDGE)
    with gzip.open(SM.CEX, "rt", newline="") as f:
        cex = {r["address"] for r in csv.DictReader(f)}
    new_map, counts = R.entities(edges, cex)
    old_map = json.loads((SM.H / "runs/s3_smoke_emap.json").read_text())["emap"]
    out = check_first(first, raw(SM.DETAIL), new_map)
    V.validate(second)
    out.update(
        scope="Dune/Trino trials only; not full result",
        platform_double_row_identical=first == second,
        edge_rows=len(edges),
        edge_kinds=dict(Counter(r["kind"] for r in edges)),
        entity_map_equals_A7_03=new_map == old_map,
        entity_counts=counts,
    )
    passed = (
        all(
            out[k]
            for k in (
                "platform_double_row_identical",
                "compressed_rows_equal_old_detail_projection",
                "remove_W1_keeps_selection",
                "frozen_selection_same",
                "entity_map_equals_A7_03",
            )
        )
        and not out["diff_N_C_G"]
        and out["full_tx_prefix_collisions"] == 0
    )
    out["status"] = "passed" if passed else "failed"
    return out


if __name__ == "__main__":
    import sys

    mode = sys.argv[1]
    out = {"offline": offline, "platform": platform}[mode]()
    (SM.H / "runs" / ("a9_" + mode + "_check.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("status") == "failed":
        raise SystemExit("平台等价核对失败，停下报告")

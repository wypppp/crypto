"""第九轮零 credits 核对；只打印等价判断与结构计数。"""

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict

import s3_first_v6 as V  # isort: skip -- establish local module path before legacy imports
import s3_first_local as L
import s3_real_replay as RP
import s3_ref as R
import s3_smoke as SM
from test_s3_sql import run

FIRST = "A10P_FIRST_0811_p002"
EDGE = "A10P_EDGE_FULLS_0811_p002"


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
        "CREATE OR REPLACE VIEW coins AS SELECT mint, CAST(to_timestamp(t) AS TIMESTAMP) AS created_at, 1 AS n_create,0 AS n_identity_bad FROM inp WHERE kind='K'"
    )
    con.execute(
        "CREATE OR REPLACE VIEW pools AS SELECT 'p_' || mint AS pool,mint,created_at,1 AS n_cp FROM coins"
    )
    con.execute("CREATE VIEW cp_candidates AS SELECT pool,mint FROM pools")
    con.execute(
        "CREATE VIEW cp AS SELECT pool,1 AS n_cp,1 AS n_mints,1 AS n_quotes,0 AS n_bad FROM pools"
    )
    sql = (
        "/* S3D_v6 already-filtered replay */ WITH cw AS ("
        + V.build(SM.W0, SM.CUT, SM.W1E, None, obs_cap=SM.CAP).split(",\ncw AS (", 1)[1]
    )
    first, second = run(con, sql), run(con, sql)
    out = check_first(first, detail, emap)
    out.update(
        scope="already filtered A7-06 detail, DuckDB first extraction core; creator/pool flags assumed zero because raw metadata absent; old map used; source guards not re-tested here",
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
    differences = [
        (u, old_map.get(u, u), new_map.get(u, u))
        for u in sorted(set(old_map) | set(new_map))
        if old_map.get(u, u) != new_map.get(u, u)
    ]
    out["mapping_difference_wallets"] = len(differences)
    if differences:
        path = SM.H / "raw/dune/a10_mapping_differences.csv.gz"
        with gzip.open(path, "wt", newline="") as f:
            w = csv.writer(f)
            w.writerow(["wallet", "old_entity", "new_entity"])
            w.writerows(differences)
        out["private_mapping_difference_file"] = str(path.relative_to(SM.H))
        out["private_mapping_difference_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    passed = (
        all(
            out[k]
            for k in (
                "platform_double_row_identical",
                "compressed_rows_equal_old_detail_projection",
                "remove_W1_keeps_selection",
                "frozen_selection_same",
            )
        )
        and not out["diff_N_C_G"]
        and out["full_tx_prefix_collisions"] == 0
    )
    out["status"] = (
        "mapping_explanations_required"
        if passed and differences
        else "passed"
        if passed
        else "failed"
    )
    return out


if __name__ == "__main__":
    import sys

    mode = sys.argv[1]
    out = {"offline": offline, "platform": platform}[mode]()
    (SM.H / "runs" / ("a10_" + mode + "_check.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("status") in ("failed", "mapping_explanations_required"):
        raise SystemExit("平台对账失败或映射差异尚未逐条解释，停止")

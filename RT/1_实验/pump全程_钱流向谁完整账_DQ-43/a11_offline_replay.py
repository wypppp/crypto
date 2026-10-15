"""旧A7-06缓存上的MV统计复放；无网络，不认证新源检查或新S映射。"""

import json

import duckdb

import paid_guard as PG  # isort: skip -- bind the local runner before legacy imports

import a10_check as C
import a11_mv_sql as M
from test_a11_mv_sql import execute, finish, load_first, load_graph, pairs_to_edges


def main():
    detail = C.raw(C.SM.DETAIL)
    short = C.L.compress_detail(detail, C.SM.W0, C.SM.CUT, C.SM.W1E, C.SM.CAP)
    for row in short:
        for key, value in row.items():
            if value == "":
                row[key] = None
        # 旧明细没有原池和创建者源记录，此处只能假设质量位合格。
        row["q"] = "1;0;0;0;0;0;0;0;0;0" if row["kind"] == "K" else None
    emap = json.loads((PG.H / "runs/s3_smoke_emap.json").read_text())["emap"]
    with duckdb.connect() as con:
        load_first(con, short)
        load_graph(con, pairs_to_edges(emap))
        rounds = finish(con)
        out = execute(
            con,
            M.stats(
                "first_data", "links", "labels", C.SM.W0, C.SM.CUT, C.SM.W1E, C.SM.CAP
            ),
        )
        M.check_quality(out)
    got = C.R.parse_out(out)
    ref = C.R.reference(detail, emap, C.SM.W0, C.SM.CUT, C.SM.W1E, C.SM.CAP)
    differences = C.R.compare(got, ref)
    if differences:
        raise ValueError(f"MV统计复放有{len(differences)}项差异，停止")
    check = {
        "scope": "offline old already-filtered A7-06 detail; old map expressed as a spanning forest; not v6 raw source, new S mapping, or Trino validation",
        "detail_rows": len(detail),
        "compressed_rows": len(short),
        "label_rounds_for_old_map_forest": rounds,
        "N_C_G_diff_count": len(differences),
        "n_C": len(got["C"]),
        "n_G": len(got["G"]),
        "source_K_flags_assumed_good_due_absent_raw_metadata": True,
        "no_network": True,
    }
    (PG.H / "runs/a11_mv_offline_check.json").write_text(
        json.dumps(check, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(check, ensure_ascii=False))


if __name__ == "__main__":
    main()

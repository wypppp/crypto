"""0 credits：在已经过滤的真实明细上复放 S3 统计核心。

不重测 Dune 的母体或池子过滤，也不代表 Trino 的执行已通过。
保留明细的完整整数、链上顺序键和交易前缀。
现金费用拆分只用于恢复 cash_in，池子创建时刻取币创建时刻：
输入的 A 行已经通过平台的池子过滤，此处只复放留下的买入。
方言转换沿用 test_s3_sql.duck；只输出等价与结构计数。
"""

from collections import Counter
import json

import duckdb
import pandas as pd

import s3_ref as R
import s3_smoke as SM
import s3_sql as S
from test_s3_sql import run


def replay(rows, emap):
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    frame = (
        pd.DataFrame(rows, columns=S.DETAIL_COLS, dtype=object).fillna("").astype(str)
    )
    con.register("raw_frame", frame)
    numbers = "t slot txi oix iix b amt tok cash r4".split()
    fields = []
    for c in S.DETAIL_COLS:
        typ = "DECIMAL(38,0)" if c in ("amt", "tok", "cash", "r4") else "BIGINT"
        fields.append(
            "CAST(NULLIF(%s, '') AS %s) AS %s" % (c, typ, c) if c in numbers else c
        )
    con.execute("CREATE VIEW inp AS SELECT %s FROM raw_frame" % ", ".join(fields))
    con.execute(
        "CREATE VIEW coins AS SELECT mint, CAST(to_timestamp(t) AS TIMESTAMP) AS created_at FROM inp WHERE kind='K'"
    )
    con.execute(
        "CREATE VIEW pools AS SELECT 'p_' || mint AS pool, mint, created_at FROM coins"
    )
    con.execute("CREATE SCHEMA pumpdotfun_solana")
    common = """
        CAST(to_timestamp(t) AS TIMESTAMP) AS evt_block_time,
        CAST(to_timestamp(t) AS DATE) AS evt_block_date,
        slot AS evt_block_slot, txi AS evt_tx_index,
        oix AS evt_outer_instruction_index, iix AS evt_inner_instruction_index,
        tx AS evt_tx_id, usr AS "user"
    """
    con.execute(
        """CREATE VIEW pumpdotfun_solana.pump_evt_tradeevent AS
        SELECT mint, %s, b=1 AS is_buy, NULL::BOOLEAN AS isBuy,
        amt AS sol_amount, NULL::DECIMAL(38,0) AS solAmount,
        tok AS token_amount, NULL::DECIMAL(38,0) AS tokenAmount,
        cash-amt AS fee, 0 AS creator_fee, r4 AS real_token_reserves
        FROM inp WHERE kind='T'"""
        % common
    )
    con.execute(
        """CREATE VIEW pumpdotfun_solana.pump_amm_evt_buyevent AS
        SELECT 'p_' || mint AS pool, %s FROM inp WHERE kind='A'"""
        % common
    )
    con.execute(
        """CREATE VIEW pumpdotfun_solana.pump_evt_completeevent AS
        SELECT mint, %s FROM inp WHERE kind='E'"""
        % common
    )
    sql = S.build_s3(SM.W0, SM.CUT, SM.W1E, None, S.emap_values(emap), obs_cap=SM.CAP)
    # 母体已由明细查询过滤。只复放原生成器从 emap 开始的统计核心。
    sql = "WITH\nemap(usr, ent) AS (" + sql.split(",\nemap(usr, ent) AS (", 1)[1]
    first = run(con, sql)
    second = run(con, sql)
    got = R.parse_out(first)
    ref = R.reference(rows, emap, SM.W0, SM.CUT, SM.W1E, SM.CAP)
    frozen = R.frozen_check(ref)
    diffs = Counter(d[0] for d in R.compare(got, ref))

    def strip(C):
        return {e: v[:6] for e, v in C.items()}

    selection = strip(got["C"])
    # 删除 W+1 的全部明细，W 的选集、得分、排序应保持不变。
    con.execute(
        """CREATE OR REPLACE VIEW inp AS SELECT %s FROM raw_frame
        WHERE mint IN (SELECT mint FROM raw_frame WHERE kind='K' AND CAST(t AS BIGINT)<%s)"""
        % (", ".join(fields), R.epoch(SM.CUT))
    )
    changed = R.parse_out(run(con, sql))

    def key(rs):
        return sorted(tuple(r[c] or "" for c in S.OUT_COLS) for r in rs)

    out = {
        "scope": "DuckDB replay of statistics on already filtered detail; not Dune/Trino acceptance",
        "detail_kinds": dict(Counter(r["kind"] for r in rows)),
        "local_double_run_identical": key(first) == key(second),
        "diff_sql_vs_reference": dict(diffs),
        "selection_certain": R.certain(got["C"], got["N"]["k_sel"]) == [],
        "frozen_select_set_same": frozen["select_set_same"],
        "T_from_G_equals_frozen": abs(float(R.t_stat(got["G"])) - frozen["T_frozen"])
        < 1e-9,
        "remove_W1_keeps_selection": selection == strip(changed["C"]),
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
        "n_C": len(got["C"]),
        "n_G": len(got["G"]),
    }
    con.close()
    return out


if __name__ == "__main__":
    emap = json.loads((SM.H / "runs/s3_smoke_emap.json").read_text())["emap"]
    out = replay(SM.raw(SM.DETAIL), emap)
    (SM.H / "runs/s3_real_replay_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))

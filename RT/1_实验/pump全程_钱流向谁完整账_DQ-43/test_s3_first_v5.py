"""手算、随机、围栏、键断言；SQL 只压缩输入，统计调用冻结参照。"""

import pytest

import edge_sgt_v5 as E
import s3_first_v5 as V
import s3_ref as R
import sql_determinism as D
from test_s3_sql import CAP, CE, CUT, EMAP, TR, W0, W1E, detail, gen, hand, run


def test_v5_mother_and_pool_guards():
    from test_s3_sql import CP, CR, t11
    from test_wm2_semantic import upto

    fx = hand()
    for mint in ("hold", "empty", "quote", "good_pool", "bad_pool"):
        fx.coin(mint, t11(0))
    for row in fx.t[CR]:
        if row["mint"] == "hold":
            row["symbol"] = "$HOLDX"
        if row["mint"] == "empty":
            row["symbol"] = " $ "
        if row["mint"] == "quote":
            row["quote_mint"] = "other"
    for mint in ("good_pool", "bad_pool"):
        fx.pool(mint, t11(1))
        fx.amm_buy(mint, "wallet", t11(2))
    fx.t[CP][-1]["evt_outer_executing_account"] = "other"
    con = fx.con()
    sql = V.build(W0, CUT, W1E, None, obs_cap=CAP)
    kept = {r[0] for r in con.execute(upto(sql, "coins")).fetchall()}
    assert "good_pool" in kept and not kept & {"hold", "empty", "quote"}
    rows = run(con, sql)
    assert {
        (r["mint"], r["kind"]) for r in rows if r["mint"] in {"good_pool", "bad_pool"}
    } == {("good_pool", "K"), ("bad_pool", "K"), ("good_pool", "A")}


def test_maturity_first_survives_nonmonotone_time():
    from test_s3_sql import t11

    fx = hand()
    fx.trade("mA", "inverse", t11(23, 40), True)
    fx.t[TR][-1]["evt_block_slot"] = 1
    fx.trade("mA", "inverse", t11(8), True)
    rows = run(fx.con(), V.build(W0, CUT, W1E, None, obs_cap=CAP))
    kept = [r for r in rows if r["usr"] == "inverse"]
    assert len(kept) == 1 and int(kept[0]["t"]) == R.epoch(t11(8))


@pytest.mark.parametrize("seed", range(12))
def test_v5_first_rows_equal_full_reference(seed):
    fx, emap = gen(seed)
    con = fx.con()
    short = run(con, V.build(W0, CUT, W1E, None, obs_cap=CAP))
    got = V.reference(short, emap, W0, CUT, W1E, CAP)
    assert R.compare(got, R.reference(detail(con, emap), emap, W0, CUT, W1E, CAP)) == []


def test_hand_and_remove_w1_are_equal():
    con = hand().con()
    q = V.build(W0, CUT, W1E, None, obs_cap=CAP)
    short = run(con, q)
    got = V.reference(short, EMAP, W0, CUT, W1E, CAP)
    assert R.compare(got, R.reference(detail(con, EMAP), EMAP, W0, CUT, W1E, CAP)) == []
    w = {r["mint"] for r in short if r["kind"] == "K" and int(r["t"]) < R.epoch(CUT)}
    only = V.reference([r for r in short if r["mint"] in w], EMAP, W0, CUT, W1E, CAP)
    assert only["sel_exact"] == got["sel_exact"]


@pytest.mark.parametrize("table", [TR, CE])
def test_duplicate_physical_key_rejects_instead_of_arbitrary_first(table):
    fx = hand()
    fx.t[table].append(dict(fx.t[table][0]))
    con = fx.con()
    rows = run(con, V.build(W0, CUT, W1E, None, obs_cap=CAP))
    with pytest.raises(ValueError, match="K.q"):
        V.validate(rows)


def test_static_v5_family_accepts_integer_sql():
    D.check(V.build(W0, CUT, W1E, 0.002, obs_cap=CAP))
    D.check(E.smoke())


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT sum(amount_display) FROM t",
        "SELECT approx_distinct(a) FROM t",
        "SELECT row_number() OVER (PARTITION BY mint ORDER BY slot) FROM t",
        "SELECT sum(CAST(a AS DOUBLE)) FROM t",
        "SELECT a FROM t LIMIT 1",
        "SELECT min_by(a,evt_block_time) FROM t",
        "SELECT a FROM t ORDER BY t",
    ],
)
def test_static_mutations_are_rejected(sql):
    with pytest.raises(ValueError):
        D.check(sql)


def test_standalone_import_does_not_select_legacy_runner():
    import subprocess
    import sys
    from pathlib import Path

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import a9_check; import run_dune; print(run_dune.__file__)",
        ],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == str(Path(__file__).resolve().parent / "run_dune.py")

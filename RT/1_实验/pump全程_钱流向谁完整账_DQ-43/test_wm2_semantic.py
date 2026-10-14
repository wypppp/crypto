"""WM2 取数 SQL 的构造表测试（10-14，GPT SQL 审阅 01～04、12）。

把生成器产出的 Trino SQL 截到某个 CTE，用 sqlglot 转成 DuckDB 方言，在同名的构造表上真跑，核对语义：
- 01 毕业、迁移、建池事件逐币限在创建后 30 天内（同批较早创建的币不得纳入第 34 天的事件）；
- 02 原始字节入口只进允许事件键（同笔混合交易里的其他事件、界外事件都不进）；
- 03 只在 PumpSwap 交易的钱包也进取边种子；
- 04 建边先按窗口过滤再汇总：创建前 7 天的关联体按逐币窗口判定（GPT 的反例），截点之后的转账不进事前图。
限制：原始字节的判别符条件（bytearray_substring）在 DuckDB 里换成 TRUE，这里只核“按允许键筛选”的连接；
留出名单换成一个构造名。不连 Dune、不读数据。
"""

import datetime as dt
import re

import duckdb
import pytest
import sqlglot

import build_wm2_sql as B

D = dt.date
T = dt.datetime
CREATOR, X, Y, Z = "creatorA", "walletX", "walletY", "walletZ"

TABLES = {
    "pumpdotfun_solana.pump_evt_createevent": (
        "mint name symbol uri creator user evt_tx_signer evt_tx_id bonding_curve token_program quote_mint",
        "evt_block_slot evt_tx_index evt_outer_instruction_index evt_inner_instruction_index "
        "virtual_sol_reserves virtual_token_reserves real_token_reserves virtual_quote_reserves token_total_supply",
        "is_mayhem_mode is_cashback_enabled",
    ),
    "pumpdotfun_solana.pump_evt_completeevent": ("mint", "", ""),
    "pumpdotfun_solana.pump_evt_completepumpammmigrationevent": ("mint pool", "", ""),
    "pumpdotfun_solana.pump_amm_evt_createpoolevent": (
        "pool base_mint quote_mint evt_outer_executing_account",
        "base_mint_decimals quote_mint_decimals index",
        "",
    ),
    "pumpdotfun_solana.pump_amm_evt_buyevent": (
        "evt_tx_id pool user",
        "evt_outer_instruction_index evt_inner_instruction_index user_quote_amount_in",
        "",
    ),
    "pumpdotfun_solana.pump_amm_evt_sellevent": (
        "evt_tx_id pool user",
        "evt_outer_instruction_index evt_inner_instruction_index user_quote_amount_out",
        "",
    ),
    "pumpdotfun_solana.pump_evt_tradeevent": (
        "mint user evt_tx_id evt_tx_signer fee_recipient creator ix_name quote_mint",
        "evt_block_slot evt_tx_index evt_outer_instruction_index evt_inner_instruction_index sol_amount solAmount "
        "token_amount tokenAmount virtual_sol_reserves virtualSolReserves virtual_token_reserves virtualTokenReserves "
        "real_sol_reserves real_token_reserves fee creator_fee cashback buyback_fee fee_basis_points "
        "creator_fee_basis_points cashback_fee_basis_points buyback_fee_basis_points quote_amount",
        "is_buy isBuy mayhem_mode track_volume",
    ),
    "solana.instruction_calls": (
        "tx_id executing_account data",
        "outer_instruction_index inner_instruction_index block_slot tx_index",
        "is_inner tx_success",
    ),
    "tokens_solana.transfers": (
        "from_owner to_owner tx_id token_version action outer_executing_account token_mint_address",
        "amount_display block_slot",
        "",
    ),
}


def db(rows: dict):
    con = duckdb.connect()
    for full, (vc, num, bo) in TABLES.items():
        schema, table = full.split(".")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cols = [f'"{c}" VARCHAR' for c in vc.split()]
        cols += [f'"{c}" DOUBLE' for c in num.split()]
        cols += [f'"{c}" BOOLEAN' for c in bo.split()]
        tcol = "block_time" if schema != "pumpdotfun_solana" else "evt_block_time"
        dcol = "block_date" if schema != "pumpdotfun_solana" else "evt_block_date"
        cols += [f'"{tcol}" TIMESTAMP', f'"{dcol}" DATE']
        con.execute(f"CREATE TABLE {full} ({', '.join(cols)})")
        for r in rows.get(full, []):
            r = dict(r)
            r.setdefault(dcol, r[tcol].date())
            keys = list(r)
            con.execute(
                f"INSERT INTO {full} ({', '.join(chr(34) + k + chr(34) for k in keys)}) VALUES ({', '.join('?' for _ in keys)})",
                [r[k] for k in keys],
            )
    return con


def upto(sql: str, name: str) -> str:
    """生成的 SQL 截到 CTE name 为止，再 SELECT 它。"""
    i = sql.index("\n%s AS (" % name) + 1
    j = sql.index("(", i)
    depth = 0
    for k in range(j, len(sql)):
        depth += {"(": 1, ")": -1}.get(sql[k], 0)
        if depth == 0:
            break
    q = sql[: k + 1] + "\nSELECT * FROM %s" % name
    q = re.sub(
        r"bn\(base\) AS \(.*?\n\),\nexcl AS \(.*?\n\),",
        "bn(base) AS (SELECT 'HOLDX'),\nexcl AS (SELECT base FROM bn),",
        q,
        flags=re.S,
    )
    # 原始字节判别符在 DuckDB 里无法计算：只核按允许键筛选的连接
    q = re.sub(r"\n\s*AND bytearray_substring\(c\.data, [19], 8\) = [^\n]*", "", q)
    q = q.replace("bytearray_substring(c.data, 9, 8) AS disc", "c.data AS disc")
    return sqlglot.transpile(q, read="trino", write="duckdb")[0]


def run(con, sql, name):
    return con.execute(upto(sql, name)).fetchall()


def coin(mint, created, creator=CREATOR, symbol="ABCX"):
    return {
        "mint": mint,
        "evt_block_time": created,
        "symbol": symbol,
        "creator": creator,
        "user": creator,
        "quote_mint": B.SYS,
    }


W10, W16 = D(2026, 8, 10), D(2026, 8, 16)  # 窗口周 08-10（W）


def test_01_completion_migration_pool_per_coin_window():
    """GPT 01：08-10 创建的币在 09-13（第 34 天）毕业、迁移、建池，不得纳入；08-16 创建的币同日（第 28 天）纳入。"""
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [
            coin("early", T(2026, 8, 10, 1)),
            coin("late", T(2026, 8, 16, 1)),
        ],
        "pumpdotfun_solana.pump_evt_completeevent": [
            {"mint": m, "evt_block_time": T(2026, 9, 13, 2)} for m in ("early", "late")
        ],
        "pumpdotfun_solana.pump_evt_completepumpammmigrationevent": [
            {"mint": m, "pool": "p_" + m, "evt_block_time": T(2026, 9, 13, 2)}
            for m in ("early", "late")
        ],
        "pumpdotfun_solana.pump_amm_evt_createpoolevent": [
            {
                "pool": "p_" + m,
                "base_mint": m,
                "quote_mint": B.WSOL,
                "evt_outer_executing_account": B.PUMP,
                "index": 0,
                "evt_block_time": T(2026, 9, 13, 2),
            }
            for m in ("early", "late")
        ],
    }
    con = db(rows)
    sql = B.build("COIN", W10, W16, W10, D(2026, 9, 14))
    assert {r[0] for r in run(con, sql, "comp")} == {"late"}
    assert {r[0] for r in run(con, sql, "mig")} == {"late"}
    pools = run(con, B.build("ATRADE", W10, W16, W10, D(2026, 9, 14)), "pools")
    assert {r[0] for r in pools} == {"p_late"}


def amm_rows():
    """允许池 p1（币 m1，08-11 创建、08-11 建池）；p2 是未纳入的池（币是留出同名）。"""
    return {
        "pumpdotfun_solana.pump_evt_createevent": [
            coin("m1", T(2026, 8, 11, 0)),
            coin("m2", T(2026, 8, 11, 0), symbol="$holdx"),
        ],
        "pumpdotfun_solana.pump_amm_evt_createpoolevent": [
            {
                "pool": p,
                "base_mint": m,
                "quote_mint": B.WSOL,
                "evt_outer_executing_account": B.PUMP,
                "index": 0,
                "evt_block_time": T(2026, 8, 11, 1),
            }
            for p, m in (("p1", "m1"), ("p2", "m2"))
        ],
        "pumpdotfun_solana.pump_amm_evt_buyevent": [
            # 同一笔交易 tx1：外层 2 买允许池，外层 3 买未纳入的池（混合交易）
            {
                "evt_tx_id": "tx1",
                "pool": "p1",
                "user": Z,
                "evt_outer_instruction_index": 2,
                "evt_inner_instruction_index": 5,
                "evt_block_time": T(2026, 8, 12, 3),
            },
            {
                "evt_tx_id": "tx1",
                "pool": "p2",
                "user": Z,
                "evt_outer_instruction_index": 3,
                "evt_inner_instruction_index": 5,
                "evt_block_time": T(2026, 8, 12, 3),
            },
        ],
        "solana.instruction_calls": [
            {
                "tx_id": "tx1",
                "outer_instruction_index": oix,
                "inner_instruction_index": 5,
                "executing_account": B.AMM,
                "is_inner": True,
                "tx_success": True,
                "data": "x",
                "block_time": T(2026, 8, 12, 3),
            }
            for oix in (2, 3)
        ],
    }


def test_02_amm_raw_entrance_only_allowed_keys():
    con = db(amm_rows())
    sql = B.build("ATRADE", W10, W16, W10, D(2026, 8, 20))
    assert run(con, sql, "ak") == [("B", "tx1", 2.0, 5.0)]
    ic = run(con, sql, "ic")
    assert [(r[0], r[3]) for r in ic] == [
        ("tx1", 2.0)
    ]  # 外层 3（未纳入的池）的原始记录不进


def test_02_curve_raw_entrance_only_allowed_keys():
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [
            coin("m1", T(2026, 8, 11, 0)),
            coin("m9", T(2026, 6, 9, 0)),  # 检验周的币
        ],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            {
                "mint": m,
                "user": Z,
                "evt_tx_id": "txc",
                "evt_outer_instruction_index": oix,
                "evt_inner_instruction_index": 7,
                "evt_block_time": T(2026, 8, 12, 3),
            }
            for m, oix in (("m1", 1), ("m9", 4))
        ],
        "solana.instruction_calls": [
            {
                "tx_id": "txc",
                "outer_instruction_index": oix,
                "inner_instruction_index": 7,
                "executing_account": B.PUMP,
                "is_inner": True,
                "tx_success": True,
                "data": "x",
                "block_time": T(2026, 8, 12, 3),
            }
            for oix in (1, 4)
        ],
    }
    con = db(rows)
    sql = B.build("CTRADE", W10, W16, W10, D(2026, 8, 20))
    assert [(r[0], r[1]) for r in run(con, sql, "ic")] == [("txc", 1.0)]


def test_03_amm_only_wallet_is_edge_seed():
    rows = amm_rows()
    con = db(rows)
    sql = B.build("EDGE", W10, W16, W10, D(2026, 8, 20))
    seeds = {r[0] for r in run(con, sql, "seed")}
    assert Z in seeds and CREATOR in seeds  # Z 只在 PumpSwap 交易过


def xfer(a, b, day, amt=1.0, version="native"):
    return {
        "from_owner": a,
        "to_owner": b,
        "amount_display": amt,
        "block_time": T(2026, 8, day, 12),
        "tx_id": "t%s%s%d" % (a, b, day),
        "token_version": version,
        "action": "transfer",
        "outer_executing_account": B.SYS,
    }


def test_04_creator_affiliation_uses_per_coin_window():
    """GPT 04 的反例：创建者与 X 在第 1、2、14 天往来，与 Y 在第 1、6、14 天往来，金额相同；币在第 11 天创建。
    全窗汇总两组一模一样；按创建前 7 天窗口，只有 Y 是关联体（第 6 天在 [4, 11) 内）。"""
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m1", T(2026, 8, 11, 0))],
        "tokens_solana.transfers": [xfer(CREATOR, X, d) for d in (1, 2, 14)]
        + [xfer(CREATOR, Y, d) for d in (1, 6, 14)],
    }
    con = db(rows)
    sql = B.build("EDGE", W10, W16, W10, D(2026, 8, 20), edge_from=D(2026, 8, 1))
    c = run(con, sql, "c_edges")
    assert [(r[0], r[2], r[3]) for r in c] == [("m1", Y, 1)]


def test_04_snapshot_cut_excludes_later_transfers():
    """事前图截点（W+1 周一 08-17 00:00）之后的转账不进 S 边；截点之前的进。"""
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m1", T(2026, 8, 11, 0))],
        "tokens_solana.transfers": [xfer(CREATOR, X, 12), xfer(CREATOR, Y, 18)],
    }
    con = db(rows)
    sql = B.build(
        "EDGE",
        W10,
        W16,
        W10,
        D(2026, 8, 20),
        edge_from=D(2026, 8, 3),
        edge_cut=D(2026, 8, 17),
    )
    s = run(con, sql, "s_edges")
    assert {(r[0], r[1]) for r in s} == {(CREATOR, X)}


def test_edge_window_guard():
    with pytest.raises(SystemExit):
        B.build("EDGE", W10, W16, W10, D(2026, 8, 20), edge_cut=D(2026, 10, 6))

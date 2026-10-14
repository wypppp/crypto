"""汇总版取数 SQL 的构造表测试（10-14，取数附录 v2 §3；冻结前清单第 8 条：核心记账有手算预期值）。

同 test_wm2_semantic.py 的做法：生成的 Trino SQL 截到某个 CTE，转成 DuckDB 方言，在同名构造表上真跑。
不连 Dune、不读数据。
"""

import datetime as dt
import re
from decimal import Decimal

import build_wm2_sql as B
from test_wm2_semantic import D, T, W10, W16, coin, db, upto

A, Bw, C = "walletA", "walletB", "walletC"
E15 = D(2026, 9, 15)


def ctr(
    mint,
    usr,
    t,
    buy,
    sol,
    tok,
    fee=1,
    cfee=1,
    slot=None,
    txi=0,
    oix=1,
    iix=0,
    rtr=500,
    cashback=None,
):
    return {
        "mint": mint,
        "user": usr,
        "evt_tx_id": "tx_%s_%s" % (usr, t.isoformat()),
        "evt_block_time": t,
        "evt_block_slot": slot if slot is not None else int(t.timestamp()),
        "evt_tx_index": txi,
        "evt_outer_instruction_index": oix,
        "evt_inner_instruction_index": iix,
        "is_buy": buy,
        "sol_amount": sol,
        "token_amount": tok,
        "fee": fee,
        "creator_fee": cfee,
        "cashback": cashback,
        "buyback_fee": 0,
        "virtual_sol_reserves": 1000,
        "virtual_token_reserves": 2000,
        "real_sol_reserves": 300,
        "real_token_reserves": rtr,
        "fee_basis_points": 95,
        "creator_fee_basis_points": 30,
    }


def s_(h, m=0, sec=0, day=11):
    return T(2026, 8, day, h, m, sec)


def curve_rows():
    """m1 08-11 00:00 创建。A 01:00:00 买 100（费 1＋1）；B 01:00:30 卖 40；C 01:01:10 买 10；
    A 01:02:00 卖 50（费 1＋1）；A 08-17 01:00 再买 20（快照截点 08-17 00:00 之后）；
    m1 第 31 天（09-11 01:00）的成交不进。"""
    return {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m1", s_(0))],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            ctr("m1", A, s_(1), True, 100, 1000),
            ctr("m1", Bw, s_(1, 0, 30), False, 40, 300),
            ctr("m1", C, s_(1, 1, 10), True, 10, 90),
            ctr("m1", A, s_(1, 2), False, 50, 400),
            ctr("m1", A, s_(1, day=17), True, 20, 150),
            ctr("m1", C, T(2026, 9, 11, 1), True, 7, 7),
        ],
    }


def dec(x):
    return None if x is None else Decimal(str(x))


def named(con, sql, name, rewrite=lambda q: q):
    cur = con.execute(rewrite(upto(sql, name)))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_cycc_wallet_coin_totals_hand():
    con = db(curve_rows())
    sql = B.build("CYCC", W10, W16, W10, E15)
    ag = {r["usr"]: r for r in named(con, sql, "ag")}
    a = ag[A]
    assert (a["n_buy"], a["n_sell"]) == (2, 1)
    assert dec(a["in_cash"]) == 102 + 22  # 买入现金＝sol＋两费
    assert dec(a["out_cash"]) == 50 - 2  # 卖出到手＝sol−两费
    assert (dec(a["tok_buy"]), dec(a["tok_sell"])) == (1150, 400)
    pre = (a["in_pre"], a["out_pre"], a["tok_buy_pre"], a["tok_sell_pre"])
    assert tuple(dec(x) for x in pre) == (102, 48, 1000, 400)  # 截点 08-17 之前
    assert dec(ag[C]["in_cash"]) == 12  # 第 31 天的那笔不进
    assert set(ag) == {A, Bw, C}


def test_cycc_first_buy_state_hand():
    """C 的首笔买入（01:01:10）：顺序键在前的成交 A＋100、B−40，净 60；其中 t−60 秒（01:00:10）之前的只有 A＋100，
    所以前 60 秒净买入＝60−100＝−40。之前的买入只有 A 一笔（现金 102）；C 的现金 12 低于它，K 为假。
    A 的首笔买入之前没有成交：净买入 0，没有先前买入，K 为空。A 先卖（01:02）后买（08-17），sb 为真。
    首笔买入的状态＝成交后的真实代币储备（构造值 500）。"""
    con = db(curve_rows())
    sql = B.build("CYCC", W10, W16, W10, E15)
    y = {r["usr"]: r for r in named(con, sql, "y")}
    c = y[C]
    assert dec(c["fb_net60"]) == -40
    assert c["fb_k"] is False
    assert (dec(c["fb_cash"]), dec(c["fb_tok"]), dec(c["fb_r"])) == (12, 90, 500)
    assert c["fb_t"] == s_(1, 1, 10).replace(tzinfo=dt.timezone.utc).timestamp()
    assert c["fb_comp"] is None  # 这个币没有毕业
    a = y[A]
    assert (dec(a["fb_net60"]), a["fb_k"]) == (0, None)
    assert a["sb"] is True and c["sb"] is None  # C 没有卖出：比较为空
    b = y[Bw]
    assert (
        b["fb_slot"] is None and b["sb"] is None and b["fb_net60"] is None
    )  # 只卖不买


def test_cycc_k_label_and_completion_tx_hand():
    """K：D 的首笔买入现金 1000＋2，高于之前全部买入（102、12）的第 99 百分位，K 为真。
    毕业：m1 在 D 那笔交易里毕业，D 的首笔买入 fb_comp 为真，其他人为假。"""
    rows = curve_rows()
    t = s_(1, 3)
    rows["pumpdotfun_solana.pump_evt_tradeevent"].append(
        ctr("m1", "walletD", t, True, 1000, 5000)
    )
    rows["pumpdotfun_solana.pump_evt_completeevent"] = [
        {
            "mint": "m1",
            "user": "walletD",
            "evt_tx_id": "tx_walletD_%s" % t.isoformat(),
            "evt_block_time": t,
        }
    ]
    con = db(rows)
    sql = B.build("CYCC", W10, W16, W10, E15)
    y = {r["usr"]: r for r in named(con, sql, "y")}
    assert y["walletD"]["fb_k"] is True and y["walletD"]["fb_comp"] is True
    assert y[C]["fb_comp"] is False


def test_cycc_price_state_snapshots_hand():
    """P 行：S＝快照截点 08-17 00:00 之前最后一笔（A 01:02 卖出）；E＝窗口内最后一笔（A 08-17 买入）。"""
    con = db(curve_rows())
    sql = B.build("CYCC", W10, W16, W10, E15)
    z = {r["z_cut"]: r for r in named(con, sql, "z")}
    assert z["S"]["ts"] == s_(1, 2) and z["E"]["ts"] == s_(1, day=17)
    assert z["E"]["z_n"] == 5  # 窗口内 5 笔（第 31 天那笔不算）
    assert (dec(z["E"]["zf_pr"]), dec(z["E"]["zf_cr"])) == (
        5,
        5,
    )  # 协议费、创建者费合计


def test_cycc_snapshot_cut_must_follow_creation():
    import pytest

    with pytest.raises(SystemExit):
        B.build("CYCC", W10, W16, W10, E15, snap=W16)


def amm(
    kind, pool, usr, t, user_q, pool_q, tok, q0, b0, lp=2, pr=1, cr=1, cashback=None
):
    r = {
        "evt_tx_id": "tx_%s_%s" % (usr, t.isoformat()),
        "pool": pool,
        "user": usr,
        "evt_block_time": t,
        "evt_block_slot": int(t.timestamp()),
        "evt_tx_index": 0,
        "evt_outer_instruction_index": 1,
        "evt_inner_instruction_index": 0,
        "protocol_fee": pr,
        "coin_creator_fee": cr,
        "lp_fee": lp,
        "pool_quote_token_reserves": q0,
        "pool_base_token_reserves": b0,
        "lp_fee_basis_points": 20,
        "protocol_fee_basis_points": 5,
        "coin_creator_fee_basis_points": 5,
    }
    if kind == "B":
        r.update(
            user_quote_amount_in=user_q,
            quote_amount_in_with_lp_fee=pool_q,
            base_amount_out=tok,
        )
    else:
        r.update(
            user_quote_amount_out=user_q,
            quote_amount_out=pool_q,
            base_amount_in=tok,
            cashback=cashback,
            buyback_fee=0,
        )
    return r


def amm_rows():
    """m1 08-11 00:00 创建，08-11 01:00 建池 p1。A 08-11 02:00 买：付 104，进池 102（含 LP 费 2），得 500 代币；
    A 08-12 03:00 卖 200：池付出 quote_amount_out 60（含 LP 费 2），到手 56，返现 3。"""
    return {
        "pumpdotfun_solana.pump_evt_createevent": [coin("m1", s_(0))],
        "pumpdotfun_solana.pump_amm_evt_createpoolevent": [
            {
                "pool": "p1",
                "base_mint": "m1",
                "quote_mint": B.WSOL,
                "evt_outer_executing_account": B.PUMP,
                "index": 0,
                "evt_block_time": s_(1),
                "evt_block_slot": 7,
                "evt_tx_id": "txpool",
            }
        ],
        "pumpdotfun_solana.pump_amm_evt_buyevent": [
            amm("B", "p1", A, s_(2), 104, 102, 500, 1000, 9000)
        ],
        "pumpdotfun_solana.pump_amm_evt_sellevent": [
            amm("S", "p1", A, s_(3, day=12), 56, 60, 200, 1102, 8500, cashback=3)
        ],
    }


def test_cyca_cash_and_reserves_hand():
    con = db(amm_rows())
    sql = B.build("CYCA", W10, W16, W10, E15)
    buy, sell = sorted(named(con, sql, "ev"), key=lambda r: r["ts"])
    assert (dec(buy["amt"]), dec(buy["cash"])) == (102, 104)  # 进池 102，用户付 104
    assert tuple(dec(buy[k]) for k in ("r1", "r2", "r3", "r4")) == (
        1000,
        9000,
        1102,
        8500,
    )
    assert (dec(sell["amt"]), dec(sell["cash"])) == (
        58,
        56,
    )  # 出池 60−LP 费 2＝58，到手 56
    assert (dec(sell["r3"]), dec(sell["r4"])) == (1102 - 58, 8700)
    (a,) = named(con, sql, "ag")
    got = tuple(
        dec(a[k]) for k in ("in_cash", "out_cash", "tok_buy", "tok_sell", "f_cb")
    )
    assert got == (104, 56, 500, 200, 3)
    (y,) = named(con, sql, "y")
    assert dec(y["fb_r"]) == 1000  # PumpSwap 首笔买入的状态＝成交前的池报价储备


def test_cyc_output_rows_and_keys():
    """输出：每个“钱包 × 币”一行 Y，每币 S、E 两行 P；键不重复。"""
    con = db(curve_rows())
    sql = B.build("CYCC", W10, W16, W10, E15)
    out = named(con, sql, "out")
    assert list(out[0]) == B.AG.CYC_COLS.split()
    kinds = sorted((r["kind"], r["usr"] or "", r["z_cut"] or "") for r in out)
    assert kinds == [
        ("P", "", "E"),
        ("P", "", "S"),
        ("Y", A, ""),
        ("Y", Bw, ""),
        ("Y", C, ""),
    ]
    assert all(r["n_key"] == 1 for r in out)
    assert {r["m12"] for r in out} == {"m1"}  # 币号＝mint 前 12 位


# ---------- COSTF：交易表的构造（DuckDB 嵌套类型） ----------


def _close(s: str, i: int) -> int:
    """s[i] 是 '('，返回与之配对的 ')' 的下标。"""
    depth = 0
    for k in range(i, len(s)):
        depth += {"(": 1, ")": -1}.get(s[k], 0)
        if depth == 0:
            return k
    raise ValueError("括号不配对")


def _split_top(s: str) -> list:
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += {"(": 1, ")": -1, "[": 1, "]": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()]


def duck(q: str) -> str:
    """Trino 专有写法换成 DuckDB 的等价写法（只用于构造表测试）：
    any_match(l, f) → len(list_filter(l, f)) > 0；CROSS JOIN UNNEST(a, b) AS x(c1, c2) → 拉链式 UNNEST 的横向子查询。"""
    while "ANY_MATCH(" in q:
        i = q.index("ANY_MATCH(")
        j = _close(q, i + len("ANY_MATCH"))
        q = (
            q[:i]
            + "(LEN(LIST_FILTER("
            + q[i + len("ANY_MATCH(") : j]
            + ")) > 0)"
            + q[j + 1 :]
        )
    while "CROSS JOIN UNNEST(" in q:
        i = q.index("CROSS JOIN UNNEST(")
        j = _close(q, i + len("CROSS JOIN UNNEST"))
        args = _split_top(q[i + len("CROSS JOIN UNNEST(") : j])
        m = re.match(r"\s*AS (\w+)\(([^)]*)\)", q[j + 1 :])
        alias, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        sel = ", ".join("UNNEST(%s) AS %s" % (a, c) for a, c in zip(args, cols))
        q = (
            q[:i]
            + "CROSS JOIN LATERAL (SELECT %s) AS %s" % (sel, alias)
            + q[j + 1 + m.end() :]
        )
    return q


def tx_db(rows: dict, txs: list):
    con = db(rows)
    con.execute("CREATE SCHEMA IF NOT EXISTS solana")
    con.execute(
        """CREATE TABLE solana.transactions (
            id VARCHAR, block_time TIMESTAMP, block_date DATE, block_slot BIGINT, "index" BIGINT, signer VARCHAR,
            success BOOLEAN, fee BIGINT, required_signatures BIGINT, account_keys VARCHAR[],
            pre_balances BIGINT[], post_balances BIGINT[],
            pre_token_balances STRUCT(account VARCHAR, mint VARCHAR, owner VARCHAR)[],
            post_token_balances STRUCT(account VARCHAR, mint VARCHAR, owner VARCHAR)[],
            loaded_addresses STRUCT(writable VARCHAR[], readonly VARCHAR[]))"""
    )
    for t in txs:
        t = dict(t)
        t.setdefault("block_date", t["block_time"].date())
        t.setdefault("loaded_addresses", {"writable": [], "readonly": []})
        keys = list(t)
        con.execute(
            "INSERT INTO solana.transactions (%s) VALUES (%s)"
            % (", ".join('"%s"' % k for k in keys), ", ".join("?" for _ in keys)),
            [t[k] for k in keys],
        )
    return con


M_IN, M_OUT = "m_in0", "a_out0"  # p＝50% 时 m_in0 入样、a_out0 不入样（B.in_sample）
FEE_RECIP, XO, JITO0 = "feeRecip", "otherX", B.JITO[0]


def cost_case():
    """手算用例（事件日 08-12，p＝50%）：
    tx1：A 在曲线买 m_in0（sol 100、两费各 1，现金 −102）；总费 6000（1 个签名：网络 5000、优先 1000），Jito 小费 10000，
         A 另付给 otherX 500（未解释）。A 的净变化 −16602，残差＝−16602＋6000＋10000＋102＝−500。只有一条腿。
    tx2：A 同一笔买 m_in0 与 a_out0（不入样）；总费 7001、无小费。腿号排序 a_out0|curve 在前：
         m_in0 分 (7001−1)/2＝3500，余数 1 给 a_out0（不输出）；网络费 5000 各 2500。
         A 名下有 a_out0 的代币账户，不在抽样腿里，范围不完整，不计残差。
    tx3：F 的失败交易，账户键含 pump、m_in0、a_out0；总费 5000，按母体币数 2 均摊，m_in0 不是排序第一，分 2500。"""
    t1, t2, t3 = s_(5, day=12), s_(6, day=12), s_(7, day=12)
    rows = {
        "pumpdotfun_solana.pump_evt_createevent": [
            coin(M_IN, s_(0)),
            coin(M_OUT, s_(0)),
        ],
        "pumpdotfun_solana.pump_evt_tradeevent": [
            dict(ctr(M_IN, A, t1, True, 100, 1000), evt_tx_id="tx1"),
            dict(ctr(M_IN, A, t2, True, 100, 1000), evt_tx_id="tx2"),
            dict(ctr(M_OUT, A, t2, True, 50, 500, oix=2), evt_tx_id="tx2"),
        ],
    }
    ata = [{"account": "ataA1", "mint": M_IN, "owner": A}]
    txs = [
        {
            "id": "tx1",
            "block_time": t1,
            "block_slot": 1,
            "index": 0,
            "signer": A,
            "success": True,
            "fee": 6000,
            "required_signatures": 1,
            "account_keys": [A, "ataA1", "curve1", FEE_RECIP, XO, JITO0, B.PUMP],
            "pre_balances": [1_000_000, 2_039_280, 0, 0, 0, 0, 1],
            "post_balances": [983_398, 2_039_280, 100, 1, 500, 10_000, 1],
            "pre_token_balances": ata,
            "post_token_balances": ata,
        },
        {
            "id": "tx2",
            "block_time": t2,
            "block_slot": 2,
            "index": 0,
            "signer": A,
            "success": True,
            "fee": 7001,
            "required_signatures": 1,
            "account_keys": [A, "ataA1", "ataA2", B.PUMP],
            "pre_balances": [983_398, 2_039_280, 2_039_280, 1],
            "post_balances": [983_398 - 7001 - 154, 2_039_280, 2_039_280, 1],
            "pre_token_balances": ata,
            "post_token_balances": ata
            + [{"account": "ataA2", "mint": M_OUT, "owner": A}],
        },
        {
            "id": "tx3",
            "block_time": t3,
            "block_slot": 3,
            "index": 0,
            "signer": "F",
            "success": False,
            "fee": 5000,
            "required_signatures": 1,
            "account_keys": ["F", B.PUMP, M_IN, M_OUT],
            "pre_balances": [100_000, 1, 1, 1],
            "post_balances": [95_000, 1, 1, 1],
            "pre_token_balances": [],
            "post_token_balances": [],
        },
    ]
    return rows, txs


def test_costf_allocation_hand():
    rows, txs = cost_case()
    con = tx_db(rows, txs)
    sql = B.build("COSTF", W10, W16, D(2026, 8, 12), D(2026, 8, 12), p=0.5)
    out = named(con, sql, "out", duck)
    assert list(out[0]) == B.AG.COSTF_COLS.split()
    got = {(r["kind"], r["signer"], r["m12"], r["stage"]): r for r in out}
    assert set(got) == {("K", A, M_IN[:12], "c"), ("F", "F", M_IN[:12], "c")}
    k = got[("K", A, M_IN[:12], "c")]
    assert k["n_tx"] == 2
    assert dec(k["cost"]) == 16000 + 3500
    assert dec(k["cost_net"]) == 5000 + 2500
    assert dec(k["cost_tip"]) == 10000
    assert dec(k["res_neg"]) == 500
    assert (k["n_tx_clean"], k["n_tx_unclean"]) == (1, 1)
    f = got[("F", "F", M_IN[:12], "c")]
    assert (f["n_tx"], dec(f["cost"]), dec(f["res_neg"])) == (1, 2500, 0)

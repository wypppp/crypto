"""S3 汇总 SQL 与本机参照的等价（10-14，总控第七轮第二、三节）。0 credits：DuckDB 构造表，不连 Dune。

覆盖：多钱包实体同买一币、自身触发（同一实体触发、同一笔交易）、逐事件排除（自身事件与外部事件都在窗内）、
未成熟、毕业后买入（PumpSwap）、截点之后的信息、得分并列（sha256 定序）；随机构造数据上 SQL 与参照逐项相等；
改动 W+1 的任何数据（含 W 币在截点之后的成交与事件）不改变入选集合；与冻结的 a_riskset 对照；并查集与确定性判断。
"""

import calendar
import datetime as dt
import random
import re
from fractions import Fraction

import pytest

import a_riskset as A
import build_wm2_sql as B
import s3_ref as R
import s3_sql as S
from test_wm2_semantic import coin, db, upto

T = dt.datetime
D = dt.date
W0, CUT, W1E, CAP = D(2026, 8, 11), D(2026, 8, 12), D(2026, 8, 13), D(2026, 8, 13)
TR, CE = (
    "pumpdotfun_solana.pump_evt_tradeevent",
    "pumpdotfun_solana.pump_evt_completeevent",
)
CP, AB = (
    "pumpdotfun_solana.pump_amm_evt_createpoolevent",
    "pumpdotfun_solana.pump_amm_evt_buyevent",
)
CR = "pumpdotfun_solana.pump_evt_createevent"


def ep(t: T) -> int:
    return calendar.timegm(t.timetuple())


def duck(sql: str) -> str:
    """Trino → DuckDB。两处方言差异：sha256 的写法；DECIMAL(38,0) 的除法在 DuckDB 里变成浮点，
    改用 HUGEINT 与整数除法（Trino 的 DECIMAL(38,0) 整除结果精确，与此相同）。"""
    q = sql.replace("lower(to_hex(sha256(to_utf8(ent))))", "entsha__(ent)")
    out = upto(q, "out")
    out = re.sub(r"(?i)entsha__\(ent\)", "sha256(ent)", out)
    out = out.replace("DECIMAL(38, 0)", "HUGEINT")
    out = out.replace("(kd - kd % sn) / sn", "(kd - kd % sn) // sn")
    assert "(kd - kd % sn) // sn" in out or "S3D" in sql
    return out


def run(con, sql):
    cur = con.execute(duck(sql))
    cols = [d[0] for d in cur.description]
    return [
        dict(
            zip(
                cols,
                [
                    None if v is None else str(v) if not isinstance(v, str) else v
                    for v in r
                ],
            )
        )
        for r in cur.fetchall()
    ]


def stats(con, emap):
    return R.parse_out(
        run(con, S.build_s3(W0, CUT, W1E, None, S.emap_values(emap), obs_cap=CAP))
    )


def detail(con, emap):
    return run(
        con,
        S.build_s3(W0, CUT, W1E, None, S.emap_values(emap), detail=True, obs_cap=CAP),
    )


class Fx:
    """构造数据：逐笔记录成交、毕业、建池与 PumpSwap 买入；同时生成 DuckDB 表与参照用的明细。"""

    def __init__(self):
        self.t = {CR: [], TR: [], CE: [], CP: [], AB: []}
        self.n = 0

    def tx(self):
        self.n += 1
        return "T%015d" % self.n

    def coin(self, m, t):
        self.t[CR].append(coin(m, t))

    def trade(
        self,
        m,
        u,
        t,
        buy,
        sol=1000,
        tok=100,
        r4=500,
        txi=0,
        oix=1,
        iix=0,
        tx=None,
        sub=0,
    ):
        tx = tx or self.tx()
        self.t[TR].append(
            {
                "mint": m, "user": u, "evt_tx_id": tx, "evt_block_time": t,
                "evt_block_slot": ep(t) * 10 + sub, "evt_tx_index": txi,
                "evt_outer_instruction_index": oix, "evt_inner_instruction_index": iix,
                "is_buy": buy, "sol_amount": sol, "token_amount": tok, "fee": 10, "creator_fee": 5,
                "real_token_reserves": r4,
            }
        )  # fmt: skip
        return tx

    def complete(self, m, u, t, tx=None, txi=0, oix=1, iix=1, sub=0):
        self.t[CE].append(
            {
                "mint": m, "user": u, "evt_tx_id": tx or self.tx(), "evt_block_time": t,
                "evt_block_slot": ep(t) * 10 + sub, "evt_tx_index": txi,
                "evt_outer_instruction_index": oix, "evt_inner_instruction_index": iix,
            }
        )  # fmt: skip

    def pool(self, m, t):
        self.t[CP].append(
            {
                "pool": "p_" + m, "base_mint": m, "quote_mint": B.WSOL, "evt_outer_executing_account": B.PUMP,
                "index": 0, "evt_block_time": t, "evt_tx_id": self.tx(), "evt_block_slot": ep(t) * 10,
            }
        )  # fmt: skip

    def amm_buy(self, m, u, t, sub=0):
        self.t[AB].append(
            {
                "evt_tx_id": self.tx(), "pool": "p_" + m, "user": u, "evt_block_time": t,
                "evt_block_slot": ep(t) * 10 + sub, "evt_tx_index": 0,
                "evt_outer_instruction_index": 1, "evt_inner_instruction_index": 0,
                "user_quote_amount_in": 1000, "quote_amount_in_with_lp_fee": 990, "base_amount_out": 10,
            }
        )  # fmt: skip

    def detail(self):
        """参照用的明细，直接从构造数据生成（不经 SQL）。"""
        out = [
            {"kind": "K", "mint": r["mint"], "t": ep(r["evt_block_time"])}
            for r in self.t[CR]
        ]
        for r in self.t[TR]:
            out.append(
                {
                    "kind": "T", "mint": r["mint"], "usr": r["user"], "t": ep(r["evt_block_time"]),
                    "slot": r["evt_block_slot"], "txi": r["evt_tx_index"], "oix": r["evt_outer_instruction_index"],
                    "iix": r["evt_inner_instruction_index"], "tx": r["evt_tx_id"][:16], "b": int(r["is_buy"]),
                    "amt": r["sol_amount"], "tok": r["token_amount"], "cash": r["sol_amount"] + 15,
                    "r4": r["real_token_reserves"],
                }
            )  # fmt: skip
        pools = {
            r["pool"]: (r["base_mint"], ep(r["evt_block_time"])) for r in self.t[CP]
        }
        for r in self.t[AB]:
            m, pt = pools[r["pool"]]
            if ep(r["evt_block_time"]) >= pt:
                out.append(
                    {
                        "kind": "A", "mint": m, "usr": r["user"], "t": ep(r["evt_block_time"]),
                        "slot": r["evt_block_slot"], "txi": 0, "oix": 1, "iix": 0, "tx": r["evt_tx_id"][:16],
                    }
                )  # fmt: skip
        for r in self.t[CE]:
            out.append(
                {
                    "kind": "E", "mint": r["mint"], "usr": r["user"], "t": ep(r["evt_block_time"]),
                    "slot": r["evt_block_slot"], "txi": r["evt_tx_index"], "oix": r["evt_outer_instruction_index"],
                    "iix": r["evt_inner_instruction_index"], "tx": r["evt_tx_id"][:16],
                }
            )  # fmt: skip
        return out

    def con(self):
        return db(self.t)


def t11(h, m=0, s=0):
    return T(2026, 8, 11, h, m, s)


EMAP = {"x1": "x1", "x2": "x1"}  # 多钱包实体 X＝{x1, x2}，代表取字典序最小


def hand():
    """W 的币 mA～mF（08-11 创建），W+1 的币 nA（08-12）。"""
    f = Fx()
    for i, m in enumerate("mA mB mC mD mE mF".split()):
        f.coin(m, t11(0, i))
    f.coin("nA", T(2026, 8, 12, 0))
    # mA：x2 先买（实体 X 的首笔），x1 后买；g1 的买入与毕业在同一笔交易（自身：同一笔交易）
    f.trade("mA", "x2", t11(1), True)
    f.trade("mA", "x1", t11(1, 1), True)
    f.trade("mA", "y1", t11(1, 2), True)
    tx = f.trade("mA", "g1", t11(1, 10), True)
    f.complete("mA", "g1", t11(1, 10), tx=tx, iix=1)
    # mB：毕业由 x2 触发（X 的首笔是 x1 02:00）→ X 自身；y1 命中
    f.trade("mB", "x1", t11(2), True)
    f.trade("mB", "y1", t11(2, 1), True)
    tx = f.trade("mB", "x2", t11(2, 5), True)
    f.complete("mB", "x2", t11(2, 5), tx=tx, iix=1)
    # mC：两条毕业事件都在 X 的窗内：一条由 x1 触发（自身），一条外部（命中）→ hit 与 slf 同为 1
    f.trade("mC", "x1", t11(3), True)
    f.trade("mC", "y1", t11(3, 0, 30), True)
    f.complete("mC", "x1", t11(3, 1))
    f.complete("mC", "g1", t11(3, 2))
    # mD：毕业在 X 首笔买入 60 分钟后，窗外
    f.trade("mD", "x1", t11(4), True)
    f.trade("mD", "y1", t11(4, 1), True)
    f.trade("mD", "z1", t11(4, 2), True)
    f.complete("mD", "g1", t11(5))
    # mE：x1 23:40 的买入＋30 分钟越过截点 08-12 00:00 → 未成熟
    f.trade("mE", "y1", t11(6), True)
    f.trade("mE", "x1", t11(23, 40), True)
    # mF：毕业 07:20；之后建池，v1 只在 PumpSwap 买（毕业后买入）；x1 也在 PumpSwap 买，但 X 已有曲线行
    f.trade("mF", "x1", t11(7), True)
    f.trade("mF", "y1", t11(7, 0, 1), True, sub=1)
    f.trade("mF", "z1", t11(7, 1), True)
    f.complete("mF", "g1", t11(7, 20))
    f.pool("mF", t11(7, 21))
    f.amm_buy("mF", "v1", t11(8))
    f.amm_buy("mF", "x1", t11(8), sub=1)
    # mA 截点之后的毕业不进 W（这里给 mE 一条截点之后的毕业）
    f.complete("mE", "g1", T(2026, 8, 12, 0, 5))
    # W+1：X 与 y1 在 nA 买入，nA 外部毕业
    f.trade("nA", "x1", T(2026, 8, 12, 1), True)
    f.trade("nA", "y1", T(2026, 8, 12, 1, 1), True)
    f.complete("nA", "g1", T(2026, 8, 12, 1, 5))
    return f


def test_labels_hand():
    f = hand()
    sql = S.build_s3(W0, CUT, W1E, None, S.emap_values(EMAP), obs_cap=CAP)
    q = upto(sql.replace("lower(to_hex(sha256(to_utf8(ent))))", "entsha__(ent)"), "lb")
    q = q.replace("DECIMAL(38, 0)", "HUGEINT")
    cur = f.con().execute(q)
    cols = [d[0] for d in cur.description]
    lb = {
        (r["ent"], r["mint"]): r for r in (dict(zip(cols, x)) for x in cur.fetchall())
    }
    hs = lambda k: (lb[k]["hit"], lb[k]["slf"])  # noqa: E731
    assert lb[("x1", "mA")]["ts"] == t11(1)  # 实体 X 的首笔是 x2 的买入
    assert ("x2", "mA") not in lb
    assert hs(("x1", "mA")) == (1, 0) and hs(("y1", "mA")) == (1, 0)
    assert hs(("g1", "mA")) == (0, 1)  # 同一笔交易
    assert hs(("x1", "mB")) == (0, 1) and hs(("y1", "mB")) == (1, 0)  # 同一实体触发
    assert hs(("x1", "mC")) == (1, 1)  # 逐事件：自身与外部都在窗内
    assert hs(("x1", "mD")) == (0, 0)  # 窗外
    assert ("x1", "mE") not in lb and ("y1", "mE") in lb  # 未成熟；截点之后的毕业不进 W
    assert hs(("y1", "mE")) == (0, 0)
    assert lb[("v1", "mF")]["stg"] == "a" and hs(("v1", "mF")) == (0, 0)  # 毕业后买入
    assert lb[("x1", "mF")]["stg"] == "c"
    assert hs(("x1", "nA")) == (1, 0)


def test_hand_sql_equals_reference():
    f = hand()
    con = f.con()
    sql = stats(con, EMAP)
    ref = R.reference(f.detail(), EMAP, W0, CUT, W1E, CAP)
    assert R.compare(sql, ref) == []
    assert R.compare(sql, R.reference(detail(con, EMAP), EMAP, W0, CUT, W1E, CAP)) == []
    n = sql["N"]
    assert (n["n_coins_w"], n["n_coins_w1"]) == (6, 1)
    assert n["n_el"] == 2  # X 有 mA、mB、mC、mD、mF 五行；y1 有六行；其余不足 5 行
    assert n["k_sel"] == 1
    assert n["chk_amm_event"] == 0 and n["chk_hit_and_slf"] == 1
    assert n["n_mapped_w"] == 1


def gen(seed, n_w=8, n_w1=6, n_wal=14):
    rng = random.Random(seed)
    f = Fx()
    wal = ["w%02d" % i for i in range(n_wal)]
    for i in range(n_w + n_w1):
        m = "c%02d" % i
        day = 11 if i < n_w else 12
        c = T(2026, 8, day, rng.randint(0, 22), rng.randint(0, 59))
        f.coin(m, c)
        t = c
        trades = []
        for j in range(rng.randint(10, 30)):
            t = t + dt.timedelta(seconds=rng.choice([0, 5, 20, 40, 90, 400]))
            u = rng.choice(wal)
            buy = rng.random() < 0.75
            tx = f.trade(
                m, u, t, buy,
                sol=rng.choice([1, 2, 3, 5]) * 1000, tok=rng.choice([0, 50, 100]),
                r4=rng.choice([100, 200, 300, 400]), sub=j % 10,
            )  # fmt: skip
            trades.append((t, u, tx, j % 10))
        if rng.random() < 0.6:
            k = rng.randrange(3, len(trades))
            t, u, tx, sub = trades[k]
            if rng.random() < 0.5:
                f.complete(m, u, t, tx=tx, sub=sub, iix=1)  # 与一笔成交同一交易
            else:
                f.complete(m, rng.choice(wal + ["gx"]), t, sub=sub, txi=1)
            if rng.random() < 0.15:
                f.complete(
                    m, rng.choice(wal), t + dt.timedelta(seconds=30), sub=9, txi=2
                )
            f.pool(m, t + dt.timedelta(seconds=60))
            for _ in range(rng.randint(0, 5)):
                f.amm_buy(
                    m, rng.choice(wal), t + dt.timedelta(seconds=rng.randint(61, 9000))
                )
    emap = {"w00": "w00", "w01": "w00", "w02": "w02", "w03": "w02", "w04": "w02"}
    return f, emap


@pytest.mark.parametrize("seed", range(12))
def test_random_sql_equals_reference(seed):
    f, emap = gen(seed)
    con = f.con()
    sql = stats(con, emap)
    ref = R.reference(f.detail(), emap, W0, CUT, W1E, CAP)
    assert R.compare(sql, ref) == []
    # SQL 导出的明细喂给参照，结果相同（冒烟日上的核对走这条路）
    assert R.compare(sql, R.reference(detail(con, emap), emap, W0, CUT, W1E, CAP)) == []
    assert R.certain(sql["C"], sql["N"]["k_sel"]) == []
    # 与冻结的 a_riskset 对照：选集相同；T 由 G 行算出与 set_statistic 相同
    fc = R.frozen_check(ref)
    assert fc["select_set_same"]
    assert float(R.t_stat(sql["G"])) == pytest.approx(fc["T_frozen"])


def test_random_data_is_not_trivial():
    """随机数据确实覆盖到：入选实体、W+1 有含入选行的层、命中、自身、PumpSwap 行、多钱包实体。"""
    tot = {"sel": 0, "G": 0, "hit": 0, "slf": 0, "amm": 0, "mapped": 0, "frac": 0}
    for seed in range(12):
        f, emap = gen(seed)
        ref = R.reference(f.detail(), emap, W0, CUT, W1E, CAP)
        tot["sel"] += len(ref["sel_exact"])
        tot["G"] += len(ref["G"])
        tot["hit"] += ref["N"]["n_hit_w"] + ref["N"]["n_hit_w1"]
        tot["slf"] += ref["N"]["n_slf"]
        tot["amm"] += ref["N"]["n_amm_rows"]
        tot["mapped"] += ref["N"]["n_mapped_w"]
        tot["frac"] += sum(1 for _, n, K, m, k in ref["G"] if 0 < K < n)
    assert all(v > 0 for v in tot.values()), tot


def _selection(sql):
    return {e: v[4] for e, v in sql["C"].items() if v[5] == 1}, sql["N"]["k_sel"]


@pytest.mark.parametrize("seed", [0, 1, 2, 5])  # 选 W 上有候选的种子（3、4 没有）
def test_w1_data_does_not_change_selection(seed):
    """改动 W+1 的任何数据：W+1 币的全部成交、毕业、池子，以及 W 币在截点之后的成交与毕业，入选集合与得分不变。"""
    f, emap = gen(seed)
    base = stats(f.con(), emap)
    g, _ = gen(seed + 100)
    cut_t = T(2026, 8, 12)
    w_coins = {r["mint"] for r in f.t[CR] if r["evt_block_time"] < cut_t}
    h = Fx()
    h.n = 10**6
    h.t[CR] = list(f.t[CR])
    for tb in (TR, CE):
        h.t[tb] = [
            r for r in f.t[tb] if r["mint"] in w_coins and r["evt_block_time"] < cut_t
        ]
    h.t[CP] = [r for r in f.t[CP] if r["base_mint"] in w_coins]
    h.t[AB] = [r for r in f.t[AB] if r["evt_block_time"] < cut_t]
    # 换上另一套 W+1：另一组随机成交与毕业，搬到本组 W+1 的币上
    w1_coins = sorted(r["mint"] for r in f.t[CR] if r["evt_block_time"] >= cut_t)
    other = sorted(
        {r["mint"] for r in g.t[TR]}
        - {r["mint"] for r in g.t[CR] if r["evt_block_time"] < cut_t}
    )
    ren = dict(zip(other, w1_coins))
    for r in g.t[TR] + g.t[CE]:
        if r["mint"] in ren:
            h.t[TR if "is_buy" in r else CE].append(dict(r, mint=ren[r["mint"]]))
    # W 的币在截点之后：大量成交与外部毕业
    for m in sorted(w_coins):
        for i in range(5):
            h.trade(m, "w00", T(2026, 8, 12, 0, 1 + i), True)
            h.trade(m, "w05", T(2026, 8, 12, 0, 1 + i, 30), True)
        h.complete(m, "gx", T(2026, 8, 12, 0, 7))
    changed = stats(h.con(), emap)
    assert _selection(changed) == _selection(base)
    # 候选的得分、名次、合格数也不变（C 行只差 W+1 的两列）
    strip = lambda C: {e: v[:6] for e, v in C.items()}  # noqa: E731
    assert strip(changed["C"]) == strip(base["C"])
    assert changed["N"]["n_rows_w"] == base["N"]["n_rows_w"]
    # 对照：去掉 W 的毕业事件，候选就没了（测试本身有区分力）
    assert base["C"]
    k = Fx()
    k.t = {tb: list(v) for tb, v in f.t.items()}
    k.t[CE] = [r for r in f.t[CE] if r["mint"] not in w_coins]
    assert stats(k.con(), emap)["C"] == {}


def test_tie_broken_by_sha256():
    """两个实体得分相同、只取 1 个：按 sha256(实体) 升序取。"""
    f = Fx()
    ws = ["ta", "tb"]
    for i in range(5):
        f.coin("k%d" % i, t11(i))
        for j, u in enumerate(ws + ["o1", "o2"]):
            f.trade("k%d" % i, u, t11(i, 1, j), True, sub=j)
        f.complete("k%d" % i, "gx", t11(i, 5))  # 四人都命中、同层 → 得分为 0
    # 第 6 个币：ta、tb 命中，o1、o2 不命中（买在毕业之后的另一层）
    f.coin("k5", t11(10))
    for j, u in enumerate(ws):
        f.trade("k5", u, t11(10, 1), True, sub=j, r4=100 + j)
    f.complete("k5", "gx", t11(10, 3))
    for j, u in enumerate(["o1", "o2"]):
        f.trade("k5", u, t11(10, 4), True, sub=5 + j)
    sql = stats(f.con(), {})
    ref = R.reference(f.detail(), {}, W0, CUT, W1E, CAP)
    assert R.compare(sql, ref) == []
    import hashlib

    sel = [e for e, v in sql["C"].items() if v[5] == 1]
    assert sql["N"]["n_el"] == 4 and sql["N"]["k_sel"] == 1
    tied = sorted(
        e for e, v in sql["C"].items() if v[4] == max(x[4] for x in sql["C"].values())
    )
    assert len(tied) >= 2
    assert sel == [min(tied, key=lambda e: hashlib.sha256(e.encode()).hexdigest())]


def test_units_exact_up_to_60_and_certain_check():
    D_ = S.D_UNITS
    assert all(D_ % n == 0 for n in range(1, 61)) and D_ % 61 != 0
    assert D_ * 10**4 < 10**38  # 一万行的命中 × D 仍在 DECIMAL(38,0) 之内
    # 得分 1/3 + 1/3 + 1/3 − 1 ＝ 0：单位制下精确为 0
    assert 1 * D_ - 3 * (1 * D_ // 3) == 0
    # 精确得分：a＝(2D − 0)/D − 1/61 − 1/61；b 的单位制得分与 a 相同、精确得分更低
    u = lambda h: h * D_  # noqa: E731
    C = {
        "a": (5, 2, 2, 1, u(2) - 2 * (D_ // 61), 1, None, None, u(2), "61:1;61:1"),
        "b": (
            5,
            2,
            1,
            2,
            u(2) - 2 * (D_ // 61),
            0,
            None,
            None,
            u(2) - D_ // 61,
            "61:2",
        ),
    }
    assert R.exact_scores(C)["a"] == 2 - Fraction(2, 61)
    assert R.certain(C, 1) == []
    # SQL 若按单位制把 b 排在前面（这里人为调换），核对就报出来
    C2 = {"a": C["a"][:5] + (0,) + C["a"][6:], "b": C["b"][:5] + (1,) + C["b"][6:]}
    assert R.certain(C2, 1) == ["a", "b"]
    # 精确得分 ≤0 的候选不入选：1 − 61/61＝0
    C3 = {"c": (5, 1, 1, 1, u(1) - (61 * D_) // 61 + 1, 1, None, None, u(1), "61:61")}
    assert R.certain(C3, 1) == ["c"]


def test_entities_union_find_hand():
    e = [
        {"kind": "S", "a": "s2", "b": "s1"},
        {"kind": "T", "a": "s3", "b": "s4"},
        {"kind": "G", "a": "f1", "b": "s4", "x": 10},
        {"kind": "G", "a": "f1", "b": "s5", "x": 10},
        {"kind": "G", "a": "f2", "b": "s6", "x": 500},  # 扇出 >200：服务节点
        {"kind": "G", "a": "f2", "b": "s7", "x": 500},
        {"kind": "G", "a": "cex", "b": "s8", "x": 3},  # 交易所名单
        {"kind": "G", "a": "cex", "b": "s9", "x": 3},
    ]
    e += [
        {"kind": "T", "a": "hub", "b": "r%03d" % i} for i in range(201)
    ]  # 对手 >200：不经它合并
    e += [{"kind": "T", "a": "hub", "b": "s1"}]
    m, n = R.entities(e, cex={"cex"})
    assert m == {"s1": "s1", "s2": "s1", "s3": "s3", "s4": "s3", "s5": "s3"}
    assert n["skip_G"] == 4 and n["skip_T"] == 202 and n["multi_entities"] == 2


def test_entities_nullable_integer_csv_hand():
    edges = [
        {"kind": "G", "a": "fund", "b": "u1", "x": "200.0"},
        {"kind": "G", "a": "fund", "b": "u2", "x": "200.0"},
        {"kind": "G", "a": "hub", "b": "u3", "x": "463.0"},
        {"kind": "G", "a": "missing", "b": "u4", "x": ""},
    ]
    emap, counts = R.entities(edges)
    assert emap == {"u1": "u1", "u2": "u1"}
    assert counts["used_G"] == 2 and counts["skip_G"] == 2
    for bad in ("199.5", "NaN", "Infinity", "-1"):
        with pytest.raises(ValueError, match="非负整数"):
            R.entities([dict(edges[0], x=bad)])


def test_t_stat_hand():
    # 一层 n＝4、K＝2，入选实体 1 行命中：k − m·K/n ＝ 1 − 1/2
    assert R.t_stat([("c", 4, 2, 1, 1)]) == Fraction(1, 2)
    rows = [
        {"entity": e, "coin": "c", "hit": h, "stratum": ("c",)}
        for e, h in (("a", 1), ("b", 1), ("c", 0), ("d", 0))
    ]
    assert A.set_statistic(rows, {"a"}) == pytest.approx(0.5)


def test_stratum_of_61_rows_is_inexact_and_flagged():
    """一层 61 行（61 不整除 D）：期望 K/61 向下取整，m_inexact 计数；SQL 与参照逐项相等，确定性判断照常。
    61 个钱包每隔 61 秒各买一次 j0～j4 五个币：前 60 秒净买入都是 0，储备与金额相同，同一小时档 → 同层。"""
    f = Fx()
    ws = ["u%02d" % i for i in range(61)]
    for c in range(5):
        m = "j%d" % c
        t0 = t11(2 * c + 1)
        f.coin(m, t11(2 * c))
        for i, u in enumerate(ws):
            f.trade(m, u, t0 + dt.timedelta(seconds=61 * i), True, r4=400, tok=0)
        # 毕业在第 20 个买入之后 1 秒：前 20 个人里，买入在毕业前 30 分钟以内的命中
        f.complete(m, "gx", t0 + dt.timedelta(seconds=61 * 19 + 1), txi=1)
    sql = stats(f.con(), {})
    ref = R.reference(f.detail(), {}, W0, CUT, W1E, CAP)
    assert R.compare(sql, ref) == []
    assert any(v[2] > 0 for v in sql["C"].values())  # 有不精确项
    assert R.certain(sql["C"], sql["N"]["k_sel"]) == []


def test_smoke_glue_prep_and_check(tmp_path, monkeypatch):
    """s3_smoke 的读写：EDGE 下载 → 映射 → SQL 与批准；统计量与明细的 CSV（空串＝空值）→ 核对全部为真。"""
    import csv as _csv

    import pandas as pd

    import paid_guard as PG
    import s3_smoke as SM

    for d in ("raw/dune", "runs", "sql"):
        (tmp_path / d).mkdir(parents=True)
    monkeypatch.setattr(SM, "H", tmp_path)
    monkeypatch.setattr(PG, "H", tmp_path)
    monkeypatch.setattr(PG, "APPROVALS", tmp_path / "runs" / "批准.csv")
    with open(PG.APPROVALS, "w", newline="") as fh:
        _csv.writer(fh).writerow(PG.FIELDS)
    cex = tmp_path / "cex.csv.gz"
    pd.DataFrame({"address": ["cexaddr"]}).to_csv(cex, index=False)
    monkeypatch.setattr(SM, "CEX", cex)
    monkeypatch.setattr(SM, "P", None)
    f, _ = gen(0)
    edges = pd.DataFrame(
        [
            {"kind": "S", "mint": "", "a": "w01", "b": "w00", "x": ""},
            {"kind": "G", "mint": "", "a": "fund", "b": "w02", "x": "5"},
            {"kind": "G", "mint": "", "a": "fund", "b": "w03", "x": "5"},
        ]
    )
    edges.to_csv(tmp_path / "raw" / "dune" / (SM.EDGE + ".csv.gz"), index=False)
    SM.prep()
    emap = {"w00": "w00", "w01": "w00", "w02": "w02", "w03": "w02"}
    import json

    assert (
        json.loads((tmp_path / "runs" / "s3_smoke_emap.json").read_text())["emap"]
        == emap
    )
    assert [r["编号"] for r in PG._rows(PG.APPROVALS)] == ["A7-04", "A7-05", "A7-06"]
    con = f.con()
    for label, det in (
        (SM.STATS + "_r1", False),
        (SM.STATS + "_r2", False),
        (SM.DETAIL, True),
    ):
        rows = run(
            con,
            S.build_s3(
                W0, CUT, W1E, None, S.emap_values(emap), detail=det, obs_cap=CAP
            ),
        )
        pd.DataFrame(rows).to_csv(
            tmp_path / "raw" / "dune" / (label + ".csv.gz"), index=False
        )
    SM.check()
    out = json.loads((tmp_path / "runs" / "s3_smoke_check.json").read_text())
    assert out["double_run_identical"] and out["diff_sql_vs_reference"] == []
    assert (
        out["selection_certain"]
        and out["frozen_select_set_same"]
        and out["T_from_G_equals_frozen"]
    )

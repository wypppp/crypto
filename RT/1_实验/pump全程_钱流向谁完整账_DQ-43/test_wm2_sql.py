"""WM2 取数 SQL 的保护边界测试（10-13）：只检查生成的 SQL 文本与日期守卫，不连 Dune、不读数据。"""

import datetime as dt
import re

import pytest
import sqlglot

import build_wm2_sql as B

D = dt.date
SMOKE = (D(2026, 8, 12), D(2026, 8, 12), D(2026, 8, 12), D(2026, 8, 12))


def all_sql(smoke):
    args = (
        SMOKE
        if smoke
        else (D(2026, 8, 10), D(2026, 8, 16), D(2026, 8, 10), D(2026, 9, 14))
    )
    # COSTF 一次只取一个事件日
    return {
        layer: B.build(layer, *(SMOKE if layer == "COSTF" else args), smoke=smoke)
        for layer in B.LAYERS
    }


def test_window_days_are_the_six_frozen_weeks():
    days = B.window_days()
    mondays = sorted({d - dt.timedelta(days=d.weekday()) for d in days})
    assert mondays == [
        D(2026, 5, 25),
        D(2026, 6, 1),
        D(2026, 7, 27),
        D(2026, 8, 3),
        D(2026, 8, 10),
        D(2026, 8, 17),
    ]
    assert len(days) == 42


@pytest.mark.parametrize(
    "c0,c1,e0,e1",
    [
        (D(2026, 6, 8), D(2026, 6, 8), D(2026, 6, 8), D(2026, 6, 8)),  # 检验周
        (D(2026, 6, 20), D(2026, 6, 20), D(2026, 6, 20), D(2026, 6, 20)),  # 封存周
        (
            D(2026, 7, 20),
            D(2026, 7, 20),
            D(2026, 7, 20),
            D(2026, 7, 20),
        ),  # 开发周但不是窗口周
        (D(2026, 8, 12), D(2026, 8, 12), D(2026, 8, 12), D(2026, 10, 5)),  # 事件到止日
        (
            D(2026, 8, 12),
            D(2026, 8, 12),
            D(2026, 8, 12),
            D(2026, 9, 12),
        ),  # 超出创建后 30 天
        (
            D(2026, 8, 12),
            D(2026, 8, 12),
            D(2026, 8, 11),
            D(2026, 8, 12),
        ),  # 事件早于创建
    ],
)
def test_date_guards_refuse(c0, c1, e0, e1):
    with pytest.raises(SystemExit):
        B.build("COIN", c0, c1, e0, e1)


@pytest.mark.parametrize("smoke", [True, False])
def test_every_layer_filters_before_export(smoke):
    for layer, sql in all_sql(smoke).items():
        sqlglot.parse_one(sql, read="trino")
        # 母体过滤：代号缺失或为空、留出同名、非 SOL 计价，都在 coins 之前
        assert "trim(replace(symbol, '$', '')) = ''" in sql, layer
        assert (
            "upper(trim(replace(symbol, '$', ''))) IN (SELECT base FROM excl)" in sql
        ), layer
        assert "quote_mint <> '%s'" % B.SYS in sql, layer
        assert "pop AS (SELECT * FROM c1 WHERE pop_class = 'in')" in sql, layer
        assert "coins AS (SELECT * FROM pop" in sql, layer
        # 止日：每层至少一处“严格早于 2026-10-05”
        assert "< TIMESTAMP '2026-10-05 00:00:00'" in sql, layer
        # 分区日期全部早于止日
        dates = re.findall(r"DATE '([0-9-]+)'", sql)
        assert max(dates) <= "2026-10-04", (layer, max(dates))


def test_event_tables_joined_to_filtered_coins():
    """所有读成交、事件的地方都经过 coins（已过滤）或由 coins 派生的 pools。"""
    sqls = all_sql(False)
    for layer in ("CTRADE", "TX", "EDGE"):
        s = sqls[layer]
        # EDGE 用截点之前创建的币（GPT 窄范围复核 04）
        k = "kc" if layer == "EDGE" else "coins"
        assert s.count("pump_evt_tradeevent") == s.count(
            "pump_evt_tradeevent t\n    JOIN %s k ON k.mint = t.mint" % k
        ), layer
    for layer in ("ATRADE", "TX"):
        s = sqls[layer]
        assert (
            "JOIN coins k ON k.mint = c.base_mint" in s
            and "JOIN pools p ON p.pool" in s
        ), layer


def test_no_fixed_width_order_key_in_wm2_parts():
    """WM2 自己写的部分不拼定宽排序键（DQ-35 ③）；ATRADE 沿用 DQ-35 的 ord 只作越界标志，输出四列键。"""
    for layer, sql in all_sql(False).items():
        own = sql.replace(B.G35.EVENTS.split("k AS (")[0], "")
        if layer != "ATRADE":
            assert "10000000000" not in own, layer
        assert "iix" in sql, layer


def test_smoke_outputs_only_structure():
    """冒烟只出计数、缺失数与估计字节（TX 另出资金路径的地址与交易数），不出金额汇总。"""
    for layer, sql in all_sql(True).items():
        tail = sql[sql.rindex("\nSELECT") :]
        # 双跑比对的逐行哈希和（取数附录 v2 §7）是唯一允许的求和，它不是金额
        tail = tail.replace(
            "sum(CAST(bitwise_and(from_big_endian_64(xxhash64(", "ck_hash_sum("
        )
        assert (
            "sum(CAST(" not in tail and "sum(sol" not in tail and "sum(amt" not in tail
        ), layer


def test_agg_layers_guards_and_entrances():
    """汇总版四层（10-14）：COSTF 只许单日、时段整除 24；CYC 截点晚于创建止日；VQ 只读允许池建池交易里的 InitBoost；
    曲线与 PumpSwap 的事件都经过 coins 或 pools；抽样条件在 coins 里。"""
    one = SMOKE
    with pytest.raises(SystemExit):
        B.build("COSTF", D(2026, 8, 10), D(2026, 8, 16), D(2026, 8, 12), D(2026, 8, 13))
    with pytest.raises(SystemExit):
        B.build("COSTF", *one, tpart=(0, 5))
    with pytest.raises(SystemExit):
        B.build(
            "CYCC",
            D(2026, 8, 10),
            D(2026, 8, 16),
            D(2026, 8, 10),
            D(2026, 9, 14),
            snap=D(2026, 8, 16),
        )
    with pytest.raises(SystemExit):
        B.build("CYCC", *one, part=(4, 4))
    vq = B.build("VQ", *one)
    assert "JOIN vp ON vp.pool_tx = c.tx_id" in vq and "= 0xae7c4af90451f611" in vq
    assert (
        "bytearray_substring(c.data, 121, 8)" in vq
        and "bytearray_substring(c.data, 89, 32)" in vq
    )
    cyc = B.build("CYCC", *one, p=0.1)
    assert "pump_evt_tradeevent t\n    JOIN coins k ON k.mint = t.mint" in cyc
    assert (
        "FROM pop\n    WHERE mod(bitwise_and(from_big_endian_64(substr(sha256(to_utf8('RT-DQ43-coin-sample-v1|' || mint))"
        in cyc
    )
    assert "% 10000" not in cyc and ", 10000) < 1000" in cyc
    cya = B.build("CYCA", *one)
    assert "JOIN pools p ON p.pool = a.pool" in cya
    cost = B.build("COSTF", *one, tpart=(1, 4))
    assert (
        "TIMESTAMP '2026-08-12 06:00:00'" in cost
        and "TIMESTAMP '2026-08-12 12:00:00'" in cost
    )
    assert cost.count("FROM solana.transactions") == 1


def test_smoke_extras_reference_output_columns():
    """冒烟的计数与缺失检查只引用该层输出里有的列（10-14：COSTF 改列名后冒烟引用旧列，Dune 编译失败）。"""
    kw = {
        "count_if",
        "count",
        "sum",
        "distinct",
        "as",
        "and",
        "or",
        "not",
        "is",
        "null",
        "cast",
        "decimal",
        "in",
    }
    for lay, cols in B.COLS.items():
        ex = re.sub(
            r"'[^']*'", "", B.SMOKE_EXTRA.get(lay, "") + " " + B.NULL_CHECK[lay]
        )
        words = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", ex))
        bad = {w for w in words - set(cols.split()) - kw if not w.startswith("n_")}
        assert bad <= {"layout0", "fanout", "n"}, (lay, bad)


def test_no_or_join_conditions():
    """10-14 EDGE 冒烟事故：连接条件里带 OR，Trino 无法哈希连接，12 分钟扣 1,087.6 credits。任何一层都不许再出现。"""
    for smoke in (False, True):
        for layer, sql in all_sql(smoke).items():
            for line in sql.splitlines():
                if re.search(r"\bJOIN\b", line) and " ON " in line:
                    assert not re.search(r"\bOR\b", line.split(" ON ", 1)[1]), (
                        layer,
                        line,
                    )

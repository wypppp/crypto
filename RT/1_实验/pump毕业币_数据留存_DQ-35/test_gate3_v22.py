"""③ 状态事件键（10-13）：GPT 10-06 清单确认 ③ 的反例与修复后的手算预期值。

旧键 slot·1e10＋txi·1e5＋oix·1e3＋iix 在分量越界时碰撞，例如 (txi,oix,iix)＝(1,100,0) 与 (2,0,0)；
iix 缺失记 -1 时还有第二类：(oix,iix)＝(1,-1) 与 (0,999)。
修复：键改为 …＋oix·1e3＋(iix＋1)，分量越界记 st_ovf＝1，P 层 n_st_ovf_7d 合计不为 0 即验收失败。
"""

import itertools
import re

import build_grad_sql_v22 as B
from check_manifest_v22 import content_rows


def old_key(slot, txi, oix, iix):
    return slot * 10**10 + txi * 10**5 + oix * 10**3 + iix


def new_key(slot, txi, oix, iix):
    """与 SQL 同式：iix 缺失按 -1。"""
    return slot * 10**10 + txi * 10**5 + oix * 10**3 + (-1 if iix is None else iix) + 1


def st_ovf(txi, oix, iix):
    i = -1 if iix is None else iix
    return int(not (0 <= txi < 100000 and 0 <= oix < 100 and -1 <= i < 999))


def test_old_key_collisions_reproduced():
    assert old_key(5, 1, 100, 0) == old_key(5, 2, 0, 0)  # GPT 原反例
    assert old_key(5, 0, 1, -1) == old_key(5, 0, 0, 999)  # 缺失记 -1 的第二类


def test_collisions_now_flagged_or_distinct():
    assert st_ovf(1, 100, 0) == 1  # oix 越界，验收阻断
    assert st_ovf(0, 0, 999) == 1  # iix 越界
    assert st_ovf(0, 1, None) == 0 and new_key(5, 0, 1, None) == 5 * 10**10 + 1000
    assert new_key(5, 0, 0, 998) == 5 * 10**10 + 999  # 与 (1,-1) 不再相等


def test_new_key_injective_and_ordered_in_range():
    """在允许范围的边角上穷举：键两两不同，且与元组顺序一致。"""
    txis, oixs, iixs = (0, 1, 99999), (0, 1, 98, 99), (-1, 0, 1, 997, 998)
    pts = sorted(itertools.product((7,), txis, oixs, iixs))
    keys = [new_key(*p) for p in pts]
    assert len(set(keys)) == len(keys) and keys == sorted(keys)
    assert all(st_ovf(t, o, i) == 0 for _, t, o, i in pts)


def test_sql_all_state_branches_use_new_key_and_flag():
    import datetime as dt

    sql = B.build("P", dt.date(2026, 8, 3), dt.date(2026, 8, 3))
    sql = sql if isinstance(sql, str) else sql[0]
    st = sql[sql.index("st AS (") : sql.index("stt AS (")]
    # 交易、加撤池、建池、boost 四支都用 (iix＋1) 的新键与越界标志
    assert (
        len(re.findall(r"\* 1000 \+ CAST\(COALESCE\([^)]*, -1\) AS BIGINT\) \+ 1", st))
        >= 3
    )
    assert st.count(">= 999 THEN 1 ELSE 0 END") >= 3
    assert (
        "* 1000 + CAST(l.iix AS BIGINT)," not in st
        and "CAST(c_iix AS BIGINT),\n" not in st
    )
    assert "sum(st_ovf) AS n_st_ovf_7d" in sql and "sn.n_st_ovf_7d" in sql


def test_manifest_blocks_on_state_overflow():
    rows = [
        {
            "chain": "solana",
            "pool": "p1",
            "n_src_dup_7d": "0",
            "n_vq_bad_7d": "0",
            "n_st_ovf_7d": "1",
            "created_t": "0",
            **{f"coverage{o}": "pre" for o in B.OFFSETS},
            **{f"target{o}_time": str(o) for o in B.OFFSETS},
        }
    ]
    probs = content_rows(rows, "P", "GRAD")
    assert any(p.startswith("n_st_ovf_7d 合计 1") for p in probs)

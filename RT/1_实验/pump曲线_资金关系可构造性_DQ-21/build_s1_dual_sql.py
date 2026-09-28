#!/usr/bin/env python3
"""在已验证的 S1 修正版 SQL 上**只追加**乐观口径（B）列，生成双口径版本。

口径说明见 F116（09-28 用户裁决）：
- A（原列，不改）：卖进不含我方仓位的观察状态，x*q/(y+q)，偏保守；
- B（新增 *_b 列）：我方仓位留在曲线里再卖回，x*y/(y-q)-x，立即往返精确，中途有他人成交时偏乐观。
PumpSwap 分支两种口径相同。b50 的止损时点按池边际价格触发，与口径无关，只换卖出金额。

python build_s1_dual_sql.py → sql/S1_{SMOKE_20260601,A,B}_固定退出基础回收_双口径.sql
自检：删去新增行后与源文件逐字相同；B 卖出式与旧 SQL 文本一致；sqlglot（trino）可解析；三张成交表各引用一次。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import sqlglot

H = Path(__file__).resolve().parent
SQL = H / "sql"
SRC = {
    "S1_SMOKE_20260601": SQL / "S1_SMOKE_20260601_固定退出基础回收_曲线卖出修正_待验.sql",
    "S1_A": SQL / "S1_A_固定退出基础回收_曲线卖出修正_待验.sql",
    "S1_B": SQL / "S1_B_固定退出基础回收_曲线卖出修正_待验.sql",
}
SUF = ("", "_e30", "_e120")
FEE = {"": "e5_fee_bps", "_e30": "e30_fee_bps", "_e120": "e120_fee_bps"}
TAG = "  /*B*/"


def b_col(s: str) -> str:
    tok = "entry_tokens" + s
    return (
        f"        LEAST({TAG}\n"
        f"            CASE{TAG}\n"
        f"                WHEN venue = 0 AND y > {tok} THEN (x * y / (y - {tok}) - x) * (1 - fee_bps / 1e4){TAG}\n"
        f"                WHEN venue = 0 THEN NULL{TAG}\n"
        f"                ELSE (x - x * y / (y + {tok})) * (1 - fee_bps / 1e4){TAG}\n"
        f"            END,{TAG}\n"
        f"            IF(venue = 0, xr + 0.5 * (1 - {FEE[s]} / 1e4), 1e18){TAG}\n"
        + (f"        ) / 0.5 AS sell_multiple{s}_b,{TAG}\n" if s == "" else
           f"        ) / 0.5 AS sell_multiple{s}_b_raw,{TAG}\n")
    )


def transform(sql: str) -> str:
    lines = sql.split("\n")
    out = []
    in_coin_path = False
    b_names = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("coin_path AS ("):
            in_coin_path = True
        elif in_coin_path and ln.startswith("all_coins AS ("):
            in_coin_path = False
        if ln == "        ) / 0.5 END AS sell_multiple_e120,":
            for s in SUF:
                out.extend(b_col(s).rstrip("\n").split("\n"))
        m = re.match(r"^(\s+NULLIF\((?:max|min)_by\(COALESCE\()sell_multiple(_e30|_e120)?(, -1\.0\), rn\).*\) AS )"
                     r"((?:ret|stop_ret|horizon_ret)_\w+),$", ln)
        if in_coin_path and m:
            s = m.group(2) or ""
            out.append(f"{m.group(1)}sell_multiple{s}_b{m.group(3)}{m.group(4)}_b,{TAG}")
            b_names.append(m.group(4) + "_b")
    sql2 = "\n".join(out)
    assert len(b_names) == 18, b_names
    # s10 之后再包一层，把 e30/e120 的 B 列限定在各自入场之后
    anchor = "coin_path AS ("
    assert sql2.count(anchor) == 1
    wrap = (
        f"s10b AS ({TAG}\n"
        f"    SELECT *,{TAG}\n"
        f"        CASE WHEN rn >= e30_rn THEN sell_multiple_e30_b_raw END AS sell_multiple_e30_b,{TAG}\n"
        f"        CASE WHEN rn >= e120_rn THEN sell_multiple_e120_b_raw END AS sell_multiple_e120_b{TAG}\n"
        f"    FROM s10{TAG}\n"
        f"),{TAG}\n"
    )
    sql2 = sql2.replace(anchor, wrap + anchor, 1)
    # coin_path 从 s10b 取数
    i0 = sql2.index(anchor)
    i1 = sql2.index("all_coins AS (")
    seg = sql2[i0:i1]
    assert seg.count("    FROM s10\n") == 1
    seg = seg.replace("    FROM s10\n", f"    FROM s10b{TAG}\n", 1)
    sql2 = sql2[:i0] + seg + sql2[i1:]
    # all_coins 透传
    a = "        p.first_dd50_s, p.last_trade_s, p.n_post_entry_trades,"
    assert sql2.count(a) == 1
    sql2 = sql2.replace(a, "        " + ", ".join("p." + n for n in b_names) + "," + TAG + "\n" + a, 1)
    # 最终输出
    tail = "    1 AS sample_preselected\nFROM all_coins\nORDER BY created_at, mint"
    assert sql2.count(tail) == 1
    fixed = [n for n in b_names if n.startswith("ret_")]
    extra = [f"    {n},{TAG}" for n in fixed]
    for d in ("d5", "d30", "d120"):
        extra.append(f"    CASE WHEN stop_time_{d} IS NOT NULL THEN stop_ret_{d}_b ELSE horizon_ret_{d}_b END AS b50_ret_{d}_b,{TAG}")
    sql2 = sql2.replace(tail, "\n".join(extra) + "\n" + tail, 1)
    head = ("/* S1 双口径（09-28，F116 用户裁决）：原列为保守口径 A，不改；后缀 _b 的列为乐观口径 B（我方仓位留在曲线里）。\n"
            "   由 build_s1_dual_sql.py 从已验证的修正版只追加生成；新增行行尾带 B 标记注释。 */\n")
    return head + sql2


def check(src: str, dual: str) -> None:
    body = dual.split("\n", 2)[2]
    src_lines = src.split("\n")
    rebuilt = []  # 删去新增行，并把唯一被替换的 FROM 行还原
    for l in body.split("\n"):
        if l == f"    FROM s10b{TAG}":
            rebuilt.append("    FROM s10")
        elif not l.endswith(TAG):
            rebuilt.append(l)
    assert rebuilt == src_lines, "非纯追加"
    old_b = "(x * y / (y - entry_tokens) - x) * (1 - fee_bps / 1e4)"
    assert old_b in (SQL / "S1_SMOKE_20260601_旧卖出公式_已执行_勿复用.sql").read_text()
    for t in ("pump_evt_tradeevent", "pump_amm_evt_buyevent", "pump_amm_evt_sellevent"):
        assert dual.count("FROM pumpdotfun_solana." + t) == 1, t
    sqlglot.parse_one(dual, read="trino")


def main():
    for name, p in SRC.items():
        src = p.read_text()
        dual = transform(src)
        check(src, dual)
        out = SQL / f"{name}_固定退出基础回收_双口径.sql"
        out.write_text(dual)
        print(out.name, "sha256", hashlib.sha256(dual.encode()).hexdigest()[:16],
              "added_lines", sum(1 for l in dual.split("\n") if l.endswith(TAG)))


if __name__ == "__main__":
    main()

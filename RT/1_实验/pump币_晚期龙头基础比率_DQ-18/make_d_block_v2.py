"""DQ-18 D 段路径块 SQL 生成器 v2（代码审计 10-03 第 11 处）。原 make_d_block.py 与已执行的 sql/D_*.sql 不改。

第 11 处：信号时刻恰为月初零点时，穿越小时（上月最后一小时）在上一块，上一块却因“信号 < 块终点”不收这个信号；
本块的成交扫描又从月初零点开始，没有穿越小时的主池，于是入场行（rt＝E）缺失，assemble_d.py 只认 E 行，整条信号丢失。
v2 只改两处，其余逐字取自 v1：
  ①成交与 SOL 价格的扫描起点提前 1 小时（分区相应多读上个月），使本块信号的穿越小时都在块内；
  ②路径行只取本块自己的小时（h ≥ 块起点），提前的那 1 小时只用于入场行——避免与上一块的路径行重复。
用法同 v1：python make_d_block_v2.py YYYY-MM [YYYY-MM] → sql/v2/D_*.sql；DQ-18 重开之前不执行（总控第十轮第 6 条）。
"""

import sys
from datetime import datetime, timedelta

import make_d_block as M

HEAD_REPL = [
    (
        "AND minute >= TIMESTAMP '{START} 00:00:00' AND minute < TIMESTAMP '{END} 00:00:00'",
        "AND minute >= TIMESTAMP '{START} 00:00:00' - INTERVAL '1' HOUR AND minute < TIMESTAMP '{END} 00:00:00'",
    ),
    (
        "WHERE t.block_month >= DATE '{START}' AND t.block_month < DATE '{END}'",
        "WHERE t.block_month >= date_add('month', -1, DATE '{START}') AND t.block_month < DATE '{END}'",
    ),
    (
        "AND t.block_time >= TIMESTAMP '{START} 00:00:00' AND t.block_time < TIMESTAMP '{END} 00:00:00'",
        "AND t.block_time >= TIMESTAMP '{START} 00:00:00' - INTERVAL '1' HOUR"
        " AND t.block_time < TIMESTAMP '{END} 00:00:00'",
    ),
]
CORE_REPL = [
    (
        "    WHERE m.h = s.signal_time - INTERVAL '1' HOUR OR (m.h >= s.signal_time AND m.valid)",
        "    WHERE m.h = s.signal_time - INTERVAL '1' HOUR\n"
        "       OR (m.h >= s.signal_time AND m.valid AND m.h >= TIMESTAMP '{START} 00:00:00')"
        "  -- v2：路径行只取本块小时",
    ),
]


def _apply(text: str, repl: list) -> str:
    for old, new in repl:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


TRINO_HEAD = _apply(M.TRINO_HEAD, HEAD_REPL)
CORE = _apply(M.CORE, CORE_REPL)


def render(a, b=None):
    """同 v1 render；块内信号的选取不变（v1 的规则在扫描提前 1 小时后已能给出月初零点信号的入场）。"""
    start = M.month_start(a)
    end = M.next_month(M.month_start(b or a))
    s0 = datetime(start.year, start.month, 1)
    s1 = datetime(end.year, end.month, 1)
    act = [x for x in M.signals() if x[2] < s1 and x[2] + timedelta(days=180) > s0]
    epoch = datetime(1970, 1, 1)
    vals = ",\n".join(
        f"('{m}',{t // 1000000},{int((st - epoch).total_seconds()) // 3600})"
        for m, t, st in act
    )
    label = a if not b or b == a else f"{a}～{b}"
    sql = (TRINO_HEAD + CORE).format(
        LABEL=label + "（v2）",
        NSIG=len(act),
        VALUES=vals,
        START=start.isoformat(),
        END=end.isoformat(),
        SOL=M.SOL,
        USDC=M.USDC,
        USDT=M.USDT,
        MINBY="MIN_BY",
        MAXBY="MAX_BY",
    )
    name = start.strftime("%Y%m") + (
        "" if not b or b == a else "_" + M.month_start(b).strftime("%Y%m")
    )
    p = M.ROOT / "sql" / "v2" / f"D_{name}.sql"
    p.parent.mkdir(exist_ok=True)
    p.write_text(sql)
    return p, len(act), len(sql)


if __name__ == "__main__":
    p, n, size = render(*sys.argv[1:3])
    print(p.name, "signals", n, "sql_kb", round(size / 1024))

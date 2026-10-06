#!/usr/bin/env python3
"""DQ-41 一周案头筛查的读取入口过滤（10-06；总控第二十二轮第二节第 1 条，导航 v1.1 §10）。

任何读进筛查的行，先过这里，再读其余列。边界一并适用：
- 55 条币安留出：sha256(baseAsset) 首字节 mod 5 == 0（F25）；
- DQ-37 检验周与封存周 2026-06-15～07-12（weeks.py）；
- 2026-10-05 起创建的币与发生的成交（前向批次）；R3 观测止日 2026-10-04 24:00 UTC。

O1 发行行（执行决定，可推翻；存档 C7 第 2 条）：
- 发行日与 TGE 日都要落在开发周，或早于 DQ-37 范围（2025-02-24 之前）；任一落在检验周、封存周或止日之后，整行排除；
- 两个日期都缺，排除；只有一个日期，按这一个判；
- 有代号就按留出规则判；没有代号而在币安上市（上市场所含 binance），先排除。
O3 源记录：记录时刻落在开发周（或 2025-02-24 之前），且早于止日。
候选币：创建时刻落在开发周，且早于止日。
"""

import datetime as dt
import hashlib
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "发射台_前期右尾评测底座_DQ-37")
)
import weeks as W  # noqa: E402

CUTOFF = dt.date(2026, 10, 4)  # R3：只用 2026-10-04 24:00 UTC 之前


def is_holdout_symbol(sym):
    """55 条币安留出的规则（F25）：sha256(baseAsset) 首字节 mod 5 == 0。代号按大写判。"""
    return hashlib.sha256(sym.strip().upper().encode()).digest()[0] % 5 == 0


def date_ok(ts):
    """一个时刻能不能读：开发周或 DQ-37 范围之前，且不晚于止日。"""
    d = W._to_date(ts)
    if d > CUTOFF:
        return False
    c = W.week_class(d)
    if c == W.DEV:
        return True
    return c == W.OUT and d < W.FIRST_MONDAY


def _parse(x):
    if x is None:
        return None
    x = str(x).strip()
    if not x or x.lower() in ("nan", "none", "na", "n/a", "unknown", "tbd", "-"):
        return None
    try:
        return W._to_date(x[:10])
    except (TypeError, ValueError):
        return None


def o1_row_ok(sale_date, tge_date, symbol=None, listing_venue=None):
    """O1 发行行能不能读（见模块说明）。"""
    ds = [d for d in (_parse(sale_date), _parse(tge_date)) if d is not None]
    if not ds or not all(date_ok(d) for d in ds):
        return False
    if symbol and str(symbol).strip():
        return not is_holdout_symbol(str(symbol))
    return "binance" not in str(listing_venue or "").lower()


def gate_csv(path, date_cols=("sale_date", "tge_date"), meta_cols=("listing_venue",)):
    """先只读日期与元数据列定下允许的行号，再读这些行的全部列。返回 (DataFrame, 排除行数)。"""
    import pandas as pd

    head = pd.read_csv(path, usecols=list(date_cols) + list(meta_cols), dtype=str)
    sym = "symbol" if "symbol" in pd.read_csv(path, nrows=0).columns else None
    syms = (
        pd.read_csv(path, usecols=[sym], dtype=str)[sym] if sym else [None] * len(head)
    )
    ok = [
        o1_row_ok(r[date_cols[0]], r[date_cols[1]], s, r.get("listing_venue"))
        for (_, r), s in zip(head.iterrows(), syms)
    ]
    skip = [i + 1 for i, k in enumerate(ok) if not k]  # 第 0 行是表头
    return pd.read_csv(path, skiprows=skip, dtype=str), len(skip)

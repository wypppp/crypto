"""DQ-37 前向批次预登记（10-04，总控第十五轮第二节第 2 条；方案 v1 阶段 1 第 1 项）。

规则写定后不改；要改只能另起 v2 并在总入口 §3.1 记录。规则全文见 前向批次预登记.md。

- 前向批次：曲线创建时刻（UTC）不早于 2026-10-05 00:00（周一）的币，覆盖机器线全部发射台。
- 机器线任何一张卡冻结并做确认读取之前，前向批次的数据存而不读：只允许结构核对
  （行数、齐全性、空值率、字段是否解码、逐笔前后储备是否守恒、费用字段是否齐全），
  不允许价格、收益、存活、倍数的任何分布或汇总，也不允许按币挑样本看路径。
- 开发代码读结果之前，先用 drop_forward() 去掉前向批次，或用 assert_not_forward() 守卫。
- 观测止日（10-04 补，总控第十六轮 R3）：第一次确认读取之前，开发分析只用 2026-10-04 24:00 UTC
  之前发生的成交（包括 10-05 之前创建的老币）；之后的成交只存不读。用 drop_after_cutoff() /
  assert_before_cutoff() 按成交时刻截断。
"""

import datetime as dt

from weeks import _to_date

FORWARD_START = dt.date(2026, 10, 5)


def is_forward(ts):
    """ts 是币的曲线创建时刻；不早于 2026-10-05（UTC）即属前向批次。"""
    return _to_date(ts) >= FORWARD_START


def drop_forward(df, created_col):
    """去掉前向批次的币（pandas DataFrame）。被去掉的行不返回，也不统计。"""
    mask = ~df[created_col].map(is_forward).astype(bool)
    return df.loc[mask].copy()


def assert_not_forward(values):
    """开发代码的守卫：有任何前向批次的币就报错（不报是哪个币）。"""
    bad = sum(1 for v in values if is_forward(v))
    if bad:
        raise ValueError("有 %d 个币属于前向批次，确认读取之前不能读" % bad)


TRADE_CUTOFF = dt.date(2026, 10, 5)  # 成交时刻 < 2026-10-05 00:00 UTC 才可在开发中读


def is_after_cutoff(ts):
    """ts 是成交时刻；不早于 2026-10-05（UTC）即在观测止日之后。"""
    return _to_date(ts) >= TRADE_CUTOFF


def drop_after_cutoff(df, trade_col):
    """去掉观测止日之后的成交（pandas DataFrame）。被去掉的行不返回，也不统计。"""
    mask = ~df[trade_col].map(is_after_cutoff).astype(bool)
    return df.loc[mask].copy()


def assert_before_cutoff(values):
    """开发代码的守卫：有任何观测止日之后的成交就报错（不报是哪一笔）。"""
    bad = sum(1 for v in values if is_after_cutoff(v))
    if bad:
        raise ValueError("有 %d 笔成交在观测止日之后，确认读取之前不能读" % bad)

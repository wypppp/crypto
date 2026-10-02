#!/usr/bin/env python3
"""代码审计（10-03，GPT 第 9、13 处）的修正，供各永续实验的 v2 与重跑脚本调用。原 perp_replicate.py 不改。

第 9 处 funding_v2：[t1, t2) 右开窗口，月文件只读到 t2 前一刻所在的月（原版在 t2 恰为月初零点时多要一个月，
    该月文件不存在——例如永续已下架——就把完整事件判成缺失）。与 holdout_score_v2.funding 相同。

第 13 处 iso_path：L 倍逐仓、开仓后不追加资金时的账户状态（原版资金费不进保证金，回收可低于 −1）。
    M＝逐仓保证金，A＝可用余额，都以初始保证金为 1 计；开仓时 M＝1、A＝0。
    每次结算 amt＝L × 费率 × 结算当日标记价收盘 / 入场价（与原版同一价格口径）；费率为正时多头付、空头收。
    收到的计入 A；付出的先从 A 扣，不足的部分从 M 扣（币安 FAQ 360033525031：资金费先从可用余额扣，
    不足才扣持仓保证金；收到的资金费进入可用余额，不进逐仓保证金）。
    逐日处理：先计入当日全部结算，再用当日不利极值（多头看标记价最低、空头看最高）检查
    M＋未实现盈亏 ≤ 0.1 即强平。阈值 0.1 使没有资金费时与原版规则逐字等价：
    空头最高 ≥ 入场 ×(1＋0.9/L)，多头最低 ≤ 入场 ×(1−0.9/L)。
    强平：逐仓部分归零，回收 r＝A − 1（已收到并留在可用余额里的资金费保留），之后不再计费，与原版一样不扣手续费；
    未强平：r＝A＋M − 1＋按退出价的价格盈亏 − 双边费，等于原版的“价格盈亏＋资金费净额”。
    所以两版只在强平上不同：新版强平不晚于原版（M ≤ 1），强平时回收 ≥ −1。
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile

import perp_replicate as P

LIQ_EQUITY = 0.1


def funding_v2(sym: str, t1: dt.datetime, t2: dt.datetime) -> list[tuple] | None:
    """[t1, t2) 内的结算 (时刻, 费率)；所需月份为 t1 所在月到 t2 前一刻所在月；任一缺失返回 None。"""
    out = []
    last = t2 - dt.timedelta(milliseconds=1)
    y, m = t1.year, t1.month
    while (y, m) <= (last.year, last.month):
        data = P.fetch(
            f"monthly/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"
        )
        if data is None:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt = z.read(z.namelist()[0]).decode()
        for row in csv.reader(io.StringIO(txt)):
            if not row or not row[0].isdigit():
                continue
            t = dt.datetime.fromtimestamp(int(row[0]) / 1000, P.UTC)
            if t1 <= t < t2:
                out.append((t, float(row[2])))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def iso_path(
    side: int,
    p0: float,
    p_exit: float,
    days: list[dt.date],
    mk: dict[dt.date, dict],
    fr: list[tuple],
    lev: float = 1.0,
    fee: float = 0.001,
) -> dict:
    """side＝+1 做多、−1 做空；days[0] 为入场日（收盘入场），days[1:] 为持有日，最后一日按 p_exit 退出。

    fr 为 (入场, 退出] 内的结算；结算日不在 mk 中的跳过（与原版 `if t.date() in mk` 相同）。
    返回 r（每份保证金的净回收）、liq、liq_day（第几个持有日强平，未强平为 None）、A、M、funding_net（A＋M−1）。
    """
    by_day: dict[dt.date, list[float]] = {}
    for t, rate in fr:
        if t.date() in mk:
            by_day.setdefault(t.date(), []).append(rate)
    M, A = 1.0, 0.0
    for k, day in enumerate(days[1:], start=1):
        for rate in by_day.get(day, []):
            pay = side * lev * rate * mk[day]["c"] / p0  # 正为付出，负为收到
            if pay < 0:
                A -= pay
            else:
                take = min(A, pay)
                A -= take
                M -= pay - take
        # 权益 M＋未实现盈亏 ≤ 0.1 换成价格写法，M＝1 时与原版的比较式逐字相同（避免浮点边界差异）
        cushion = (M - LIQ_EQUITY) / lev
        if (side > 0 and mk[day]["l"] <= p0 * (1 - cushion)) or (
            side < 0 and mk[day]["h"] >= p0 * (1 + cushion)
        ):
            return {
                "r": A - 1.0,
                "liq": True,
                "liq_day": k,
                "A": A,
                "M": 0.0,
                "funding_net": A + M - 1.0,
            }
    px = side * lev * (p_exit / p0 - 1) - fee * lev
    return {
        "r": A + M - 1.0 + px,
        "liq": False,
        "liq_day": None,
        "A": A,
        "M": M,
        "funding_net": A + M - 1.0,
    }


def iso_event(
    side: int,
    sym: str,
    d: dt.date,
    last: dt.date,
    p_exit: float | None = None,
    lev: float = 1.0,
    fee: float = 0.001,
) -> dict | None:
    """按原版口径取数（入场日 d 收盘、持有到 last 收盘或按 p_exit 退出），用 iso_path 重算；缺数据返回 None。"""
    days = [d + dt.timedelta(days=k) for k in range((last - d).days + 1)]
    kl = P.daily("klines", sym, d, last)
    mk = P.daily("markPriceKlines", sym, d, last)
    if any(x not in kl or x not in mk for x in days):
        return None
    t1 = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(), P.UTC)
    t2 = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), P.UTC)
    fr = funding_v2(sym, t1, t2)
    if fr is None:
        return None
    p0 = kl[d]["c"]
    pe = kl[last]["c"] if p_exit is None else p_exit
    return iso_path(side, p0, pe, days, mk, fr, lev, fee)

#!/usr/bin/env python3
"""DQ-43（WM2）与 DQ-44（B）共同合同：过滤契约（10-13，WM2 v5 §7、B v2 §8）。

所有读进分析的行，先过这里，再算任何聚合、特征或标签（前向批次预登记第 12 条）。
过滤函数只返回留下的行，不报被去掉的是哪些、有多少（不展示保护范围的活跃度）。

三条边界（全部支路共用）：
1. 币：曲线创建时刻落在 DQ-37 开发周（weeks.py；检验周、封存周 06-15～07-12、范围外都不取），
   且早于前向批次起点 2026-10-05 00:00 UTC（forward.py）。
2. 成交：成交时刻严格早于 2026-10-05 00:00 UTC（观测止日，forward.py 第 6 条）。
3. 留出同名：代号规范化后与“币安现货基础资产中命中留出规则者”同名的币不取
   （规则与名单沿用 DQ-35 sql/_holdout_names.sqlpart：upper(trim(replace(symbol,'$',''))) 在名单内）。

逐支路的允许域（WM2 §7 表；B §8）：
- trade / raw_event：币与成交都允许；
- edge（实体与关联图的边）：转账早于止日；从成交里取的边，该成交所在的币必须允许；
- behavior（狙击名单、自动化代理）与 quantile（全体分位）：只用允许的成交形成；
- first_seen（钱包首次出现）：只在允许域内判定，会把域外的老钱包算成新（写进卡）；
- same_name（同名币计数）：只数允许域内、触发前已创建的币，会少计（写进卡）；
- label（标签与结果窗）：结果窗终点晚于止日或观察窗终点的，记“未成熟”，不删、不当作没发生；
- lagvar（B 的上一周行情变量）：上一周不是开发周就记缺失，不用“上一个可用周”顶替。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "发射台_前期右尾评测底座_DQ-37")
)
import forward as F  # noqa: E402
import weeks as W  # noqa: E402

UTC = dt.timezone.utc
CUTOFF = dt.datetime(2026, 10, 5, tzinfo=UTC)  # 成交与一切事件须严格早于此刻
HOLDOUT_LIST = (
    Path(__file__).resolve().parents[1]
    / "pump毕业币_数据留存_DQ-35"
    / "sql"
    / "_holdout_names.sqlpart"
)


def to_utc(ts) -> dt.datetime:
    """epoch 秒（数值）、ISO 字符串、datetime（无时区按 UTC）→ 带时区的 UTC datetime。"""
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return dt.datetime.fromtimestamp(ts, UTC)
    if isinstance(ts, str):
        ts = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if isinstance(ts, dt.datetime):
        return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    raise TypeError("不支持的时间类型: %r" % type(ts))


# ---------- 留出同名 ----------


def _load_bases(path: Path = HOLDOUT_LIST) -> list[str]:
    import re

    return re.findall(r"\('([^']*)'\)", path.read_text(encoding="utf-8"))


def holdout_hash(base: str) -> bool:
    """留出规则（F25）：sha256(baseAsset) 首字节 mod 5 == 0。"""
    return hashlib.sha256(base.encode("utf-8")).digest()[0] % 5 == 0


HOLDOUT_NAMES = frozenset(b for b in _load_bases() if holdout_hash(b))


def norm_symbol(sym: str | None) -> str:
    """与 DQ-35 SQL 相同：upper(trim(replace(symbol, '$', '')))。"""
    return (sym or "").replace("$", "").strip().upper()


def symbol_allowed(sym: str | None) -> bool:
    return norm_symbol(sym) not in HOLDOUT_NAMES


# ---------- 三条边界 ----------


def coin_allowed(created_ts, symbol: str | None) -> bool:
    """缺创建时刻报错；缺代号按 DQ-35 的做法排除（查不到代号的币保守排除，GPT 门 1 第 11 条）。"""
    if created_ts is None:
        raise ValueError("币缺曲线创建时刻")
    if symbol is None:
        return False
    t = to_utc(created_ts)
    return W.is_dev(t) and not F.is_forward(t) and t < CUTOFF and symbol_allowed(symbol)


def before_cutoff(ts) -> bool:
    return to_utc(ts) < CUTOFF


def trade_allowed(trade_ts, coin_created_ts, symbol: str | None) -> bool:
    return before_cutoff(trade_ts) and coin_allowed(coin_created_ts, symbol)


def edge_allowed(transfer_ts, via_coin: tuple | None = None) -> bool:
    """via_coin＝(创建时刻, 代号)：这条边取自某个币的成交时给出。"""
    if not before_cutoff(transfer_ts):
        return False
    return via_coin is None or coin_allowed(*via_coin)


# ---------- 入口：先过滤，后计算 ----------


def entry(rows, branch: str, *, created="created_ts", symbol="symbol", ts="ts"):
    """按支路过滤一组字典行。trade、raw_event、behavior、quantile、first_seen、cost、reward 用同一规则；
    edge 的行必须带 source（transfer／trade），trade 来源必须带 via_created、via_symbol；fx 只看时刻。
    这些过滤在 SQL 导出之前也要落实（GPT 11），这里是下载后的第二道。"""
    out = []
    for r in rows:
        if branch in (
            "trade",
            "raw_event",
            "behavior",
            "quantile",
            "first_seen",
            "cost",
            "reward",
        ):
            ok = trade_allowed(r[ts], r[created], r.get(symbol))
        elif branch == "coin":
            ok = coin_allowed(r[created], r.get(symbol))
        elif branch == "edge":
            # 来源类型必填：独立转账（transfer）或取自成交（trade）；取自成交的必须带上该币，缺失报错
            src = r.get("source")
            if src == "transfer":
                ok = edge_allowed(r[ts])
            elif src == "trade":
                if r.get("via_created") is None:
                    raise ValueError("取自成交的边缺所在币的创建时刻")
                ok = edge_allowed(r[ts], (r["via_created"], r.get("via_symbol")))
            else:
                raise ValueError("边缺来源类型（transfer／trade）")
        elif branch == "fx":  # 汇率等全局序列：只看时刻
            ok = before_cutoff(r[ts])
        else:
            raise ValueError("未知支路 %s" % branch)
        if ok:
            out.append(r)
    return out


def first_seen(trade_rows, wallet="wallet", ts="ts") -> dict:
    """允许域内每个钱包的首次出现时刻。调用前必须已过 entry(…, 'first_seen')。"""
    out: dict = {}
    for r in trade_rows:
        t = to_utc(r[ts])
        if r[wallet] not in out or t < out[r[wallet]]:
            out[r[wallet]] = t
    return out


def same_name_count(coins, name_key: str, name: str, before_ts) -> int:
    """允许域内、早于 before_ts 创建、规范化名称相同的币数（coins 已过 entry(…, 'coin')）。"""
    b = to_utc(before_ts)
    n = norm_symbol(name)
    return sum(
        1
        for c in coins
        if norm_symbol(c[name_key]) == n and to_utc(c["created_ts"]) < b
    )


def label_status(trigger_ts, horizon: dt.timedelta, window_end=None) -> str:
    """结果窗 (trigger, trigger+horizon] 是否成熟：终点须严格早于止日与观察窗终点。"""
    end = to_utc(trigger_ts) + horizon
    lim = CUTOFF if window_end is None else min(CUTOFF, to_utc(window_end))
    return (
        "mature" if end < lim else "immature"
    )  # 成交严格早于止日：终点恰在止日也看不到（GPT 12）


def truncate(trade_rows, ts="ts", window_end=None):
    """截断到止日（和观察窗终点）之前。派生字段（全窗最高价、存活等）必须从截断后的行重算。"""
    lim = CUTOFF if window_end is None else min(CUTOFF, to_utc(window_end))
    return [r for r in trade_rows if to_utc(r[ts]) < lim]


def lagged_week(week_monday: dt.date) -> dt.date | None:
    """B 的行情变量取“上一周”；上一周不是开发周就返回 None（记缺失）。"""
    prev = week_monday - dt.timedelta(days=7)
    return prev if W.week_class(prev) == W.DEV else None

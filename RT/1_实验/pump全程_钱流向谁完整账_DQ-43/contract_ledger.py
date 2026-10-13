#!/usr/bin/env python3
"""DQ-43（WM2）与 DQ-44（B）共同合同：记账定义（10-13，WM2 v5 §2 末段、§3 E2、E5，§8 T2a、T2b）。

单位：lamports 整数（1 SOL = 10^9 lamports）；比例用 Fraction 精确计算，报告时才转小数。
一个周期＝一个实体在一个币上、整个观察窗内的全部进出（E5）。观察窗＝创建后 30 天，且截在止日之前。

定义（冻结卡原样写入）：
- IN   ＝Σ 买入时离开交易者钱包、进入兑换的 SOL（含内嵌的协议费、创建者费、LP 费、回购费）。
- COST ＝Σ 交易者付款账户为这个币付的网络费、优先费、Jito 小费，含失败交易；
         一笔交易涉及多个币时按币均摊（整数余数给排序第一的币），另报不分摊的敏感性，不重复分摊。
- OUT  ＝Σ 卖出到手的 SOL（已扣内嵌费用）＋Σ 返现＋Σ 持有人奖励（交易者实际收到的 SOL）。
- HELD ＝估值时点（观察窗终点）的剩余代币，按“单独卖出”的可成交清算价值估值：用真实报价储备按恒定乘积卖出，
         不超过真实报价储备（T2b 主口径）。另报按有效报价储备边际价的标价，二者之差为估值残差。
- NET  ＝OUT ＋ HELD − IN − COST。
- RR   ＝OUT ÷ (IN ＋ COST)；MR ＝(OUT ＋ HELD) ÷ (IN ＋ COST)。分母为 0 记 None。
- 成本未知：周期里有转入的代币（不是买来的），或卖出的代币多于此前买入的，整周期记入“成本未知”一类，不按零成本计。
- 阶段分解（E5）：移动平均成本连续结转。曲线阶段的净额＝曲线卖出的已实现盈亏 − 曲线阶段 COST ＋ 曲线阶段返现与奖励；
  毕业后同理，期末未实现盈亏（HELD − 期末库存成本）记在期末所在阶段。两段之和恒等于整段 NET。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

LAMPORTS = 1_000_000_000
STAGES = ("curve", "amm")


@dataclass(frozen=True)
class Fill:
    entity: str
    coin: str
    slot: int
    tx: int  # 区块内交易序
    outer: int  # 外层指令序
    inner: int  # 内层指令序（无内层记 -1）
    stage: str  # curve / amm
    side: str  # buy / sell / xfer_in / xfer_out
    sol: int = 0  # buy：离开钱包的 SOL；sell：到手的 SOL
    tok: int = 0
    cashback: int = 0  # 这笔成交返给交易者的 SOL
    fees: dict = field(
        default_factory=dict, compare=False, hash=False
    )  # 内嵌费用，供 T2a：protocol、creator、lp、buyback

    def key(self) -> tuple:
        return (self.slot, self.tx, self.outer, self.inner)


@dataclass(frozen=True)
class TxCost:
    entity: str
    tx_id: str
    coins: tuple  # 这笔交易涉及的币（按排序）
    network: int
    priority: int
    tip: int
    failed: bool = False
    stage: str = "curve"


@dataclass(frozen=True)
class Reward:
    entity: str
    coin: str
    sol: int
    stage: str = "amm"


def order_key_unique(fills) -> bool:
    """排序键（slot, 交易序, 外层指令序, 内层指令序）在同一个币里必须唯一（冻结前清单第 9 条）。"""
    seen = set()
    for f in fills:
        k = (f.coin,) + f.key()
        if k in seen:
            return False
        seen.add(k)
    return True


def allocate_tx_costs(costs, split: bool = True) -> dict:
    """{(entity, coin): lamports}。split=False：整笔记到排序第一的币（敏感性口径）。"""
    out: dict = {}
    for c in costs:
        total = c.network + c.priority + c.tip
        coins = sorted(c.coins)
        if not split:
            parts = [total] + [0] * (len(coins) - 1)
        else:
            q, r = divmod(total, len(coins))
            parts = [q + r] + [q] * (len(coins) - 1)
        for coin, p in zip(coins, parts):
            out[(c.entity, coin)] = out.get((c.entity, coin), 0) + p
    return out


def sell_out(
    q: int, x_quote: int, y_tok: int, fee_bps: int = 0, cap: int | None = None
) -> Fraction:
    """恒定乘积卖出 q 个代币得到的报价资产：x·q'/(y+q')，q'＝q·(1−费率)；不超过 cap（真实报价储备）。"""
    if q <= 0:
        return Fraction(0)
    qe = Fraction(q) * (10_000 - fee_bps) / 10_000
    out = Fraction(x_quote) * qe / (y_tok + qe)
    return min(out, Fraction(cap)) if cap is not None else out


def mark_value(q: int, x_eff: int, y_tok: int) -> Fraction:
    """按有效报价储备的边际价标价：q·x_eff/y。"""
    return Fraction(q) * x_eff / y_tok if y_tok else Fraction(0)


@dataclass
class Cycle:
    entity: str
    coin: str
    IN: int = 0
    OUT: int = 0
    COST: int = 0
    HELD: Fraction = Fraction(0)
    HELD_mark: Fraction = Fraction(0)
    q_end: int = 0
    cost_unknown: bool = False
    stage_net: dict = field(default_factory=lambda: {s: Fraction(0) for s in STAGES})

    @property
    def NET(self) -> Fraction:
        return self.OUT + self.HELD - self.IN - self.COST

    @property
    def RR(self):
        d = self.IN + self.COST
        return Fraction(self.OUT, d) if d else None

    @property
    def MR(self):
        d = self.IN + self.COST
        return (self.OUT + self.HELD) / d if d else None


def cycle(
    fills, costs_alloc: dict, rewards, end_value, end_mark=None, end_stage: str = "amm"
) -> Cycle:
    """一个 (实体, 币) 的周期。fills 只含该周期的成交（已过过滤契约、已截断到观察窗）。
    end_value(q)→ 清算价值；end_mark(q)→ 标价；end_stage：期末库存所在阶段。"""
    fills = sorted(fills, key=Fill.key)
    if not fills:
        raise ValueError("空周期")
    ent, coin = fills[0].entity, fills[0].coin
    c = Cycle(ent, coin)
    q, basis = 0, Fraction(0)
    for f in fills:
        if f.side == "buy":
            c.IN += f.sol
            q += f.tok
            basis += f.sol
        elif f.side == "sell":
            c.OUT += f.sol
            if f.tok > q:
                c.cost_unknown = True
                removed = basis
                q = 0
            else:
                removed = basis * f.tok / q if q else Fraction(0)
                q -= f.tok
            basis -= removed
            c.stage_net[f.stage] += f.sol - removed
        elif f.side == "xfer_in":
            c.cost_unknown = True
            q += f.tok
        elif f.side == "xfer_out":
            removed = basis * f.tok / q if q else Fraction(0)
            q -= min(f.tok, q)
            basis -= removed
            c.stage_net[f.stage] -= removed  # 转出按成本离开，不当作收入
        if f.cashback:
            c.OUT += f.cashback
            c.stage_net[f.stage] += f.cashback
    for r in rewards:
        c.OUT += r.sol
        c.stage_net[r.stage] += r.sol
    cost = costs_alloc.get((ent, coin), 0)
    c.COST = cost
    # 交易成本按阶段：调用方可传 {(ent, coin, stage): …}；没有就记在曲线阶段
    staged = [costs_alloc.get((ent, coin, s)) for s in STAGES]
    if any(v is not None for v in staged):
        if sum(v or 0 for v in staged) != cost:
            raise ValueError("分阶段的交易成本之和与周期 COST 不一致")
        for s, v in zip(STAGES, staged):
            c.stage_net[s] -= v or 0
    else:
        c.stage_net["curve"] -= cost
    c.q_end = q
    c.HELD = end_value(q) if q else Fraction(0)
    c.HELD_mark = end_mark(q) if (q and end_mark) else Fraction(0)
    c.stage_net[end_stage] += c.HELD - basis
    return c


# ---------- T2a 现金守恒 ----------


def net_receipts(gross: dict, redistributed: dict) -> dict:
    """费用收款方的净收款：毛收款减去已转给交易者的部分（例如创建者费里分给持有人的奖励、协议费里付的返现）。
    redistributed 的每一项必须在 gross 里有同名来源。"""
    out = dict(gross)
    for k, v in redistributed.items():
        if k not in out:
            raise KeyError("再分配的来源 %s 不在毛收款里" % k)
        out[k] -= v
    return out


def t2a_residual(
    trader_in: int,
    trader_cost: int,
    trader_out: int,
    receipts: dict,
    pool_delta: int,
    boundary: int = 0,
    lp_in_pool: bool = True,
) -> int:
    """(交易者现金净流出) − (费用收款方净收款 ＋ 池子真实报价资产变化 ＋ 跨边界净流出)。应为 0。
    LP 费留在池子里时（lp_in_pool），已体现在 pool_delta，不能再在 receipts 里出现。"""
    if lp_in_pool and receipts.get("lp"):
        raise ValueError("LP 费已在池子储备里，不能再记为收款方收入")
    lhs = trader_in + trader_cost - trader_out
    rhs = sum(receipts.values()) + pool_delta + boundary
    return lhs - rhs

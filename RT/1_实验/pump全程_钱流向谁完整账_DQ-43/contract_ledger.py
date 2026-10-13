#!/usr/bin/env python3
"""DQ-43（WM2）与 DQ-44（B）共同合同：记账定义（10-13 v2，按 GPT 门 1 第 03～08 条修改）。

单位：lamports 整数（1 SOL = 10^9 lamports）；比例用 Fraction 精确计算，报告时才转小数。
一个周期＝一个实体在一个币上、整个观察窗内的全部进出（E5）。周期的主键来自成交、交易成本、奖励三者的并集：
只有费用（例如失败交易、代付）或只有奖励的实体也有周期。

定义（冻结卡原样写入）：
- IN   ＝Σ 买入时离开交易者钱包、进入兑换的 SOL（含内嵌的协议费、创建者费、LP 费、回购费）。
- COST ＝Σ 付款实体为这个币付的交易成本：network（只含签名基础费）＋priority（计算单元价格费）＋tip（Jito 小费），
         含失败交易；同一 tx_id 只记一次。一笔交易涉及多条（币, 阶段）腿时按腿均摊，整数余数给排序第一的腿；
         另报不分摊（整笔给第一腿）的敏感性。成本记在付款实体名下：第三方代付时，付款实体有一个只有 COST 的周期。
- OUT  ＝Σ 卖出到手的 SOL（已扣内嵌费用）＋Σ 返现＋Σ 持有人奖励（交易者实际收到的 SOL）。
- HELD ＝估值时点（观察窗终点）的剩余代币单独卖出的清算价值：
         毛额＝x·q/(y＋q)，x、y 是该场所的定价储备（曲线：虚拟 SOL 与虚拟代币储备；PumpSwap：池报价储备＋虚拟报价储备、池代币储备）；
         兑付上限＝真实报价储备（曲线：真实 SOL 储备；PumpSwap：池报价储备）；卖出费按比例从兑付额里扣；最后向下取整到 lamport。
         不扣假设清仓时的网络费与小费。HELD 是“各自单独卖出”的值，不能相加解释为全体同时可兑付的金额（GPT 04）。
- HELD_mark ＝剩余代币 × 定价储备边际价 x/y；与 HELD 之差为估值残差（T2b）。
- NET  ＝OUT ＋ HELD − IN − COST。RR ＝OUT ÷ (IN＋COST)；MR ＝(OUT＋HELD) ÷ (IN＋COST)；分母为 0 记 None。
- 成本未知（非交易的代币进出）：周期里有转入或转出的代币，或卖出多于此前买入，整周期打标；NET 照算（转出按无收入计）但单列，
  另报转出带走的成本 xfer_out_basis；不进标签账（R1 两种口径见卡）。同一实体内部钱包之间的转移在实体归并时先抵销，不进这里。
- 阶段账（E5，GPT 08）：按“实现阶段”归属，不表示利润在哪个阶段形成。移动平均成本连续结转；阶段只能从曲线到毕业后。
  曲线：OUT_c ＋ 结转出成本 − IN_c − COST_c；毕业后：OUT_a ＋ HELD − IN_a − COST_a − 结转入成本（期末库存在曲线阶段时 HELD 记在曲线）。
  两段之和恒等于整段 NET。阶段 RR、MR 的分母＝该阶段 IN＋COST＋结转入成本，分子＝OUT＋结转出成本（＋期末阶段的 HELD）。
- T2a（GPT 07）：只按账户类之间的真实转移对账。每条流水是 (付出类, 收到类, lamports)；同类之间的转移自动抵销，
  所以回购金库再买入、费用 sweep、金库转持有人等内部转移不会重复计。boundary 只能来自流水本身，不能当残差配平。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

LAMPORTS = 1_000_000_000
STAGES = ("curve", "amm")
ACCOUNT_CLASSES = (
    "trader",
    "pool",
    "protocol",
    "creator",
    "validator",
    "jito",
    "buyback",
    "holder_vault",
    "burn",
    "boundary",
)


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

    def key(self) -> tuple:
        return (self.slot, self.tx, self.outer, self.inner)


@dataclass(frozen=True)
class TxCost:
    tx_id: str
    payer: str  # 付款实体（实际付费账户归并后的实体）
    legs: tuple  # ((币, 阶段), …)：这笔交易涉及的腿
    network: int  # 只含签名基础费
    priority: int  # 计算单元价格费
    tip: int  # Jito 小费
    failed: bool = False


@dataclass(frozen=True)
class Reward:
    entity: str
    coin: str
    sol: int
    stage: str


def order_key_unique(fills) -> bool:
    """排序键（slot, 交易序, 外层指令序, 内层指令序）在同一个币里必须唯一（冻结前清单第 9 条）。"""
    seen = set()
    for f in fills:
        k = (f.coin,) + f.key()
        if k in seen:
            return False
        seen.add(k)
    return True


def allocate_tx_costs(costs, split: bool = True, keep_coin=None) -> dict:
    """{(付款实体, 币, 阶段): lamports}。同一 tx_id 只记一次；内容不同的重复记录报错。
    keep_coin(币)→bool：混合允许币与保护币的交易，按全部腿均摊，只输出允许币的份额（只用腿数，不读保护币的结果）。"""
    seen: dict = {}
    for c in costs:
        if c.tx_id in seen:
            if seen[c.tx_id] != c:
                raise ValueError("同一 tx_id 有两条不同的成本记录：%s" % c.tx_id)
            continue
        seen[c.tx_id] = c
    out: dict = {}
    for c in seen.values():
        legs = sorted(set(c.legs))
        if not legs:
            raise ValueError("交易 %s 没有腿" % c.tx_id)
        for _, st in legs:
            if st not in STAGES:
                raise ValueError("未知阶段 %s" % st)
        total = c.network + c.priority + c.tip
        if split:
            q, r = divmod(total, len(legs))
            parts = [q + r] + [q] * (len(legs) - 1)
        else:
            parts = [total] + [0] * (len(legs) - 1)
        for (coin, st), p in zip(legs, parts):
            if keep_coin is not None and not keep_coin(coin):
                continue
            k = (c.payer, coin, st)
            out[k] = out.get(k, 0) + p
    return out


def cycle_keys(fills, cost_alloc: dict, rewards) -> set:
    keys = {(f.entity, f.coin) for f in fills}
    keys |= {(e, c) for (e, c, _s) in cost_alloc}
    keys |= {(r.entity, r.coin) for r in rewards}
    return keys


def liquidation(q: int, x_price: int, y_price: int, cap: int, fee_bps: int) -> int:
    """单独卖出 q 个代币的清算价值（lamports，向下取整）：min(x·q/(y＋q), cap)·(1 − 费率)。"""
    if q <= 0:
        return 0
    gross = Fraction(x_price) * q / (y_price + q)
    pay = min(gross, Fraction(cap))
    net = pay * (10_000 - fee_bps) / 10_000
    return net.numerator // net.denominator


def mark_value(q: int, x_price: int, y_price: int) -> Fraction:
    """按定价储备边际价标价：q·x/y。"""
    return Fraction(q) * x_price / y_price if y_price else Fraction(0)


@dataclass
class Cycle:
    entity: str
    coin: str
    IN: int = 0
    OUT: int = 0
    COST: int = 0
    HELD: int = 0
    HELD_mark: Fraction = Fraction(0)
    q_end: int = 0
    cost_unknown: bool = False
    stage_in: dict = field(default_factory=lambda: {s: 0 for s in STAGES})
    stage_out: dict = field(default_factory=lambda: {s: 0 for s in STAGES})
    stage_cost: dict = field(default_factory=lambda: {s: 0 for s in STAGES})
    carry_in: dict = field(default_factory=lambda: {s: Fraction(0) for s in STAGES})
    carry_out: dict = field(default_factory=lambda: {s: Fraction(0) for s in STAGES})
    end_stage: str = ""
    xfer_out_basis: Fraction = Fraction(0)  # 转出代币带走的成本（周期单列时一起报）

    @property
    def NET(self) -> int:
        return self.OUT + self.HELD - self.IN - self.COST

    @property
    def RR(self):
        d = self.IN + self.COST
        return Fraction(self.OUT, d) if d else None

    @property
    def MR(self):
        d = self.IN + self.COST
        return Fraction(self.OUT + self.HELD, d) if d else None

    def stage_net(self, s: str) -> Fraction:
        held = self.HELD if s == self.end_stage else 0
        return (
            self.stage_out[s]
            + self.carry_out[s]
            + held
            - self.stage_in[s]
            - self.stage_cost[s]
            - self.carry_in[s]
        )

    def stage_mr(self, s: str):
        d = self.stage_in[s] + self.stage_cost[s] + self.carry_in[s]
        held = self.HELD if s == self.end_stage else 0
        return (self.stage_out[s] + self.carry_out[s] + held) / d if d else None


def cycle(
    entity: str,
    coin: str,
    fills,
    cost_alloc: dict,
    rewards,
    end_value,
    end_stage: str,
    end_mark=None,
) -> Cycle:
    """一个 (实体, 币) 的周期。fills、rewards 可以含别的周期，这里只取本周期的；可以为空（只有费用或奖励）。
    end_value(q) → 清算价值（整数 lamports）；end_stage：期末库存所在阶段，必须显式给出。"""
    if end_stage not in STAGES:
        raise ValueError("期末阶段必须显式给出（curve 或 amm）")
    mine = sorted(
        (f for f in fills if f.entity == entity and f.coin == coin), key=Fill.key
    )
    c = Cycle(entity, coin, end_stage=end_stage)
    q, basis, cur = 0, Fraction(0), None
    for f in mine:
        if cur is not None and f.stage != cur:
            if (cur, f.stage) != ("curve", "amm"):
                raise ValueError("阶段只能从曲线到毕业后")
            c.carry_out["curve"] += basis
            c.carry_in["amm"] += basis
        cur = f.stage
        if f.side == "buy":
            c.IN += f.sol
            c.stage_in[f.stage] += f.sol
            q += f.tok
            basis += f.sol
        elif f.side == "sell":
            c.OUT += f.sol
            c.stage_out[f.stage] += f.sol
            if f.tok > q:
                c.cost_unknown = True
                removed, q = basis, 0
            else:
                removed = basis * f.tok / q if q else Fraction(0)
                q -= f.tok
            basis -= removed
        elif f.side == "xfer_in":
            c.cost_unknown = True
            q += f.tok
        elif f.side == "xfer_out":
            removed = basis * min(f.tok, q) / q if q else Fraction(0)
            q -= min(f.tok, q)
            basis -= removed
            c.cost_unknown = True  # 转出到别的实体：去向价值不明，整周期单列（GPT 09）
            c.xfer_out_basis += removed
        else:
            raise ValueError("未知方向 %s" % f.side)
        if f.cashback:
            c.OUT += f.cashback
            c.stage_out[f.stage] += f.cashback
    if cur == "amm" and end_stage == "curve" and q:
        raise ValueError("期末库存已在毕业后阶段，期末阶段不能是曲线")
    if cur == "curve" and end_stage == "amm" and q:
        c.carry_out["curve"] += basis  # 曲线买入、毕业后才持有到期末
        c.carry_in["amm"] += basis
    for r in rewards:
        if r.entity == entity and r.coin == coin:
            c.OUT += r.sol
            c.stage_out[r.stage] += r.sol
    for s in STAGES:
        v = cost_alloc.get((entity, coin, s), 0)
        c.COST += v
        c.stage_cost[s] += v
    c.q_end = q
    c.HELD = end_value(q) if q else 0
    c.HELD_mark = end_mark(q) if (q and end_mark) else Fraction(0)
    return c


# ---------- T2a 现金守恒（按账户类的真实转移） ----------


def class_nets(flows) -> dict:
    """flows：[(付出类, 收到类, lamports)]。返回各类的净流入；同类之间的转移抵销。"""
    net = {k: 0 for k in ACCOUNT_CLASSES}
    for src, dst, lam in flows:
        if src not in net or dst not in net:
            raise ValueError("未知账户类 %s→%s" % (src, dst))
        if lam < 0:
            raise ValueError("流水金额不能为负")
        net[src] -= lam
        net[dst] += lam
    return net


def t2a_residual(trader_in: int, trader_cost: int, trader_out: int, flows) -> int:
    """事件口径的交易者净流出（IN＋COST−OUT）减去流水口径的交易者净流出。应为 0。"""
    return (trader_in + trader_cost - trader_out) - (-class_nets(flows)["trader"])

"""第十五～十七轮纯函数草稿。无网络、无真实S3；输入须先过保护域。"""

from collections import defaultdict
from dataclasses import dataclass


class StrongRows:
    """可重复扫描：先在完整原图计算服务度数，再筛种子直接S/T。"""

    def __init__(self, rows, cex=()):
        if iter(rows) is rows:
            raise ValueError("须能重复扫描完整图")
        self.rows = rows
        self.cex = set(cex)
        self.seeds = set()
        neighbors = defaultdict(set)
        for row in rows:
            kind, a, b = row["kind"], row["a"], row["b"]
            if kind == "V":
                if not a or a in self.seeds:
                    raise ValueError("种子缺失或重复")
                self.seeds.add(a)
            elif kind in ("S", "T"):
                neighbors[kind, a].add(b)
                neighbors[kind, b].add(a)
            elif kind != "G":
                raise ValueError("未知边类型")
        if not self.seeds:
            raise ValueError("缺完整W种子")
        self.hubs = {k for k, v in neighbors.items() if len(v) > 200}
        # 不保留庞大的邻居集合；后续扫描只用服务节点集合。

    def __iter__(self):
        for row in self.rows:
            kind, a, b = row["kind"], row["a"], row["b"]
            if kind in ("V", "G") or (
                kind in ("S", "T")
                and a in self.seeds
                and b in self.seeds
                and not ({a, b} & self.cex)
                and (kind, a) not in self.hubs
                and (kind, b) not in self.hubs
            ):
                yield row


def size_bins(histogram):
    """输入实体完整成员规模→实体数；单钱包另报，不混入多钱包档。"""
    bounds = ((2, 2), (3, 5), (6, 10), (11, 20), (21, 50), (51, 200))
    out = {str(lo) if lo == hi else f"{lo}-{hi}": 0 for lo, hi in bounds}
    out[">200"] = 0
    for size, count in histogram.items():
        size = int(size)
        if size <= 1:
            continue
        label = next(
            (
                str(lo) if lo == hi else f"{lo}-{hi}"
                for lo, hi in bounds
                if lo <= size <= hi
            ),
            ">200",
        )
        out[label] += count
    return out


@dataclass(frozen=True)
class Proof:
    """锚点前完整度数由提取方保证；不接受仅目标筛选后的计数。"""

    kind: str
    other: str
    key: tuple
    degree_wallet: int
    degree_other: int
    lamports: int = 0
    fanout: int | None = None
    window_first: bool = False


@dataclass(frozen=True)
class Attachment:
    entity: str
    status: str
    anchor: tuple


def attach(wallet, anchor, fixed, proofs, fixed_g, *, coverage_complete, cex=()):
    """演示只挂靠规则；不负责Dune提取、G首源核验或上游保护过滤。"""
    if wallet in fixed:
        return Attachment(fixed[wallet], "fixed", anchor)
    if wallet in cex:
        return Attachment(wallet, "service", anchor)
    if not coverage_complete:
        return Attachment(wallet, "unknown", anchor)
    targets = set()
    fixed_entities = set(fixed.values())
    for p in proofs:
        if p.kind not in ("S", "T", "G"):
            raise ValueError("未知强连接")
        if p.kind == "G" and p.fanout is None:
            raise ValueError("G完整扇出缺失；不能声称覆盖完整")
        if p.key >= anchor or p.other in cex:
            continue
        if p.kind in ("S", "T"):
            if min(p.degree_wallet, p.degree_other) < 0:
                raise ValueError("度数缺失")
            if max(p.degree_wallet, p.degree_other) > 200:
                continue
            if p.kind == "S" and p.lamports < 50_000_000:
                continue
            if p.other in fixed:
                targets.add(fixed[p.other])
        elif (
            p.window_first
            and p.fanout is not None
            and 0 <= p.fanout <= 200
            and p.lamports >= 50_000_000
        ):
            candidates = set(fixed_g.get(p.other, ()))
            if not candidates <= fixed_entities:
                raise ValueError("G指向非固定W实体")
            targets.update(candidates)
    if len(targets) == 1:
        return Attachment(next(iter(targets)), "attached", anchor)
    return Attachment(wallet, "ambiguous" if targets else "unattached", anchor)


def entity_at(wallet, key, fixed, attachments):
    """事件不能使用它之后才成立的挂靠；固定成员不随W1改变。"""
    if wallet in fixed:
        return fixed[wallet]
    result = attachments.get(wallet)
    return result.entity if result is not None and key >= result.anchor else wallet


def activity(eligible, selected, buy_entities):
    """只统计预给定的E/S与允许域任意买入，未要求成熟。"""
    eligible, selected, active = set(eligible), set(selected), set(buy_entities)
    if not selected <= eligible:
        raise ValueError("S须为E子集")
    groups = {
        "selected": selected,
        "eligible": eligible,
        "nonselected": eligible - selected,
    }
    counts = {k: {"n": len(v), "active": len(v & active)} for k, v in groups.items()}
    ns, ne = len(selected), len(eligible)
    a, b = len(selected & active), len(eligible & active)
    return {
        "groups": counts,
        "low_activity_flag": None
        if not ns or not ne or not b
        else (10 * (a * ne - b * ns) <= -ns * ne and 5 * a * ne <= 4 * b * ns),
    }

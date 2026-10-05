#!/usr/bin/env python3
"""DQ-37 曲线阶段留存 v1：逐笔层的选周规则（10-06；GPT 批 0 A5、总控第十五轮第 7 条、第十七轮第四节）。

python select_curve_weeks.py  → 打印选中的周与替补顺序（写进 曲线阶段留存_设计_v1.md §3）
规则（在读任何曲线阶段数据之前写定；本脚本只用日历、weeks.py 与仓库里已记录的制度节点）：
1. 日历范围：DQ-37 的全部周（2025-02-24～2026-09-28 的周一），去掉封存周与范围外；前向批次（2026-10-05 起创建）不在范围内。
2. 制度阶段（按周一所在日期归属；节点来自事实库 F33、F36 与 DQ-18 README §6.2，都是事先已知的协议变更）：
   P1 2025-02-24～05-12（PumpSwap 03-20 上线，无创作者费）；P2 05-13～09-02（创作者费）；P3 09-03～11-11（按市值分档收费）；
   P4 11-12～2026-05-06（Mayhem）；P5 2026-05-07～07-14（曲线可用非 SOL 计价）；P6 07-15～09-28（PumpSwap vq；09-12 起持币奖励）。
3. 名额：开发周 8 个、检验周 3 个（推进方案 v1 §4 的量级）。各阶段按该类周数用最大余数法分配；开发周每个阶段至少 1 个。
4. 抽取：每个阶段、每一类里，按 sha256("RT-DQ37-curvev1-weeks|" + weeks.SALT + "|" + 周一) 从小到大排序，取前 k 个。
   SALT 是 09-30 写定的检验周盐值；本标签与排序方式在看任何曲线阶段数据之前提交。
5. 替补：只有“数据缺失”才替补——该周 7 天里任何一天的 pump 创建事件或曲线成交事件在 Dune 解码表里为 0 行
   （整日断档）。替补取同阶段、同类别排序里的下一个周。冷清、币少、成交少都不是替补理由。
"""

import datetime as dt
import hashlib

import weeks

TAG = "RT-DQ37-curvev1-weeks"
PHASES = [
    ("P1", dt.date(2025, 2, 24), dt.date(2025, 5, 12)),
    ("P2", dt.date(2025, 5, 13), dt.date(2025, 9, 2)),
    ("P3", dt.date(2025, 9, 3), dt.date(2025, 11, 11)),
    ("P4", dt.date(2025, 11, 12), dt.date(2026, 5, 6)),
    ("P5", dt.date(2026, 5, 7), dt.date(2026, 7, 14)),
    ("P6", dt.date(2026, 7, 15), dt.date(2026, 9, 28)),
]
QUOTA = {weeks.DEV: 8, weeks.TEST: 3}


def phase_of(monday):
    for name, a, b in PHASES:
        if a <= monday <= b:
            return name
    return None


def rank_key(monday):
    return hashlib.sha256(
        ("%s|%s|%s" % (TAG, weeks.SALT, monday.isoformat())).encode("utf-8")
    ).hexdigest()


def all_weeks():
    out = []
    m = weeks.FIRST_MONDAY
    while m <= weeks.LAST_MONDAY:
        c = weeks.week_class(m.isoformat())
        if c in (weeks.DEV, weeks.TEST):
            out.append((m, c, phase_of(m)))
        m += dt.timedelta(days=7)
    return out


def allocate(counts, total, min_one):
    """最大余数法：counts {阶段: 周数} → {阶段: 名额}。min_one 时每个非空阶段至少 1 个。"""
    alloc = {p: 0 for p in counts}
    rest = total
    if min_one:
        for p, n in counts.items():
            if n > 0:
                alloc[p] = 1
                rest -= 1
    tot = sum(counts.values())
    quota = {p: rest * n / tot for p, n in counts.items()}
    for p in counts:
        alloc[p] += int(quota[p])
    left = total - sum(alloc.values())
    for p in sorted(counts, key=lambda p: (-(quota[p] - int(quota[p])), p))[:left]:
        alloc[p] += 1
    return alloc


def select():
    ws = all_weeks()
    picked, order = [], {}
    for cls, total in QUOTA.items():
        counts = {
            p: sum(1 for _, c, ph in ws if c == cls and ph == p) for p, _, _ in PHASES
        }
        alloc = allocate(counts, total, min_one=(cls == weeks.DEV))
        for p, _, _ in PHASES:
            cand = sorted((m for m, c, ph in ws if c == cls and ph == p), key=rank_key)
            order[(p, cls)] = cand
            picked += [(m, cls, p) for m in cand[: alloc[p]]]
    return sorted(picked), order, ws


def main():
    picked, order, ws = select()
    print(
        "可选周：%d（开发 %d、检验 %d）"
        % (
            len(ws),
            sum(c == weeks.DEV for _, c, _ in ws),
            sum(c == weeks.TEST for _, c, _ in ws),
        )
    )
    print(
        "| 阶段 | 开发周数 | 检验周数 | 选中的开发周 | 选中的检验周 | 替补顺序（开发／检验，各前 2 个） |"
    )
    print("|---|---|---|---|---|---|")
    for p, _, _ in PHASES:
        dv = order[(p, weeks.DEV)]
        ts = order[(p, weeks.TEST)]
        pd_ = [m for m, c, ph in picked if ph == p and c == weeks.DEV]
        pt = [m for m, c, ph in picked if ph == p and c == weeks.TEST]
        print(
            "| %s | %d | %d | %s | %s | %s／%s |"
            % (
                p,
                len(dv),
                len(ts),
                "、".join(m.isoformat() for m in pd_) or "—",
                "、".join(m.isoformat() for m in pt) or "—",
                "、".join(m.isoformat() for m in dv[len(pd_) : len(pd_) + 2]) or "—",
                "、".join(m.isoformat() for m in ts[len(pt) : len(pt) + 2]) or "—",
            )
        )


if __name__ == "__main__":
    main()

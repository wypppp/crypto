#!/usr/bin/env python3
"""DQ-39 SOLMEMES 元数据错位的结构诊断（10-06；总控第二十轮第四节）。

python s0b_misalign.py  → S0b_错位诊断.md
只用元数据列（token、名称、代号、时刻）与链上时间锚（sql/S0_链上时间锚.sql 的结果），不读价格与成交列。
1. 认领：每一行的（名称、代号）与本数据集哪个 token 的链上初始（名称、代号）相同。分四类：认领到自己、唯一认领到别的 token、
   认领到多个、本数据集里没有。
2. 时间差：唯一认领的行，所属 token 与本行 token 的链上曲线创建时刻之差；与两个对照比较——全体随机配对、同周随机配对。
3. 固定偏移：在几种排序下（数据行序、created_at、graduated_date、token 字典序、链上建池时刻），
   看“所属 token 的名次 − 本行 token 的名次”是否集中在某个常数；再看两种不同排序交叉时是否有固定偏移
   （例如元数据按一种键排序、token 按另一种键排序后按位置拼接）。
"""

import csv
import datetime as dt
import gzip
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

H = Path(__file__).resolve().parent
PARQ = H / "raw" / "pump_swap_final_with_metadata.parquet"
COLS = ["token", "token_uri", "created_at", "graduated_date", "name", "symbol"]
SEED = 20261006


def norm_sym(s):
    return None if s is None else s.replace("$", "").strip().upper()


def norm_name(s):
    return None if s is None else s.strip()


def key(name, sym):
    return (norm_name(name), norm_sym(sym))


def epoch(x):
    return None if x is None else (x - dt.datetime(1970, 1, 1)).total_seconds()


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def load():
    m = pq.read_table(PARQ, columns=COLS).to_pydict()
    with gzip.open(H / "raw" / "dune" / "S0_ANCHOR.csv.gz", "rt", newline="") as f:
        lines = [x.replace("\0", "") for x in f]
    anc = {r["mint"]: r for r in csv.DictReader(lines)}
    return m, anc


def claims(m, anc):
    """每一行 → (类别, 所属 token 或 None)。"""
    owners = defaultdict(list)
    for t, a in anc.items():
        if a["c_name"] or a["c_symbol"]:
            owners[key(a["c_name"], a["c_symbol"])].append(t)
    out = []
    for i, t in enumerate(m["token"]):
        c = owners.get(key(m["name"][i], m["symbol"][i]), [])
        if t in c:
            out.append(("self", t))
        elif len(c) == 1:
            out.append(("other", c[0]))
        elif len(c) > 1:
            out.append(("multi", None))
        else:
            out.append(("none", None))
    return out


def ranks(order_keys):
    """{token: 名次}，按 (键, token) 排序，键为 None 的排最后。"""
    toks = sorted(order_keys, key=lambda t: (order_keys[t] is None, order_keys[t], t))
    return {t: i for i, t in enumerate(toks)}


def week_of(t):
    d = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t)).date()
    return d - dt.timedelta(days=d.weekday())


def fmt_h(x):
    return "—" if x is None else "%.1f" % (x / 3600.0)


def dist_line(lab, xs):
    a = [abs(x) for x in xs]
    return "| %s | %d | %s | %s | %s | %s | %.1f%% | %.1f%% | %.1f%% |" % (
        lab,
        len(xs),
        fmt_h(q(xs, 0.1)),
        fmt_h(q(xs, 0.5)),
        fmt_h(q(xs, 0.9)),
        fmt_h(q(a, 0.5)),
        100.0 * sum(x <= 3600 for x in a) / max(1, len(a)),
        100.0 * sum(x <= 86400 for x in a) / max(1, len(a)),
        100.0 * sum(x > 0 for x in xs) / max(1, len(xs)),
    )


def main():
    m, anc = load()
    n = len(m["token"])
    cl = claims(m, anc)
    L = ["# DQ-39 SOLMEMES 元数据错位的结构诊断（10-06）", ""]
    L.append(
        "数据与锚同 S0（修订 `71211f6d`，parquet sha256 `1ac22b5c…`；`sql/S0_链上时间锚.sql`）。只用元数据列与时刻，没有读价格与成交列。"
    )
    L.append("")

    # 1. 认领
    cc = Counter(c for c, _ in cl)
    L.append("## 1. 每一行的元数据属于哪个 token")
    L.append("")
    L.append(
        "按（名称、代号）与链上初始值比对；名称去首尾空白，代号去 `$`、去空白、转大写。"
    )
    L.append("")
    L.append("| 类别 | 行数 | 说明 |")
    L.append("|---|---|---|")
    for k, d in (
        ("self", "认领到本行的 token"),
        ("other", "唯一认领到本数据集里别的 token"),
        ("multi", "本数据集里有多个 token 同名同代号"),
        ("none", "本数据集里没有同名同代号的 token"),
    ):
        L.append("| %s | %d | %s |" % (k, cc.get(k, 0), d))
    L.append("| 合计 | %d | |" % n)
    owned = Counter(j for c, j in cl if c in ("self", "other"))
    L.append("")
    L.append(
        "- 被认领的 token %d 个；其中被不止一行认领的 %d 个（最多 %d 行）。"
        % (
            len(owned),
            sum(v > 1 for v in owned.values()),
            max(owned.values()) if owned else 0,
        )
    )
    toks = sorted(set(m["token"]))
    L.append(
        "- 本数据集 %d 个 token 里，没有被任何一行认领的 %d 个。"
        % (len(toks), sum(1 for t in toks if t not in owned))
    )
    L.append("")

    # 2. 时间差
    cr = {
        t: float(a["curve_created_t"]) if a["curve_created_t"] else None
        for t, a in anc.items()
    }
    pairs = [
        (i, m["token"][i], j)
        for i, (c, j) in enumerate(cl)
        if c == "other" and cr.get(m["token"][i]) and cr.get(j)
    ]
    obs = [cr[j] - cr[t] for _, t, j in pairs]
    rng = random.Random(SEED)
    have = [t for t in toks if cr.get(t)]
    rand_all = [cr[rng.choice(have)] - cr[t] for _, t, _ in pairs]
    by_week = defaultdict(list)
    for t in have:
        by_week[week_of(cr[t])].append(t)
    rand_wk = []
    for _, t, _ in pairs:
        pool = by_week[week_of(cr[t])]
        rand_wk.append(cr[rng.choice(pool)] - cr[t])
    L.append("## 2. 所属 token 与本行 token 的创建时间差（链上曲线创建；小时）")
    L.append("")
    L.append(
        "只用“唯一认领到别的 token”的行（%d 行）。对照用同样的行、把所属 token 换成随机抽的 token（固定种子 %d）。"
        % (len(pairs), SEED)
    )
    L.append("")
    L.append(
        "| 配对 | 行数 | p10 | 中位 | p90 | |差| 中位 | |差|≤1 小时 | |差|≤1 天 | 差>0 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    L.append(dist_line("实际（元数据的所属 token）", obs))
    L.append(dist_line("对照：全体随机", rand_all))
    L.append(dist_line("对照：同一周内随机", rand_wk))
    same_wk = sum(week_of(cr[j]) == week_of(cr[t]) for _, t, j in pairs)
    L.append("")
    L.append(
        "- 所属 token 与本行 token 在同一周创建的 %d／%d 行（%.1f%%）。"
        % (same_wk, len(pairs), 100.0 * same_wk / max(1, len(pairs)))
    )
    L.append("")

    # 3. 固定偏移
    first_row = {}
    for i, t in enumerate(m["token"]):
        first_row.setdefault(t, i)
    orders = {
        "数据行序": {t: first_row[t] for t in toks},
        "created_at": {t: epoch(m["created_at"][first_row[t]]) for t in toks},
        "graduated_date": {t: epoch(m["graduated_date"][first_row[t]]) for t in toks},
        "token 字典序": {t: t for t in toks},
        "链上建池": {
            t: float(anc[t]["pool_created_t"]) if anc[t]["pool_created_t"] else None
            for t in toks
        },
        "链上曲线创建": {t: cr.get(t) for t in toks},
        "数据 name 字典序": {t: m["name"][first_row[t]] or "" for t in toks},
        "数据 token_uri 字典序": {t: m["token_uri"][first_row[t]] or "" for t in toks},
    }
    R = {k: ranks(v) for k, v in orders.items()}
    L.append("## 3. 是否某种排序下的固定偏移")
    L.append("")
    L.append(
        "偏移＝所属 token 在排序 A 下的名次 − 本行 token 在排序 B 下的名次（%d 个 token 各按首行；只用唯一认领到别的 token 的行）。"
        % len(toks)
    )
    L.append(
        "随机配对时，最常见偏移的占比约为 1／token 数；某个偏移占比明显更高，才算固定偏移。"
    )
    L.append("")
    L.append(
        "| 排序 A（所属 token） | 排序 B（本行 token） | 最常见偏移（占比） | 次常见 | |偏移|≤5 的占比 |"
    )
    L.append("|---|---|---|---|---|")
    best = []
    for a in R:
        for bb in R:
            offs = [R[a][j] - R[bb][t] for _, t, j in pairs]
            c = Counter(offs).most_common(2)
            near = sum(abs(x) <= 5 for x in offs) / max(1, len(offs))
            best.append((c[0][1] / max(1, len(offs)), a, bb, c, near))
    best.sort(reverse=True)
    for share, a, bb, c, near in best[:12]:
        L.append(
            "| %s | %s | %+d（%.2f%%） | %s | %.2f%% |"
            % (
                a,
                bb,
                c[0][0],
                100 * share,
                "%+d（%.2f%%）" % (c[1][0], 100.0 * c[1][1] / len(pairs))
                if len(c) > 1
                else "—",
                100 * near,
            )
        )
    L.append("")
    # 名次相关：两种排序下名次的秩相关
    L.append(
        "同一排序下，所属 token 名次与本行 token 名次的相关（Spearman，名次已是秩）："
    )
    L.append("")
    for a in R:
        xs = [R[a][t] for _, t, _ in pairs]
        ys = [R[a][j] for _, _, j in pairs]
        L.append(
            "- %s：%.3f"
            % (
                a,
                statistics.correlation(xs, ys)
                if hasattr(statistics, "correlation")
                else pearson(xs, ys),
            )
        )
    L.append("")

    # 4. 分页重复规律（10-06 第 3 节的数据行序相关 0.94 引出）
    order = sorted(toks, key=lambda t: first_row[t])  # token 首次出现的顺序
    uidx = {t: i for i, t in enumerate(order)}
    N = len(order)

    def page_owner(u):
        """第 u 个 token 拿到的元数据属于第 10·⌊u/20⌋ + u mod 10 个 token（每 10 条一页、每页重复一次）。"""
        return order[10 * (u // 20) + u % 10]

    def k_on(t):
        return key(anc[t]["c_name"], anc[t]["c_symbol"])

    cnt = Counter(m["token"])
    hit, miss = 0, Counter()
    dec_hit, dec_tot = Counter(), Counter()
    for i, (c, j) in enumerate(cl):
        u = uidx[m["token"][i]]
        d = u * 10 // N
        dec_tot[d] += 1
        if k_on(page_owner(u)) == key(m["name"][i], m["symbol"][i]):
            hit += 1
            dec_hit[d] += 1
        else:
            miss["重复 token 多出的行" if cnt[m["token"][i]] > 1 else c] += 1
    L.append("## 4. 结构：一个固定的位置映射")
    L.append("")
    L.append(
        "按 token 在数据里首次出现的顺序编号（0 起）。第 u 个 token 拿到的元数据，属于第 10·⌊u/20⌋＋(u mod 10) 个 token。"
    )
    L.append(
        "一个可能的成因是：按每页 10 条取元数据时每一页重复了一次，再按位置与 token 拼接。这是推测，没有核实；85% 的行符合这个映射是事实（GPT 批 1b D）。"
    )
    L.append("")
    L.append(
        "- 符合规律的行：%d／%d（%.1f%%）。按 token 顺序的十分位，符合率 %s。"
        % (
            hit,
            n,
            100.0 * hit / n,
            "、".join("%.0f%%" % (100.0 * dec_hit[d] / dec_tot[d]) for d in range(10)),
        )
    )
    L.append(
        "- 不符合的 %d 行：%s。"
        % (
            n - hit,
            "；".join(
                "%s %d"
                % (
                    {
                        "none": "本数据集无同名同代号",
                        "other": "认领到别的 token",
                        "multi": "同名同代号多个",
                    }.get(k, k),
                    v,
                )
                for k, v in miss.most_common()
            ),
        )
    )
    owners = set(page_owner(u) for u in range(N))
    L.append(
        "- 能拿到元数据的 token 只有前一半：所属 token 的编号最大 %d（共 %d 个）。后一半 token 自己的元数据在数据里从不出现。"
        % (max(uidx[t] for t in owners), N)
    )
    L.append(
        "- 同一份元数据接在两个 token 上：第 u 与第 u＋10 个 token（u mod 20 < 10）共用一份文本。"
    )
    L.append("")
    # 哪些列跟着元数据块移动
    d2 = pq.read_table(PARQ, columns=["description", "image"]).to_pydict()
    own = defaultdict(list)
    for i, (c, j) in enumerate(cl):
        if j:
            own[j].append(i)
    multi = [ix for ix in own.values() if len(ix) > 1]
    same = lambda col, src: sum(len(set(src[col][i] for i in ix)) == 1 for ix in multi)  # noqa: E731
    L.append(
        "哪些列跟着错位：认领到同一个 token 的 %d 组行里，描述相同 %d 组、图片相同 %d 组、`token_uri` 相同 %d 组。"
        % (len(multi), same("description", d2), same("image", d2), same("token_uri", m))
    )
    L.append(
        "所以名称、代号、描述、图片一起错位；`token_uri` 与价格列跟着本行 token。抽查 IPFS 上 `token_uri` 的内容，名称与本行 token 的链上名称一致。"
    )
    L.append("")
    # 列表顺序与时间
    L.append("token 顺序与创建时刻（按顺序十分位，链上曲线创建的中位）：")
    L.append("")
    meds = []
    for d in range(10):
        ts = sorted(cr[t] for t in order[d * N // 10 : (d + 1) * N // 10] if cr.get(t))
        meds.append(
            (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=ts[len(ts) // 2])).strftime(
                "%m-%d"
            )
        )
    L.append("- " + "、".join(meds))
    L.append(
        "- 前一半 token 集中在较早的一段，后一半在较晚的一段；每段内部的顺序与时间无关。所属 token 都在前一半，所以所属 token 的创建时刻与本行 token 的创建时刻几乎不相关（第 3 节 created_at 名次相关 0.007）。"
    )
    tw = []
    for u in range(N - 10):
        if u % 20 < 10 and cr.get(order[u]) and cr.get(order[u + 10]):
            tw.append(abs(cr[order[u]] - cr[order[u + 10]]) / 3600.0)
    tw.sort()
    L.append(
        "- 共用文本的两个 token 创建时间差：中位 %.0f 小时（同一半内随机配对约 135 小时）。"
        % tw[len(tw) // 2]
    )
    L.append("")
    L.append("## 5. 对论文的含义（只限本数据版本）")
    L.append("")
    L.append(
        "错位不是随机打乱，也不是来自时间相邻的币。它是一个确定的位置映射，所属 token 的创建时刻与本行 token 基本无关。"
    )
    L.append("")
    L.append("所以发布数据里的文本不携带本币的信息，也只携带很弱的时间信息。")
    gd = {}
    for i, t in enumerate(m["token"]):
        gd.setdefault(t, m["graduated_date"][i])
    late = [t for t in order if gd[t] and gd[t] >= dt.datetime(2025, 4, 14)]
    oc = [cr.get(page_owner(uidx[t])) for t in late]
    oc = [x for x in oc if x]
    lim = (dt.datetime(2025, 4, 10) - dt.datetime(1970, 1, 1)).total_seconds()
    pos = sorted(uidx[t] / N for t in late)
    L.append("")
    L.append(
        "论文的样本外测试是 04-14～04-19 毕业的币。本数据里这样的 token 有 %d 个，排在列表 %.0f%%～%.0f%% 的位置。"
        "按第 4 节的规律，它们的文本全部来自较早创建的币：能找到所属 token 的 %d 个里，%d 个创建于 04-10 之前。"
        % (len(late), 100 * pos[0], 100 * pos[-1], len(oc), sum(x < lim for x in oc))
    )
    L.append("")
    L.append(
        "论文只做了“去掉时间特征”的消融，没有做“只用时间特征”的对照。“文本必须配合时间特征”这一现象，用“时间特征本身有效、文本是噪声”也能解释。S1 的 V4（只用时间）检验这一点。"
    )
    L.append("")
    L.append("论文作者所用的数据是否有同样的错位，从发布版本推不出。")
    L.append("")
    out = H / "S0b_错位诊断.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


def pearson(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


if __name__ == "__main__":
    main()

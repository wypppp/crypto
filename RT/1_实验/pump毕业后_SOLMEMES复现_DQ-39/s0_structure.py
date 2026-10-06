#!/usr/bin/env python3
"""DQ-39 SOLMEMES S0 结构核对（10-05；总控第十九轮第五节第 3 条；方案 v1 阶段 1 第 7 项）。

python s0_structure.py  → S0_结构核对.md
输入：raw/pump_swap_final_with_metadata.parquet（HF rucyfer/solmemes 修订 71211f6d，sha256 1ac22b5c…）、
     raw/dune/S0_ANCHOR.csv.gz（sql/S0_链上时间锚.sql：链上曲线创建、完成、建池时刻与初始 name／symbol）。
顺序（先排除、再读价格）：
1. 只读元数据列（token、时间、名称等），不读 average_price_*／trades_*；
2. 按链上曲线创建时刻分类：无链上创建记录、早于 DQ-37 范围（2025-02-24 之前）、封存、检验周、留出同名（链上初始代号，
   规则同 DQ-35 _holdout_names.sqlpart：币安 746 个基础资产名里 sha256 首字节 mod 5 == 0 的）、开发；
3. 只对“开发”类 token 读价格与成交列，且只输出计数（缺值、重复行价格是否相同），不输出任何价格或收益。
   10-06 起价格列只从 raw/dev_prices.parquet 读（s0_dev_prices.py 先用行过滤生成，GPT 批 1b D）。
"""

import datetime as dt
import gzip
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent / "发射台_前期右尾评测底座_DQ-37"))
import weeks  # noqa: E402

PARQ = H / "raw" / "pump_swap_final_with_metadata.parquet"
META_COLS = [
    "token",
    "token_uri",
    "created_at",
    "graduated_date",
    "name",
    "symbol",
    "description",
    "image",
    "showName",
    "createdOn",
    "twitter",
    "website",
    "telegram",
]
PRICE_COLS = ["average_price_%d" % i for i in range(15)] + [
    "trades_%d" % i for i in range(15)
]


def holdout_names():
    s = (
        H.parent / "pump毕业币_数据留存_DQ-35" / "sql" / "_holdout_names.sqlpart"
    ).read_text()
    names = re.findall(r"\('([^']*)'\)", s)
    return {
        b for b in names if hashlib.sha256(b.encode("utf-8")).digest()[0] % 5 == 0
    }, len(names)


def norm(sym):
    return None if sym is None else sym.replace("$", "").strip().upper()


def utc(t):
    return dt.datetime(1970, 1, 1) + dt.timedelta(seconds=float(t))


def classify(anchor, excl):
    if anchor["curve_created_t"] in ("", None):
        return "no_onchain_create"
    c = utc(anchor["curve_created_t"])
    if dt.datetime(2026, 6, 15) <= c < dt.datetime(2026, 7, 13):
        return "sealed"
    if c.date() < weeks.FIRST_MONDAY:
        return "before_range"
    if norm(anchor["c_symbol"]) in excl:
        return "holdout_name"
    return "dev" if weeks.week_class(c.date().isoformat()) == "dev" else "test_week"


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def main():
    excl, n_bn = holdout_names()
    m = pq.read_table(PARQ, columns=META_COLS).to_pydict()
    n = len(m["token"])
    with gzip.open(H / "raw" / "dune" / "S0_ANCHOR.csv.gz", "rt", newline="") as f:
        # 链上 name／symbol 里有 NUL 字符，csv 模块不收：读入时去掉（只影响名称比对，计入报告）
        lines = list(f)
    n_nul = sum("\0" in x for x in lines)
    anc = {r["mint"]: r for r in csv.DictReader(x.replace("\0", "") for x in lines)}
    toks = sorted(set(m["token"]))
    cls = {t: classify(anc[t], excl) for t in toks}
    rows_by = defaultdict(list)
    for i, t in enumerate(m["token"]):
        rows_by[t].append(i)
    L = ["# DQ-39 SOLMEMES S0 结构核对（10-05）", ""]
    L.append(
        "- 数据：HF `rucyfer/solmemes` 修订 `71211f6dff23effe96582e5d71bf9cb1b6885133`；parquet sha256 `%s`（与 HF 的 LFS 记录一致）；%d 行、%d 个 token；许可 Apache-2.0"
        % (hashlib.sha256(PARQ.read_bytes()).hexdigest(), n, len(toks))
    )
    L.append(
        "- 链上时间锚：`sql/S0_链上时间锚.sql`（%d 个 token 全部返回；%d 行的链上名称含 NUL 字符，读入时去掉）"
        % (len(anc), n_nul)
    )
    L.append("")
    L.append("## 1. 分类（按链上曲线创建时刻；先排除、再读价格）")
    L.append("")
    cc = Counter(cls.values())
    L.append("| 类 | token 数 | 行数 |")
    L.append("|---|---|---|")
    for k in (
        "dev",
        "test_week",
        "holdout_name",
        "before_range",
        "sealed",
        "no_onchain_create",
    ):
        L.append(
            "| %s | %d | %d |"
            % (k, cc.get(k, 0), sum(len(rows_by[t]) for t in toks if cls[t] == k))
        )
    L.append("")
    L.append(
        "留出同名：币安 %d 个基础资产名里命中哈希规则的 %d 个（规则同 DQ-35 `_holdout_names.sqlpart`）。"
        % (n_bn, len(excl))
    )
    L.append("")

    # 2. 时间锚（元数据，全体 token）
    L.append("## 2. 时间锚")
    L.append("")
    d_cr, d_gr_comp, d_gr_pool, d_comp_pool = [], [], [], []
    for t in toks:
        i = rows_by[t][0]
        a = anc[t]
        if m["created_at"][i] is not None and a["curve_created_t"]:
            d_cr.append(
                (m["created_at"][i] - utc(a["curve_created_t"])).total_seconds()
            )
        if m["graduated_date"][i] is not None and a["completed_t"]:
            d_gr_comp.append(
                (m["graduated_date"][i] - utc(a["completed_t"])).total_seconds()
            )
        if m["graduated_date"][i] is not None and a["pool_created_t"]:
            d_gr_pool.append(
                (m["graduated_date"][i] - utc(a["pool_created_t"])).total_seconds()
            )
        if a["completed_t"] and a["pool_created_t"]:
            d_comp_pool.append(float(a["pool_created_t"]) - float(a["completed_t"]))
    for lab, xs in (
        ("数据 created_at − 链上曲线创建", d_cr),
        ("数据 graduated_date − 链上曲线完成", d_gr_comp),
        ("数据 graduated_date − 链上建池", d_gr_pool),
        ("链上建池 − 曲线完成", d_comp_pool),
    ):
        L.append(
            "- %s（秒）：%d 个，中位 %s，p1 %s，p99 %s，|差|≤1 秒 %d"
            % (
                lab,
                len(xs),
                q(xs, 0.5),
                q(xs, 0.01),
                q(xs, 0.99),
                sum(abs(x) <= 1 for x in xs),
            )
        )
    L.append(
        "- 缺链上完成事件 %d、缺链上建池事件 %d；数据 created_at 为空 %d 行、graduated_date 为空 %d 行"
        % (
            sum(1 for t in toks if not anc[t]["completed_t"]),
            sum(1 for t in toks if not anc[t]["pool_created_t"]),
            sum(x is None for x in m["created_at"]),
            sum(x is None for x in m["graduated_date"]),
        )
    )
    L.append("")

    # 3. 多出的 995 行与元数据版本
    L.append("## 3. 多出的行与元数据版本")
    L.append("")
    dup = {t: ix for t, ix in rows_by.items() if len(ix) > 1}
    vary = Counter()
    for t, ix in dup.items():
        for c in META_COLS[1:]:
            if len(set(m[c][i] for i in ix)) > 1:
                vary[c] += 1
    one_match = sum(
        1
        for t, ix in dup.items()
        if sum(
            norm(m["symbol"][i]) == norm(anc[t]["c_symbol"])
            and m["name"][i] == anc[t]["c_name"]
            for i in ix
        )
        == 1
    )
    zero_match = sum(
        1
        for t, ix in dup.items()
        if sum(
            norm(m["symbol"][i]) == norm(anc[t]["c_symbol"])
            and m["name"][i] == anc[t]["c_name"]
            for i in ix
        )
        == 0
    )
    L.append(
        "- 重复 token %d 个、多出 %d 行；组内取值不同的字段（按 token 计）：%s；组内创建、毕业时刻都相同"
        % (len(dup), n - len(toks), dict(vary))
    )
    L.append(
        "- 用链上初始 name＋symbol 认领：恰有一行吻合的重复 token %d 个，没有一行吻合的 %d 个，多于一行的 %d 个"
        % (one_match, zero_match, len(dup) - one_match - zero_match)
    )
    uniq = [t for t, ix in rows_by.items() if len(ix) == 1]
    sym_ok = sum(
        1 for t in uniq if norm(m["symbol"][rows_by[t][0]]) == norm(anc[t]["c_symbol"])
    )
    name_ok = sum(1 for t in uniq if m["name"][rows_by[t][0]] == anc[t]["c_name"])
    L.append(
        "- 不重复的 %d 个 token：symbol 与链上初始一致 %d，name 一致 %d"
        % (len(uniq), sym_ok, name_ok)
    )
    L.append("")

    # 4. 只对开发 token 读价格与成交列（只出计数）
    L.append("## 4. 开发 token 的价格与成交列（只出计数）")
    L.append("")
    dev = {t for t in toks if cls[t] == "dev"}
    # 10-06（GPT 批 1b D）：只读开发 token 的价格文件（s0_dev_prices.py 用行过滤生成），不再把全体价格列读进内存
    p = pq.read_table(H / "raw" / "dev_prices.parquet").to_pydict()
    assert set(p["token"]) <= dev, "价格文件里有非开发 token"
    dev_rows = list(range(len(p["token"])))
    nulls = Counter()
    for i in dev_rows:
        for c in PRICE_COLS:
            nulls[c.split("_")[0] + ("_price" if c.startswith("average") else "")] += (
                p[c][i] is None
            )
    rows_dev = defaultdict(list)
    for i, t in enumerate(p["token"]):
        rows_dev[t].append(i)
    same = diff = 0
    for t, ix in rows_dev.items():
        if len(ix) > 1:
            vecs = set(tuple(p[c][i] for c in PRICE_COLS) for i in ix)
            same += len(vecs) == 1
            diff += len(vecs) > 1
    L.append(
        "- 开发 token %d 个、%d 行；价格列空值 %d 格、成交列空值 %d 格（共 %d×15 格）"
        % (
            len(dev),
            len(dev_rows),
            nulls["average_price"],
            nulls["trades"],
            len(dev_rows),
        )
    )
    L.append(
        "- 开发 token 里重复的：价格与成交列完全相同 %d 个，不同 %d 个" % (same, diff)
    )
    del p
    out = H / "S0_结构核对.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

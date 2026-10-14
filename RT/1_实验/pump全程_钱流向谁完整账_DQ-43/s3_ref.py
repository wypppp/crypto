"""S3 的本机参照与核对（10-14，总控第七轮第二节；取数附录 v4）。

1. entities()：EDGE v3 的 S、G、T 边 → 并查集（DQ-26 entities.py 的规则）→ 钱包到实体代表的映射（只含多钱包实体）。
2. reference()：从逐笔明细（s3_sql 的明细导出，或构造数据）按冻结卡 §8 重算 S3 SQL 的全部输出。
   命中、自身、成熟、首笔买入直接调用冻结的 a_riskset.label、collapse。
3. compare()：SQL 输出与参照逐项比对；certain()：只凭 SQL 输出判断入选是否确定（全量时没有明细可比）。
4. t_stat()：由 G 行算 T（精确分数）。
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction

import a_riskset as A
import s3_sql as S

HUB = 200  # 扇出或对手数 >200 视为服务节点（DQ-26）


def epoch(d: dt.date) -> int:
    return calendar.timegm(d.timetuple())


CUTOFF_T = epoch(dt.date(2026, 10, 5))


# ---------- 实体归并 ----------


class DSU:
    """同 DQ-26 entities.py：代表取字典序最小的地址。"""

    def __init__(self) -> None:
        self.p: dict = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def entities(edges, cex=frozenset()) -> tuple[dict, dict]:
    """edges：EDGE v3（SGT）的行（kind, a, b, x）。返回（钱包 → 实体代表，只含多钱包实体；计数）。
    S、T 边：任一端在该类边里的不同对手 >200 或在交易所名单里，不经它合并（DQ-26 偏离②）。
    G：同一个第一笔来源的种子并成一个实体；来源扇出 >200、扇出缺失或在交易所名单里的不用。"""
    nb: dict = {"S": defaultdict(set), "T": defaultdict(set)}
    for e in edges:
        if e["kind"] in nb:
            nb[e["kind"]][e["a"]].add(e["b"])
            nb[e["kind"]][e["b"]].add(e["a"])
    hubs = {k: {a for a, s in v.items() if len(s) > HUB} for k, v in nb.items()}
    d = DSU()
    n = Counter()
    funders: dict = defaultdict(list)
    for e in edges:
        k, a, b = e["kind"], e["a"], e["b"]
        if k in ("S", "T"):
            if {a, b} & (hubs[k] | set(cex)):
                n["skip_" + k] += 1
                continue
            d.union(a, b)
            n["used_" + k] += 1
        elif k == "G":
            x = e.get("x")
            # 下载 CSV 的可空整数列会写成 463.0；按精确十进制解析，禁止截断小数。
            fanout = None if x in (None, "") else Decimal(str(x))
            if fanout is not None and (
                not fanout.is_finite()
                or fanout < 0
                or fanout != fanout.to_integral_value()
            ):
                raise ValueError("G 边扇出须为非负整数")
            if fanout is None or fanout > HUB or a in cex:
                n["skip_G"] += 1
                continue
            funders[a].append(b)
            n["used_G"] += 1
    for seeds in funders.values():
        for s in seeds[1:]:
            d.union(seeds[0], s)
    comp: dict = defaultdict(list)
    for a in list(d.p):
        comp[d.find(a)].append(a)
    out = {u: r for r, us in comp.items() if len(us) > 1 for u in us}
    n["multi_entities"] = sum(1 for us in comp.values() if len(us) > 1)
    n["mapped_wallets"] = len(out)
    return out, dict(n)


# ---------- 参照实现 ----------


def _key(r) -> tuple:
    return (int(r["slot"]), int(r["txi"]), int(r["oix"]), int(r["iix"]))


def _edges(vals, n_q):
    """最近秩法：第 q 个边界＝升序第 ⌈q·N/n_q⌉ 个值（q＝1..n_q−1）；没有值时为 None。"""
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return [None] * (n_q - 1)
    return [v[(q * n + n_q - 1) // n_q - 1] for q in range(1, n_q)]


def _bin(x, edges) -> int:
    return sum(1 for e in edges if e is not None and x > e)


def _hour_bin(ts: int) -> int:
    return ((ts % 86400) // 3600) // 6


def reference(detail, emap: dict, w0, cut, w1end, obs_cap) -> dict:
    """detail：明细行（kind T／A／E／K，字段同 s3_sql.DETAIL_COLS）。返回与 SQL 输出同结构的结果，另附精确选集。"""
    ent = lambda u: emap.get(u, u)  # noqa: E731
    cut_t, cap_t = epoch(cut), epoch(obs_cap)
    created = {
        r["mint"]: int(r["t"])
        for r in detail
        if r["kind"] == "K" and epoch(w0) <= int(r["t"]) < epoch(w1end)
    }
    is_w = {m: c < cut_t for m, c in created.items()}

    def obs_end(m):
        o = min(created[m] + 30 * 86400, CUTOFF_T, cap_t)
        return min(o, cut_t) if is_w[m] else o

    by_coin = defaultdict(list)
    for r in detail:
        if r["kind"] == "T" and r["mint"] in created:
            if created[r["mint"]] <= int(r["t"]) < obs_end(r["mint"]):
                by_coin[r["mint"]].append(r)
    buys, bid = [], 0
    for m, trs in by_coin.items():
        trs.sort(key=_key)
        sg = [int(r["amt"]) * (1 if int(r["b"]) else -1) for r in trs]
        for i, r in enumerate(trs):
            if not int(r["b"]):
                continue
            t = int(r["t"])
            cum_x = sum(sg[:i])
            cum_60 = sum(s for s, x in zip(sg, trs) if int(x["t"]) <= t - 60)
            state = ("c", int(r["r4"]) + int(r["tok"]), cum_x - cum_60, int(r["cash"]))
            buys.append(
                A.Buy(bid, ent(r["usr"]), m, t, _key(r), r["tx"], state, obs_end(m))
            )
            bid += 1
    for r in detail:
        if (
            r["kind"] == "A"
            and r["mint"] in created
            and int(r["t"]) < obs_end(r["mint"])
        ):
            buys.append(
                A.Buy(
                    bid,
                    ent(r["usr"]),
                    r["mint"],
                    int(r["t"]),
                    _key(r),
                    r["tx"],
                    ("a",),
                    obs_end(r["mint"]),
                )
            )
            bid += 1
    events = [
        A.Event(r["mint"], "grad", int(r["t"]), _key(r), r["tx"], ent(r["usr"]))
        for r in detail
        if r["kind"] == "E"
        and r["mint"] in created
        and created[r["mint"]] <= int(r["t"]) < obs_end(r["mint"])
    ]
    rows = A.collapse(A.label(buys, events, "grad", float(S.H_SEC)))
    ts_of = {b.bid: b.ts for b in buys}
    for r in rows:
        r["is_w"] = is_w[r["coin"]]
        r["ts"] = ts_of[r["bid"]]
    wc = [r for r in rows if r["is_w"] and r["state"][0] == "c"]
    ed = {
        "p": _edges([r["state"][1] for r in wc], S.DECILES),
        "q": _edges([r["state"][2] for r in wc], S.TERCILES),
        "z": _edges([r["state"][3] for r in wc], S.TERCILES),
    }
    for r in rows:
        st = r["state"]
        if st[0] == "c":
            st = (
                "c",
                _bin(st[1], ed["p"]),
                _bin(st[2], ed["q"]),
                _bin(st[3], ed["z"]),
                _hour_bin(r["ts"]),
            )
        else:
            st = ("a", -1, -1, -1, -1)
        r["state"] = st
        r["stratum"] = (r["coin"], r["day"], st, r["self"])
    return _summarize(rows, ed, created, is_w, events, emap)


def _summarize(rows, ed, created, is_w, events, emap) -> dict:
    D = S.D_UNITS
    nK: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        nK[r["stratum"]][0] += 1
        nK[r["stratum"]][1] += r["hit"]
    rw = [r for r in rows if r["is_w"]]
    r1 = [r for r in rows if not r["is_w"]]
    agg: dict = defaultdict(
        lambda: {"n": 0, "h": 0, "u": 0, "ue": 0, "m": 0, "ix": [], "fr": Fraction(0)}
    )
    for r in rw:
        n, K = nK[r["stratum"]]
        a = agg[r["entity"]]
        a["n"] += 1
        a["h"] += r["hit"]
        a["u"] += (K * D) // n
        if (K * D) % n:
            a["m"] += 1
            a["ix"].append("%d:%d" % (n, K))
        else:
            a["ue"] += (K * D) // n
        a["fr"] += Fraction(K, n)
    sha = lambda e: hashlib.sha256(e.encode()).hexdigest()  # noqa: E731
    el = {e: a for e, a in agg.items() if a["n"] >= S.MIN_ROWS}
    k_sel = (len(el) + 9) // 10
    for a in el.values():
        a["s"] = a["h"] * D - a["u"]
        a["exact"] = a["h"] - a["fr"]
    cand = sorted(
        (e for e, a in el.items() if a["s"] > 0), key=lambda e: (-el[e]["s"], sha(e))
    )
    sel = set(cand[:k_sel])
    cand_x = sorted(
        (e for e, a in el.items() if a["exact"] > 0),
        key=lambda e: (-el[e]["exact"], sha(e)),
    )
    a1: dict = defaultdict(lambda: [0, 0])
    groups: dict = defaultdict(lambda: [0, 0])
    for r in r1:
        if r["entity"] in sel:
            a1[r["entity"]][0] += 1
            a1[r["entity"]][1] += r["hit"]
            groups[r["stratum"]][0] += 1
            groups[r["stratum"]][1] += r["hit"]
    C = {
        e: (
            el[e]["n"],
            el[e]["h"],
            el[e]["m"],
            i + 1,
            el[e]["s"],
            int(e in sel),
            a1[e][0] if e in a1 else None,
            a1[e][1] if e in a1 else None,
            el[e]["h"] * D - el[e]["ue"],
            ";".join(sorted(el[e]["ix"])) or None,
        )
        for i, e in enumerate(cand)
    }
    G = sorted((s[2][0], nK[s][0], nK[s][1], m, k) for s, (m, k) in groups.items())
    reps = set(emap.values())
    N = {
        "n_el": len(el),
        "k_sel": k_sel,
        "n_cand": len(cand),
        "n_ent_w": len(agg),
        "n_rows_w": len(rw),
        "n_rows_w1": len(r1),
        "n_hit_w": sum(r["hit"] for r in rw),
        "n_hit_w1": sum(r["hit"] for r in r1),
        "n_slf": sum(r["self"] for r in rows),
        "n_amm_rows": sum(1 for r in rows if r["state"][0] == "a"),
        "chk_amm_event": sum(
            1 for r in rows if r["state"][0] == "a" and (r["hit"] or r["self"])
        ),
        "chk_state_null": 0,
        "chk_hit_and_slf": sum(1 for r in rows if r["hit"] and r["self"]),
        "n_coins_w": sum(1 for m in created if is_w[m]),
        "n_coins_w1": sum(1 for m in created if not is_w[m]),
        "n_events": len(events),
        "n_mapped_w": len({r["entity"] for r in rw if r["entity"] in reps}),
    }
    for lb, v in ed.items():
        for q, x in enumerate(v, 1):
            N["%s%d" % (lb, q)] = x
    return {
        "N": N,
        "C": C,
        "G": G,
        "sel_exact": set(cand_x[:k_sel]),
        "rows_w": rw,
        "rows_w1": r1,
    }


# ---------- SQL 输出的读入、比对与确定性 ----------


def parse_out(rows) -> dict:
    """SQL 统计量输出（s3_sql.OUT_COLS）→ 与 reference() 同结构。"""
    iv = lambda x: None if x is None or x == "" else int(x)  # noqa: E731
    N, C, G = {}, {}, []
    for r in rows:
        k = r["kind"]
        if k == "N":
            N[r["ent"]] = iv(r["a"])
        elif k == "C":
            C[r["ent"]] = (
                iv(r["a"]),
                iv(r["b"]),
                iv(r["c"]),
                iv(r["d"]),
                int(r["s"]),
                iv(r["e"]),
                iv(r["f"]),
                iv(r["g"]),
                int(r["x"]),
                r["ix"] or None,
            )
        elif k == "G":
            G.append((r["s"], iv(r["a"]), iv(r["b"]), iv(r["c"]), iv(r["d"])))
    return {"N": N, "C": C, "G": sorted(G)}


def exact_scores(C: dict) -> dict:
    """每个候选的精确得分（分数）：s_exact/D − Σ 不精确项 K/n。"""
    out = {}
    for e, v in C.items():
        x = Fraction(v[8], S.D_UNITS)
        for it in (v[9] or "").split(";"):
            if it:
                n, K = it.split(":")
                x -= Fraction(int(K), int(n))
        out[e] = x
    return out


def certain(C: dict, k_sel: int) -> list:
    """只凭 SQL 输出核对入选：用精确得分重做“得分 >0、降序、并列按 sha256、取前 k 个”，与 SQL 的入选比对。
    SQL 未输出的实体（单位制得分 ≤0）精确得分也 ≤0（单位制向下取整期望，只会高估得分）。返回差异；空＝相同。"""
    ex = exact_scores(C)
    sha = lambda e: hashlib.sha256(e.encode()).hexdigest()  # noqa: E731
    cand = sorted((e for e, x in ex.items() if x > 0), key=lambda e: (-ex[e], sha(e)))
    want = set(cand[:k_sel])
    got = {e for e, v in C.items() if v[5] == 1}
    return sorted(want ^ got)


def compare(sql: dict, ref: dict) -> list:
    """逐项比对；返回不一致的项（空＝完全一致）。"""
    diff = []
    for k in sorted(set(sql["N"]) | set(ref["N"])):
        if sql["N"].get(k) != ref["N"].get(k):
            diff.append(("N", k, sql["N"].get(k), ref["N"].get(k)))
    for e in sorted(set(sql["C"]) | set(ref["C"])):
        if sql["C"].get(e) != ref["C"].get(e):
            diff.append(("C", e, sql["C"].get(e), ref["C"].get(e)))
    if sql["G"] != ref["G"]:
        diff.append(("G", len(sql["G"]), len(ref["G"])))
    sel_sql = {e for e, v in sql["C"].items() if v[5] == 1}
    if sel_sql != ref["sel_exact"]:
        diff.append(("选集与精确算法不同", sorted(sel_sql ^ ref["sel_exact"])))
    return diff


def t_stat(G) -> Fraction:
    """一对的 T＝Σ 入选实体（命中 − 同层期望）＝Σ_层 (k − m·K/n)。"""
    return sum((Fraction(k) - Fraction(m * K, n) for _, n, K, m, k in G), Fraction(0))


def frozen_check(ref: dict) -> dict:
    """与冻结的 a_riskset 对照：select_set（浮点得分）与 set_statistic。"""
    sel_frozen = set(A.select_set(ref["rows_w"]))
    T_frozen = A.set_statistic(ref["rows_w1"], ref["sel_exact"])
    return {"select_set_same": sel_frozen == ref["sel_exact"], "T_frozen": T_frozen}

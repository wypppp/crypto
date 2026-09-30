#!/usr/bin/env python3
"""R1a v3 §3：由每个钱包锚点前的一页交易构造来源与关系，逐币打分。不看收益。

来源口径（variant）：
- full：flows.py（R0 口径）的唯一可归因流入；nonce 提款的授权人算作来源——含义是“出资或控制来源”；
- fund：同 full，但去掉含 nonce 证据的流入（纯出资，敏感性；同 09-28 audit_nonce_control_sensitivity.py）；
- light：只认系统程序的转账、建账户注资、带种子转账（v2 的 Light 层）。
主来源：非服务来源中金额最大者（平手取最近）；只有服务来源时记 "service"；无唯一来源为未解析；买家不在曲线上为程序账户。
服务集合（mode）：main = 交易所严格标签（Q_cex_all 166）∪ services.csv 宽松 ∪ R1a 画像为服务型；strict = 只用严格标签；
  tmpl = main 另加 R0 的 11 个模板化 10 SOL 出资地址（敏感性）。
关系：V1 = 与创建者直接往来，或主来源是创建者，或主来源等于创建者的主来源（非服务）；
      V2 = 与至少另一个早买者主来源相同（非服务），所有这样的买家都算相连。
强度 S = 相连 ÷（相连 + 已解析不相连）；分母 <2 时缺失。入场时刻 d5、d30 各算一次（d5 为 d30 名单的前缀）。

python build_r1a.py [--candidates]   → raw/r1a/r1a_scores.csv、raw/r1a/r1a_wallets.csv
  --candidates 另写 raw/r1a/r1a_profile_candidates.csv（R0 画像规则的候选），供 fetch_r1a.py profile
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import flows as F
from evt_decode import b58d

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "helius" / "r1a"
OUT = HERE / "raw" / "r1a"
WEEK = 7 * 86400
LIGHT_KINDS = {"sys", "sys_create", "sys_seed"}
VARIANTS = ("full", "fund", "light")
MODES = ("main", "strict", "tmpl")
DELAYS = (5, 30)


def load_page(key: str) -> list[dict] | None:
    f = RAW / f"{key}.jsonl.gz"
    if not f.exists():
        return None
    with gzip.open(f, "rt") as fh:
        return [json.loads(line) for line in fh]


def before_anchor(
    txs: list[dict], slot: int, txi: int, sig: str, gte: int
) -> list[dict]:
    """锚点交易及之前（同 slot 只取交易序号不大于锚点的；锚点交易在入场前已可见），且不早于 gte。同 R0 build_r0.py。"""
    out = []
    for x in txs:
        if (x.get("blockTime") or 0) < gte:
            continue
        s, i = x["slot"], x.get("transactionIndex")
        if (
            x["transaction"]["signatures"][0] == sig
            or s < slot
            or (s == slot and i is not None and i <= txi)
        ):
            out.append(x)
    return out


def light_inflows(x: dict, W: str) -> list[dict]:
    v = F.tx_view(x)
    agg: dict[str, int] = defaultdict(int)
    for kind, s, _ctl, d, amt, _mt in F.decode_moves(x, v):
        if d == W and s != W and kind in LIGHT_KINDS:
            agg[s] += amt
    return [
        {
            "source": s,
            "amount": a,
            "ts": x.get("blockTime"),
            "status": "unique" if F.on_curve(s) else "program",
        }
        for s, a in agg.items()
        if a >= F.MIN_LAMPORTS
    ]


def wallet_evidence(W: str, txs: list[dict]) -> dict:
    """一页内的流入（三种口径）与往来边。"""
    full, links, light = [], [], []
    for x in txs:
        a, lk = F.wallet_flows(x, W)
        full += a
        links += lk
        light += light_inflows(x, W)
    u_full = [r for r in full if r["status"] == "unique"]
    u_fund = [r for r in u_full if "nonce" not in r["evidence"].split("+")]
    u_light = [r for r in light if r["status"] == "unique"]
    return {
        "full": u_full,
        "fund": u_fund,
        "light": u_light,
        "links": links,
        "n_inflow": len(full),
    }


def primary(u: list[dict], services: set[str]) -> str | None:
    if not u:
        return None
    agg: dict[str, list] = {}
    for r in u:
        a = agg.setdefault(r["source"], [0, 0])
        a[0] += r["amount"]
        a[1] = max(a[1], r["ts"] or 0)
    ns = {s: v for s, v in agg.items() if s not in services}
    if not ns:
        return "service"
    return max(ns, key=lambda k: (ns[k][0], ns[k][1]))


def note(seen: dict, addr: str, ts: int | None) -> dict:
    """记录某来源地址在样本中首次出现的时刻（画像窗口的截止点）。"""
    o = seen.setdefault(addr, {"ts": None, "w": set(), "c": set(), "creator": False})
    if ts and (o["ts"] is None or ts < o["ts"]):
        o["ts"] = ts
    return o


def load_services() -> dict[str, set[str]]:
    strict = set(pd.read_csv(HERE / "raw" / "dune" / "Q_cex_all.csv.gz").address)
    sv = pd.read_csv(HERE / "services.csv")
    lenient = set(sv[sv["class"] == "lenient"].address) | set(
        sv[sv["class"] == "strict"].address
    )
    pf = OUT / "r1a_service_profiles.csv"
    if pf.exists():
        p = pd.read_csv(pf)
        if "service_like" in p:
            lenient |= set(p[p.service_like.astype(str) == "True"].address)
    # R0 画像中 11 个行为一致的模板化 10 SOL 出资地址（每个 100 笔中 62 笔转出、34 个接收方）：敏感性里当作服务
    prof = pd.read_csv(HERE / "results" / "service_profiles.csv")
    tmpl = set(prof[(prof.n_out == 62) & (prof.n_recipients == 34)].address)
    return {"main": strict | lenient, "strict": strict, "tmpl": strict | lenient | tmpl}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", action="store_true")
    a = ap.parse_args()
    services = load_services()
    plan = pd.read_csv(OUT / "r1a_fetch_plan.csv")
    buyers = pd.read_csv(OUT / "r1a_buyers.csv")
    pre = pd.read_csv(OUT / "r1a_coins_pre.csv").set_index("mint")

    wallets, coins = [], []
    origins_seen: dict[str, dict] = {}
    for mint, grp in plan.groupby("mint", sort=False):
        c = grp[grp.role == "creator"].iloc[0]
        C = c.W
        cpage = load_page(c.key)
        rec = {"mint": mint, "order": int(c.order), "complete": cpage is not None}
        bl = buyers[buyers.mint == mint].sort_values("rank")
        bpages = {}
        for b in bl.itertuples():
            k = f"{b.W}__{b.t_buy}"
            bpages[b.W] = load_page(k)
            rec["complete"] &= bpages[b.W] is not None
        if not rec["complete"]:
            coins.append(rec)
            continue
        cev = wallet_evidence(
            C, before_anchor(cpage, int(c.slot), int(c.txi), c.sig, int(c.t) - WEEK)
        )
        bev = {}
        for b in bl.itertuples():
            if not F.on_curve(b.W):
                bev[b.W] = None
                continue
            bev[b.W] = wallet_evidence(
                b.W,
                before_anchor(
                    bpages[b.W], int(b.slot), int(b.txi), b.sig, int(b.t_buy) - WEEK
                ),
            )
        for var in VARIANTS:
            cp = primary(cev[var], services["main"])
            if cp not in (None, "service"):
                ts = min(
                    (s["ts"] for s in cev[var] if s["source"] == cp and s["ts"]),
                    default=None,
                )
                note(origins_seen, cp, ts)["creator"] = True
        for mode in MODES:
            sv = services[mode]
            cpf = {var: primary(cev[var], sv) for var in VARIANTS}
            rows = []
            for b in bl.itertuples():
                ev = bev[b.W]
                row = {
                    "mint": mint,
                    "W": b.W,
                    "rank": b.rank,
                    "by_d5": bool(b.by_d5),
                    "mode": mode,
                }
                if ev is None:
                    row["status"] = "program_account"
                    for var in VARIANTS:
                        row[f"o_{var}"] = None
                    row["direct"] = False
                else:
                    row["status"] = "ok"
                    for var in VARIANTS:
                        row[f"o_{var}"] = primary(ev[var], sv)
                    row["direct"] = any(lk["cp"] == C for lk in ev["links"]) or any(
                        r["source"] == C for r in ev["full"]
                    )
                    if mode == "main":
                        for var in VARIANTS:
                            for s in ev[var]:
                                o = note(origins_seen, s["source"], s["ts"])
                                o["w"].add(b.W)
                                o["c"].add(mint)
                rows.append(row)
            cols = ["mint", "W", "rank", "by_d5", "mode", "status", "direct"] + [
                f"o_{v}" for v in VARIANTS
            ]
            W = pd.DataFrame(rows, columns=cols)
            if mode == "main":
                wallets += rows
            for dly in DELAYS:
                sub = W if dly == 30 else W[W.by_d5.astype(bool)]
                rec[f"n_buyers_d{dly}"] = len(sub)
                rec[f"n_program_d{dly}"] = int((sub.status == "program_account").sum())
                for var in VARIANTS:
                    o = sub[f"o_{var}"]
                    real = o.notna() & (o != "service")
                    cnt = o[real].value_counts()
                    shared = set(cnt[cnt >= 2].index)
                    cp = cpf[var]
                    v1 = (
                        sub.direct.astype(bool)
                        | (o == C)
                        | (real & (o == cp) & (cp not in (None, "service")))
                    )
                    v2 = o.isin(shared)
                    linked = v1 | v2
                    resolved_unl = o.notna() & ~linked
                    tag = f"{var}_{mode}_d{dly}"
                    rec[f"n_link_{tag}"] = int(linked.sum())
                    rec[f"n_v1_{tag}"] = int(v1.sum())
                    rec[f"n_v2_{tag}"] = int(v2.sum())
                    rec[f"n_resunl_{tag}"] = int(resolved_unl.sum())
                    rec[f"n_unres_{tag}"] = int(
                        (o.isna() & (sub.status == "ok") & ~linked).sum()
                    )
                    den = int(linked.sum() + resolved_unl.sum())
                    rec[f"S_{tag}"] = linked.sum() / den if den >= 2 else np.nan
        for dly in DELAYS:
            p = pre.loc[mint]
            rec[f"zero_d{dly}"] = p[f"zero_d{dly}"]
            rec[f"dev_buy_sol_d{dly}"] = p[f"dev_buy_sol_d{dly}"]
            rec[f"n_q_d{dly}"] = p[f"n_q_d{dly}"]
        coins.append(rec)
    Cd = pd.DataFrame(coins)
    Cd.to_csv(OUT / "r1a_scores.csv", index=False)
    pd.DataFrame(wallets).to_csv(OUT / "r1a_wallets.csv", index=False)
    print("coins", len(Cd), "complete", int(Cd.complete.sum()))
    if a.candidates:
        # R0 画像规则：≥2 个早买者的主来源；创建者主来源且为 ≥1 个早买者的主来源；样本内为 ≥20 个钱包、跨 ≥5 个币出资
        Wd = pd.DataFrame(wallets)
        prim = pd.concat(
            [Wd[["W", f"o_{v}"]].rename(columns={f"o_{v}": "o"}) for v in VARIANTS]
        )
        prim = prim[prim.o.notna() & (prim.o != "service")]
        n_w = prim.groupby("o").W.nunique()
        cand = set(n_w[n_w >= 2].index)
        cand |= {k for k, v in origins_seen.items() if v["creator"]} & set(prim.o)
        cand |= {
            k for k, v in origins_seen.items() if len(v["w"]) >= 20 and len(v["c"]) >= 5
        }
        cand -= services["main"]
        rows = [
            {"address": k, "first_ts": int(origins_seen[k]["ts"] or 0)}
            for k in sorted(cand)
            if k in origins_seen and F.on_curve(k)
        ]
        pd.DataFrame(rows).to_csv(OUT / "r1a_profile_candidates.csv", index=False)
        print("profile candidates", len(rows))


def _selfcheck() -> None:
    assert b58d("11111111111111111111111111111111") == b"\0" * 32


if __name__ == "__main__":
    _selfcheck()
    main()

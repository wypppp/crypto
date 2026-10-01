#!/usr/bin/env python3
"""DQ-26 第一步·实体归并（卡片_v1.md §2；只用 t_R 之前的信息）。

python entities.py funders  → runs/funders_for_E2.csv（候选钱包的第一笔 ≥0.05 SOL 来源，去掉交易所严格标签）
python entities.py expand   → runs/expand_candidates.csv（与候选有第 1、2 类边的非候选地址，待查是否在 R 有成交）
python entities.py build    → runs/entities_R.csv（并查集；记 sha256）

边（卡片 §2）：
  1 直接 SOL 往来：E1 的 S 行（顶层 System Program、≥0.05 SOL、回看期 07-27～08-16）；
  2 R 币直接代币转移：E1 的 T 行；
  3 共同的第一笔资金来源：两候选的第一笔 ≥0.05 SOL 来自同一个非服务节点。
     服务节点＝`Q_cex_all`（DQ-21，166 个）或 E2 中扇出 >200 的来源。
     （执行决定：第 3 类只连候选与候选——非候选地址的“第一笔来源”需要它自己的全部入账，第一步不取。）
  成员：候选钱包，加上经第 1、2 类边相连、且在 R 有成交的地址（扩展一层）。

10-01 执行偏离（看过 E1 的关系结构之后、看任何实体收益与检验期之前；记入试验记录与总入口 §3.1）：
  ①扩展成员只取满足最低活动量的 R 交易者（排名查询 W 的合格钱包）：E1 有 14 万个非候选对手地址，逐个查是否
    在 R 有成交需要另一条全量查询；只影响实体划分与“无法归因转入”的描述，不影响 G1a、G1b、G2；
  ②服务节点的扇出规则同样用于第 1、2 类边：在 E1 中某类边的不同对手地址 >200 的地址，不经它合并
    （有候选钱包向上万个地址直接发币，照字面会把空投接收者并成一个实体）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
RUNS = H / "runs"
CEX = H.parent / "pump曲线_资金关系可构造性_DQ-21" / "raw" / "dune" / "Q_cex_all.csv.gz"


def load() -> tuple[set[str], pd.DataFrame, set[str]]:
    cand = set(pd.read_csv(RUNS / "candidates_K1000.csv").usr)
    e1 = pd.read_csv(H / "raw" / "dune" / "EDGE_E1_R.csv.gz")
    cex = set(pd.read_csv(CEX).address)
    return cand, e1, cex


def first_funders(cand: set[str], e1: pd.DataFrame) -> pd.DataFrame:
    s = e1[(e1.kind == "S") & e1.to_owner.isin(cand)].copy()
    s["first_ts"] = pd.to_datetime(s.first_ts)
    s = s.sort_values(["to_owner", "first_ts", "from_owner"])
    return s.groupby("to_owner").head(1)[["to_owner", "from_owner", "first_ts", "amt"]]


class DSU:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, a: str) -> str:
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def main() -> None:
    mode = sys.argv[1]
    cand, e1, cex = load()
    ff = first_funders(cand, e1)
    if mode == "funders":
        f = ff[~ff.from_owner.isin(cex)].from_owner.drop_duplicates().sort_values()
        f.to_frame("addr").to_csv(RUNS / "funders_for_E2.csv", index=False)
        print(
            json.dumps(
                {
                    "candidates_with_inbound": int(len(ff)),
                    "first_funder_is_cex": int(ff.from_owner.isin(cex).sum()),
                    "distinct_noncex_funders": int(len(f)),
                },
                ensure_ascii=False,
            )
        )
        return
    other = pd.concat(
        [
            e1.loc[~e1.from_owner.isin(cand), "from_owner"],
            e1.loc[~e1.to_owner.isin(cand), "to_owner"],
        ]
    )
    other = other[~other.isin(cex)].drop_duplicates().sort_values()
    if mode == "expand":
        other.to_frame("usr").to_csv(RUNS / "expand_candidates.csv", index=False)
        print(json.dumps({"expand_candidates": int(len(other))}, ensure_ascii=False))
        return
    assert mode == "build"
    traders = set(
        pd.read_csv(H / "raw" / "dune" / "RANK_W_R.csv.gz", usecols=["usr"]).usr
    )
    e2 = pd.read_csv(H / "raw" / "dune" / "EDGE_E2_R.csv.gz")
    hubs = cex | set(e2.loc[e2.fanout > 200, "from_owner"])
    members = cand | (set(other) & traders)
    fan: dict[str, set[str]] = {}
    for kind in ("S", "T"):
        s = e1[e1.kind == kind]
        deg = pd.concat(
            [
                s[["from_owner", "to_owner"]].set_axis(["a", "b"], axis=1),
                s[["to_owner", "from_owner"]].set_axis(["a", "b"], axis=1),
            ]
        ).drop_duplicates()
        n = deg.groupby("a").b.size()
        fan[kind] = set(n[n > 200].index)
    d = DSU()
    for a in members:
        d.find(a)
    via: dict[str, set[str]] = {}
    for kind, a, b in e1[["kind", "from_owner", "to_owner"]].itertuples(index=False):
        if a in members and b in members and not ({a, b} & (fan[kind] | cex)):
            d.union(a, b)
            via.setdefault(a, set()).add(kind)
            via.setdefault(b, set()).add(kind)
    shared = ff[~ff.from_owner.isin(hubs)].groupby("from_owner").to_owner.apply(list)
    for addrs in shared:
        for x in addrs[1:]:
            d.union(addrs[0], x)
            via.setdefault(addrs[0], set()).add("F")
            via.setdefault(x, set()).add("F")
    rows = []
    for a in sorted(members):
        rows.append(
            {
                "usr": a,
                "entity": d.find(a),
                "is_candidate": a in cand,
                "via": "".join(sorted(via.get(a, set()))),
            }
        )
    ent = pd.DataFrame(rows)
    # 只保留含候选钱包的实体（与候选不相连的扩展地址不是成员）
    ent = ent[ent.entity.isin(ent.loc[ent.is_candidate, "entity"])].reset_index(
        drop=True
    )
    ent.to_csv(RUNS / "entities_R.csv", index=False)
    size = ent.groupby("entity").usr.size()
    summ = {
        "members": int(len(ent)),
        "candidates": int(ent.is_candidate.sum()),
        "expanded_members": int((~ent.is_candidate).sum()),
        "entities_with_candidate": int(ent[ent.is_candidate].entity.nunique()),
        "entity_size_max": int(size.max()),
        "entities_multi_wallet": int((size > 1).sum()),
        "hubs_funder": int(len(hubs)),
        "service_nodes_S": int(len(fan["S"])),
        "service_nodes_T": int(len(fan["T"])),
        "candidates_as_service_node": int(len((fan["S"] | fan["T"]) & cand)),
        "sha256": hashlib.sha256((RUNS / "entities_R.csv").read_bytes()).hexdigest(),
    }
    (RUNS / "entities_R_summary.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=1)
    )
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

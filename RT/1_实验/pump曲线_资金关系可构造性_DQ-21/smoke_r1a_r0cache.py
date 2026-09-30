#!/usr/bin/env python3
"""R1a v3 §9 第 2 步：解析冒烟（0 credits）。用 R0 缓存的 10 个币（不进 R1a 主分析），
把 build_r1a.py 的一页解析与 09-28 审计脚本（audit_onepage/audit_nonce_control_sensitivity 的 primary）逐钱包对照。

python smoke_r1a_r0cache.py → 过程/R1a_解析冒烟.json
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import build_r1a as B
import flows as F
from audit_nonce_control_sensitivity import primary as audit_primary

HERE = Path(__file__).resolve().parent
OUT = HERE / "过程" / "R1a_解析冒烟.json"


def first_page(W: str, t: int) -> list[dict] | None:
    f = HERE / "raw" / "helius" / f"back__{W}__{t}.jsonl.gz"
    if not f.exists():
        return None
    with gzip.open(f, "rt") as fh:
        return [json.loads(line) for line in itertools.islice(fh, 100)]


def main() -> None:
    q = pd.read_csv(HERE / "raw" / "dune" / "Q_buyers.csv.gz")
    q["t"] = (
        pd.to_datetime(q.ts.str.replace(" UTC", ""), utc=True).astype("int64") // 10**9
    )
    strict = set(
        pd.read_csv(HERE / "services.csv").query("`class` == 'strict'").address
    )
    inf = pd.read_csv(HERE / "results" / "all_inflows.csv.gz")
    inf = inf[(inf.role == "buyer") & (inf.status == "unique")]
    mints = sorted(
        q.mint.unique(), key=lambda m: hashlib.sha256(m.encode()).hexdigest()
    )[:10]
    stats, rows = Counter(), []
    for mint in mints:
        c = q[(q.kind == "create") & (q.mint == mint)].iloc[0]
        cp = first_page(c.usr, int(c.t))
        stats["creator_page"] += cp is not None
        for b in q[
            (q.kind == "buy") & (q.mint == mint) & (q.buyer_rank <= 30)
        ].itertuples():
            pg = first_page(b.usr, int(b.t))
            if pg is None:
                stats["missing_page"] += 1
                continue
            if not F.on_curve(b.usr):
                stats["program_account"] += 1
                continue
            txs = B.before_anchor(
                pg, int(b.slot), int(b.txi), b.tx_id, int(b.t) - B.WEEK
            )
            ev = B.wallet_evidence(b.usr, txs)
            mine = B.primary(ev["full"], strict)
            sigs = {x["transaction"]["signatures"][0] for x in pg}
            f = inf[(inf.mint == mint) & (inf.W == b.usr) & inf.sig.isin(sigs)]
            ref = audit_primary(f.to_dict("records"), strict, False)
            ref_fund = audit_primary(f.to_dict("records"), strict, True)
            mine_fund = B.primary(ev["fund"], strict)
            stats["buyers"] += 1
            stats["full_same"] += mine == ref
            stats["fund_same"] += mine_fund == ref_fund
            stats["light_resolved"] += B.primary(ev["light"], strict) is not None
            stats["full_resolved"] += mine is not None
            if mine != ref or mine_fund != ref_fund:
                rows.append(
                    {
                        "mint": mint,
                        "W": b.usr,
                        "mine": mine,
                        "ref": ref,
                        "mine_fund": mine_fund,
                        "ref_fund": ref_fund,
                    }
                )
    out = {"coins": mints, "stats": dict(stats), "mismatches": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(
        json.dumps(
            {"stats": dict(stats), "n_mismatch": len(rows), "first": rows[:5]},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()

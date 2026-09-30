#!/usr/bin/env python3
"""R1a v3 §9 第 1 步：资金/控制关系的原件病例追溯（02 §10.3），0 credits。

从 R0 缓存（raw/helius/back__W__t.jsonl.gz 的第一页，≤100 笔，即 v3 的“一页”口径）按边界类型各取样例，
对每笔带来流入的交易，用按一手规范独立写的解码（Solana System Program、SPL Token、Stake Program 的指令布局与
账户顺序）列出指向 W 的资金移动及各账户的角色，与 flows.py 的归因（来源、控制者、证据、状态）逐笔对照。

python trace_r1a_cases.py → 过程/R1a_原件病例追溯.json（逐例原始对照，供 .md 引用）
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

import flows as F
from evt_decode import account_keys, b58d

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "helius"
OUT = HERE / "过程" / "R1a_原件病例追溯.json"

SYSTEM = "11111111111111111111111111111111"
TOKEN = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}
STAKE = "Stake11111111111111111111111111111111111111"

# System Program（solana-program system_instruction.rs）：u32 判别值 → 名称、账户角色、lamports 偏移
SYS_SPEC = {
    0: ("CreateAccount", ["funding(signer)", "new_account(signer)"], 4),
    2: ("Transfer", ["from(signer)", "to"], 4),
    3: (
        "CreateAccountWithSeed",
        ["funding(signer)", "created", "base(signer,opt)"],
        None,
    ),
    5: (
        "WithdrawNonceAccount",
        [
            "nonce_account",
            "recipient",
            "recent_blockhashes",
            "rent",
            "nonce_authority(signer)",
        ],
        4,
    ),
    11: ("TransferWithSeed", ["from(derived)", "base(signer)", "to"], 4),
}
# SPL Token（token/program/src/instruction.rs）：u8 判别值
TOK_SPEC = {
    3: ("Transfer", ["source", "destination", "authority(signer)"]),
    12: ("TransferChecked", ["source", "mint", "destination", "authority(signer)"]),
    9: ("CloseAccount", ["account", "destination", "owner(signer)"]),
}
# Stake Program：u32 判别值 4 = Withdraw
STAKE_SPEC = {
    4: (
        "Withdraw",
        [
            "stake_account",
            "recipient",
            "clock",
            "stake_history",
            "withdraw_authority(signer)",
        ],
    )
}


def u64(b: bytes, o: int) -> int:
    return int.from_bytes(b[o : o + 8], "little")


def instrs(x):
    keys = account_keys(x)
    top = x["transaction"]["message"]["instructions"]
    inner = {
        g["index"]: g["instructions"] for g in x["meta"].get("innerInstructions") or []
    }
    for i, ins in enumerate(top):
        yield f"{i}", keys[ins["programIdIndex"]], ins["accounts"], ins["data"]
        for j, sub in enumerate(inner.get(i, [])):
            yield f"{i}.{j}", keys[sub["programIdIndex"]], sub["accounts"], sub["data"]


def spec_moves(x, W: str) -> list[dict]:
    """按规范独立解码：列出资金去向为 W（系统账户或 W 名下代币账户）的指令，并给出各账户角色。"""
    keys = account_keys(x)
    owner = {}
    for tb in (x["meta"].get("preTokenBalances") or []) + (
        x["meta"].get("postTokenBalances") or []
    ):
        owner[tb["accountIndex"]] = tb.get("owner")

    def own(i):
        return owner.get(i) or keys[i]

    out = []
    for pos, prog, acc, data in instrs(x):
        try:
            d = b58d(data)
        except ValueError:
            continue
        rec = None
        if prog == SYSTEM and len(d) >= 4:
            tag = int.from_bytes(d[:4], "little")
            if tag in SYS_SPEC:
                name, roles, off = SYS_SPEC[tag]
                if tag == 3:
                    n = u64(d, 36)
                    lam = u64(d, 44 + n)
                else:
                    lam = u64(d, off)
                dest = {0: 1, 2: 1, 3: 1, 5: 1, 11: 2}[tag]
                rec = (name, roles, dest, lam, "SOL")
        elif prog in TOKEN and d:
            tag = d[0]
            if tag in TOK_SPEC:
                name, roles = TOK_SPEC[tag]
                dest = {3: 1, 12: 2, 9: 1}[tag]
                lam = u64(d, 1) if tag != 9 else x["meta"]["preBalances"][acc[0]]
                rec = (name, roles, dest, lam, "token/lamports")
        elif prog == STAKE and len(d) >= 12:
            tag = int.from_bytes(d[:4], "little")
            if tag in STAKE_SPEC:
                name, roles = STAKE_SPEC[tag]
                rec = (name, roles, 1, u64(d, 4), "SOL")
        if rec is None:
            continue
        name, roles, dest, lam, unit = rec
        if dest >= len(acc) or own(acc[dest]) != W:
            continue
        out.append(
            {
                "pos": pos,
                "program": {SYSTEM: "System", STAKE: "Stake"}.get(prog, "SPL Token"),
                "instruction": name,
                "accounts": {
                    roles[k]: keys[a] + (f" (owner {own(a)})" if a in owner else "")
                    for k, a in enumerate(acc[: len(roles)])
                },
                "amount": lam,
                "unit": unit,
            }
        )
    return out


def first_page(W: str, t: int) -> list[dict] | None:
    f = RAW / f"back__{W}__{t}.jsonl.gz"
    if not f.exists():
        return None
    with gzip.open(f, "rt") as fh:
        return [json.loads(line) for line in itertools.islice(fh, 100)]


def hkey(*a) -> str:
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()


def pick(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return (
        df.assign(_h=[hkey(r.mint, r.W, r.sig) for r in df.itertuples()])
        .sort_values("_h")
        .head(n)
    )


def main() -> None:
    inf = pd.read_csv(HERE / "results" / "all_inflows.csv.gz")
    inf = inf[inf.role == "buyer"]
    wal = pd.read_csv(HERE / "results" / "all_wallets.csv")
    tbuy = {(r.mint, r.W): int(r.t_buy) for r in wal.itertuples()}
    cex = set(pd.read_csv(HERE / "raw" / "dune" / "Q_cex_all.csv.gz").address)
    svc = pd.read_csv(HERE / "services.csv")
    lenient = set(svc[svc["class"] == "lenient"].address)
    prof = pd.read_csv(HERE / "results" / "service_profiles.csv")
    template = set(prof[(prof.n_out == 62) & (prof.n_recipients == 34)].address)

    # 只保留落在第一页里的流入（每个钱包只读一次缓存）
    sigs = {}
    for (mint, W), t in tbuy.items():
        pg = first_page(W, t)
        if pg is not None:
            sigs[(mint, W)] = {x["transaction"]["signatures"][0] for x in pg}
    inf = inf[[r.sig in sigs.get((r.mint, r.W), ()) for r in inf.itertuples()]]

    types = [
        (
            "普通系统转账",
            inf[
                (inf.status == "unique")
                & (inf.evidence == "sys")
                & ~inf.source.isin(cex | lenient | template)
            ],
            2,
        ),
        (
            "持久化 nonce 提款",
            inf[(inf.status == "unique") & (inf.evidence == "nonce")],
            3,
        ),
        ("wSOL 代币转账", inf[(inf.status == "unique") & (inf.evidence == "wsol")], 2),
        (
            "建账户注资（含 wSOL）",
            inf[(inf.status == "unique") & inf.evidence.str.contains("sys_create")],
            1,
        ),
        ("关闭账户转余额", inf[inf.evidence == "close"], 2),
        (
            "余额证据·唯一",
            inf[(inf.status == "unique") & (inf.evidence == "balance")],
            2,
        ),
        (
            "余额证据·多方",
            inf[(inf.status == "multiple") & (inf.evidence == "balance")],
            1,
        ),
        (
            "程序账户（PDA）来源·系统转账",
            inf[(inf.status == "program") & (inf.evidence == "sys")],
            1,
        ),
        ("交易所（严格标签）", inf[(inf.status == "unique") & inf.source.isin(cex)], 2),
        (
            "宽松画像服务（如终端）",
            inf[(inf.status == "unique") & inf.source.isin(lenient)],
            1,
        ),
        (
            "模板化 10 SOL 出资地址",
            inf[(inf.status == "unique") & inf.source.isin(template)],
            1,
        ),
    ]
    cases = []
    for label, df, n in types:
        for r in pick(df, n).itertuples():
            t = tbuy[(r.mint, r.W)]
            pg = first_page(r.W, t)
            x = next(x for x in pg if x["transaction"]["signatures"][0] == r.sig)
            got, _ = F.wallet_flows(x, r.W)
            cases.append(
                {
                    "type": label,
                    "mint": r.mint,
                    "W": r.W,
                    "sig": r.sig,
                    "slot": int(r.slot),
                    "signers": x["transaction"]["message"]["accountKeys"][
                        : x["transaction"]["message"]["header"]["numRequiredSignatures"]
                    ],
                    "spec_moves": spec_moves(x, r.W),
                    "flows": [
                        {
                            k: g[k]
                            for k in (
                                "source",
                                "control",
                                "amount",
                                "evidence",
                                "status",
                            )
                        }
                        for g in got
                    ],
                    "W_balance_change": x["meta"]["postBalances"][
                        account_keys(x).index(r.W)
                    ]
                    - x["meta"]["preBalances"][account_keys(x).index(r.W)]
                    if r.W in account_keys(x)
                    else None,
                    "programs": sorted({p for _, p, _, _ in instrs(x)}),
                }
            )
    # 质押账户中转：页内任一交易含 Stake Withdraw 且收款人是 W
    stake_cases = []
    for r in pick(
        wal[wal.status != "program_account"].assign(sig=""), 400
    ).itertuples():
        pg = first_page(r.W, int(r.t_buy)) or []
        for x in pg:
            sm = [m for m in spec_moves(x, r.W) if m["program"] == "Stake"]
            if sm:
                got, _ = F.wallet_flows(x, r.W)
                stake_cases.append(
                    {
                        "type": "质押账户中转",
                        "mint": r.mint,
                        "W": r.W,
                        "sig": x["transaction"]["signatures"][0],
                        "signers": x["transaction"]["message"]["accountKeys"][
                            : x["transaction"]["message"]["header"][
                                "numRequiredSignatures"
                            ]
                        ],
                        "spec_moves": sm,
                        "flows": [
                            {
                                k: g[k]
                                for k in (
                                    "source",
                                    "control",
                                    "amount",
                                    "evidence",
                                    "status",
                                )
                            }
                            for g in got
                        ],
                        "programs": sorted({p for _, p, _, _ in instrs(x)}),
                    }
                )
                break
        if len(stake_cases) >= 1:
            break
    cases += stake_cases
    # 程序账户买家（买家地址不在曲线上）与页内无唯一来源的买家
    pa = pick(wal[wal.status == "program_account"].assign(sig=""), 1)
    for r in pa.itertuples():
        cases.append(
            {
                "type": "程序账户买家",
                "mint": r.mint,
                "W": r.W,
                "on_curve": F.on_curve(r.W),
            }
        )
    nu = pick(wal[wal.status == "partial_no_candidate"].assign(sig=""), 1)
    for r in nu.itertuples():
        pg = first_page(r.W, int(r.t_buy)) or []
        allin = [g for x in pg for g in F.wallet_flows(x, r.W)[0]]
        cases.append(
            {
                "type": "页内无唯一来源",
                "mint": r.mint,
                "W": r.W,
                "page_tx": len(pg),
                "inflows_in_page": [
                    {k: g[k] for k in ("source", "evidence", "status")} for g in allin
                ][:10],
            }
        )
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n")
    print(len(cases), "cases →", OUT)


if __name__ == "__main__":
    main()

"""DQ-21 §4：从完整交易（Helius `json` 编码）中提取某个钱包 W 的 SOL 流入与往来边，并做来源归因。

W 的 SOL = 原生 SOL + W 名下代币账户（按 pre/postTokenBalances 的 owner 合并）。
每笔流入记录一行（交易 × 来源），证据与状态：
- 指令证据（含内层指令）：系统转账 / 带种子转账 / 建账户注资（sys）、wSOL 代币转账（wsol）、关闭账户把余额转给 W（close）。
  这些指令都要求转出方或被关闭账户的所有者签名；转出方是非 PDA 地址 → unique，是 PDA → program。
- 余额证据：该交易没有任何指向 W 的指令流入，而 W 按所有者合并后净增加 >= 0.05 SOL 时才用。
  付费方先加回手续费；只有一个非 PDA 所有者的净减少 >= W 净增加的 95% → unique；
  不止一个 → multiple；没有非 PDA、但有 PDA 满足 → program；都没有 → payer_only。
只有 unique 进入 V1–V3；付费方与签名者另存，不默认等于出资方。每个（交易, 来源）累计 >= 0.05 SOL 才记。
另记 W 与非 PDA 地址之间的 SOL 转出、以及任何代币的转入/转出（links），用于创建者往来（V1 ①）。
"""
from evt_decode import account_keys, b58d

SYS = "11111111111111111111111111111111"
TOKEN_PROGS = {"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}
WSOL = "So11111111111111111111111111111111111111112"
MIN_LAMPORTS = 50_000_000

# ---- ed25519：地址是否在曲线上（不在 = PDA，由程序控制） ----
_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_ONCURVE = {}


def on_curve(addr):
    if addr in _ONCURVE:
        return _ONCURVE[addr]
    b = b58d(addr).rjust(32, b"\0")
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P:
        ok = False
    else:
        y2 = y * y % _P
        u, v = (y2 - 1) % _P, (_D * y2 + 1) % _P
        x2 = u * pow(v, _P - 2, _P) % _P
        ok = x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1
    _ONCURVE[addr] = ok
    return ok


def _instructions(x):
    """顶层与内层指令：(program, [账户下标], data bytes)。"""
    keys = account_keys(x)
    top = x["transaction"]["message"]["instructions"]
    inner = {g["index"]: g["instructions"] for g in x["meta"].get("innerInstructions") or []}
    for i, ins in enumerate(top):
        yield keys[ins["programIdIndex"]], ins["accounts"], ins["data"]
        for sub in inner.get(i, []):
            yield keys[sub["programIdIndex"]], sub["accounts"], sub["data"]


def _u64(b, o):
    return int.from_bytes(b[o:o + 8], "little")


def tx_view(x):
    keys = account_keys(x)
    hdr = x["transaction"]["message"]["header"]
    owner, mint = {}, {}
    for tb in (x["meta"].get("preTokenBalances") or []) + (x["meta"].get("postTokenBalances") or []):
        owner[tb["accountIndex"]] = tb.get("owner")
        mint[tb["accountIndex"]] = tb.get("mint")
    pre, post = x["meta"]["preBalances"], x["meta"]["postBalances"]
    agg = {}
    for i, k in enumerate(keys):
        o = owner.get(i) or k
        d = post[i] - pre[i] + (x["meta"]["fee"] if i == 0 else 0)
        agg[o] = agg.get(o, 0) + d
    return {"keys": keys, "signers": keys[:hdr["numRequiredSignatures"]], "payer": keys[0],
            "owner": lambda i: owner.get(i) or keys[i], "mint": mint, "pre": pre, "agg": agg}


def decode_moves(x, v):
    """解码 SOL 与代币移动：(kind, src_owner, dst_owner, amount, mint)。"""
    out = []
    for prog, acc, data in _instructions(x):
        try:
            d = b58d(data)
        except ValueError:
            continue
        if prog == SYS and len(d) >= 12:
            tag = int.from_bytes(d[:4], "little")
            if tag in (0, 2):          # create_account / transfer：from = a0, to = a1
                src, dst = acc[0], acc[1]
            elif tag == 11 and len(acc) >= 3:   # transfer_with_seed：from = a0, to = a2
                src, dst = acc[0], acc[2]
            else:
                continue
            out.append(("sys", v["owner"](src), v["owner"](dst), _u64(d, 4), WSOL))
        elif prog in TOKEN_PROGS and d:
            tag = d[0]
            if tag == 3 and len(acc) >= 3 and len(d) >= 9:
                src, dst, mt = acc[0], acc[1], v["mint"].get(acc[0]) or v["mint"].get(acc[1])
            elif tag == 12 and len(acc) >= 4 and len(d) >= 9:
                src, dst, mt = acc[0], acc[2], v["keys"][acc[1]]
            elif tag == 9 and len(acc) >= 3:   # close：账户余额（lamports）转给 destination
                out.append(("close", v["owner"](acc[0]), v["owner"](acc[1]), v["pre"][acc[0]], WSOL))
                continue
            else:
                continue
            out.append(("wsol" if mt == WSOL else "token", v["owner"](src), v["owner"](dst), _u64(d, 1), mt))
    return out


def wallet_flows(x, W):
    """返回 (inflows, links)。inflows：来源归因后的流入；links：W 与非 PDA 地址之间的 SOL 转出与代币往来。"""
    v = tx_view(x)
    base = {"sig": x["transaction"]["signatures"][0], "slot": x["slot"], "txi": x.get("transactionIndex"),
            "ts": x.get("blockTime"), "payer": v["payer"], "signers": "|".join(v["signers"]),
            "w_signed": W in v["signers"]}
    moves = decode_moves(x, v)
    by_src, links = {}, []
    for kind, s, d, amt, mt in moves:
        if s == d:
            continue
        if d == W and kind in ("sys", "wsol", "close"):
            k = by_src.setdefault(s, {"amount": 0, "ev": set()})
            k["amount"] += amt
            k["ev"].add(kind)
        if W in (s, d):
            cp = d if s == W else s
            if on_curve(cp) and (kind == "token" or s == W):
                links.append({**base, "dir": "out" if s == W else "in", "cp": cp, "kind": kind, "mint": mt, "amount": amt})
    inflows = []
    for s, k in by_src.items():
        if k["amount"] < MIN_LAMPORTS:
            continue
        inflows.append({**base, "source": s, "amount": k["amount"], "evidence": "+".join(sorted(k["ev"])),
                        "status": "unique" if on_curve(s) else "program"})
    if not by_src:
        dW = v["agg"].get(W, 0)
        if dW >= MIN_LAMPORTS:
            neg = {o: a for o, a in v["agg"].items() if o != W and a < 0}
            full = [o for o, a in neg.items() if a <= -0.95 * dW]      # 单独就能覆盖 W 的净增加
            full_on = [o for o in full if on_curve(o)]
            part_on = [o for o in neg if on_curve(o) and neg[o] <= -MIN_LAMPORTS]
            if len(full_on) == 1:
                st, src = "unique", full_on[0]
            elif len(full_on) > 1:
                st, src = "multiple", "|".join(sorted(full_on))
            elif full:                                                  # 只有 PDA 能覆盖
                st, src = "program", "|".join(sorted(full))
            elif part_on:                                               # 几方分摊，无法唯一归因
                st, src = "multiple", "|".join(sorted(part_on + [o for o in neg if not on_curve(o)]))
            elif neg:
                st, src = "program", "|".join(sorted(neg))
            else:
                st, src = "payer_only", v["payer"]
            inflows.append({**base, "source": src, "amount": dW, "evidence": "balance", "status": st})
    return inflows, links

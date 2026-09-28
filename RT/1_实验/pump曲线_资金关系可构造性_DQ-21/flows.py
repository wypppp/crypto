"""DQ-21 §4：从完整交易（Helius `json` 编码）中提取某个钱包 W 的 SOL 流入与往来边，并做来源归因。

W 的 SOL = 原生 SOL + W 名下代币账户（按 pre/postTokenBalances 的 owner 合并）。
09-28 审计注意：历史 R0 口径把 nonce 提款授权人记作 source；这只能证明提款控制权，
不能证明 nonce 账户原始注资方或经济所有权。此文件保留 R0 可复算口径，R1 不得直接
把该分支当作“同一资金来源”；见 3_审计/2026-09-28_DQ21_S0结果复核/执行方独立意见.md。
每笔流入记录一行（交易 × 来源），证据与状态：
- 指令证据（含内层指令）：系统转账 / 建账户注资 / 带种子建账户（sys）、带种子转账（来源记 base 签名者）、
  nonce 账户提款（历史 R0 把授权人记作来源；实际只证明控制权）、wSOL 代币转账（wsol）、关闭账户把余额转给 W（close）。
  来源（source）= 资产的经济所有者：系统账户是转出方本身；带种子账户是 base；nonce 账户是授权人；
  SPL 转账与关闭账户是源代币账户 / 被关闭账户的 owner（取自 pre/postTokenBalances，缺失时退回授权人）。
  指令的签名授权人另存为 control，只用于控制关系与服务节点诊断。来源是非 PDA → unique，是 PDA → program。
- 余额证据：该交易没有任何指向 W 的指令流入，而 W 按所有者合并后净增加 >= 0.05 SOL 时才用。
  付费方先加回手续费；只有一个非 PDA 所有者的净减少 >= W 净增加的 95%，并且它是该交易的签名者 → unique；
  它不是签名者（钱由别人控制的账户转出）或不止一个 → multiple；没有非 PDA、但有 PDA 满足 → program；都没有 → payer_only。
09-27 R0a 核验第 1 轮后修改（过程/R0a_归因核验.md）：原版未解码 nonce 提款，按余额把来源记成 nonce 账户本身（应为授权人）。
09-27 R0b 后：系统指令的证据标签细分为 sys（转账）/ sys_create / sys_seed / nonce，归因不变，用于报告漏边率。
09-27 R0a 复核后修改：第 1 轮修改时把 SPL 转账与关闭账户的来源也改成了授权人，这超出了发现的错误；
  委托转账中授权人可能只是代理或终端。改回资产所有者为来源，授权人另存（control）。
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
            "owner": lambda i: owner.get(i) or keys[i], "tok_owner": owner, "mint": mint, "pre": pre, "agg": agg}


def decode_moves(x, v):
    """解码 SOL 与代币移动：(kind, 来源=经济所有者, 控制者=签名授权人, dst_owner, amount, mint)。"""
    out = []
    for prog, acc, data in _instructions(x):
        try:
            d = b58d(data)
        except ValueError:
            continue
        if prog == SYS and len(d) >= 12:
            tag = int.from_bytes(d[:4], "little")
            amt = _u64(d, 4)
            if tag in (0, 2):          # create_account / transfer：from = a0（签名），to = a1
                src, dst = acc[0], acc[1]
            elif tag == 11 and len(acc) >= 3:   # transfer_with_seed：from = a0（派生），base = a1（签名），to = a2
                src, dst = acc[1], acc[2]
            elif tag == 5 and len(acc) >= 5:    # withdraw_nonce_account：nonce = a0，to = a1，authority = a4（签名）
                src, dst = acc[4], acc[1]
            elif tag == 3 and len(acc) >= 2 and len(d) >= 44:   # create_account_with_seed：from = a0（签名），to = a1
                n = _u64(d, 36)
                if len(d) < 44 + n + 8:
                    continue
                src, dst, amt = acc[0], acc[1], _u64(d, 44 + n)
            else:
                continue
            kind = {2: "sys", 0: "sys_create", 3: "sys_create", 11: "sys_seed", 5: "nonce"}[tag]   # 只细分证据标签
            out.append((kind, v["keys"][src], v["keys"][src], v["owner"](dst), amt, WSOL))
        elif prog in TOKEN_PROGS and d:
            tag = d[0]
            if tag == 3 and len(acc) >= 3 and len(d) >= 9:      # transfer：source, dest, authority（签名）
                srcacc, auth, dst, mt = acc[0], acc[2], acc[1], v["mint"].get(acc[0]) or v["mint"].get(acc[1])
            elif tag == 12 and len(acc) >= 4 and len(d) >= 9:   # transfer_checked：source, mint, dest, authority
                srcacc, auth, dst, mt = acc[0], acc[3], acc[2], v["keys"][acc[1]]
            elif tag == 9 and len(acc) >= 3:   # close：account, destination, authority；账户余额（lamports）转给 destination
                econ = v["tok_owner"].get(acc[0]) or v["keys"][acc[2]]
                out.append(("close", econ, v["keys"][acc[2]], v["owner"](acc[1]), v["pre"][acc[0]], WSOL))
                continue
            else:
                continue
            econ = v["tok_owner"].get(srcacc) or v["keys"][auth]
            out.append(("wsol" if mt == WSOL else "token", econ, v["keys"][auth], v["owner"](dst), _u64(d, 1), mt))
    return out


def wallet_flows(x, W):
    """返回 (inflows, links)。inflows：来源归因后的流入；links：W 与非 PDA 地址之间的 SOL 转出与代币往来。"""
    v = tx_view(x)
    base = {"sig": x["transaction"]["signatures"][0], "slot": x["slot"], "txi": x.get("transactionIndex"),
            "ts": x.get("blockTime"), "payer": v["payer"], "signers": "|".join(v["signers"]),
            "w_signed": W in v["signers"]}
    moves = decode_moves(x, v)
    by_src, links = {}, []
    for kind, s, ctl, d, amt, mt in moves:
        if s == d:
            continue
        if d == W and kind in ("sys", "sys_create", "sys_seed", "nonce", "wsol", "close"):
            k = by_src.setdefault(s, {"amount": 0, "ev": set(), "ctl": set()})
            k["amount"] += amt
            k["ev"].add(kind)
            k["ctl"].add(ctl)
        if W in (s, d):
            cp = d if s == W else s
            if on_curve(cp) and (kind == "token" or s == W):   # SOL 转出（任何 sys 类）与代币往来
                links.append({**base, "dir": "out" if s == W else "in", "cp": cp, "kind": kind, "mint": mt, "amount": amt})
    inflows = []
    for s, k in by_src.items():
        if k["amount"] < MIN_LAMPORTS:
            continue
        inflows.append({**base, "source": s, "control": "|".join(sorted(k["ctl"])), "amount": k["amount"],
                        "evidence": "+".join(sorted(k["ev"])), "status": "unique" if on_curve(s) else "program"})
    if not by_src:
        dW = v["agg"].get(W, 0)
        if dW >= MIN_LAMPORTS:
            neg = {o: a for o, a in v["agg"].items() if o != W and a < 0}
            full = [o for o, a in neg.items() if a <= -0.95 * dW]      # 单独就能覆盖 W 的净增加
            full_on = [o for o in full if on_curve(o)]
            signed = set(v["signers"])
            part_on = [o for o in neg if on_curve(o) and neg[o] <= -MIN_LAMPORTS]
            if len(full_on) == 1 and full_on[0] in signed:
                st, src = "unique", full_on[0]
            elif len(full_on) == 1:                                     # 余额从非签名账户转出，控制者不明
                st, src = "multiple", "|".join([full_on[0]] + sorted(signed - {W}))
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
            inflows.append({**base, "source": src, "control": src, "amount": dW, "evidence": "balance", "status": st})
    return inflows, links

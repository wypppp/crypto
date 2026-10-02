"""DQ-21 flows.py 的修正版（代码审计 10-03 第 10 处）。原 flows.py 不改；F114、F120 按总控第十轮第 6 条只修代码、不重跑。

第 10 处：关闭代币账户（CloseAccount）时，原版把“交易开始时”的余额当作转给目标的金额；同一交易里先转出一部分再关闭，
会重复计算（审计反例：wSOL 账户 1.002 SOL，先转 0.9 再关闭，真实流入 1.002，原版 1.902）。
v2 在 decode_moves 里按指令顺序维护各账户 lamports：系统转账与带种子转账、wSOL 代币转账都更新余额，关闭时取当时余额。
不在这两类程序里的 lamports 变动（其他程序直接改 PDA 余额）仍看不到，关闭金额只在这些变动发生时才会偏。
wallet_flows 逐字照抄原版，只是调用本模块的 decode_moves。
"""

from flows import MIN_LAMPORTS, SYS, TOKEN_PROGS, WSOL, _instructions, _u64, b58d, on_curve, tx_view


def decode_moves(x, v):
    """解码 SOL 与代币移动：(kind, 来源=经济所有者, 控制者=签名授权人, dst_owner, amount, mint)。
    v2：按指令顺序维护各账户的 lamports（bal），关闭账户转出的是关闭时的余额，而不是交易开始时的余额。"""
    out = []
    bal = list(v["pre"])  # v2（审计第 10 处）
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
            bal[acc[0]] -= amt  # v2：四种指令的 lamports 都从 a0 转到目标账户
            bal[acc[1] if tag != 11 else acc[2]] += amt
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
                amt_close = max(bal[acc[0]], 0)  # v2：关闭时的余额
                bal[acc[1]] += amt_close
                bal[acc[0]] = 0
                out.append(("close", econ, v["keys"][acc[2]], v["owner"](acc[1]), amt_close, WSOL))
                continue
            else:
                continue
            if mt == WSOL:  # v2：原生 SOL 代币账户的转账同时移动 lamports
                bal[srcacc] -= _u64(d, 1)
                bal[dst] += _u64(d, 1)
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

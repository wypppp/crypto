"""核验：PumpSwap 事件池储备是交易前还是交易后；曲线 TradeEvent 储备时点；各项费用是否叠加。"""
import json, struct, subprocess, time
RPC = "https://api.mainnet-beta.solana.com"
AMM, PUMP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
TAG = bytes.fromhex("e445a52e51cb9a1d")
DISC = {bytes([103,244,82,31,44,245,119,119]): "buy", bytes([62,47,55,10,165,3,220,42]): "sell",
        bytes([189,219,127,211,78,230,97,238]): "trade"}
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58d(s):
    n = 0
    for c in s: n = n * 58 + A.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
def b58e(b):
    n = int.from_bytes(b, "big"); out = ""
    while n: n, r = divmod(n, 58); out = A[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out

def rpc(method, params, tag):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    for _ in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "40", "-H", "Content-Type: application/json", "-d", body, RPC], capture_output=True, text=True)
        try:
            j = json.loads(r.stdout)
            if "result" in j:
                open(f"{tag}.json", "w").write(r.stdout); return j["result"]
        except Exception: pass
        time.sleep(3)
    return None

u64 = lambda b, o: struct.unpack_from("<Q", b, o)[0]

def amm(ev, b):
    d = dict(kind=ev, pool_base=u64(b,40), pool_quote=u64(b,48), amt_quote=u64(b,56), lp_fee=u64(b,72), protocol_fee=u64(b,88),
             pool=b58e(b[112:144]), cc_fee=u64(b,344), base_amt=u64(b,8))
    if ev == "sell" and len(b) >= 384:
        d.update(cashback=u64(b,360), buyback_bps=u64(b,368), buyback_fee=u64(b,376))
    return d

def trade(b):
    d = dict(kind="trade", mint=b58e(b[0:32]), sol_amount=u64(b,32), token_amount=u64(b,40), is_buy=b[48]==1,
             vsr=u64(b,89), vtr=u64(b,97), real_sol=u64(b,105), real_tok=u64(b,113),
             fee_bps=u64(b,153), fee=u64(b,161), creator_fee_bps=u64(b,201), creator_fee=u64(b,209))
    o = 250; L = struct.unpack_from("<I", b, o)[0]; o += 4 + L
    if len(b) >= o + 1 + 32:
        d["mayhem"] = b[o] == 1; o += 1
        d.update(cashback_bps=u64(b,o), cashback=u64(b,o+8), buyback_bps=u64(b,o+16), buyback_fee=u64(b,o+24))
    return d

def events(tx):
    keys = tx["transaction"]["message"]["accountKeys"] + tx["meta"].get("loadedAddresses", {}).get("writable", []) + tx["meta"].get("loadedAddresses", {}).get("readonly", [])
    out = []
    for grp in tx["meta"].get("innerInstructions") or []:
        for ins in grp["instructions"]:
            try: raw = b58d(ins["data"])
            except Exception: continue
            if raw[:8] == TAG and raw[8:16] in DISC:
                kind = DISC[raw[8:16]]; b = raw[16:]
                out.append(amm(kind, b) if kind in ("buy", "sell") else trade(b))
    return keys, out

def main_run():
    res = {"amm": [], "curve": []}
    for prog, bucket in [(AMM, "amm"), (PUMP, "curve")]:
        sigs = rpc("getSignaturesForAddress", [prog, {"limit": 40}], f"sigs_{bucket}") or []
        n = 0
        for s in sigs:
            if s.get("err") or n >= 6: continue
            tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "json"}], f"tx_{bucket}_{n}")
            time.sleep(0.6)
            if not tx: continue
            keys, evs = events(tx)
            evs = [e for e in evs if (e["kind"] != "trade") == (bucket == "amm")]
            if len(evs) != 1: continue  # 只用单事件交易，避免同一池多笔的前后状态混淆
            e = evs[0]; m = tx["meta"]; n += 1
            if bucket == "amm":
                pre = {(t["owner"], t["mint"]): int(t["uiTokenAmount"]["amount"]) for t in m["preTokenBalances"] if t.get("owner") == e["pool"]}
                post = {(t["owner"], t["mint"]): int(t["uiTokenAmount"]["amount"]) for t in m["postTokenBalances"] if t.get("owner") == e["pool"]}
                base_key = [k for k in post if k[1] != WSOL]; quote_key = [k for k in post if k[1] == WSOL]
                if not base_key or not quote_key: n -= 1; continue
                bk, qk = base_key[0], quote_key[0]
                e.update(vault_base_pre=pre.get(bk), vault_base_post=post.get(bk), vault_quote_pre=pre.get(qk), vault_quote_post=post.get(qk))
                e["base_matches"] = "pre" if e["pool_base"] == pre.get(bk) else ("post" if e["pool_base"] == post.get(bk) else "neither")
                e["quote_matches"] = "pre" if e["pool_quote"] == pre.get(qk) else ("post" if e["pool_quote"] == post.get(qk) else "neither")
                res["amm"].append(e)
            else:
                delta = [(i, m["postBalances"][i] - m["preBalances"][i]) for i in range(len(m["preBalances"]))]
                want = e["sol_amount"] if e["is_buy"] else -e["sol_amount"]
                idx = [i for i, dl in delta if dl == want]
                if not idx: n -= 1; continue
                i = idx[0]
                e.update(curve_lamports_pre=m["preBalances"][i], curve_lamports_post=m["postBalances"][i],
                         gap_post=m["postBalances"][i] - e["real_sol"], gap_pre=m["preBalances"][i] - e["real_sol"])
                fee_recv = [dl for _, dl in delta if dl in (e["fee"], e["creator_fee"], e.get("buyback_fee", -1)) and dl > 0]
                e["fee_accounts_received"] = fee_recv
                e["fee_on_top_check"] = round(e["fee"] / e["sol_amount"] * 1e4, 2) if e["sol_amount"] else None
                res["curve"].append(e)
    json.dump(res, open("verify_result.json", "w"), indent=1)
    for k in res:
        print(f"== {k} ({len(res[k])} 笔单事件交易)")
        for e in res[k]:
            print("  ", {x: e[x] for x in e if x not in ("pool", "mint")})

if __name__ == "__main__":
    main_run()

"""DQ-18 执行估值：由 D 段输出的成交 tx 取交易前池状态，按恒定乘积为我方仓位计算买价、卖价与容量。

链条（README v2.1 §3.6 第 2、3 条）：
  D 段 SQL 给出“t_s+L 之后主池（恒定乘积）第一笔成交”的 tx_id
  → 公共 RPC getTransaction 的 preTokenBalances：该笔之前的池储备
  = t_s+L 时刻已知的池状态（前提：两者之间没有加减流动性；无成交时状态不变）
  → 我方给定金额的买入均价 / 卖出所得 / 5% 冲击模型容量。
费率（用户侧单边合计）按场所与时期：Raydium AMM v4 0.25%；Raydium CPMM 按池配置（缺省 0.25%）；
PumpSwap 2025-03-20 起 0.25%、2025-05-13 起 0.30%、2025-09-03 起按 SOL 计价市值分档（官方表）。
python valuation.py --demo：用第 1 步缓存的 5 个知名币入场原件跑一遍。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOL = "So11111111111111111111111111111111111111112"
RAYDIUM_V4_AUTH = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
RAYDIUM_CPMM_AUTH = "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"
# 2025-09-03 起 PumpSwap canonical 池：SOL 计价市值上界 → 用户侧单边合计费率（官方 fees 页，09-24 核实）
PUMPSWAP_TIERS = [(420, .0125), (1470, .012), (2460, .0115), (3440, .011), (4420, .0105), (9820, .01),
                  (14740, .0095), (19650, .009), (24560, .0085), (29470, .008), (34380, .0075),
                  (39300, .007), (44210, .0065), (49120, .006), (54030, .0055), (58940, .00525),
                  (63860, .005), (68770, .00475), (73681, .0045), (78590, .00425), (83500, .004),
                  (88400, .00375), (93330, .0035), (98240, .00325), (float("inf"), .003)]


def fee_side(project, when, sol_mcap):
    if project == "raydium_v4":
        return 0.0025
    if project == "raydium_cpmm":
        return 0.0025
    if project == "pumpswap":
        if when < datetime(2025, 5, 13):
            return 0.0025
        if when < datetime(2025, 9, 3):
            return 0.0030
        for bound, f in PUMPSWAP_TIERS:
            if sol_mcap < bound:
                return f
    raise ValueError("unsupported venue " + project)


RAYDIUM_PROGRAMS = {"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("raydium_v4", RAYDIUM_V4_AUTH),
                    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": ("raydium_cpmm", RAYDIUM_CPMM_AUTH)}


def pool_reserves(tx, mint, pool):
    """交易前的池储备（代币, SOL）与场所，只认目标池自己的 vault。

    PumpSwap：vault 的 owner 就是池地址，唯一。
    Raydium v4/CPMM：vault 的 owner 是全局 authority，多池路由时同一 owner 下有多个 vault（09-24 独立复核发现，
    旧版取“最后一个”会串池）。改为：只看 Raydium 程序的、账户列表含目标池地址的指令（外层或内层），
    在这些指令的账户里找该 authority 名下的目标代币 vault 与 SOL vault，各须恰好一个，否则记未知。
    """
    meta = tx["meta"]
    msg = tx["transaction"]["message"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    la = meta.get("loadedAddresses") or {}
    keys += la.get("writable", []) + la.get("readonly", [])
    pre = {x["accountIndex"]: x for x in meta["preTokenBalances"]}
    amt = lambda b: float(b["uiTokenAmount"]["uiAmountString"])
    pp = {b["mint"]: amt(b) for b in pre.values() if b.get("owner") == pool and b["mint"] in (mint, SOL)}
    if mint in pp and SOL in pp:
        return pp[mint], pp[SOL], "pumpswap"
    if pool not in keys:
        raise ValueError("pool not in tx")
    pidx = keys.index(pool)
    ins = list(msg["instructions"]) + [i for g in meta.get("innerInstructions") or [] for i in g["instructions"]]
    for prog, (venue, auth) in RAYDIUM_PROGRAMS.items():
        accts = {a for i in ins if keys[i["programIdIndex"]] == prog and pidx in i["accounts"] for a in i["accounts"]}
        vaults = {}
        for a in accts:
            b = pre.get(a)
            if b and b.get("owner") == auth and b["mint"] in (mint, SOL):
                vaults.setdefault(b["mint"], set()).add(a)
        if vaults:
            if len(vaults.get(mint, ())) != 1 or len(vaults.get(SOL, ())) != 1:
                raise ValueError("ambiguous raydium vaults")
            return amt(pre[next(iter(vaults[mint]))]), amt(pre[next(iter(vaults[SOL]))]), venue
    raise ValueError("no constant-product vault pair in tx")


def buy(x_sol, y_tok, q_sol, f):
    """花 q_sol（含费）买入：返回得到的代币数。费从输入扣除。"""
    qin = q_sol * (1 - f)
    return y_tok - x_sol * y_tok / (x_sol + qin)


def sell(x_sol, y_tok, t_tok, f):
    """卖出 t_tok：返回到手 SOL（费从输出扣除）。"""
    return (x_sol - x_sol * y_tok / (y_tok + t_tok)) * (1 - f)


def cap5_buy_sol(x_sol):
    return x_sol * (1.05 ** 0.5 - 1)


def cap5_sell_sol(x_sol):
    return x_sol * (1 - 1 / 1.05 ** 0.5)


def demo():
    rows = json.load(open(ROOT / "raw" / "entry_pool_vaults_5known.json"))
    names = {"CzLSujWB": "GOAT", "9BB6NFEc": "FARTCOIN", "2qEHjDLD": "PNUT", "a3W4qutoE": "WHITEWHALE",
             "8Jx8AAHj8": "PENGUIN"}
    out = []
    for r in rows:
        tx = json.load(open(ROOT / "raw" / "rpc_entry" / (r["tx_id"] + ".json")))["result"]
        when = datetime.utcfromtimestamp(tx["blockTime"])
        y, x, venue = pool_reserves(tx, r["mint"], r["pool_id_dune"])
        sol_usd = float(r["coinbase_sol_close"])
        marg_cap = x / y * 1e9 * sol_usd
        f = fee_side(venue, when, x / y * 1e9)
        q = 1400 / sol_usd
        t = buy(x, y, q, f)
        back = sell(x + q * (1 - f), y - t, t, f)  # 立即卖回（同一状态后）
        out.append({
            "coin": next(v for k, v in names.items() if r["mint"].startswith(k)), "venue": venue,
            "time": when.isoformat(), "pool_sol": round(x, 2), "marginal_cap_musd": round(marg_cap / 1e6, 3),
            "fee_side": f, "buy1400_avg_cap_musd": round(q / t * 1e9 * sol_usd / 1e6, 3),
            "buy1400_cost_vs_marginal_pct": round((q / t) / (x / y) * 100 - 100, 3),
            "roundtrip_1400_loss_pct": round(100 - back / q * 100, 3),
            "cap5_buy_usd": round(cap5_buy_sol(x) * sol_usd), "cap5_sell_usd": round(cap5_sell_sol(x) * sol_usd),
            "reserves_match_step1": abs(x - r["quote_reserve_pre_sol"]) < 1e-6 and abs(y - r["target_reserve_pre"]) < 1e-3,
        })
    (ROOT / "raw" / "valuation_demo_5known.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for o in out:
        print(o)


if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        demo()

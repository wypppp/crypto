#!/usr/bin/env python3
"""母体经济基线 · 少量端到端试跑（开发样本）

只做 MEASUREMENT_SPEC.md 定义的测量，不读收益结论、不抽正式 300 样本。
所有 EVM 原语复用 baseline_20260909/verify_capabilities.py（已验证，sha256 bc9ea52e…），
本脚本不重新实现 buy/sell/槽位扫描。

用法：
    python pilot_measure.py declare --n 8 --out pilot/dev_sample.json
    python pilot_measure.py measure --sample pilot/dev_sample.json --out pilot/pilot_results.json
"""
import argparse, csv, hashlib, json, os, random, sys, time, urllib.parse, urllib.request
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "baseline_20260909"
sys.path.insert(0, str(PKG))
import verify_capabilities as V          # noqa: E402

UNIVERSE = Path(__file__).resolve().parent / "universe_run" / "universe.csv"
SEED = 20260910
CUTOFF_BLOCK = 24_781_026               # 配置 §1 的 b_end：首个 Mint 须在窗口结束前
MINT_TOPIC = "0x" + V.keccak(b"Mint(address,uint256,uint256)").hex()
GAS_SCENARIOS = [(g, t) for g in (120_000, 150_000, 200_000) for t in (0, 10**8, 10**9)]
MAIN_SCENARIO = (150_000, 10**8)
APPROVE_GAS = 50_000


def etherscan(key, **kw):
    kw.update({"chainid": 1, "apikey": key})
    time.sleep(0.34)
    url = "https://api.etherscan.io/v2/api?" + urllib.parse.urlencode(kw)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def declare(args):
    """先冻结开发样本，再测量 —— 样本文件写完之后才允许跑 measure。"""
    rows = [r for r in csv.DictReader(open(UNIVERSE)) if r["category"] == "weth"]
    rng = random.Random(SEED)
    pick = sorted(rng.sample(rows, args.n), key=lambda r: int(r["index"]))
    blob = {"declared_at": V.utcnow(), "seed": SEED, "n": args.n,
            "universe_sha256": hashlib.sha256(UNIVERSE.read_bytes()).hexdigest(),
            "universe_weth_rows": len(rows),
            "purpose": "development sample for end-to-end measurement; NOT the formal 300",
            "sample": [{"index": int(r["index"]), "pair": r["pair"],
                        "token": r["token0"] if r["token1"].lower() == V.WETH else r["token1"],
                        "created_block": int(r["block"])} for r in pick]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"declared {args.n} dev candidates -> {args.out}")
    print(f"  sample_sha256 = {hashlib.sha256(Path(args.out).read_bytes()).hexdigest()}")
    return 0


def first_mint(scan_key, pair, from_block):
    """首个 Mint。用 Etherscan logs（Alchemy 免费档 eth_getLogs 只有 10 块跨度）。"""
    j = etherscan(scan_key, module="logs", action="getLogs", address=pair,
                  topic0=MINT_TOPIC, fromBlock=from_block, toBlock=CUTOFF_BLOCK,
                  page=1, offset=1000)
    if str(j.get("status")) != "1":
        txt = (str(j.get("message", "")) + " " + str(j.get("result", ""))).lower()
        if "no records found" in txt:
            return None, "no_mint_by_cutoff"
        return None, "data_missing"
    rows = j.get("result") or []
    if not rows:
        return None, "no_mint_by_cutoff"
    lg = min(rows, key=lambda x: (int(x["blockNumber"], 16), int(x["logIndex"], 16)))
    return int(lg["blockNumber"], 16), "ok"


def find_slot(rpc, token, block, limit):
    """复用 Verifier.find_balance_slot 的算法；此处独立实现以便记录扫描成本。"""
    data = V.calldata("balanceOf(address)", V.WALLET)
    original = V.word(rpc.call(token, data, block))
    sent = [1234567890123456789, 2345678901234567890]
    if original in sent:
        sent = [x + 7 for x in sent]
    hits, calls = [], 0
    for slot in range(limit):
        key = V.mapping_key(V.WALLET, slot)
        calls += 1
        if V.word(rpc.call(token, data, block, {token: {"stateDiff": {key: "0x" + V.pad(sent[0])}}})) != sent[0]:
            continue
        calls += 1
        if V.word(rpc.call(token, data, block, {token: {"stateDiff": {key: "0x" + V.pad(sent[1])}}})) == sent[1]:
            hits.append((slot, key))
    calls += 1
    if V.word(rpc.call(token, data, block)) != original:
        return None, calls, "slot_probe_polluted"
    if len(hits) != 1:
        return None, calls, f"unresolved_{len(hits)}_hits"
    return hits[0], calls, "ok"


def gas_table(base_entry, base_exit, n_buy_attempts, n_sell_attempts, n_approvals):
    """按 SPEC §4 逐情景算 G；缺项不记零。"""
    out = {}
    for g, tip in GAS_SCENARIOS:
        gi = (base_entry + tip) * g * n_buy_attempts
        ge = (base_exit + tip) * g * n_sell_attempts
        ga = (base_exit + tip) * APPROVE_GAS * n_approvals
        out[f"swap{g}_tip{tip}"] = gi + ge + ga
    return out


def measure(args):
    key = os.environ.get("ETHERSCAN_API_KEY", "")
    url = os.environ.get("ETH_RPC_URL", "")
    if not url or not key:
        print("need ETH_RPC_URL and ETHERSCAN_API_KEY", file=sys.stderr)
        return 2
    decl = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    rpc = V.RPC(url, max_calls=args.max_calls, max_seconds=args.max_seconds, rps=args.rps)
    # 配置 §1：运行开始固定 finalized 快照，不随 latest 漂移。
    # eth_blockNumber 不在包的只读白名单内，本就该用 finalized。
    fin = rpc.request("eth_getBlockByNumber", ["finalized", False])
    HEAD = int(fin["number"], 16)
    SNAPSHOT = {"number": HEAD, "hash": fin["hash"], "timestamp": int(fin["timestamp"], 16)}
    print(f"finalized 快照 {HEAD}  {fin['hash'][:18]}…")
    _bc = {}

    def blk(b):
        if b not in _bc:
            _bc[b] = rpc.request("eth_getBlockByNumber", [hex(b), False])
        return _bc[b]

    t_all = time.time()
    results = []
    for i, c in enumerate(decl["sample"], 1):
        t0, c0 = time.time(), len(rpc.records)
        rec = {"index": c["index"], "pair": c["pair"], "token": c["token"],
               "created_block": c["created_block"],
               "trigger": None, "entry": None, "exit": None, "model": None, "data": None}
        try:
            mb, why = first_mint(key, c["pair"], c["created_block"])
            rec["trigger"] = {"first_mint_block": mb, "status": why}
            if mb is None:
                rec["state"] = why
            else:
                eb = mb + 1
                ets = int(blk(eb)["timestamp"], 16)
                base_e = int(blk(eb).get("baseFeePerGas", "0x0"), 16)
                buy = V.probe_call(rpc, c["token"], V.ROUTER, eb, ets, V.AMOUNT)
                rec["entry"] = {"entry_block": eb, "entry_ts": ets, "stage": buy["stage"],
                                "classification": buy["classification"],
                                "received": buy["token_after"] - buy["token_before"],
                                "eth_debit": buy["eth_before"] - buy["eth_after"],
                                "base_fee": base_e, "reason": buy["reason"][:80]}
                if buy["stage"] != 0 or buy["token_after"] <= buy["token_before"]:
                    rec["state"] = ("entry_failed_verified" if buy["stage"] == 20
                                    else "entry_unknown")
                else:
                    target = ets + 30 * V.DAY
                    if SNAPSHOT["timestamp"] < target:
                        rec["state"] = "right_censored"
                        rec["exit"] = {"reason": "exit snapshot beyond finalized head"}
                        results.append(rec); continue
                    xb = V.first_true(eb, HEAD, lambda b: int(blk(b)["timestamp"], 16) >= target)
                    xts = int(blk(xb)["timestamp"], 16)
                    base_x = int(blk(xb).get("baseFeePerGas", "0x0"), 16)
                    amount = buy["token_after"] - buy["token_before"]
                    slot, scan_calls, slot_why = find_slot(rpc, c["token"], xb, args.slot_limit)
                    rec["model"] = {"slot_scan_calls": scan_calls, "slot_status": slot_why,
                                    "slot": slot[0] if slot else None}
                    if slot is None:
                        rec["state"] = "model_unsupported"
                        rec["exit"] = {"exit_block": xb, "exit_ts": xts, "base_fee": base_x}
                    else:
                        ov = {c["token"]: {"stateDiff": {slot[1]: "0x" + V.pad(amount)}}}
                        sell = V.probe_call(rpc, c["token"], V.ROUTER, xb, xts, amount,
                                            selling=True, overrides=ov)
                        rec["exit"] = {"exit_block": xb, "exit_ts": xts, "base_fee": base_x,
                                       "stage": sell["stage"], "classification": sell["classification"],
                                       "token_before": sell["token_before"], "token_after": sell["token_after"],
                                       "cash_in": sell["eth_after"] - sell["eth_before"],
                                       "reason": sell["reason"][:80]}
                        # SPEC §2 的充分性判据 H1–H4
                        if sell["stage"] == 0 and sell["token_before"] == amount and sell["token_after"] == 0:
                            rec["state"] = "measured_exit"
                            rec["model"]["holding_state"] = "adequate_proven_by_execution"
                        elif sell["stage"] in (10, 11):
                            rec["state"] = "model_unsupported"
                            rec["model"]["holding_state"] = "injection_not_effective"
                        else:
                            rec["state"] = "execution_reverted_unknown"
                            rec["model"]["holding_state"] = "undetermined"
                            if args.diagnostics and sell["stage"] == 20:
                                d = {}
                                s1 = V.probe_call(rpc, c["token"], V.ROUTER, xb, xts, 1,
                                                  selling=True,
                                                  overrides={c["token"]: {"stateDiff": {slot[1]: "0x" + V.pad(amount)}}})
                                d["size_probe_stage"] = s1["stage"]
                                rec["model"]["diagnostics"] = d
                        # 成本（SPEC §4）
                        n_sell = 1
                        rec["cost"] = {"A_wei": V.AMOUNT,
                                       "R_wei": rec["exit"].get("cash_in"),
                                       "G_by_scenario": gas_table(base_e, base_x, 1, n_sell, 2),
                                       "main_scenario": f"swap{MAIN_SCENARIO[0]}_tip{MAIN_SCENARIO[1]}"}
        except V.Unrun as e:
            rec["state"], rec["data"] = "model_unsupported", {"unrun": str(e)[:160]}
        except V.RpcFailure as e:
            rec["state"], rec["data"] = "data_missing", {"rpc_failure": str(e)[:160]}
        except Exception as e:                                            # noqa: BLE001
            rec["state"], rec["data"] = "decode_error", {"error": f"{type(e).__name__}: {str(e)[:160]}"}
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["rpc_calls"] = len(rpc.records) - c0
        results.append(rec)
        print(f"  [{i}/{len(decl['sample'])}] idx={c['index']} state={rec.get('state')} "
              f"{rec['elapsed_s']}s rpc={rec['rpc_calls']}", flush=True)
    doc = {"started_at": V.utcnow(), "sample_file": str(args.sample),
           "finalized_snapshot": SNAPSHOT,
           "sample_sha256": hashlib.sha256(Path(args.sample).read_bytes()).hexdigest(),
           "package_script_sha256": hashlib.sha256((PKG / "verify_capabilities.py").read_bytes()).hexdigest(),
           "spec": "MEASUREMENT_SPEC.md v1 (draft)",
           "slot_limit": args.slot_limit, "diagnostics": args.diagnostics,
           "total_elapsed_s": round(time.time() - t_all, 1),
           "rpc_calls": len(rpc.records),
           "results": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n-> {args.out}")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("declare"); d.add_argument("--n", type=int, default=8); d.add_argument("--out", required=True)
    m = sub.add_parser("measure"); m.add_argument("--sample", required=True); m.add_argument("--out", required=True)
    m.add_argument("--slot-limit", type=int, default=32); m.add_argument("--max-calls", type=int, default=4000)
    m.add_argument("--max-seconds", type=int, default=3000); m.add_argument("--rps", type=float, default=3)
    m.add_argument("--diagnostics", action="store_true", default=True)
    a = p.parse_args()
    sys.exit(declare(a) if a.cmd == "declare" else measure(a))


if __name__ == "__main__":
    main()

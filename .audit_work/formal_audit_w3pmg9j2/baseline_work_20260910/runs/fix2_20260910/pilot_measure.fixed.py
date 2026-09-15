#!/usr/bin/env python3
"""母体经济基线 · 少量端到端试跑（开发样本）

只做 MEASUREMENT_SPEC.md 定义的测量，不读收益结论、不抽正式 300 样本。
所有 EVM 原语复用 baseline_20260909/verify_capabilities.py（已验证，sha256 bc9ea52e…），
本脚本不重新实现 buy/sell/槽位扫描。

用法：
    python pilot_measure.py declare --n 8 --out pilot/dev_sample.json
    python pilot_measure.py measure --sample pilot/dev_sample.json --out pilot/pilot_results.json
"""
import argparse, csv, hashlib, json, os, random, sys, threading, time
import urllib.parse, urllib.request
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "baseline_20260909"
sys.path.insert(0, str(PKG))
import verify_capabilities as V          # noqa: E402
import evidence as EV                    # noqa: E402

UNIVERSE = Path(__file__).resolve().parent / "universe_run" / "universe.csv"
SEED = 20260910
CUTOFF_BLOCK = 24_781_026               # 配置 §1 的 b_end：首个 Mint 须在窗口结束前
MINT_TOPIC = "0x" + V.keccak(b"Mint(address,uint256,uint256)").hex()
LOG_PAGE = 1000
GAS_SCENARIOS = [(g, t) for g in (120_000, 150_000, 200_000) for t in (0, 10**8, 10**9)]
MAIN_SCENARIO = (150_000, 10**8)
APPROVE_GAS = 50_000


def etherscan(key, log=None, candidate=None, stage=None, gate=None, worker=None, **kw):
    """Etherscan 请求 —— 原始响应逐条落盘（审查 §5：证据不能只有汇总）。"""
    kw.update({"chainid": 1, "apikey": key})
    if gate is not None:
        gate.acquire(worker, kind="etherscan")   # 与 RPC 共用同一预算与节流
    else:
        time.sleep(0.34)
    safe = {k: v for k, v in kw.items() if k != "apikey"}
    url = "https://api.etherscan.io/v2/api?" + urllib.parse.urlencode(kw)
    t0 = time.time()
    err, obj = None, None

    def scrub(x):
        # 异常串与非 JSON 响应都可能带上完整 URL（含 apikey）→ 统一脱敏后才落盘
        return log.redact(x) if log is not None else "<redacted>"

    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = r.read(4 * 1024 * 1024)
            try:
                obj = json.loads(body)
            except json.JSONDecodeError:
                obj = {"_non_json": scrub(body.decode("utf-8", "replace")[:2000])}
                raise ValueError("Etherscan returned non-JSON")
    except Exception as exc:                                          # noqa: BLE001
        err = scrub(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if log is not None:
            log.write("etherscan", candidate=candidate, stage=stage,
                      params=safe, response=obj, error=err,
                      elapsed_s=round(time.time() - t0, 3))
    return obj


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


def _is_hash32(s):
    """32 字节 hash 的规范形状：0x + 64 个十六进制字符。"""
    return (isinstance(s, str) and s.startswith("0x") and len(s) == 66
            and all(ch in "0123456789abcdefABCDEF" for ch in s[2:]))


def _as_uint(v):
    """日志里的数量字段：十六进制串或十进制整数，必须是非负整数。否则返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, str):
        t = v.strip()
        try:
            n = int(t, 16) if t.lower().startswith("0x") else int(t, 10)
        except ValueError:
            return None
        return n if n >= 0 else None
    return None


def _validate_log(r, pair, a, b):
    """规范 Mint 事件校验。Mint(address indexed sender,uint256,uint256)
    ⇒ topics 恰好 2 个、data 为 2 个 uint256（128 个十六进制字符）。"""
    if not isinstance(r, dict):
        return "not_object"
    if r.get("removed") in (True, "true", "True", 1):
        return "removed_log"
    if (r.get("address") or "").lower() != pair.lower():
        return f"address_mismatch:{str(r.get('address'))[:12]}"
    tp = r.get("topics")
    if not isinstance(tp, list) or len(tp) != 2:
        return f"topics_count:{len(tp) if isinstance(tp, list) else 'none'}"
    if str(tp[0]).lower() != MINT_TOPIC:
        return "topic0_mismatch"
    data = str(r.get("data") or "")
    if not data.startswith("0x") or len(data) - 2 != 128:
        return f"data_shape:{len(data)-2 if data.startswith('0x') else 'missing'}"
    body = data[2:]
    if any(ch not in "0123456789abcdefABCDEF" for ch in body):
        return "data_not_hex"
    a0, a1 = int(body[:64], 16), int(body[64:], 16)
    if a0 == 0 and a1 == 0:
        return "mint_amounts_both_zero"      # 两侧都为 0 不是有效的流动性注入
    tp1 = str(r.get("topics")[1])
    if not (tp1.startswith("0x") and len(tp1) == 66):
        return "sender_topic_shape"
    if any(ch not in "0123456789abcdefABCDEF" for ch in tp1[2:]):
        return "sender_topic_not_hex"        # 明确拒收，不要让 int() 裸抛
    if int(tp1, 16) >> 160:
        return "sender_topic_not_address"    # 高位必须为 0（indexed address）
    # 日志身份三件套：交易 hash / 块 hash / 日志序号。
    # 只查前缀不够 —— transactionHash='0x' 曾整条通过（审查反例 6）。
    txh = str(r.get("transactionHash") or "")
    if not _is_hash32(txh):
        return f"tx_hash_shape:{len(txh)}"
    bh = r.get("blockHash")
    if bh is not None and not _is_hash32(str(bh)):
        return f"block_hash_shape:{str(bh)[:12]}"
    if r.get("logIndex") in (None, ""):
        return "missing_log_index"          # 不得默认为 0
    if _as_uint(r.get("logIndex")) is None:
        return f"log_index_unparsable:{str(r.get('logIndex'))[:16]}"
    try:
        bn = int(r["blockNumber"], 16)
    except (KeyError, TypeError, ValueError):
        return "blocknumber_unparsable"
    if not (a <= bn <= b):
        return f"block_out_of_range:{bn}"
    return None


def _logs_page(scan_key, pair, a, b, log, candidate):
    """取一页并做规范校验。返回 (valid_rows, page_full, reject_reasons)。"""
    j = etherscan(scan_key, log=log, candidate=candidate, stage="first_mint",
                  gate=getattr(log, "_gate", None),
                  worker=getattr(threading.current_thread(), "worker_id", None),
                  module="logs", action="getLogs", address=pair,
                  topic0=MINT_TOPIC, fromBlock=a, toBlock=b,
                  page=1, offset=LOG_PAGE)
    status = str(j.get("status"))
    if status != "1":
        txt = (str(j.get("message", "")) + " " + str(j.get("result", ""))).lower()
        if "no records found" in txt:
            return [], False, []
        raise V.RpcFailure("etherscan", f"logs status={status} msg={j.get('message')}")
    rows = j.get("result")
    if not isinstance(rows, list):
        raise V.RpcFailure("etherscan", "logs result is not a list")
    good, rejected = [], []
    for r in rows:
        why = _validate_log(r, pair, a, b)
        (rejected.append(why) if why else good.append(r))
    return good, len(rows) >= LOG_PAGE, rejected


def _find_earliest_log(scan_key, pair, a, b, log, candidate, detail, _depth=0):
    """
    在 [a,b] 内找最早的规范 Mint 事件。**不做任何供给推断** —— 子区间返回空
    是合法结果，不能当成日志不完整（审查 B：旧版把空左区间误判为 log_incomplete，
    右半区间从此永不被查询）。

    返回 (block_or_None, unresolvable: bool)。unresolvable 表示满页且无法再收窄。
    """
    good, page_full, rejected = _logs_page(scan_key, pair, a, b, log, candidate)
    detail["pages"] += 1
    detail["rejected"] += rejected
    detail["queried"].append([a, b])
    if page_full:
        detail["truncated"] = True
        if a >= b or _depth >= 32:
            return None, True                      # 单块内就满页，无法再分
        mid = (a + b) // 2
        lb, lu = _find_earliest_log(scan_key, pair, a, mid, log, candidate, detail, _depth + 1)
        if lb is not None:
            return lb, False
        if lu:
            return None, True                      # 左半无法解析 ⇒ 不能跳过它
        return _find_earliest_log(scan_key, pair, mid + 1, b, log, candidate,
                                  detail, _depth + 1)   # 左半确实为空 ⇒ 查右半
    if not good:
        return None, False
    lg = min(good, key=lambda x: (int(x["blockNumber"], 16), int(x["logIndex"], 16)))
    return int(lg["blockNumber"], 16), False


def first_mint(scan_key, pair, from_block, to_block, log=None, candidate=None,
               supply_at_cutoff=None, supply_at=None):
    """
    首次 Mint（规格 v1.1 §6）。校验链：

    1. 事件规范性（`_validate_log`）：removed / topics 数 / data 形状 / tx hash /
       logIndex / 块范围，全部不合格即拒收；
    2. 分页满即递归收窄，**空子区间是合法空**，不与供给推断混用；
    3. 与链上供给交叉核验（canonical V2 Pair：首次 Mint 永久锁 MINIMUM_LIQUIDITY，
       故「发生过 Mint」⟺「totalSupply > 0」）；
    4. **候选块的首次性验证**：`totalSupply(block-1)==0` 且 `totalSupply(block)>0`。
       仅供给非零不证明找到的是最早那次（审查 A）。

    `supply_at(block)` 由调用方注入，便于离线测试。
    """
    detail = {"range": [from_block, to_block], "supply_at_cutoff": supply_at_cutoff,
              "rejected": [], "pages": 0, "truncated": False, "queried": [],
              "supply_before": None, "supply_at_block": None}
    blk_found, unresolvable = _find_earliest_log(scan_key, pair, from_block, to_block,
                                                 log, candidate, detail)
    if unresolvable:
        return None, "log_incomplete", detail
    if blk_found is None:
        if supply_at_cutoff is None:
            return None, "supply_check_unavailable", detail
        if supply_at_cutoff > 0:
            return None, "log_incomplete", detail
        return None, "no_mint_by_cutoff", detail
    # 找到了日志 —— 先查与截止供给是否矛盾
    if supply_at_cutoff is not None and supply_at_cutoff == 0:
        return None, "state_contradiction", detail     # 有日志却供给为零
    if supply_at is None:
        return blk_found, "first_mint_unverified", detail
    before = supply_at(blk_found - 1)
    at = supply_at(blk_found)
    detail["supply_before"], detail["supply_at_block"] = before, at
    if before != 0 or at <= 0:
        # 该块之前已有供给 ⇒ 更早的 Mint 被漏掉；或该块供给未增加 ⇒ 事件与状态矛盾
        return None, "not_first_mint", detail
    return blk_found, "ok", detail


def identity_probe(rpc, token, slot_key_for, amount, block, ts):
    """
    换一个虚拟身份重做同一次卖出（规格 v1.3 §2 的收窄诊断）。

    做法：把 `Probe` 代码注入 `CALLER`（而不是 `WALLET`），余额注入 `CALLER` 名下的
    同一映射槽，然后由 `CALLER` 发起卖出。

    **只记录，不判定。** 两个虚拟地址都没有真实买入历史，所以：
    * 两者都失败 ⇒ **不能**排除「两者都缺历史状态」这一共同原因；
    * 结果不同 ⇒ 说明行为与具体地址相关，但仍不指明是哪一种机制。
    """
    ov = {V.WALLET: {"code": V.RUNTIMES["Probe"], "balance": hex(10 ** 20), "state": {}},
          V.CALLER: {"code": V.RUNTIMES["Probe"], "balance": hex(10 ** 20), "state": {}},
          token: {"stateDiff": {slot_key_for(V.CALLER): "0x" + V.pad(amount)}}}
    raw = rpc.call(V.CALLER, V.calldata(
        "sell(address,address,uint256,uint256,bool)",
        token, V.ROUTER, amount, ts + 3600, True), block, ov)
    res = V.parse_probe(raw)
    res["classification"] = V.classify_probe(res)
    return {"identity": "CALLER", "stage": res["stage"],
            "classification": res["classification"],
            "reason": res["reason"][:80],
            "token_before": res["token_before"], "token_after": res["token_after"],
            "note": "record only; both virtual identities lack real purchase history, "
                    "so agreement does NOT exclude missing-history as a common cause"}


def snapshot_block(rpc, blk, b, *, bracket_target=None):
    """块快照 + 结构校验。返回的 failures 非空即须阻断（审查 E）。"""
    cur, prev = blk(b), blk(b - 1)
    out = {"number": b, "hash": cur.get("hash"), "parent_hash": cur.get("parentHash"),
           "timestamp": int(cur["timestamp"], 16),
           "prev_number": b - 1, "prev_hash": prev.get("hash"),
           "prev_timestamp": int(prev["timestamp"], 16),
           "failures": []}
    if int(cur.get("number", "0x0"), 16) != b:
        out["failures"].append(f"block number mismatch: {cur.get('number')} != {hex(b)}")
    for k in ("hash", "parentHash"):
        v = cur.get(k)
        if not (isinstance(v, str) and v.startswith("0x") and len(v) == 66):
            out["failures"].append(f"bad {k} format: {str(v)[:20]}")
    out["parent_links"] = cur.get("parentHash") == prev.get("hash")
    if not out["parent_links"]:
        out["failures"].append("parent link broken: block.parentHash != prev.hash")
    if bracket_target is not None:
        # 退出块必须是「首个时间戳 >= 目标」的块：前块必须严格早于目标
        out["bracket_target"] = bracket_target
        if not (out["prev_timestamp"] < bracket_target <= out["timestamp"]):
            out["failures"].append(
                f"exit not bracketed: prev_ts={out['prev_timestamp']} "
                f"target={bracket_target} ts={out['timestamp']}")
    return out


def validate_identity_closure(rpc, token, pair, b0):
    """身份闭环（审查 F）：pair 的两侧必须就是 {WETH, token}，
    且 factory.getPair(token0,token1) 必须回到同一个 pair。
    代码存在与 hash 记录是证据，不自动证明实现等价。"""
    fails = {}
    t0 = V.addr_from_word(rpc.call(pair, V.calldata("token0()"), b0))
    t1 = V.addr_from_word(rpc.call(pair, V.calldata("token1()"), b0))
    fails["token0"], fails["token1"] = t0, t1
    if {t0, t1} != {V.WETH, token.lower()}:
        fails["error"] = f"pair sides {t0},{t1} != WETH+{token.lower()}"
    got = V.addr_from_word(rpc.call(V.FACTORY,
                                    V.calldata("getPair(address,address)", t0, t1), b0))
    fails["getPair"] = got
    if got != pair.lower():
        fails["error2"] = f"factory.getPair -> {got} != {pair.lower()}"
    return fails


def validate_candidate_state(rpc, log, candidate, token, pair, blocks):
    """
    候选级状态校验（规格 v1.1 §6）。任一项失败 ⇒ 阻断，不得升级到测量结论。

    **通过不等于跨期持仓充分**：本函数只证明「注入前虚拟地址干净、协议身份正确、
    所用区块可核验」；它与 H1 是两件事，不能相互替代。
    """
    out = {"blocks": {}, "identity": {}, "wallet_clean": {}, "failures": [],
           "note": "state validation only; NOT evidence of cross-period holding adequacy"}
    # 1. 虚拟地址在每个用到的块上必须无代码；余额原值留档
    for b in blocks:
        for who, name in ((V.WALLET, "WALLET"), (V.CALLER, "CALLER")):
            code = rpc.request("eth_getCode", [who, hex(b)])
            bal = rpc.request("eth_getBalance", [who, hex(b)])
            key = f"{name}@{b}"
            out["wallet_clean"][key] = {"code": code, "balance": bal}
            if code != "0x":
                out["failures"].append(f"{key}: virtual address already has code")
    # 2. 协议身份与字节码指纹
    b0 = blocks[0]
    for name, addr in (("factory", V.FACTORY), ("router", V.ROUTER),
                       ("weth", V.WETH), ("token", token), ("pair", pair)):
        code = V.raw_hex(rpc.request("eth_getCode", [addr, hex(b0)]))
        if not code:
            out["failures"].append(f"{name}: no code at block {b0}")
            out["identity"][name] = {"address": addr, "code_keccak256": None}
            continue
        out["identity"][name] = {"address": addr,
                                 "code_keccak256": "0x" + V.keccak(code).hex()}
    try:
        closure = validate_identity_closure(rpc, token, pair, b0)
        out["identity_closure"] = closure
        if "error" in closure:
            out["failures"].append(closure["error"])
        if "error2" in closure:
            out["failures"].append(closure["error2"])
        if V.addr_from_word(rpc.call(pair, V.calldata("factory()"), b0)) != V.FACTORY:
            out["failures"].append("pair.factory() mismatch")
        if V.addr_from_word(rpc.call(V.ROUTER, V.calldata("factory()"), b0)) != V.FACTORY:
            out["failures"].append("router.factory() mismatch")
        if V.addr_from_word(rpc.call(V.ROUTER, V.calldata("WETH()"), b0)) != V.WETH:
            out["failures"].append("router.WETH() mismatch")
    except (V.RpcFailure, ValueError) as e:
        out["failures"].append(f"identity_call_failed: {str(e)[:80]}")
    out["passed"] = not out["failures"]
    log.write("state_validation", candidate=candidate, passed=out["passed"],
              failures=out["failures"], identity=out["identity"],
              wallet_clean=out["wallet_clean"])
    return out


def verify_wallet_not_persisted(rpc, log, candidate, blocks, before):
    """注入后复读：虚拟地址的代码与余额不得被持久化。"""
    bad = []
    for b in blocks:
        for who, name in ((V.WALLET, "WALLET"), (V.CALLER, "CALLER")):
            key = f"{name}@{b}"
            code = rpc.request("eth_getCode", [who, hex(b)])
            bal = rpc.request("eth_getBalance", [who, hex(b)])
            was = before.get(key, {})
            if code != was.get("code"):
                bad.append(f"{key}: code persisted")
            if bal != was.get("balance"):
                bad.append(f"{key}: balance persisted")
    log.write("wallet_restore_check", candidate=candidate, passed=not bad, failures=bad)
    return bad


def find_slot(rpc, token, block, limit):
    """注意：实际 RPC 次数 = 1(原值) + limit(第一哨兵) + 命中数(第二哨兵) + 1(恢复核验)。
    旧版 calls 计数漏了原值读取，勘误见 PILOT_ERRATA_20260910.md E5。"""
    """复用 Verifier.find_balance_slot 的算法；此处独立实现以便记录扫描成本。"""
    data = V.calldata("balanceOf(address)", V.WALLET)
    calls = 1                                    # 扫描前的原值读取，必须计入
    original = V.word(rpc.call(token, data, block))
    sent = [1234567890123456789, 2345678901234567890]
    if original in sent:
        sent = [x + 7 for x in sent]
    hits = []
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


UNKNOWN = "unknown"


def reached_attempts(kind, stage, do_approve=True):
    """
    按**实际到达的执行阶段**给出尝试次数（规格 v1.2 §4）。
    依据 `Probe.buy/sell` 源码的控制流，不从最终 stage 反推精确成本。

    返回 {"swap": n, "approve": n 或 (lo,hi) 或 UNKNOWN, "basis": 说明}
    """
    if kind == "buy":
        # Probe.buy 无授权步骤，且总是发出 router.call；成败都已付出该次尝试
        return {"swap": 1, "approve": 0, "basis": "buy always attempts swap; no approve"}
    if stage == 10:
        return {"swap": 0, "approve": 0,
                "basis": "b0<amount returns before any approve or swap"}
    if stage == 12:
        # approve(0) 与 approve(amount) 都可能是失败点，stage 无法区分
        return {"swap": 0, "approve": (1, 2),
                "basis": "approve failed; which of the two is indistinguishable from stage"}
    if stage == 11:
        return {"swap": 0, "approve": 2 if do_approve else 0,
                "basis": "allowance check returns before swap"}
    if stage in (0, 20):
        return {"swap": 1, "approve": 2 if do_approve else 0,
                "basis": "reached swap"}
    return {"swap": UNKNOWN, "approve": UNKNOWN, "basis": f"unmapped stage {stage}"}


def _mul(units, gas, price):
    if units is UNKNOWN:
        return UNKNOWN, UNKNOWN
    if units == 0:
        return 0, 0          # 该腿未执行 ⇒ 成本确定为 0，价格未知不应污染已知的另一腿
    if price is None:
        return UNKNOWN, UNKNOWN
    if isinstance(units, tuple):
        return units[0] * gas * price, units[1] * gas * price
    v = units * gas * price
    return v, v


def gas_cost(entry_attempts, exit_attempts, base_entry, base_exit):
    """
    逐情景算 G。**缺 baseFeePerGas 记未知，不记零**；
    approve 次数不确定时给出区间而不是取一个数。
    """
    out = {}
    for g in (120_000, 150_000, 200_000):
        for tip in (0, 10 ** 8, 10 ** 9):
            pe = None if base_entry is None else base_entry + tip
            px = None if base_exit is None else base_exit + tip
            parts = [
                _mul(entry_attempts["swap"], g, pe),
                _mul(exit_attempts["swap"], g, px),
                _mul(entry_attempts["approve"], APPROVE_GAS, pe),
                _mul(exit_attempts["approve"], APPROVE_GAS, px),
            ]
            key = f"swap{g}_tip{tip}"
            if any(lo is UNKNOWN for lo, _ in parts):
                out[key] = UNKNOWN
                continue
            lo = sum(x for x, _ in parts)
            hi = sum(y for _, y in parts)
            out[key] = lo if lo == hi else {"min": lo, "max": hi}
    return out


class _Censored(Exception):
    pass


class _Blocked(Exception):
    """候选级状态校验失败 —— 保留证据并阻断后续升级。"""


def measure(args):
    key = os.environ.get("ETHERSCAN_API_KEY", "")
    url = os.environ.get("ETH_RPC_URL", "")
    if not url or not key:
        print("need ETH_RPC_URL and ETHERSCAN_API_KEY", file=sys.stderr)
        return 2
    decl = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    # 冻结样本自身必须自洽：声明数量与条目数一致、候选编号唯一。
    # 集合差检查只能发现"少了"，发现不了"同一个候选算了两次"（审查反例 5）。
    _sample = decl.get("sample") or []
    _idx = [c.get("index") for c in _sample]
    _dups = sorted({i for i in _idx if _idx.count(i) > 1})
    _problems = []
    if decl.get("n") is not None and decl["n"] != len(_sample):
        _problems.append(f"n={decl['n']} 与条目数 {len(_sample)} 不符")
    if _dups:
        _problems.append(f"候选编号重复：{_dups}")
    if any(i is None for i in _idx):
        _problems.append("存在没有 index 的候选")
    if _problems:
        print("冻结样本不自洽，拒绝测量：" + "；".join(_problems), file=sys.stderr)
        return 2
    secrets = {key, url}
    secrets.update(x for x in urllib.parse.urlsplit(url).path.split("/") if len(x) >= 12)
    log = EV.EvidenceLog(args.evidence, secrets=secrets)
    # 全局闸门：**在第一个请求之前**建立并装到真实 HTTP 边界上。
    # 旧版只在 parallel>1 时建、且建在 chainId/finalized 之后 ——
    # 启动请求、串行分支、Etherscan、以及 V.RPC 内部的 HTTP 重试全都在预算之外
    # （审查反例 2 与 retry 反例）。现在这些一律经过同一份预算与节流。
    gate = EV.SharedGate(args.rps, args.max_calls, args.max_seconds)
    EV.install_http_gate(gate)
    # 各 worker 的 V.RPC 自身限流让位给全局闸门（其 max_calls 仍是本地兜底）
    raw = V.RPC(url, max_calls=args.max_calls, max_seconds=args.max_seconds, rps=10 ** 6)
    rpc = EV.RpcTap(raw, log, gate=gate, worker=0)
    log._gate = gate                             # Etherscan 走同一闸门
    started_at = V.utcnow()                      # 开始时即固定，不在结束时补写
    log.resource(stage="startup")
    log.write("gate_installed", rps=args.rps, max_calls=args.max_calls,
              max_seconds=args.max_seconds,
              scope="startup+serial+parallel+etherscan+http_retry")

    # 审查 §3：链身份必须实测，不能默认。
    rpc.mark(stage="chain_id")
    try:
        chain_id = int(rpc.request("eth_chainId", []), 16)
    except EV.BudgetExhausted as e:
        # 启动请求现在也在同一预算内（旧版建 gate 之前就发了，游离在外）
        log.write("abort", reason="budget_exhausted", stage="chain_id",
                  detail=str(e)[:160], gate=gate.stats())
        log.close()
        EV.uninstall_http_gate()
        print(f"全局预算在链身份阶段即耗尽：{e}", file=sys.stderr)
        return 2
    if chain_id != 1:
        log.write("abort", reason="chain_id_mismatch", chain_id=chain_id)
        log.close()
        print(f"chain_id={chain_id}，非以太坊主网", file=sys.stderr)
        return 2

    # 配置 §1：运行开始固定 finalized 快照，不随 latest 漂移。
    # eth_blockNumber 不在包的只读白名单内，本就该用 finalized。
    ckpt = EV.Checkpoint(args.checkpoint)
    prior = ckpt.binding
    rpc.mark(stage="snapshot")
    pin = None
    if getattr(args, "pin_finalized", None):
        # 串行与并行对照必须绑在**同一状态块**上。共用检查点会让第二次
        # 直接跳过候选，各自新建检查点又会各取各的 finalized ——
        # 两条路都不能构成同快照对照（审查并行条件 4）。
        try:
            _n, _h = str(args.pin_finalized).split(":", 1)
            pin = (int(_n, 0), _h)
        except ValueError:
            print("--pin-finalized 格式应为 <块号>:<块hash>", file=sys.stderr)
            return 2
        if prior and (prior["finalized_number"] != pin[0]
                      or prior["finalized_hash"] != pin[1]):
            print(f"--pin-finalized 与检查点里的快照不符："
                  f"{prior['finalized_number']}/{prior['finalized_hash'][:18]}… vs "
                  f"{pin[0]}/{pin[1][:18]}… —— 拒绝", file=sys.stderr)
            return 2
    try:
        if pin and not prior:
            fin = rpc.request("eth_getBlockByNumber", [hex(pin[0]), False])
            if fin["hash"] != pin[1]:
                log.write("abort", reason="pinned_snapshot_mismatch", block=pin[0],
                          want=pin[1], got=fin["hash"])
                print(f"指定的 finalized 块 {pin[0]} hash 不符（可能已重组）：拒绝",
                      file=sys.stderr)
                return 2
            log.write("snapshot_pinned", number=pin[0], hash=pin[1],
                      basis="--pin-finalized; 供串行/并行同快照对照")
        elif prior:
            # 续跑：复用检查点里的 finalized 快照，使结果跨会话可复现；
            # 但必须核验该块 hash 未变（重组会让原有结果失效）。
            pinned = prior["finalized_number"]
            fin = rpc.request("eth_getBlockByNumber", [hex(pinned), False])
            if fin["hash"] != prior["finalized_hash"]:
                log.write("abort", reason="finalized_reorg", block=pinned,
                          was=prior["finalized_hash"], now=fin["hash"])
                print(f"finalized 块 {pinned} 的 hash 已变（重组），拒绝续跑", file=sys.stderr)
                return 2
        else:
            fin = rpc.request("eth_getBlockByNumber", ["finalized", False])
    except EV.BudgetExhausted as e:
        log.write("abort", reason="budget_exhausted", stage="snapshot",
                  detail=str(e)[:160], gate=gate.stats())
        log.close()
        EV.uninstall_http_gate()
        print(f"全局预算在固定 finalized 快照时耗尽：{e}", file=sys.stderr)
        return 2
    HEAD = int(fin["number"], 16)
    SNAPSHOT = {"number": HEAD, "hash": fin["hash"], "timestamp": int(fin["timestamp"], 16)}
    print(f"chain_id={chain_id}  finalized 快照 {HEAD}  {fin['hash'][:18]}…")

    # 检查点绑定：样本 / 规格 / 脚本 / 证据模块 / 台账 / finalized 状态块
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = Path(__file__).resolve().parent / spec_path
    resumed, _ = ckpt.verify_binding(
        sample_sha256=EV.sha256_file(args.sample),
        spec_sha256=EV.sha256_file(spec_path) if spec_path.is_file() else None,
        script_sha256=EV.sha256_file(__file__),
        evidence_module_sha256=EV.sha256_file(EV.__file__),
        primitives_sha256=EV.sha256_file(V.__file__),      # 测量原语本身
        universe_sha256=EV.sha256_file(UNIVERSE),
        runtime_params={"slot_limit": args.slot_limit,
                        "diagnostics": bool(args.diagnostics),
                        "cutoff_block": CUTOFF_BLOCK,
                        "amount_wei": V.AMOUNT},
        finalized_number=SNAPSHOT["number"], finalized_hash=SNAPSHOT["hash"])
    # ---- 续跑：只有"结果拿得出且 hash 对得上"的候选才允许跳过 ----
    # 旧版只看 completed 标志：删掉旧结果 JSON 与证据后，续跑仍 exit=0、
    # results=[]、set_complete=true —— 交付的是一份空汇总（审查反例 1）。
    carried, ckpt_broken, evidence_chain = {}, [], []
    if resumed:
        carried, ckpt_broken = ckpt.deliverable()
        flagged = ckpt.completed() - set(carried)
        # 检查点里引用过的证据必须**确实支持**被复用的那条结果：
        # 文件在、结构完整、含记录的 run_id、该运行的绑定与检查点一致、
        # 且该运行里有这个候选的 candidate_result 且 hash 对得上。
        # 只查"文件结构完整"是不够的 —— 换成另一个运行的完整证据也能过
        # （审查 v1.5 反例 1）。
        for cand, (_res, att) in sorted(carried.items()):
            ev_path = att.get("evidence_file")
            if not ev_path:
                evidence_chain.append({"candidate": cand, "reason": "no_evidence_reference"})
                continue
            run_id = att.get("evidence_run_id")
            if not run_id:
                evidence_chain.append({"candidate": cand,
                                       "reason": "no_evidence_run_id_reference",
                                       "path": ev_path})
                continue
            for pb in EV.verify_evidence_supports(
                    ev_path, run_id=run_id, candidate=cand,
                    result_sha256=att.get("result_sha256"),
                    binding=prior,
                    # 本次运行可能就写在同一个证据文件里，此刻当然还没有运行尾
                    ignore_runs=(log.run_id,)):
                evidence_chain.append(dict(pb, candidate=cand))
        if ckpt_broken:
            print(f"检查点里有 {len(ckpt_broken)} 个候选标了完成却拿不出可信结果，"
                  f"将**重新测量**：{[b['candidate'] for b in ckpt_broken]}", file=sys.stderr)
        if flagged:
            log.write("checkpoint_result_unusable", candidates=sorted(flagged),
                      detail=ckpt_broken)
    done = set(carried)
    if resumed:
        print(f"续跑：检查点已有 {len(ckpt.attempts())} 条尝试，"
              f"可交付已完成 {len(done)} 个候选，将跳过并原样并入交付")
    log.write("checkpoint_state", resumed=resumed, completed=sorted(done),
              carried_results=sorted(done), unusable=ckpt_broken,
              evidence_chain_problems=evidence_chain,
              prior_attempts=len(ckpt.attempts()))

    # 运行头：在任何候选工作之前写入；台账 hash 与声明不符即拒绝复用。
    EV.run_header(log, script=__file__, spec=args.spec, sample=args.sample,
                  universe=UNIVERSE, declared_universe_sha=decl["universe_sha256"],
                  chain_id=chain_id, snapshot=SNAPSHOT,
                  params={"slot_limit": args.slot_limit, "diagnostics": args.diagnostics,
                          "rps": args.rps, "max_calls": args.max_calls,
                          "max_seconds": args.max_seconds, "cutoff_block": CUTOFF_BLOCK,
                          "amount_wei": V.AMOUNT, "gas_scenarios": len(GAS_SCENARIOS)})
    _bc = {}                 # block -> (payload, fetched_by_worker)
    _bc_lock = threading.Lock()

    def blk(b, fresh=False, rpc=None):
        """fresh=True 绕过缓存，发新请求。防重组复读必须用它 ——
        旧版收尾复读命中缓存，等于拿同一份数据自比（审查 D）。

        缓存跨 worker 共享，所以每次命中都记一条证据：谁取的、谁用的。
        串行/并行证据比对时，缓存口径由这些记录界定，不靠推断（审查并行条件 2）。"""
        r = rpc if rpc is not None else globals().get("_never")
        if r is None:
            raise AssertionError("blk() 必须显式传入本 worker 的 rpc，不得用外层共享实例")
        me = getattr(threading.current_thread(), "worker_id", None)
        if not fresh:
            with _bc_lock:
                hit = _bc.get(b)
            if hit is not None:
                payload, owner = hit
                log.write("block_cache_hit", block=b, fetched_by_worker=owner,
                          used_by_worker=me, block_hash=payload.get("hash"))
                return payload
        got = r.request("eth_getBlockByNumber", [hex(b), False])
        if not fresh:
            with _bc_lock:
                _bc.setdefault(b, (got, me))
        else:
            log.write("block_refetch", block=b, used_by_worker=me,
                      reason="fresh=True bypasses cache")
        return got

    t_all = time.time()
    results, skipped = [], []
    res_lock = threading.Lock()
    worker_errors = []
    taps = [rpc]                    # 汇总 RPC 计数用：主 tap + 各 worker 的 tap

    def handle(i, c, rpc):
        """处理一个候选。**串行与并行共用同一份语义**，只有调度不同。"""
        t0, c0 = time.time(), len(rpc.records)
        if c["index"] in done:
            log.write("candidate_skipped", candidate=c["index"], reason="already_completed")
            with res_lock:
                skipped.append(c["index"])
            return
        rpc.mark(candidate=c["index"], stage="start")
        log.write("candidate_start", candidate=c["index"], pair=c["pair"],
                  token=c["token"], created_block=c["created_block"], ordinal=i)
        log.resource(candidate=c["index"], stage="start")
        rec = {"index": c["index"], "pair": c["pair"], "token": c["token"],
               "created_block": c["created_block"],
               "trigger": None, "entry": None, "exit": None, "model": None, "data": None}
        fees = {"entry": None, "exit": None}    # 已知的 base fee，异常收尾也要用得上
        try:
            # 交叉核验用：UniswapV2 首次 Mint 会把 MINIMUM_LIQUIDITY 永久锁在
            # address(0)，所以「截止块 totalSupply > 0」⟺「截止前发生过 Mint」。
            rpc.mark(stage="supply_check")
            _sup = {}

            def supply_at(bn):
                """totalSupply(bn)。**合约当时不存在 ⇒ 供给按定义为 0**，
                不是错误：建池与首次 Mint 常在同一块，此时 bn-1 上 pair 尚无代码，
                eth_call 返回 0x。必须与「有代码却返回空」区分开（后者是异常）。"""
                if bn in _sup:
                    return _sup[bn]
                raw = rpc.call(c["pair"], V.calldata("totalSupply()"), bn)
                if raw in (None, "0x", ""):
                    code = rpc.request("eth_getCode", [c["pair"], hex(bn)])
                    if code in (None, "0x", ""):
                        _sup[bn] = 0
                        _sup_basis[bn] = "no_code_at_block"
                        return 0
                    raise V.RpcFailure("abi",
                                       f"totalSupply empty while code present at {bn}")
                _sup[bn] = V.word(raw)
                _sup_basis[bn] = "call"
                return _sup[bn]

            _sup_basis = {}

            supply = supply_at(CUTOFF_BLOCK)
            rpc.mark(stage="first_mint")
            mb, why, fm_detail = first_mint(key, c["pair"], c["created_block"],
                                            CUTOFF_BLOCK, log=log, candidate=c["index"],
                                            supply_at_cutoff=supply, supply_at=supply_at)
            fm_detail["supply_basis"] = dict(_sup_basis)
            rec["trigger"] = {"first_mint_block": mb, "status": why,
                              "supply_at_cutoff": supply, "detail": fm_detail}
            log.write("first_mint_result", candidate=c["index"], block=mb,
                      status=why, supply_at_cutoff=supply, detail=fm_detail)
            if mb is None:
                # log_incomplete / supply_check_unavailable 都不是「没有 Mint」
                rec["state"] = why if why == "no_mint_by_cutoff" else "data_missing"
                rec["data"] = {"first_mint": why, "detail": fm_detail}
            else:
                eb = mb + 1
                rpc.mark(stage="entry_block")
                ets = int(blk(eb, rpc=rpc)["timestamp"], 16)
                _bf = blk(eb, rpc=rpc).get("baseFeePerGas")
                base_e = int(_bf, 16) if _bf else None      # 缺失记未知，不记零
                fees["entry"] = base_e
                rpc.mark(stage="state_validation")
                sv = validate_candidate_state(rpc, log, c["index"], c["token"],
                                              c["pair"], [eb])
                rec["state_validation"] = sv
                rec["blocks"] = {"entry": snapshot_block(rpc, lambda b, **k: blk(b, rpc=rpc, **k), eb)}
                if rec["blocks"]["entry"]["failures"]:
                    sv["passed"] = False
                    sv["failures"] += rec["blocks"]["entry"]["failures"]
                if not sv["passed"]:
                    rec["state"] = "state_validation_failed"
                    raise _Blocked()
                rpc.mark(stage="entry_buy")
                buy = V.probe_call(rpc, c["token"], V.ROUTER, eb, ets, V.AMOUNT)
                rec["entry"] = {"entry_block": eb, "entry_ts": ets, "stage": buy["stage"],
                                "classification": buy["classification"],
                                "received": buy["token_after"] - buy["token_before"],
                                "eth_debit": buy["eth_before"] - buy["eth_after"],
                                "base_fee": base_e, "reason": buy["reason"][:80]}
                rec["entry"]["attempts"] = reached_attempts("buy", buy["stage"])
                if buy["stage"] != 0 or buy["token_after"] <= buy["token_before"]:
                    # 规格 v1.2 §3：钱包/持仓模型未获独立验证之前，
                    # 通用 revert 不得升级为「已验证入场失败」。
                    rec["state"] = "entry_unknown"
                    rec["entry"]["classification_note"] = (
                        "generic revert is NOT verified entry failure; "
                        "entry_failed_verified requires independent basis")
                    rec["cost"] = {
                        "A_wei": V.AMOUNT, "R_wei": None,
                        "entry_attempts": rec["entry"]["attempts"],
                        "exit_attempts": {"swap": 0, "approve": 0,
                                          "basis": "no exit attempted"},
                        "G_by_scenario": gas_cost(rec["entry"]["attempts"],
                                                  {"swap": 0, "approve": 0},
                                                  base_e, None),
                        "main_scenario": f"swap{MAIN_SCENARIO[0]}_tip{MAIN_SCENARIO[1]}",
                        "note": "buy gas already spent even though entry outcome unknown"}
                else:
                    target = ets + 30 * V.DAY
                    if SNAPSHOT["timestamp"] < target:
                        rec["state"] = "right_censored"
                        rec["exit"] = {"reason": "exit snapshot beyond finalized head"}
                        raise _Censored()
                    rpc.mark(stage="exit_locate")
                    xb = V.first_true(eb, HEAD, lambda b: int(blk(b, rpc=rpc)["timestamp"], 16) >= target)
                    xts = int(blk(xb, rpc=rpc)["timestamp"], 16)
                    _bfx = blk(xb, rpc=rpc).get("baseFeePerGas")
                    base_x = int(_bfx, 16) if _bfx else None
                    fees["exit"] = base_x
                    amount = buy["token_after"] - buy["token_before"]
                    rec["blocks"]["exit"] = snapshot_block(rpc, lambda b, **k: blk(b, rpc=rpc, **k), xb,
                                                            bracket_target=target)
                    rpc.mark(stage="state_validation_exit")
                    sv2 = validate_candidate_state(rpc, log, c["index"], c["token"],
                                                   c["pair"], [xb])
                    rec["state_validation_exit"] = sv2
                    if rec["blocks"]["exit"]["failures"]:
                        sv2["passed"] = False
                        sv2["failures"] += rec["blocks"]["exit"]["failures"]
                    if not sv2["passed"]:
                        rec["state"] = "state_validation_failed"
                        raise _Blocked()
                    rpc.mark(stage="slot_scan")
                    slot, scan_calls, slot_why = find_slot(rpc, c["token"], xb, args.slot_limit)
                    rec["model"] = {"slot_scan_calls": scan_calls, "slot_status": slot_why,
                                    "slot": slot[0] if slot else None}
                    if slot is None:
                        rec["state"] = "model_unsupported"
                        rec["exit"] = {"exit_block": xb, "exit_ts": xts, "base_fee": base_x,
                                       "attempts": {"swap": 0, "approve": 0,
                                                    "basis": "slot unresolved; no exit attempted"}}
                        rec["cost"] = {
                            "A_wei": V.AMOUNT, "R_wei": None,
                            "entry_attempts": rec["entry"]["attempts"],
                            "exit_attempts": rec["exit"]["attempts"],
                            "base_fee_entry": base_e, "base_fee_exit": base_x,
                            "G_by_scenario": gas_cost(rec["entry"]["attempts"],
                                                      rec["exit"]["attempts"],
                                                      base_e, base_x),
                            "note": "buy cost already incurred"}
                    else:
                        ov = {c["token"]: {"stateDiff": {slot[1]: "0x" + V.pad(amount)}}}
                        rpc.mark(stage="exit_sell")
                        sell = V.probe_call(rpc, c["token"], V.ROUTER, xb, xts, amount,
                                            selling=True, overrides=ov)
                        rec["exit"] = {"exit_block": xb, "exit_ts": xts, "base_fee": base_x,
                                       "stage": sell["stage"], "classification": sell["classification"],
                                       "token_before": sell["token_before"], "token_after": sell["token_after"],
                                       "cash_in": sell["eth_after"] - sell["eth_before"],
                                       "reason": sell["reason"][:80]}
                        # 卖出到达的阶段**在主卖出返回后立即记下**，不能等到诊断之后。
                        # 否则诊断抛异常时，统一收尾会把缺失的 attempts 当成 0，
                        # 把已经发生的 swap 记成"未尝试"（审查 v1.5 反例 2）。
                        # 诊断调用本身不是交易尝试，不进这个计数。
                        rec["exit"]["attempts"] = reached_attempts(
                            "sell", sell["stage"], do_approve=True)
                        # SPEC §2 的充分性判据 H1–H4
                        if sell["stage"] == 0 and sell["token_before"] == amount and sell["token_after"] == 0:
                            rec["state"] = "measured_exit"
                            # 勘误 E1：执行成功【不】证明跨期持仓适配充分。
                            # 反例：unlockAt[buyer]=buyTime+90天，注入余额而锁定字段保持
                            # 默认 0 时卖出会成功并清零，真实买家却应被拒。
                            rec["model"]["holding_state"] = "simulated_completion_under_injection"
                            rec["model"]["holding_state_basis"] = "none_beyond_injection"
                        elif sell["stage"] in (10, 11):
                            rec["state"] = "model_unsupported"
                            rec["model"]["holding_state"] = "injection_not_effective"
                            rec["model"]["holding_state_basis"] = "none_beyond_injection"
                        else:
                            rec["state"] = "execution_reverted_unknown"
                            rec["model"]["holding_state"] = "undetermined"
                            rec["model"]["holding_state_basis"] = "none_beyond_injection"
                            if args.diagnostics and sell["stage"] == 20:
                                d = {}
                                rpc.mark(stage="diag_size_probe")
                                s1 = V.probe_call(rpc, c["token"], V.ROUTER, xb, xts, 1,
                                                  selling=True,
                                                  overrides={c["token"]: {"stateDiff": {slot[1]: "0x" + V.pad(amount)}}})
                                d["size_probe"] = {
                                    "stage": s1["stage"],
                                    "note": "minimum-unit revert does NOT exclude a "
                                            "size-related mechanism (rounding to zero "
                                            "or coexisting limits remain possible)"}
                                rpc.mark(stage="diag_identity_probe")
                                try:
                                    d["identity_probe"] = identity_probe(
                                        rpc, c["token"],
                                        lambda who: V.mapping_key(who, slot[0]),
                                        amount, xb, xts)
                                except (V.RpcFailure, ValueError) as e:
                                    d["identity_probe"] = {"error": str(e)[:120]}
                                rec["model"]["diagnostics"] = d
                                # 诊断调用不计为交易尝试（规格 v1.3 §4）
                                rec["model"]["diagnostics_note"] = (
                                    "diagnostic calls are NOT transaction attempts")
                        # 成本（规格 v1.2 §4）：按实际到达的阶段记，不用固定次数
                        ea = rec["entry"]["attempts"]
                        xa = rec["exit"]["attempts"]        # 主卖出返回时即已记下
                        rec["cost"] = {
                            "A_wei": V.AMOUNT,
                            "R_wei": (rec["exit"].get("cash_in")
                                      if sell["stage"] == 0 else None),
                            "entry_attempts": ea, "exit_attempts": xa,
                            "base_fee_entry": base_e, "base_fee_exit": base_x,
                            "G_by_scenario": gas_cost(ea, xa, base_e, base_x),
                            "main_scenario": f"swap{MAIN_SCENARIO[0]}_tip{MAIN_SCENARIO[1]}",
                            "excluded": "HTTP retries and size/identity probes are NOT "
                                        "transaction attempts"}
        except _Censored:
            pass
        except _Blocked:
            pass
        except EV.BudgetExhausted as e:
            # 全局预算耗尽：该 HTTP **未发出**。标成独立状态，不混进 decode_error。
            rec["state"], rec["data"] = "budget_exhausted", {"budget": str(e)[:160]}
        except V.Unrun as e:
            rec["state"], rec["data"] = "model_unsupported", {"unrun": str(e)[:160]}
        except V.RpcFailure as e:
            rec["state"], rec["data"] = "data_missing", {"rpc_failure": str(e)[:160]}
        except Exception as e:                                            # noqa: BLE001
            rec["state"], rec["data"] = "decode_error", {"error": f"{type(e).__name__}: {str(e)[:160]}"}
        # 买入腿一旦执行过，其成本就已经发生，**不因后续步骤失败而消失**。
        # 上一版只覆盖了「槽位正常返回不支持」，没覆盖槽位查询直接抛异常
        # ——那条路径下 entry 完整、cost 却整个不存在（审查反例 3）。
        if rec.get("entry") and rec.get("cost") is None:
            ea = rec["entry"].get("attempts") or {"swap": 0, "approve": 0,
                                                  "basis": "entry attempts unknown"}
            xa = (rec.get("exit") or {}).get("attempts") or {
                "swap": 0, "approve": 0,
                "basis": "exit leg never attempted; run aborted before the sell"}
            rec["cost"] = {
                "A_wei": V.AMOUNT,
                "R_wei": None,                  # 退出腿未完成 ⇒ 回款未知，独立保留未知
                "entry_attempts": ea, "exit_attempts": xa,
                "base_fee_entry": fees["entry"], "base_fee_exit": fees["exit"],
                "G_by_scenario": gas_cost(ea, xa, fees["entry"], fees["exit"]),
                "main_scenario": f"swap{MAIN_SCENARIO[0]}_tip{MAIN_SCENARIO[1]}",
                "partial": True,
                "note": ("buy leg executed; cost already incurred. "
                         "later stage aborted, so R_wei and exit cost stay UNKNOWN "
                         "— an unknown exit price must not erase the known entry cost")}
        # 注入后复读：代码与余额不得持久化；块 hash 复读防重组
        try:
            used = [b for b in (rec.get("blocks") or {}).values()]
            if used:
                rpc.mark(stage="restore_check")
                before = {}
                for k, v in (rec.get("state_validation") or {}).get("wallet_clean", {}).items():
                    before[k] = v
                for k, v in (rec.get("state_validation_exit") or {}).get("wallet_clean", {}).items():
                    before[k] = v
                bad = verify_wallet_not_persisted(
                    rpc, log, c["index"], [b["number"] for b in used], before)
                # fresh=True：必须发新请求，不能拿缓存自比（审查 D）
                reread = {b["number"]: blk(b["number"], fresh=True, rpc=rpc)["hash"] for b in used}
                moved = [n_ for n_, h_ in reread.items()
                         if h_ != next(x["hash"] for x in used if x["number"] == n_)]
                rec["restore_check"] = {"persisted": bad, "reorged_blocks": moved,
                                        "passed": not bad and not moved}
                if bad or moved:
                    rec["state"] = "state_validation_failed"
        except (V.RpcFailure, StopIteration, KeyError) as e:
            # 必需检查无法完成 ⇒ 不得保留测量结论（审查 E）
            rec["restore_check"] = {"error": str(e)[:120], "passed": False}
            rec["state"] = "state_validation_failed"

        # 没有可审查的状态语义依据之前，任何候选都不得进入经济统计。
        # no_mint / right_censored 等分支本就不会走到入场校验；
        # 缺席不等于失败，只有【实际执行过且失败】才判不通过（审查反例 6）。
        rec["validation_passed"] = bool(
            (rec.get("state_validation") or {}).get("passed", True) is not False
            and (rec.get("state_validation_exit") or {}).get("passed", True) is not False
            and (rec.get("restore_check") or {}).get("passed", True) is not False
            and rec.get("state") != "state_validation_failed")
        rec["economic_eligible"] = False
        rec["economic_eligible_reason"] = (
            "holding-state adequacy unproven; see PILOT_ERRATA_20260910.md E1")
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["rpc_calls"] = len(rpc.records) - c0
        # 全局差值在并行下会把别的候选的调用算进来 —— 按候选归集
        rec["etherscan_calls"] = log.counts_by_candidate.get(("etherscan", c["index"]), 0)
        with res_lock:
            results.append(rec)
        log.resource(candidate=c["index"], stage="end")
        COMPLETE_STATES = {"measured_exit", "execution_reverted_unknown",
                           "no_mint_by_cutoff", "entry_failed_verified", "entry_unknown",
                           "model_unsupported", "right_censored"}
        # 先把逐候选结果落盘（含 fsync），再标"完成"。
        # 否则存在"检查点已标完成、结果却没写下去"的窗口（审查反例 7）。
        #
        # 检查点与证据必须存**同一份字节**：证据写入时会脱敏，检查点若存未脱敏的
        # 原件，两边 hash 天然对不上，续跑时就无法用 hash 把结果与证据钉在一起
        # （审查 v1.5 反例 1）。所以在这里脱敏一次，两处共用。
        # 顺带也堵住了"检查点未过脱敏"这个口子。
        rec = log.redact(rec)
        log.write("candidate_result", candidate=c["index"], record=rec)
        _complete = (rec.get("state") in COMPLETE_STATES
                     and rec.get("validation_passed") is True)
        ckpt.record_attempt(
            c["index"], rec.get("state"),
            completed=_complete,
            # 标"完成"就必须把结果本身连同 hash 一起持久化 ——
            # 否则续跑只知道"做过"，交付不出这一条（审查反例 1）
            result=rec if _complete else None,
            validation_passed=rec.get("validation_passed"),
            rpc_calls=rec["rpc_calls"], elapsed_s=rec["elapsed_s"],
            evidence_run_id=log.run_id,
            evidence_file=str(Path(args.evidence).resolve()),
            result_file=str(Path(args.out).resolve()))
        log.write("candidate_end", candidate=c["index"], state=rec.get("state"),
                  elapsed_s=rec["elapsed_s"], rpc_calls=rec["rpc_calls"],
                  etherscan_calls=rec["etherscan_calls"], record=rec)
        print(f"  [{i}/{len(decl['sample'])}] idx={c['index']} state={rec.get('state')} "
              f"{rec['elapsed_s']}s rpc={rec['rpc_calls']}", flush=True)

    # ---- 调度：串行 or N 路并行。语义共用 handle()，仅调度不同 ----
    if args.parallel <= 1:
        for i, c in enumerate(decl["sample"], 1):
            try:
                handle(i, c, rpc)
            except BaseException as e:                   # noqa: BLE001
                worker_errors.append({"worker": 0, "candidate": c["index"],
                                      "error": f"{type(e).__name__}: {str(e)[:200]}"})
                log.write("worker_error", worker=0, candidate=c["index"],
                          error=f"{type(e).__name__}: {str(e)[:200]}")
    else:
        lanes = [[] for _ in range(args.parallel)]
        for k, c in enumerate(decl["sample"]):
            lanes[k % args.parallel].append((k + 1, c))

        def worker(wid, items):
            threading.current_thread().worker_id = wid
            try:
                own = V.RPC(url, max_calls=args.max_calls,
                            max_seconds=args.max_seconds, rps=10 ** 6)
                tap = EV.RpcTap(own, log, gate=gate, worker=wid)
                with res_lock:
                    taps.append(tap)
            except BaseException as e:                   # noqa: BLE001
                # 连 RPC 都建不起来 ⇒ 本路全部候选都没做，必须逐个记为异常
                with res_lock:
                    for _, c in items:
                        worker_errors.append(
                            {"worker": wid, "candidate": c["index"],
                             "error": f"init: {type(e).__name__}: {str(e)[:160]}"})
                log.write("worker_error", worker=wid, phase="init",
                          error=f"{type(e).__name__}: {str(e)[:160]}")
                return
            for i, c in items:
                try:
                    handle(i, c, tap)
                except BaseException as e:               # noqa: BLE001
                    # 线程里的异常若被吞掉，主进程会把"少了候选"当成成功。
                    with res_lock:
                        worker_errors.append(
                            {"worker": wid, "candidate": c["index"],
                             "error": f"{type(e).__name__}: {str(e)[:200]}"})
                    log.write("worker_error", worker=wid, candidate=c["index"],
                              error=f"{type(e).__name__}: {str(e)[:200]}")

        threads = [threading.Thread(target=worker, args=(w, items), daemon=True)
                   for w, items in enumerate(lanes) if items]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    gate_stats = gate.stats()                 # 串行分支同样受同一预算约束
    log.write("gate_stats", **gate_stats)
    EV.uninstall_http_gate()
    # 续跑交付的是**累计**结果：本次测的 + 检查点里校验通过带过来的。
    # 少了这一步，同一 out 路径续跑会用本次 results 覆盖掉之前的汇总。
    measured_now = {r["index"] for r in results}
    for cand, (res, att) in sorted(carried.items()):
        if cand in measured_now:
            continue
        r = dict(res)
        r["carried_from_checkpoint"] = {
            "attempt": att.get("attempt"), "at": att.get("at"),
            "result_sha256": att.get("result_sha256"),
            "evidence_file": att.get("evidence_file"),
            "evidence_run_id": att.get("evidence_run_id")}
        results.append(r)
    results.sort(key=lambda r: r["index"])
    doc = {"started_at": started_at, "finished_at": V.utcnow(),
           "parallel": args.parallel, "gate_stats": gate_stats,
           "evidence_file": str(args.evidence), "run_id": log.run_id,
           "chain_id": chain_id, "sample_file": str(args.sample),
           "finalized_snapshot": SNAPSHOT,
           "sample_sha256": hashlib.sha256(Path(args.sample).read_bytes()).hexdigest(),
           "package_script_sha256": hashlib.sha256((PKG / "verify_capabilities.py").read_bytes()).hexdigest(),
           "spec": {"path": str(spec_path.name),
                    "sha256": EV.sha256_file(spec_path) if spec_path.is_file() else None},
           "slot_limit": args.slot_limit, "diagnostics": args.diagnostics,
           "total_elapsed_s": round(time.time() - t_all, 1),
           # 必须把各 worker 自己的 V.RPC 记录一并计入，
           # 只数主 tap 会严重少报（审查反例 3）
           "rpc_calls": sum(len(t.records) for t in taps),
           "rpc_calls_by_tap": [len(t.records) for t in taps],
           "results": results}
    # 审查 §5：采集失败/未完成必须阻断，不能全失败仍退出 0
    # data_missing / decode_error 不在其中 —— 它们是未完成，必须阻断
    COMPLETE = {"measured_exit", "execution_reverted_unknown", "no_mint_by_cutoff",
                "entry_failed_verified", "entry_unknown", "model_unsupported",
                "right_censored", "state_validation_failed"}
    incomplete = [r["index"] for r in results if r.get("state") not in COMPLETE]
    declared = [c["index"] for c in decl["sample"]]
    accounted = {r["index"] for r in results}
    missing = [i for i in declared if i not in accounted]
    # 一候选**恰好**一条结果，且字段与冻结样本逐项一致。
    got = [r["index"] for r in results]
    dup_results = sorted({i for i in got if got.count(i) > 1})
    extra = sorted(set(got) - set(declared))
    by_idx = {c["index"]: c for c in decl["sample"]}
    mismatched = []
    for r in results:
        c = by_idx.get(r["index"])
        if c is None:
            continue
        for f in ("pair", "token", "created_block"):
            if r.get(f) != c.get(f):
                mismatched.append({"candidate": r["index"], "field": f,
                                   "sample": c.get(f), "result": r.get(f)})
    failed_validation = [r["index"] for r in results if r.get("validation_passed") is False]
    set_problems = (bool(missing) or bool(worker_errors) or bool(dup_results)
                    or bool(extra) or bool(mismatched))
    doc["acceptance"] = {
        "declared": len(declared), "n": len(results),
        # 「已跳过」不再算进账：跳过的候选必须以**带过来的结果**出现在 results 里，
        # 否则就是静默丢失（审查反例 1）
        "missing_candidates": missing,
        "duplicate_results": dup_results,       # 一候选恰好一条（审查反例 5）
        "unexpected_results": extra,
        "sample_field_mismatch": mismatched,    # 结果与冻结样本逐项一致
        "worker_errors": worker_errors,
        "set_complete": not set_problems,
        "skipped_already_completed": skipped,
        "carried_from_checkpoint": sorted(carried),
        "checkpoint_results_unusable": ckpt_broken,   # 标了完成却拿不出可信结果
        "evidence_chain_problems": evidence_chain,   # 旧证据缺失/损坏
        "resumed": resumed, "checkpoint": str(args.checkpoint),
        "incomplete": incomplete,
        "complete": len(results) - len(incomplete),
        "evidence_records": log.seq,
        "gate": gate_stats,
        "validation_failed": failed_validation,
        "validation_passed": (not failed_validation and not set_problems
                              and not evidence_chain),
        "process_completed": not incomplete and not set_problems,
        "meaning": ("process_completed 仅表示本次采集流程走完且每个候选落到已定义状态；"
                    "它【不】代表测量语义已验证，也【不】代表正式实验验收通过。"),
        "measurement_semantics_verified": False,
        "economic_results_eligible": False}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    # 证据 JSONL 已脱敏，最终结果 JSON 也必须过同一道（审查反例 2）
    doc = log.redact(doc)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.write("run_footer", counts=log.counts, acceptance=doc["acceptance"])
    ckpt.close()
    log.resource(stage="shutdown")
    log.close()
    print(f"\n-> {args.out}\n-> {args.evidence}  ({log.seq} 条证据)")
    if set_problems:
        print(f"候选集合不完整：声明 {len(declared)} 个，实得 {len(results)} 条；"
              f"缺 {missing}；重复 {dup_results}；多余 {extra}；"
              f"与样本字段不符 {len(mismatched)} 处；worker 异常 {len(worker_errors)} 条 —— 阻断",
              file=sys.stderr)
        for e in worker_errors[:5]:
            print(f"    worker{e['worker']} 候选{e['candidate']}: {e['error']}",
                  file=sys.stderr)
        for m in mismatched[:5]:
            print(f"    候选{m['candidate']} {m['field']}: 样本={m['sample']} 结果={m['result']}",
                  file=sys.stderr)
        return 1
    if evidence_chain:
        print(f"证据链不完整 {len(evidence_chain)} 处 —— 结果已从检查点带出，"
              f"但对应证据缺失或损坏，验收不通过：", file=sys.stderr)
        for e in evidence_chain[:5]:
            print(f"    候选{e['candidate']}: {e['reason']} {e.get('path','')}",
                  file=sys.stderr)
        return 1
    if failed_validation:
        print(f"状态校验未通过 {len(failed_validation)} 个：{failed_validation} —— "
              f"必需检查失败或无法完成，验收不通过", file=sys.stderr)
        return 1
    if incomplete:
        print(f"未完成候选 {len(incomplete)} 个：{incomplete} —— 阻断，不得作为正式结果",
              file=sys.stderr)
        return 1
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("declare"); d.add_argument("--n", type=int, default=8); d.add_argument("--out", required=True)
    m = sub.add_parser("measure"); m.add_argument("--sample", required=True); m.add_argument("--out", required=True)
    m.add_argument("--slot-limit", type=int, default=32); m.add_argument("--max-calls", type=int, default=4000)
    m.add_argument("--max-seconds", type=int, default=3000); m.add_argument("--rps", type=float, default=3)
    m.add_argument("--diagnostics", action="store_true", default=True)
    m.add_argument("--evidence", default=None)
    m.add_argument("--parallel", type=int, default=1,
                   help="并行路数。>1 时限流与调用预算由全局闸门共享，不各分一半")
    m.add_argument("--checkpoint", default=None,
                   help="断点续跑检查点（追加式）。绑定样本/规格/脚本/台账/finalized 块")
    m.add_argument("--spec", default="MEASUREMENT_SPEC.v1.6.md",
                   help="按脚本目录定位；缺失即阻断。证据记录该文件的 hash")
    m.add_argument("--pin-finalized", default=None, metavar="块号:块hash",
                   help="把本次运行绑到指定 finalized 状态块（先核验 hash）。"
                        "串行与并行对照用同一值，才能构成同快照对照")
    a = p.parse_args()
    if a.cmd == "measure" and not a.evidence:
        a.evidence = str(Path(a.out).with_suffix("")) + ".evidence.jsonl"
    if a.cmd == "measure" and not a.checkpoint:
        a.checkpoint = str(Path(a.out).with_suffix("")) + ".checkpoint.jsonl"
    sys.exit(declare(a) if a.cmd == "declare" else measure(a))


if __name__ == "__main__":
    main()

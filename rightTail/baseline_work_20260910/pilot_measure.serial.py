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
import evidence as EV                    # noqa: E402

UNIVERSE = Path(__file__).resolve().parent / "universe_run" / "universe.csv"
SEED = 20260910
CUTOFF_BLOCK = 24_781_026               # 配置 §1 的 b_end：首个 Mint 须在窗口结束前
MINT_TOPIC = "0x" + V.keccak(b"Mint(address,uint256,uint256)").hex()
LOG_PAGE = 1000
GAS_SCENARIOS = [(g, t) for g in (120_000, 150_000, 200_000) for t in (0, 10**8, 10**9)]
MAIN_SCENARIO = (150_000, 10**8)
APPROVE_GAS = 50_000


def etherscan(key, log=None, candidate=None, stage=None, **kw):
    """Etherscan 请求 —— 原始响应逐条落盘（审查 §5：证据不能只有汇总）。"""
    kw.update({"chainid": 1, "apikey": key})
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
    if not str(r.get("transactionHash") or "").startswith("0x"):
        return "missing_tx_hash"
    if r.get("logIndex") in (None, ""):
        return "missing_log_index"          # 不得默认为 0
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
    if units is UNKNOWN or price is None:
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
    secrets = {key, url}
    secrets.update(x for x in urllib.parse.urlsplit(url).path.split("/") if len(x) >= 12)
    log = EV.EvidenceLog(args.evidence, secrets=secrets)
    raw = V.RPC(url, max_calls=args.max_calls, max_seconds=args.max_seconds, rps=args.rps)
    rpc = EV.RpcTap(raw, log)
    started_at = V.utcnow()                      # 开始时即固定，不在结束时补写
    log.resource(stage="startup")

    # 审查 §3：链身份必须实测，不能默认。
    rpc.mark(stage="chain_id")
    chain_id = int(rpc.request("eth_chainId", []), 16)
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
    if prior:
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
        universe_sha256=EV.sha256_file(UNIVERSE),
        finalized_number=SNAPSHOT["number"], finalized_hash=SNAPSHOT["hash"])
    done = ckpt.completed() if resumed else set()
    if resumed:
        print(f"续跑：检查点已有 {len(ckpt.attempts())} 条尝试，"
              f"已完成 {len(done)} 个候选，将跳过")
    log.write("checkpoint_state", resumed=resumed, completed=sorted(done),
              prior_attempts=len(ckpt.attempts()))

    # 运行头：在任何候选工作之前写入；台账 hash 与声明不符即拒绝复用。
    EV.run_header(log, script=__file__, spec=args.spec, sample=args.sample,
                  universe=UNIVERSE, declared_universe_sha=decl["universe_sha256"],
                  chain_id=chain_id, snapshot=SNAPSHOT,
                  params={"slot_limit": args.slot_limit, "diagnostics": args.diagnostics,
                          "rps": args.rps, "max_calls": args.max_calls,
                          "max_seconds": args.max_seconds, "cutoff_block": CUTOFF_BLOCK,
                          "amount_wei": V.AMOUNT, "gas_scenarios": len(GAS_SCENARIOS)})
    _bc = {}

    def blk(b, fresh=False):
        """fresh=True 绕过缓存，发新请求。防重组复读必须用它 ——
        旧版收尾复读命中缓存，等于拿同一份数据自比（审查 D）。"""
        if fresh or b not in _bc:
            got = rpc.request("eth_getBlockByNumber", [hex(b), False])
            if not fresh:
                _bc[b] = got
            return got
        return _bc[b]

    t_all = time.time()
    results, skipped = [], []
    for i, c in enumerate(decl["sample"], 1):
        t0, c0 = time.time(), len(rpc.records)
        if c["index"] in done:
            log.write("candidate_skipped", candidate=c["index"], reason="already_completed")
            skipped.append(c["index"])
            continue
        es0 = log.counts.get("etherscan", 0)
        rpc.mark(candidate=c["index"], stage="start")
        log.write("candidate_start", candidate=c["index"], pair=c["pair"],
                  token=c["token"], created_block=c["created_block"], ordinal=i)
        log.resource(candidate=c["index"], stage="start")
        rec = {"index": c["index"], "pair": c["pair"], "token": c["token"],
               "created_block": c["created_block"],
               "trigger": None, "entry": None, "exit": None, "model": None, "data": None}
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
                ets = int(blk(eb)["timestamp"], 16)
                _bf = blk(eb).get("baseFeePerGas")
                base_e = int(_bf, 16) if _bf else None      # 缺失记未知，不记零
                rpc.mark(stage="state_validation")
                sv = validate_candidate_state(rpc, log, c["index"], c["token"],
                                              c["pair"], [eb])
                rec["state_validation"] = sv
                rec["blocks"] = {"entry": snapshot_block(rpc, blk, eb)}
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
                    xb = V.first_true(eb, HEAD, lambda b: int(blk(b)["timestamp"], 16) >= target)
                    xts = int(blk(xb)["timestamp"], 16)
                    _bfx = blk(xb).get("baseFeePerGas")
                    base_x = int(_bfx, 16) if _bfx else None
                    amount = buy["token_after"] - buy["token_before"]
                    rec["blocks"]["exit"] = snapshot_block(rpc, blk, xb,
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
                        xa = reached_attempts("sell", sell["stage"], do_approve=True)
                        rec["exit"]["attempts"] = xa
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
        except V.Unrun as e:
            rec["state"], rec["data"] = "model_unsupported", {"unrun": str(e)[:160]}
        except V.RpcFailure as e:
            rec["state"], rec["data"] = "data_missing", {"rpc_failure": str(e)[:160]}
        except Exception as e:                                            # noqa: BLE001
            rec["state"], rec["data"] = "decode_error", {"error": f"{type(e).__name__}: {str(e)[:160]}"}
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
                reread = {b["number"]: blk(b["number"], fresh=True)["hash"] for b in used}
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
        rec["validation_passed"] = bool(
            (rec.get("state_validation") or {}).get("passed", False) is not False
            and (rec.get("state_validation_exit") or {}).get("passed", True) is not False
            and (rec.get("restore_check") or {}).get("passed", True) is not False
            and rec.get("state") != "state_validation_failed")
        rec["economic_eligible"] = False
        rec["economic_eligible_reason"] = (
            "holding-state adequacy unproven; see PILOT_ERRATA_20260910.md E1")
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["rpc_calls"] = len(rpc.records) - c0
        rec["etherscan_calls"] = log.counts.get("etherscan", 0) - es0
        results.append(rec)
        log.resource(candidate=c["index"], stage="end")
        COMPLETE_STATES = {"measured_exit", "execution_reverted_unknown",
                           "no_mint_by_cutoff", "entry_failed_verified", "entry_unknown",
                           "model_unsupported", "right_censored"}
        ckpt.record_attempt(
            c["index"], rec.get("state"),
            completed=(rec.get("state") in COMPLETE_STATES
                       and rec.get("validation_passed") is True),
            validation_passed=rec.get("validation_passed"),
            rpc_calls=rec["rpc_calls"], elapsed_s=rec["elapsed_s"],
            evidence_run_id=log.run_id)
        log.write("candidate_end", candidate=c["index"], state=rec.get("state"),
                  elapsed_s=rec["elapsed_s"], rpc_calls=rec["rpc_calls"],
                  etherscan_calls=rec["etherscan_calls"], record=rec)
        print(f"  [{i}/{len(decl['sample'])}] idx={c['index']} state={rec.get('state')} "
              f"{rec['elapsed_s']}s rpc={rec['rpc_calls']}", flush=True)
    doc = {"started_at": started_at, "finished_at": V.utcnow(),
           "evidence_file": str(args.evidence), "run_id": log.run_id,
           "chain_id": chain_id, "sample_file": str(args.sample),
           "finalized_snapshot": SNAPSHOT,
           "sample_sha256": hashlib.sha256(Path(args.sample).read_bytes()).hexdigest(),
           "package_script_sha256": hashlib.sha256((PKG / "verify_capabilities.py").read_bytes()).hexdigest(),
           "spec": "MEASUREMENT_SPEC.md v1 (draft)",
           "slot_limit": args.slot_limit, "diagnostics": args.diagnostics,
           "total_elapsed_s": round(time.time() - t_all, 1),
           "rpc_calls": len(rpc.records),
           "results": results}
    # 审查 §5：采集失败/未完成必须阻断，不能全失败仍退出 0
    # data_missing / decode_error 不在其中 —— 它们是未完成，必须阻断
    COMPLETE = {"measured_exit", "execution_reverted_unknown", "no_mint_by_cutoff",
                "entry_failed_verified", "entry_unknown", "model_unsupported",
                "right_censored", "state_validation_failed"}
    incomplete = [r["index"] for r in results if r.get("state") not in COMPLETE]
    failed_validation = [r["index"] for r in results if r.get("validation_passed") is False]
    doc["acceptance"] = {
        "n": len(results), "skipped_already_completed": skipped,
        "resumed": resumed, "checkpoint": str(args.checkpoint),
        "incomplete": incomplete,
        "complete": len(results) - len(incomplete),
        "evidence_records": log.seq,
        "validation_failed": failed_validation,
        "validation_passed": not failed_validation,
        "process_completed": not incomplete,
        "meaning": ("process_completed 仅表示本次采集流程走完且每个候选落到已定义状态；"
                    "它【不】代表测量语义已验证，也【不】代表正式实验验收通过。"),
        "measurement_semantics_verified": False,
        "economic_results_eligible": False}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.write("run_footer", counts=log.counts, acceptance=doc["acceptance"])
    ckpt.close()
    log.resource(stage="shutdown")
    log.close()
    print(f"\n-> {args.out}\n-> {args.evidence}  ({log.seq} 条证据)")
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
    m.add_argument("--checkpoint", default=None,
                   help="断点续跑检查点（追加式）。绑定样本/规格/脚本/台账/finalized 块")
    m.add_argument("--spec", default="MEASUREMENT_SPEC.v1.4.md",
                   help="按脚本目录定位；缺失即阻断。证据记录该文件的 hash")
    a = p.parse_args()
    if a.cmd == "measure" and not a.evidence:
        a.evidence = str(Path(a.out).with_suffix("")) + ".evidence.jsonl"
    if a.cmd == "measure" and not a.checkpoint:
        a.checkpoint = str(Path(a.out).with_suffix("")) + ".checkpoint.jsonl"
    sys.exit(declare(a) if a.cmd == "declare" else measure(a))


if __name__ == "__main__":
    main()

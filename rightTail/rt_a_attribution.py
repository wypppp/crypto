#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RT-A 第一周：身份归因可行性门（只读取数，不涉及价格、不涉及收益、不下单）  v2

本脚本只回答一个问题：
    在候选出现的那一刻，RT-A 所需的身份与历史信息，能不能及时、可靠地取得？

它【不】回答：RT-A 有没有 edge、筛选有没有用、能不能赚钱。

------------------------------------------------------------------------------
v2 相对 v1 的修改（v1 的对应缺陷会让报出的低覆盖率由脚本自身决定，而不是由数据源决定）

[崩溃] forward 的 INSERT 占位符 28 个、表 29 列 —— 第一个候选就抛。
       结构性修复：所有写入改成【具名列 + 字典绑定】，列数漂移在语法上不再可能。

[口径] no_history 曾被算进"不可用"。"确认这个创建者没有前科"是一个已判完的答案，
       不是缺失。联合覆盖率现在接受 ok 与 no_history；真正的不可用只有
       history_truncated / api_failure / timeout / ambiguous。

[口径] HIST_SAMPLED_FULLY 在以太坊上几乎恒为 False，于是所有零关联候选一律被记
       history_truncated，把上一条再放大一次。现在按通道判：外部通道（创建者历史
       部署）给出确定答案时就是确定答案，自足通道的抽样上限只影响自足通道本身。

[口径] probe 对历史 eth_getCode 只检查"不报错"。非归档节点的典型失败是不报错地
       返回错误内容。现在对 factory 自己跑一次双向断言（创建区块-1 必须为 0x，
       创建区块必须非空）；不满足则把 L2b 整条标为 data_source_unavailable，
       而不是逐候选记成 no_history / history_truncated。

[性能] l2b 曾对创建区块的每一笔交易各取一次回执（150-200 次 RPC/候选）。现在改成
       eth_getLogs(address=token, 单区块) → 命中则 1-2 次调用；未命中再试
       eth_getBlockReceipts（1 次）；都不行才退化到逐笔回执并带上限与提前退出。

[数据] L3 曾用 bn+50000 单次 getLogs，超出多数供应商 10k 上限。现在分块 + 首个
       Mint 即停 + 区分 api_failure 与 no_history。
[数据] L4 只取前 20 笔却在找不到入账时返回 no_history。现在分页打满即记
       history_truncated。
[数据] creator 历史部署曾只数 to 为空的外部交易，漏掉工厂内 CREATE/CREATE2
       （新币的主流方式）。现在同时数 txlistinternal 里 type=create 的记录。
[数据] 通道乙 JOIN 正在写入的表，存在处理顺序偏置。改为主循环结束后的第二遍统一重算。
[数据] forward 曾把 token_had_prior_pair 硬写 0，污染报告【5】。现在写 NULL，
       且报告【5】只统计 backfill 行。
[性能] block_timestamps 曾对 2.5M 区块内的全部历史事件逐块取时间戳，而历史比较用的
       是 block_number。现在只对候选区间取时间戳。
[审计] report 曾打当前 spec_hash 而不是采数时那次。现在每行存 spec_hash，报告按
       哈希分组并在混用时明确告警。
[计时] 曾把"单候选处理耗时"报成"从事件到全部链路返回"。现在两个量分开存、分开报。

------------------------------------------------------------------------------
依赖：  pip install requests "eth-utils" "eth-hash[pycryptodome]"
运行：
    python rt_a_attribution.py selftest              # 离线自测，不需要网络
    python rt_a_attribution.py probe
    python rt_a_attribution.py backfill
    python rt_a_attribution.py forward --minutes 120
    python rt_a_attribution.py report
"""

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

# ---- 事件 topic0：优先运行时 keccak；后端缺失则退回已核对常量 ----
_FALLBACK_TOPICS = {
    "PairCreated(address,address,address,uint256)":
        "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9",
    "Transfer(address,address,uint256)":
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "Mint(address,uint256,uint256)":
        "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f",
}
TOPIC_SOURCE = "runtime_keccak"
try:
    from eth_utils import keccak as _keccak
    _keccak(text="x")

    def topic0(sig):
        return "0x" + _keccak(text=sig).hex()
except Exception:                                                  # noqa: BLE001
    TOPIC_SOURCE = "verified_constant_fallback"
    print('[warn] keccak 后端不可用，改用已校验常量（topic0 仍然正确，只是不再运行时计算）。\n'
          '[warn] 恢复运行时计算需要【两个】包，缺一不可：\n'
          '[warn]     pip install eth-utils "eth-hash[pycryptodome]"\n'
          '[warn] 只装 eth-hash 不够 —— 本脚本 import 的是 eth_utils.keccak。',
          file=sys.stderr)

    def topic0(sig):
        return _FALLBACK_TOPICS[sig]


# =============================================================================
# 冻结规格
# =============================================================================
SPEC = {
    "spec_version": "rt-a-feasibility-v3.1",
    "purpose": "身份归因可行性门；不测收益",
    "chain": os.environ.get("RTA_CHAIN", "ethereum"),
    "chains": {
        # 已核对 Uniswap 官方 v2-deployments；probe 仍在链上校验，不信任写死值
        "ethereum": {"chain_id": 1,
                     "factory": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                     "rpc_env": "RTA_RPC_ETH", "etherscan_free_tier": True},
        "base": {"chain_id": 8453,
                 "factory": "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
                 "rpc_env": "RTA_RPC_BASE", "etherscan_free_tier": False},
    },
    "candidate_from_block": int(os.environ.get("RTA_FROM_BLOCK", "0")),
    "candidate_to_block": int(os.environ.get("RTA_TO_BLOCK", "0")),
    "history_lookback_blocks": int(os.environ.get("RTA_LOOKBACK", "2500000")),
    "decision_window_seconds": int(os.environ.get("RTA_DEADLINE", "300")),
    "max_candidates": int(os.environ.get("RTA_MAX", "400")),
    "hist_sender_cap": int(os.environ.get("RTA_HIST_SENDERS", "3000")),
    "audit_sample_size": 20,
    "random_seed": 20260906,
    # 联合覆盖率所依据的字段组合
    "required_fields_for_rule": ["pair_created_tx_sender", "token_creator",
                                 "creator_prior_activity_known"],
    # 哪些状态算"已判完"（可用），哪些算"不可用"
    "decisive_statuses": ["ok", "no_history"],
    "unavailable_statuses": ["history_truncated", "api_failure", "timeout", "ambiguous"],
    # 归因口径的标识符。它不是开关，是"这批数据是按哪一版规则算出来的"的记号——
    # 改了 attribute() 里 token_creator 的取值规则，就要改这里，否则两版数据会
    # 带着同一个 spec_hash 混进同一个库而报告不告警（v2→v3 就发生过）。
    "attribution_rule": "creator-from-ok-status-only-v3.1-no-unknown-subject-claims",
    # forward 的回看窗口。此前硬编码 500_000，既与 backfill 的 2.5M 不同，
    # 又不进 spec_hash —— 两个模式的 L2b history_truncated 门槛因此不可比。
    # 默认与 backfill 取同一个值，两份报告的 L2b 覆盖率才可比；
    # 只有显式设了 RTA_FWD_LOOKBACK 才分叉，那时报告会告警。
    "forward_lookback_blocks": int(os.environ.get(
        "RTA_FWD_LOOKBACK", os.environ.get("RTA_LOOKBACK", "2500000"))),
    "rpc_qps": float(os.environ.get("RTA_RPC_QPS", "8")),
    "etherscan_qps": float(os.environ.get("RTA_SCAN_QPS", "4")),
    "log_chunk_blocks": int(os.environ.get("RTA_LOG_CHUNK", "2000")),
    "l2b_receipt_scan_cap": int(os.environ.get("RTA_RECEIPT_CAP", "40")),
    "l3_scan_blocks": int(os.environ.get("RTA_L3_SCAN", "20000")),
}

OUTDIR = os.environ.get("RTA_OUT", "./rt_a_out")
DB_PATH = os.path.join(OUTDIR, "rt_a.sqlite")
ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
ZERO40 = "0x" + "0" * 40

TOPIC_PAIR_CREATED = topic0("PairCreated(address,address,address,uint256)")
TOPIC_MINT = topic0("Mint(address,uint256,uint256)")
TOPIC_TRANSFER = topic0("Transfer(address,address,uint256)")

# 全局：L2b 这条链路本身是否可用（由 probe / backfill 开头的 factory 自测决定）
L2B_USABLE = None
L2B_NOTE = ""

# forward 轮询节奏（selftest 会置零，避免自测空转等待）
POLL_SLEEP = 8.0
IDLE_SLEEP = 5.0


# =============================================================================
# 基础设施
# =============================================================================
class Limiter:
    def __init__(self, qps):
        self.min_gap = 1.0 / qps if qps > 0 else 0.0
        self.last = 0.0

    def wait(self):
        gap = time.monotonic() - self.last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last = time.monotonic()


rpc_limiter = Limiter(SPEC["rpc_qps"])
scan_limiter = Limiter(SPEC["etherscan_qps"])
_session = requests.Session()
_rpc_id = [0]
RPC_CALLS = [0]


def chain_cfg():
    return SPEC["chains"][SPEC["chain"]]


def rpc_url():
    env = chain_cfg()["rpc_env"]
    url = os.environ.get(env, "")
    if not url:
        raise SystemExit(f"请设置环境变量 {env} 为一个 {SPEC['chain']} 的 JSON-RPC 端点")
    return url


def rpc(method, params, timeout=30, retries=3):
    """返回 (result, error)。不抛异常——失败也是数据。"""
    _rpc_id[0] += 1
    RPC_CALLS[0] += 1
    payload = {"jsonrpc": "2.0", "id": _rpc_id[0], "method": method, "params": params}
    last = None
    for a in range(retries):
        rpc_limiter.wait()
        try:
            r = _session.post(rpc_url(), json=payload, timeout=timeout)
            if r.status_code != 200:
                last = f"http {r.status_code}"
                time.sleep(1.5 * (a + 1))
                continue
            j = r.json()
            if "error" in j:
                return None, f"rpc_error {j['error'].get('code')} {j['error'].get('message')}"
            return j.get("result"), None
        except Exception as e:                                      # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (a + 1))
    return None, last or "unknown"


def etherscan(module, action, **kw):
    if not ETHERSCAN_KEY:
        return None, "no_api_key"
    p = {"chainid": chain_cfg()["chain_id"], "module": module,
         "action": action, "apikey": ETHERSCAN_KEY}
    p.update(kw)
    scan_limiter.wait()
    try:
        j = _session.get(ETHERSCAN_V2, params=p, timeout=30).json()
    except Exception as e:                                          # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if str(j.get("status", "")) == "1":
        return j.get("result"), None
    txt = (str(j.get("message", "")) + " " + str(j.get("result", ""))).lower()
    if "no transactions found" in txt or "no records found" in txt:
        return [], None
    return None, f"status0: {j.get('message')} | {str(j.get('result'))[:180]}"


def as_rows(r):
    """Etherscan 的 result 可能是 list / dict / 字符串。形状不对返回 None，
    由调用方记成 api_failure —— 绝不让它抛异常穿出去。"""
    if isinstance(r, list):
        return r if all(isinstance(x, dict) for x in r) else None
    if isinstance(r, dict):
        return [r]
    return None


def hex_int(x):
    return None if x is None else (x if isinstance(x, int) else int(x, 16))


def topic_to_addr(t):
    return ("0x" + t[-40:]).lower()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_out():
    os.makedirs(OUTDIR, exist_ok=True)


def spec_hash():
    core = {k: v for k, v in SPEC.items()}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()[:16]


# =============================================================================
# 数据库 —— 所有写入用具名列，杜绝列数漂移
# =============================================================================
ATTR_COLS = [
    "pair", "spec_hash", "mode", "fetched_at", "event_time", "decision_deadline",
    "pair_created_tx_sender", "pair_created_tx_to", "l1_status",
    "token_creator", "token_creation_tx", "l2_source",
    "l2a_creator", "l2a_status", "l2b_creator", "l2b_status", "l2_agree",
    "first_mint_tx_sender", "first_mint_event_sender", "lp_token_recipient",
    "first_mint_block", "l3_status",
    "earliest_observed_inbound", "earliest_inbound_block", "l4_status", "l4_subject",
    "deploy_kind", "creator_status",
    "creator_prior_pairs_in_sample", "sender_prior_pairs", "creator_prior_deploys",
    "creator_prior_activity_known", "earliest_prior_block",
    "processing_seconds", "resolution_lag_seconds",
]

DDL = f"""
CREATE TABLE IF NOT EXISTS candidates (
  pair TEXT PRIMARY KEY, chain TEXT, factory TEXT, token0 TEXT, token1 TEXT,
  block_number INTEGER, log_index INTEGER, tx_hash TEXT, event_time INTEGER,
  in_candidate_range INTEGER, new_token TEXT, token_had_prior_pair INTEGER
);
CREATE TABLE IF NOT EXISTS hist_sender (
  pair TEXT PRIMARY KEY, block_number INTEGER, tx_sender TEXT
);
CREATE TABLE IF NOT EXISTS attribution (
  {', '.join(c + (' TEXT PRIMARY KEY' if c == 'pair' else '') for c in ATTR_COLS)}
);
CREATE INDEX IF NOT EXISTS ix_hs ON hist_sender(tx_sender, block_number);
CREATE INDEX IF NOT EXISTS ix_at ON attribution(token_creator);
CREATE TABLE IF NOT EXISTS capability (
  probed_at TEXT, chain TEXT, source TEXT, ok INTEGER, detail TEXT
);
"""


def migrate(con):
    """
    DDL 用的是 CREATE TABLE IF NOT EXISTS —— 表已存在时新增的列不会被建出来，
    于是旧版本建的库会在 upsert_attr 跑到一半时抛
    "table attribution has no column named ..."。这里在连接时就补齐。
    旧版本写入的行在新列上是 NULL；它们的 spec_hash 与当前不同，报告会告警。
    """
    have = {d[1] for d in con.execute("PRAGMA table_info(attribution)")}
    added = [c for c in ATTR_COLS if c not in have]
    for c in added:
        con.execute(f"ALTER TABLE attribution ADD COLUMN {c}")
    if added:
        con.commit()
        print(f"[migrate] attribution 补列 {len(added)} 个：{', '.join(added)}\n"
              f"[migrate] 旧行在这些列上为 NULL。若这个库里混有旧版本的数据，"
              f"报告的 spec_hash 一行会告警——那两批数据不是一次实验。",
              file=sys.stderr)
    return added


def db():
    ensure_out()
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)
    migrate(con)
    return con


def upsert_attr(con, row):
    row = {k: row.get(k) for k in ATTR_COLS}
    cols = ", ".join(ATTR_COLS)
    binds = ", ".join(":" + c for c in ATTR_COLS)
    con.execute(f"INSERT OR REPLACE INTO attribution ({cols}) VALUES ({binds})", row)


# =============================================================================
# L2b 自测：非归档节点常见的失败方式是"不报错地返回错误内容"
# =============================================================================
def l2b_self_test():
    """对 factory 自己二分一次，双向断言。返回 (usable: bool, note: str)。"""
    global L2B_USABLE, L2B_NOTE
    cfg = chain_cfg()
    head, err = rpc("eth_blockNumber", [])
    if err:
        L2B_USABLE, L2B_NOTE = False, f"eth_blockNumber 失败: {err}"
        return L2B_USABLE, L2B_NOTE
    hi = hex_int(head)
    lo = 1
    c_hi, e = rpc("eth_getCode", [cfg["factory"], hex(hi)])
    if e or not c_hi or c_hi == "0x":
        L2B_USABLE, L2B_NOTE = False, f"factory 在最新块无代码（err={e}）"
        return L2B_USABLE, L2B_NOTE
    c_lo, e = rpc("eth_getCode", [cfg["factory"], hex(lo)])
    if e:
        L2B_USABLE, L2B_NOTE = False, f"历史块 getCode 报错: {e}"
        return L2B_USABLE, L2B_NOTE
    if c_lo and c_lo != "0x":
        L2B_USABLE, L2B_NOTE = False, (
            "block=1 就返回了非空代码 —— 节点很可能对历史块返回最新状态（非归档）")
        return L2B_USABLE, L2B_NOTE
    a, b = lo, hi
    while a + 1 < b:
        m = (a + b) // 2
        c, e = rpc("eth_getCode", [cfg["factory"], hex(m)])
        if e:
            L2B_USABLE, L2B_NOTE = False, f"二分中 getCode 报错: {e}"
            return L2B_USABLE, L2B_NOTE
        if c and c != "0x":
            b = m
        else:
            a = m
    cb = b
    c_before, _ = rpc("eth_getCode", [cfg["factory"], hex(cb - 1)])
    c_at, _ = rpc("eth_getCode", [cfg["factory"], hex(cb)])
    ok = (c_before in (None, "0x")) and bool(c_at) and c_at != "0x"
    L2B_USABLE = bool(ok)
    L2B_NOTE = (f"factory 创建区块定位为 {cb}；双向断言{'通过' if ok else '失败'}"
                f"（cb-1 空={c_before in (None, '0x')}, cb 非空={bool(c_at) and c_at != '0x'}）")
    return L2B_USABLE, L2B_NOTE


# =============================================================================
# probe
# =============================================================================
def probe():
    con = db()
    cfg = chain_cfg()
    rows = []

    def rec(src, ok, detail):
        rows.append((now_iso(), SPEC["chain"], src, 1 if ok else 0,
                     json.dumps(detail, ensure_ascii=False)))
        print(f"[{'OK  ' if ok else 'FAIL'}] {src}: "
              f"{json.dumps(detail, ensure_ascii=False)[:200]}")

    t0 = time.time()
    head, err = rpc("eth_blockNumber", [])
    head_n = hex_int(head) if head else None
    rec("rpc.eth_blockNumber", err is None,
        {"head": head_n, "err": err, "latency_s": round(time.time() - t0, 3)})

    code, err = rpc("eth_getCode", [cfg["factory"], "latest"])
    rec("factory.code_present", bool(code) and code != "0x",
        {"factory": cfg["factory"], "code_len": len(code or ""), "err": err})

    res, err = rpc("eth_call", [{"to": cfg["factory"], "data": "0x574f2ba3"}, "latest"])
    n = hex_int(res) if res and res != "0x" else None
    rec("factory.allPairsLength", bool(n), {"allPairsLength": n, "err": err})

    if head_n:
        logs, err = rpc("eth_getLogs", [{
            "address": cfg["factory"], "topics": [TOPIC_PAIR_CREATED],
            "fromBlock": hex(head_n - SPEC["log_chunk_blocks"]), "toBlock": hex(head_n)}])
        rec("rpc.eth_getLogs", err is None,
            {"span": SPEC["log_chunk_blocks"], "n": len(logs or []), "err": err,
             "topic0": TOPIC_PAIR_CREATED, "topic0_source": TOPIC_SOURCE})

    # L2b 双向断言（不是"没报错就算通过"）
    ok, note = l2b_self_test()
    rec("l2b.archive_bidirectional_assert", ok,
        {"note": note,
         "含义": "不通过时 L2b 整条标 api_failure（数据源限制），"
                 "而不是逐候选记 no_history/history_truncated"})

    br, err = rpc("eth_getBlockReceipts", [hex(head_n)] if head_n else ["latest"])
    rec("rpc.eth_getBlockReceipts", err is None and br is not None,
        {"err": err, "note": "支持则 L2b 回退路径为 1 次调用；不支持则退化到逐笔回执（有上限）"})

    if not ETHERSCAN_KEY:
        rec("etherscan.key", False, {"note": "未设置 ETHERSCAN_API_KEY；L2a/L4/历史部署全记 api_failure"})
    else:
        r, e = etherscan("contract", "getcontractcreation", contractaddresses=cfg["factory"])
        rec("etherscan.getcontractcreation", e is None,
            {"chain_id": cfg["chain_id"], "free_tier_per_docs": cfg["etherscan_free_tier"],
             "sample": str(r)[:160], "err": e,
             "note": "官方支持表：Base(8453) 为 Paid Tier Only"})
        r, e = etherscan("account", "txlist", address=cfg["factory"],
                         startblock=0, endblock=99999999, page=1, offset=1, sort="asc")
        rec("etherscan.txlist", e is None, {"err": e})
        r, e = etherscan("account", "txlistinternal", address=cfg["factory"],
                         startblock=0, endblock=99999999, page=1, offset=1, sort="asc")
        rec("etherscan.txlistinternal", e is None,
            {"err": e, "note": "工厂内 CREATE/CREATE2 部署要靠它才数得到"})

    con.executemany("INSERT INTO capability VALUES (?,?,?,?,?)", rows)
    con.commit()
    out = {"probed_at": now_iso(), "spec_hash": spec_hash(), "chain": SPEC["chain"],
           "chain_id": cfg["chain_id"], "head_block": head_n,
           "topic0_source": TOPIC_SOURCE, "l2b_usable": L2B_USABLE, "l2b_note": L2B_NOTE,
           "results": [{"source": r[2], "ok": bool(r[3]), "detail": json.loads(r[4])}
                       for r in rows],
           "suggested_candidate_range":
               ({"from_block": head_n - 200_000, "to_block": head_n - 100_000}
                if head_n else None)}
    p = os.path.join(OUTDIR, "capability_report.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n→ {p}\n→ 把 suggested_candidate_range 填进 RTA_FROM_BLOCK / RTA_TO_BLOCK 再跑 backfill")


# =============================================================================
# 日志与解析
# =============================================================================
BASE_ASSETS = {
    "ethereum": {"0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
                 "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                 "0xdac17f958d2ee523a2206206994597c13d831ec7",
                 "0x6b175474e89094c44da98b954eedeac495271d0f"},
    "base": {"0x4200000000000000000000000000000000000006",
             "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
}


def fetch_pair_created(a, b):
    cfg, chunk, out = chain_cfg(), SPEC["log_chunk_blocks"], []
    while a <= b:
        e = min(a + chunk - 1, b)
        logs, err = rpc("eth_getLogs", [{"address": cfg["factory"],
                                         "topics": [TOPIC_PAIR_CREATED],
                                         "fromBlock": hex(a), "toBlock": hex(e)}])
        if err and chunk > 200:
            half = max(200, chunk // 2)
            e2 = min(a + half - 1, b)
            logs, err2 = rpc("eth_getLogs", [{"address": cfg["factory"],
                                              "topics": [TOPIC_PAIR_CREATED],
                                              "fromBlock": hex(a), "toBlock": hex(e2)}])
            if err2 is None:
                err, e = None, e2
        if err:
            print(f"  ! {a}-{e} 日志失败: {err}（记为缺口）", file=sys.stderr)
            out.append({"_gap": [a, e], "_err": err})
        else:
            out.extend(logs or [])
        print(f"  .. {a}-{e}  累计 {sum(1 for o in out if '_gap' not in o)}", end="\r")
        a = e + 1
    print()
    return out


def parse_pair_created(lg):
    d = lg["data"][2:]
    return (topic_to_addr(lg["topics"][1]), topic_to_addr(lg["topics"][2]),
            ("0x" + d[24:64]).lower())


def pick_new_token(t0, t1):
    base = BASE_ASSETS.get(SPEC["chain"], set())
    if t0 in base and t1 not in base:
        return t1
    if t1 in base and t0 not in base:
        return t0
    return None


# =============================================================================
# 四条归因链路
# =============================================================================
def l1_tx_sender(tx_hash):
    tx, err = rpc("eth_getTransactionByHash", [tx_hash])
    if err or not tx:
        return None, None, "api_failure"
    return (tx.get("from") or "").lower() or None, (tx.get("to") or "").lower() or None, "ok"


def l2a_creator(token):
    r, e = etherscan("contract", "getcontractcreation", contractaddresses=token)
    if e:
        return None, None, "api_failure"
    rows = as_rows(r)
    if rows is None:
        return None, None, "api_failure"        # 形状异常按接口失败记
    if not rows:
        return None, None, "no_history"
    row = rows[0]
    return (row.get("contractCreator") or "").lower() or None, row.get("txHash"), "ok"


def l2b_creator(token, lo, hi):
    """
    纯 RPC 创建归因。调用量：约 log2(区间) 次 getCode + 1~2 次定位调用。
    L2B_USABLE 为 False（非归档等）时直接返回 api_failure —— 这是数据源限制，
    不能记成 no_history 或 history_truncated。
    """
    if L2B_USABLE is False:
        return None, None, "api_failure", "unknown"
    c_hi, err = rpc("eth_getCode", [token, hex(hi)])
    if err:
        return None, None, "api_failure", "unknown"
    if not c_hi or c_hi == "0x":
        return None, None, "no_history", "unknown"
    c_lo, err = rpc("eth_getCode", [token, hex(lo)])
    if err:
        return None, None, "api_failure", "unknown"
    if c_lo and c_lo != "0x":
        return None, None, "history_truncated", "unknown"   # 创建早于回看窗口
    a, b = lo, hi
    while a + 1 < b:
        m = (a + b) // 2
        c, err = rpc("eth_getCode", [token, hex(m)])
        if err:
            return None, None, "api_failure", "unknown"
        if c and c != "0x":
            b = m
        else:
            a = m
    cb = b

    # 便宜路径 1：该区块内 token 自己发出的日志 → 一次调用锁定交易
    logs, err = rpc("eth_getLogs", [{"address": token,
                                     "fromBlock": hex(cb), "toBlock": hex(cb)}])
    if not err and logs:
        txh = logs[0]["transactionHash"]
        tx, e2 = rpc("eth_getTransactionByHash", [txh])
        if not e2 and tx:
            direct = (tx.get("to") or "") in ("", None)
            # 工厂部署时该地址只是"发起那笔交易的人"，不是合约创建者 → ambiguous
            return ((tx.get("from") or "").lower(), txh,
                    "ok" if direct else "ambiguous", "direct" if direct else "factory")

    # 便宜路径 2：整块回执一次拿完
    brs, err = rpc("eth_getBlockReceipts", [hex(cb)])
    if not err and brs:
        for r in brs:
            if (r.get("contractAddress") or "").lower() == token:
                tx, _ = rpc("eth_getTransactionByHash", [r["transactionHash"]])
                return ((tx or {}).get("from", "").lower() or None,
                        r["transactionHash"], "ok", "direct")
        return None, None, "ambiguous", "factory"

    # 退化路径：逐笔回执，带上限与提前退出
    blk, err = rpc("eth_getBlockByNumber", [hex(cb), True])
    if err or not blk:
        return None, None, "api_failure", "unknown"
    for i, tx in enumerate(blk.get("transactions", [])):
        if i >= SPEC["l2b_receipt_scan_cap"]:
            return None, None, "history_truncated", "unknown"   # 扫描上限，不是"没有"
        rc, e2 = rpc("eth_getTransactionReceipt", [tx["hash"]])
        if e2 or not rc:
            continue
        if (rc.get("contractAddress") or "").lower() == token:
            return (tx.get("from") or "").lower(), tx["hash"], "ok", "direct"
    return None, None, "ambiguous", "unknown"


def l3_first_mint(pair, bn):
    """分块扫，找到第一个 Mint 即停；区分 api_failure 与 no_history。"""
    chunk = SPEC["log_chunk_blocks"]
    end = bn + SPEC["l3_scan_blocks"]
    a, any_err = bn, False
    while a <= end:
        e = min(a + chunk - 1, end)
        logs, err = rpc("eth_getLogs", [{"address": pair, "topics": [TOPIC_MINT],
                                         "fromBlock": hex(a), "toBlock": hex(e)}])
        if err:
            any_err = True
            a = e + 1
            continue
        if logs:
            lg = sorted(logs, key=lambda x: (hex_int(x["blockNumber"]),
                                             hex_int(x["logIndex"])))[0]
            out = {"first_mint_event_sender": topic_to_addr(lg["topics"][1]),
                   "first_mint_block": hex_int(lg["blockNumber"])}
            tx, e1 = rpc("eth_getTransactionByHash", [lg["transactionHash"]])
            out["first_mint_tx_sender"] = ((tx or {}).get("from") or "").lower() or None
            rc, e2 = rpc("eth_getTransactionReceipt", [lg["transactionHash"]])
            lp = None
            if rc and not e2:
                for l2 in rc.get("logs", []):
                    if ((l2.get("address") or "").lower() == pair
                            and l2.get("topics") and l2["topics"][0].lower() == TOPIC_TRANSFER
                            and len(l2["topics"]) >= 3
                            and topic_to_addr(l2["topics"][1]) == ZERO40):
                        lp = topic_to_addr(l2["topics"][2])
                        break
            out["lp_token_recipient"] = lp
            return out, ("ok" if lp else "ambiguous")
        a = e + 1
    return {}, ("api_failure" if any_err else "no_history")


def l4_earliest_inbound(address, before_block):
    if not address:
        return None, None, "not_applicable"
    page = 200
    r, e = etherscan("account", "txlist", address=address, startblock=0,
                     endblock=before_block, page=1, offset=page, sort="asc")
    rows = as_rows(r) if e is None else None
    if rows is None:
        return None, None, "api_failure"
    if not rows:
        return None, None, "no_history"
    r = rows
    for t in r:
        if (t.get("to") or "").lower() == address and int(t.get("value", "0")) > 0:
            return (t.get("from") or "").lower(), int(t.get("blockNumber", 0)), "ok"
    # 分页打满却没找到入账 → 看不到更早，不是"没有"
    return None, None, ("history_truncated" if len(r) >= page else "no_history")


def creator_prior_deploys(address, before_block):
    """
    该地址在 before_block 之前的部署次数。
    外部部署（to 为空）+ 工厂内部 CREATE/CREATE2（txlistinternal type=create）都数。
    返回 (count, earliest_block, status)
    """
    if not address:
        return None, None, "not_applicable"
    total, earliest, truncated, any_ok = 0, None, False, False
    page = 5000
    r, e = etherscan("account", "txlist", address=address, startblock=0,
                     endblock=max(0, before_block - 1), page=1, offset=page, sort="asc")
    rows = as_rows(r) if e is None else None
    if rows is not None:
        any_ok = True
        r = rows
        d = [t for t in r if not (t.get("to") or "").strip()]
        total += len(d)
        if d:
            earliest = min(int(t["blockNumber"]) for t in d)
        truncated |= len(r) >= page
    r2, e2 = etherscan("account", "txlistinternal", address=address, startblock=0,
                       endblock=max(0, before_block - 1), page=1, offset=page, sort="asc")
    rows2 = as_rows(r2) if e2 is None else None
    if rows2 is not None:
        any_ok = True
        r2 = rows2
        d2 = [t for t in r2 if (t.get("type") or "").lower().startswith("create")]
        total += len(d2)
        if d2:
            m = min(int(t["blockNumber"]) for t in d2)
            earliest = m if earliest is None else min(earliest, m)
        truncated |= len(r2) >= page
    if not any_ok:
        return None, None, "api_failure"
    if truncated:
        return total, earliest, "history_truncated"
    return total, earliest, ("ok" if total else "no_history")


# =============================================================================
# 归因一个候选
# =============================================================================
def attribute(con, pair, tx_hash, new_token, bn, ev_ts, hist_from, mode,
              hist_fully_sampled, hist_sampled_floor=None):
    t0 = time.time()
    deadline = (ev_ts + SPEC["decision_window_seconds"]) if ev_ts else None

    s_from, s_to, l1 = l1_tx_sender(tx_hash)
    if new_token:
        a_cr, a_tx, l2a = l2a_creator(new_token)
        b_cr, b_tx, l2b, kind = l2b_creator(new_token, hist_from, bn)
    else:
        a_cr = a_tx = b_cr = b_tx = None
        l2a = l2b = "ambiguous"
        kind = "unknown"

    # 只有状态为 ok 的归因才可作为确定值向下游传递。
    # 被标 ambiguous 的地址仍保留在 l2a_creator / l2b_creator 里供人工看，
    # 但不进 token_creator，也不拿去查历史 —— 否则一个已知歧义的地址查出来的
    # 历史会被计成"已判完"。
    creator = (a_cr if l2a == "ok" else None) or (b_cr if l2b == "ok" else None)
    # 兜底链里必须先判 ambiguous：new_token 为 None（判不出哪侧是新币）时两条链路
    # 都是 ambiguous 且都没有值，若直接落到 no_history，就会被 decisive_statuses
    # 计成"已判完"，报告【3b】虚高。
    creator_status = ("ok" if creator else
                      ("ambiguous" if ((a_cr or b_cr) or "ambiguous" in (l2a, l2b)) else
                       ("api_failure" if "api_failure" in (l2a, l2b) else
                        ("history_truncated" if "history_truncated" in (l2a, l2b)
                         else "no_history"))))
    l3d, l3 = l3_first_mint(pair, bn)
    # creator 拿不到时退回建池发送者 —— 那是另一个主体，必须记下来，
    # 否则审计 CSV 里无法判断这条入账线索说的是谁。
    l4_target = creator or s_from
    l4_subject = "creator" if creator else ("pair_created_tx_sender" if s_from else None)
    l4a, l4b, l4 = l4_earliest_inbound(l4_target, bn)

    # 通道甲（自足）：同一建池发送者的更早出现
    prior_s, earliest_s = 0, None
    if s_from:
        r = con.execute(
            "SELECT COUNT(*), MIN(block_number) FROM ("
            " SELECT block_number FROM hist_sender WHERE tx_sender=? AND block_number<?"
            " UNION ALL"
            " SELECT c.block_number FROM candidates c JOIN attribution a ON a.pair=c.pair"
            "  WHERE a.pair_created_tx_sender=? AND c.block_number<?)",
            (s_from, bn, s_from, bn)).fetchone()
        prior_s, earliest_s = r[0], r[1]

    # 通道丙（外部）：创建者的历史部署
    prior_d, earliest_d, d_status = creator_prior_deploys(creator, bn)

    # ---- 历史可见性状态：按通道判，不让某一通道的抽样上限污染确定答案 ----
    if d_status in ("ok", "no_history"):
        hist_status = d_status                    # 外部通道给了确定答案（不受本地回看窗口约束）
    elif d_status == "history_truncated":
        hist_status = "history_truncated"
    else:                                          # api_failure / not_applicable
        # 这一列答的是"该 creator 的历史"。creator 没取到时，自足通道（答的是建池
        # 发送者）不能替一个未知主体宣称 ok / no_history —— 那是把假阳性掺进【2b】。
        if prior_s > 0 and creator:
            hist_status = "ok"                     # 自足通道已确认有前科
        elif d_status == "api_failure":
            # 外部通道拿不到（没有 key / 无权限 / 接口报错）。这是数据源限制，
            # 必须排在抽样上限之前判 —— 否则"没有 key"会被写成"看不到更早"。
            hist_status = "api_failure"
        elif hist_sampled_floor is not None and hist_sampled_floor > hist_from:
            # 自足通道实际抽到的最早区块还没到回看窗口起点 → 确实看不到更早
            hist_status = "history_truncated"
        elif not hist_fully_sampled:
            hist_status = "history_truncated"
        elif not creator:
            # 没有 creator，就没有"该 creator 有没有前科"这个问题的答案。
            # 拿不到 creator 的原因，就是答不出这一列的原因。
            hist_status = creator_status
        else:
            hist_status = "no_history"

    cands_e = [x for x in (earliest_s, earliest_d) if x]
    finished = time.time()
    return {
        "pair": pair, "spec_hash": spec_hash(), "mode": mode, "fetched_at": now_iso(),
        "event_time": ev_ts, "decision_deadline": deadline,
        "pair_created_tx_sender": s_from, "pair_created_tx_to": s_to, "l1_status": l1,
        "token_creator": creator, "token_creation_tx": a_tx or b_tx,
        # 描述 token_creator 的来源，因此只认状态为 ok 的那条链路；
        # 否则会出现 token_creator 为空、l2_source 却说 rpc_binary_search 的自相矛盾行。
        "l2_source": ("etherscan" if (a_cr and l2a == "ok")
                      else ("rpc_binary_search" if (b_cr and l2b == "ok") else "none")),
        "l2a_creator": a_cr, "l2a_status": l2a, "l2b_creator": b_cr, "l2b_status": l2b,
        "deploy_kind": kind, "creator_status": creator_status,
        # 只在两条链路都判定为 ok 时才比较；否则不一致来自口径差而非真实分歧
        "l2_agree": (None if not (l2a == "ok" and l2b == "ok" and a_cr and b_cr)
                     else (1 if a_cr == b_cr else 0)),
        "first_mint_tx_sender": l3d.get("first_mint_tx_sender"),
        "first_mint_event_sender": l3d.get("first_mint_event_sender"),
        "lp_token_recipient": l3d.get("lp_token_recipient"),
        "first_mint_block": l3d.get("first_mint_block"), "l3_status": l3,
        "earliest_observed_inbound": l4a, "earliest_inbound_block": l4b, "l4_status": l4,
        "l4_subject": l4_subject,
        "creator_prior_pairs_in_sample": None,                 # 第二遍统一重算，避免顺序偏置
        "sender_prior_pairs": prior_s, "creator_prior_deploys": prior_d,
        "creator_prior_activity_known": hist_status,
        "earliest_prior_block": min(cands_e) if cands_e else None,
        "processing_seconds": round(finished - t0, 3),
        "resolution_lag_seconds": (round(finished - ev_ts, 1) if ev_ts else None),
    }


# =============================================================================
# backfill
# =============================================================================
def backfill():
    cfg, con = chain_cfg(), db()
    random.seed(SPEC["random_seed"])
    f_b, t_b = SPEC["candidate_from_block"], SPEC["candidate_to_block"]
    if not f_b or not t_b:
        raise SystemExit("先跑 probe，再设 RTA_FROM_BLOCK / RTA_TO_BLOCK")
    hist_from = max(1, f_b - SPEC["history_lookback_blocks"])

    ok, note = l2b_self_test()
    print(f"链={SPEC['chain']}  factory={cfg['factory']}  spec_hash={spec_hash()}")
    print(f"候选 {f_b}-{t_b}；历史回看自 {hist_from}")
    print(f"L2b 可用性：{ok} —— {note}")

    print("\n[1/5] 历史区间 PairCreated（只建历史，不作候选）…")
    hist = [l for l in fetch_pair_created(hist_from, f_b - 1) if "_gap" not in l]
    print("[2/5] 候选区间 PairCreated…")
    cand = [l for l in fetch_pair_created(f_b, t_b) if "_gap" not in l]
    print(f"  历史 {len(hist)}；候选 {len(cand)}")

    # 时间戳只对候选区间取（历史比较用 block_number，不需要时间戳）
    ts = {}
    for b in sorted({hex_int(l["blockNumber"]) for l in cand}):
        blk, e = rpc("eth_getBlockByNumber", [hex(b), False])
        ts[b] = hex_int(blk["timestamp"]) if blk and not e else None

    seen, rows = {}, []
    for lg, inr in [(l, 0) for l in hist] + [(l, 1) for l in cand]:
        t0, t1, pair = parse_pair_created(lg)
        bn = hex_int(lg["blockNumber"])
        nt = pick_new_token(t0, t1)
        had = 1 if (nt and nt in seen) else 0
        if nt:
            seen.setdefault(nt, bn)
        rows.append((pair, SPEC["chain"], cfg["factory"], t0, t1, bn,
                     hex_int(lg["logIndex"]), lg["transactionHash"],
                     ts.get(bn) if inr else None, inr, nt, had))
    con.executemany("INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()

    # 历史建池发送者
    cap = SPEC["hist_sender_cap"]
    total_hist = con.execute(
        "SELECT COUNT(*) FROM candidates WHERE in_candidate_range=0").fetchone()[0]
    todo = [r for r in con.execute(
        "SELECT pair, tx_hash FROM candidates WHERE in_candidate_range=0 "
        "AND pair NOT IN (SELECT pair FROM hist_sender) "
        "ORDER BY block_number DESC LIMIT ?", (cap,)).fetchall()]
    print(f"[3/5] 历史建池发送者：抓 {len(todo)}，历史总数 {total_hist}，上限 {cap}/次")
    for j, (pr, txh) in enumerate(todo, 1):
        sf, _, _ = l1_tx_sender(txh)
        bn2 = con.execute("SELECT block_number FROM candidates WHERE pair=?", (pr,)).fetchone()[0]
        con.execute("INSERT OR REPLACE INTO hist_sender VALUES (?,?,?)", (pr, bn2, sf))
        if j % 50 == 0:
            con.commit()
            print(f"  .. {j}/{len(todo)}", end="\r")
    con.commit()
    # 覆盖度按【库里实际有多少】判，不是按单次上限判 —— 否则断点续跑把历史补齐了，
    # fully 仍然是 False，自足通道的零关联会被永远记成 history_truncated。
    have_hs = con.execute("SELECT COUNT(*) FROM hist_sender").fetchone()[0]
    fully = have_hs >= total_hist
    print(f"  自足通道覆盖 {have_hs}/{total_hist} → "
          f"{'全覆盖' if fully else '仅一部分（零关联将记 history_truncated；再跑一次 backfill 可继续补）'}")

    cands = con.execute(
        "SELECT pair, tx_hash, new_token, block_number, event_time FROM candidates "
        "WHERE in_candidate_range=1 ORDER BY block_number, log_index").fetchall()
    if len(cands) > SPEC["max_candidates"]:
        cands = sorted(random.sample(cands, SPEC["max_candidates"]), key=lambda r: r[3])
    done = {r[0] for r in con.execute("SELECT pair FROM attribution WHERE mode='backfill'")}
    floor = con.execute("SELECT MIN(block_number) FROM hist_sender").fetchone()[0]
    print(f"[4/5] 归因 {len(cands)} 个候选…（自足通道实际抽到的最早区块 = {floor}，"
          f"回看窗口起点 = {hist_from}）")
    c0 = RPC_CALLS[0]
    for i, (pair, txh, nt, bn, ev) in enumerate(cands, 1):
        if pair in done:
            continue
        upsert_attr(con, attribute(con, pair, txh, nt, bn, ev, hist_from,
                                   "backfill", fully, floor))
        con.commit()
        if i % 10 == 0:
            print(f"  .. {i}/{len(cands)}  RPC {RPC_CALLS[0]-c0} "
                  f"(均 {(RPC_CALLS[0]-c0)/i:.1f}/候选)", end="\r")
    print()

    # 第二遍：通道乙统一重算，消除处理顺序偏置
    print("[5/5] 第二遍重算 creator_prior_pairs（消除处理顺序偏置）…")
    for (pair,) in con.execute("SELECT pair FROM attribution WHERE mode='backfill'").fetchall():
        r = con.execute(
            "SELECT a.token_creator, c.block_number FROM attribution a "
            "JOIN candidates c ON c.pair=a.pair WHERE a.pair=?", (pair,)).fetchone()
        cr, bn = r
        cnt = 0
        if cr:
            cnt = con.execute(
                "SELECT COUNT(*) FROM attribution a JOIN candidates c ON c.pair=a.pair "
                "WHERE a.token_creator=? AND c.block_number<?", (cr, bn)).fetchone()[0]
        con.execute("UPDATE attribution SET creator_prior_pairs_in_sample=? WHERE pair=?", (cnt, pair))
    con.commit()
    print(f"完成。总 RPC 调用 {RPC_CALLS[0]}。数据库 {DB_PATH}")


# =============================================================================
# forward
# =============================================================================
def forward(minutes):
    cfg, con = chain_cfg(), db()
    l2b_self_test()
    head, _ = rpc("eth_blockNumber", [])
    cur = hex_int(head)
    end = time.time() + minutes * 60
    print(f"前向观察 {minutes} 分钟，起始 {cur}；截止 = 事件时间 + "
          f"{SPEC['decision_window_seconds']}s")
    while time.time() < end:
        head, _ = rpc("eth_blockNumber", [])
        h = hex_int(head)
        if not h or h <= cur:
            time.sleep(IDLE_SLEEP)
            continue
        logs = [l for l in fetch_pair_created(cur + 1, h) if "_gap" not in l]
        cur = h
        for lg in logs:
            t0, t1, pair = parse_pair_created(lg)
            bn = hex_int(lg["blockNumber"])
            blk, _ = rpc("eth_getBlockByNumber", [hex(bn), False])
            ev = hex_int(blk["timestamp"]) if blk else None
            nt = pick_new_token(t0, t1)
            con.execute("INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (pair, SPEC["chain"], cfg["factory"], t0, t1, bn,
                         hex_int(lg["logIndex"]), lg["transactionHash"], ev, 1, nt, None))
            row = attribute(con, pair, lg["transactionHash"], nt, bn, ev,
                            max(1, bn - SPEC["forward_lookback_blocks"]),
                            "forward", True)
            late = (row["decision_deadline"] is not None
                    and time.time() > row["decision_deadline"])
            if late:
                for k in ("l1_status", "l2a_status", "l2b_status", "l3_status",
                          "l4_status", "creator_prior_activity_known"):
                    if row[k] in SPEC["decisive_statuses"]:
                        row[k] = "timeout"
            upsert_attr(con, row)
            con.commit()
            print(f"  {pair[:10]}… 处理 {row['processing_seconds']:5.1f}s  "
                  f"事件→完成 {row['resolution_lag_seconds']}s  "
                  f"{'超过截止' if late else '在截止内'}")
        time.sleep(POLL_SLEEP)
    print("前向观察结束。")


# =============================================================================
# report
# =============================================================================
def report():
    con = db()
    ensure_out()
    cols = [d[0] for d in con.execute("SELECT * FROM attribution LIMIT 0").description]

    def pct(a, b):
        return f"{100.0*a/b:.1f}%" if b else "n/a"

    for mode in ("backfill", "forward"):
        rs = [dict(zip(cols, r)) for r in
              con.execute("SELECT * FROM attribution WHERE mode=?", (mode,)).fetchall()]
        if not rs:
            continue
        n = len(rs)
        lookback = (SPEC["history_lookback_blocks"] if mode == "backfill"
                    else SPEC["forward_lookback_blocks"])
        # 写成真分支而不是多行条件表达式：Python 3.8 的行号归属会把条件表达式的
        # 每一行都标成"已执行"，行覆盖因此测不出这个告警到底有没有触发。
        lookback_warn = ""
        if SPEC["history_lookback_blocks"] != SPEC["forward_lookback_blocks"]:
            lookback_warn = ("   ⚠ 两个模式的回看窗口不同，L2b 的 history_truncated "
                             "门槛不同，两份报告的 L2b 覆盖率不可直接比较")
        hashes = sorted({r["spec_hash"] for r in rs})
        L = [f"\n{'='*78}",
             f"模式：{mode}    候选数 N = {n}",
             f"数据采集时的 spec_hash：{', '.join(hashes)}"
             + ("   ⚠ 多个哈希混用，下面的合计跨越了不同规格" if len(hashes) > 1 else ""),
             f"当前进程 spec_hash：{spec_hash()}"
             + ("   ⚠ 与采集时不同" if spec_hash() not in hashes else ""),
             f"链 = {SPEC['chain']}   决策窗口 = {SPEC['decision_window_seconds']}s",
             f"本模式回看窗口 = {lookback} 区块" + lookback_warn,
             "=" * 78]

        L.append("\n【1】四条链路各自状态分布（分母 = N）")
        for label, c in [("L1 建池交易发送者", "l1_status"),
                         ("L2a 浏览器创建归因", "l2a_status"),
                         ("L2b 纯RPC创建归因", "l2b_status"),
                         ("L3 首次Mint与LP接收", "l3_status"),
                         ("L4 最早观察到的入账", "l4_status")]:
            dec = sum(1 for r in rs if r[c] in SPEC["decisive_statuses"])
            L.append(f"  {label:<22} 已判完 = {dec:>4}/{n} ({pct(dec, n)})")
            d = {}
            for r in rs:
                d[r[c]] = d.get(r[c], 0) + 1
            L.append("  " + " " * 22 + "  " +
                     "  ".join(f"{k}={v}" for k, v in sorted(d.items(), key=lambda x: -x[1])))

        L.append("\n【2】联合覆盖率 —— 唯一的结论行")
        L.append(f"  规则需要：{', '.join(SPEC['required_fields_for_rule'])}")
        L.append(f"  '已判完'计入可用的状态：{SPEC['decisive_statuses']}"
                 "  （确认没有前科是答案，不是缺失）")
        joint = sum(1 for r in rs if (
            r["l1_status"] == "ok" and r["pair_created_tx_sender"]
            and (r["l2a_status"] == "ok" or r["l2b_status"] == "ok") and r["token_creator"]
            and r["creator_prior_activity_known"] in SPEC["decisive_statuses"]))
        L.append(f"  联合可用 = {joint}/{n}  ({pct(joint, n)})")

        L.append("\n【2b】历史可见性状态分布")
        d = {}
        for r in rs:
            d[r["creator_prior_activity_known"]] = d.get(r["creator_prior_activity_known"], 0) + 1
        for k, v in sorted(d.items(), key=lambda x: -x[1]):
            tag = "（已判完）" if k in SPEC["decisive_statuses"] else "（不可用）"
            L.append(f"  {k:<20}{tag} {v:>4}/{n} ({pct(v, n)})")

        L.append("\n【3】两条创建归因链路的交叉校验（按部署形态分层）")
        L.append("  只比较两条链路都判 ok 的行；工厂部署下 L2b 给的是交易发起人、")
        L.append("  与 L2a 的 contractCreator 口径不同，混在一起算会得到必然的不一致。")
        for kind in ("direct", "factory", "unknown"):
            sub = [r for r in rs if r["deploy_kind"] == kind]
            both = [r for r in sub if r["l2_agree"] is not None]
            ag = sum(1 for r in both if r["l2_agree"] == 1)
            L.append(f"  {kind:<8} 候选 {len(sub):>4}；可比 {len(both):>4}；"
                     f"一致 {ag} ({pct(ag, len(both))})")
        L.append("\n【3b】token_creator 的确定性（ambiguous 的地址不进下游）")
        d = {}
        for r in rs:
            d[r["creator_status"]] = d.get(r["creator_status"], 0) + 1
        for k, v in sorted(d.items(), key=lambda x: -x[1]):
            L.append(f"  {k:<20} {v:>4}/{n} ({pct(v, n)})")

        if mode == "forward":
            L.append("\n【4】时间（两个不同的量，不要混读）")
            for key, name in [("processing_seconds", "单候选处理耗时"),
                              ("resolution_lag_seconds", "事件时间→四条链路全部返回")]:
                v = sorted(x[key] for x in rs if x[key] is not None)
                if v:
                    L.append(f"  {name}：中位 {v[len(v)//2]:.1f}s  "
                             f"p90 {v[int(len(v)*0.9)]:.1f}s  最大 {v[-1]:.1f}s")
            to = sum(1 for r in rs if "timeout" in (r["l1_status"], r["l2a_status"],
                                                    r["l2b_status"], r["l3_status"], r["l4_status"]))
            L.append(f"  超过决策截止 {to}/{n} ({pct(to, n)})")
            L.append("  注意：若处理耗时本身就接近截止，这里量到的是脚本速度，不是数据源速度。")

        if mode == "backfill":
            L.append("\n【5】新池 ≠ 新币（只统计 backfill 候选）")
            q = con.execute("SELECT SUM(token_had_prior_pair), COUNT(*) FROM candidates c "
                            "JOIN attribution a ON a.pair=c.pair WHERE a.mode='backfill'").fetchone()
            L.append(f"  该代币此前已有池：{q[0] or 0}/{q[1]} ({pct(q[0] or 0, q[1])})")
            amb = con.execute("SELECT COUNT(*) FROM candidates c JOIN attribution a "
                              "ON a.pair=c.pair WHERE a.mode='backfill' AND c.new_token IS NULL"
                              ).fetchone()[0]
            L.append(f"  无法判定哪侧是新币：{amb}/{q[1]} ({pct(amb, q[1])})")

        L.append("\n【本周能否定什么 / 不能否定什么】")
        L.append("  能否定：在这个冻结的母体、数据源、回看范围与决策截止内，")
        L.append("          【这一版归因规则】覆盖不足或来不及返回。")
        L.append("  不能否定：信息不存在；RT-A 有没有 edge；换数据源后是否可行。")
        L.append("  若 L2b 整条为 api_failure，请回看 capability_report.json 的")
        L.append("  l2b_usable —— 那是数据源限制，不是链上没有信息。")

        print("\n".join(L))
        with open(os.path.join(OUTDIR, f"coverage_report_{mode}.md"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(L))

    random.seed(SPEC["random_seed"])
    rows = con.execute(
        "SELECT a.pair, c.tx_hash, c.new_token, a.deploy_kind, a.creator_status,"
        " a.token_creator,"
        " a.pair_created_tx_sender, a.pair_created_tx_to,"
        " a.l2a_creator, a.l2b_creator, a.l2_agree, a.first_mint_tx_sender,"
        " a.first_mint_event_sender, a.lp_token_recipient,"
        " a.earliest_observed_inbound, a.l4_subject,"
        " a.creator_prior_pairs_in_sample, a.sender_prior_pairs, a.creator_prior_deploys,"
        " a.creator_prior_activity_known FROM attribution a "
        "JOIN candidates c ON c.pair=a.pair").fetchall()
    if rows:
        # 分层抽样：direct / factory / unknown 各抽一部分，避免样本被某一类占满
        by = {}
        for r in rows:
            by.setdefault(r[3] or "unknown", []).append(r)
        per = max(1, SPEC["audit_sample_size"] // max(1, len(by)))
        s = []
        for k in sorted(by):
            s += random.sample(by[k], min(per, len(by[k])))
        rest = [r for r in rows if r not in s]
        if len(s) < SPEC["audit_sample_size"] and rest:
            s += random.sample(rest, min(SPEC["audit_sample_size"] - len(s), len(rest)))
        hdr = ("pair,pair_created_tx,new_token,deploy_kind,creator_status,"
               "token_creator,"
               "pair_created_tx_sender,pair_created_tx_to,"
               "l2a_creator,l2b_creator,l2_agree,first_mint_tx_sender,first_mint_event_sender,"
               "lp_token_recipient,earliest_observed_inbound,l4_subject,"
               "creator_prior_pairs_in_sample,"
               "sender_prior_pairs,creator_prior_deploys,history_status,"
               "人工判定[正确/错误/无法判断],备注")
        p = os.path.join(OUTDIR, "audit_sample.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write(hdr + "\n")
            for r in s:
                f.write(",".join("" if v is None else str(v) for v in r) + ",,\n")
        print(f"\n→ {p}（最后两列请手工填）")
        print("  重点看：关联是不是只是共用了 router、工厂或交易所热钱包。")


# =============================================================================
# selftest —— 离线，不需要网络；backfill / forward / report 三条路径都跑
# =============================================================================
# =============================================================================
# selftest —— 离线场景化自测
#
# 上一版的自测只断言"backfill 行数>0、forward 行数>0"，于是：
#   - mock 恒返回成功，v2 最重要的三处口径修复一次都没被执行；
#   - 报告里 21/21 全 ok 也算 PASS。
# 这一版改成【场景 + 状态断言】：每个场景构造一种失败形态，断言得到的是
# 该形态应有的状态码，而不是"跑完了"。
# =============================================================================
def _mk_mocks(cfg):
    """按场景配置造一组 (mrpc, mscan)。cfg 见各场景。"""
    WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    h32 = lambda i: "0x" + f"{i:064x}"                              # noqa: E731
    ad = lambda i: "0x" + f"{i:040x}"                               # noqa: E731
    P = cfg["pairs"]
    LOGS = {}
    for blk, tok, pr, cr, sd, tx in P:
        LOGS.setdefault(blk, []).append({
            "address": chain_cfg()["factory"], "blockNumber": hex(blk), "logIndex": "0x0",
            "transactionHash": tx,
            "topics": [TOPIC_PAIR_CREATED, h32(int(WETH, 16)), h32(int(tok, 16))],
            "data": "0x" + f"{int(pr,16):064x}" + f"{1:064x}"})
    BYTX = {p[5]: p for p in P}
    BYTOK = {p[1]: p for p in P}
    BYPAIR = {p[2]: p for p in P}
    sched = list(cfg.get("blocknum_sched", []))
    state = {"i": 0}

    def mrpc(method, params, **kw):
        RPC_CALLS[0] += 1
        if method == "eth_blockNumber":
            # 计数排程：每次调用取排程里的下一个值，最后一个值之后保持不变。
            # （一次性 head=next 的写法无法产生 [1400, 1400, 1403] 这类序列，
            #   而 forward 开头的 l2b_self_test 会先消耗掉一次调用。）
            v = sched[min(state["i"], len(sched) - 1)]
            state["i"] += 1
            return hex(v), None
        if method == "eth_getLogs":
            f = params[0]
            a, b = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            t = (f.get("topics") or [None])[0]
            if t == TOPIC_PAIR_CREATED:
                return [x for blk in range(a, b + 1) for x in LOGS.get(blk, [])], None
            if t == TOPIC_MINT:
                p = BYPAIR.get(f["address"])
                if p and a <= p[0] + 1 <= b:
                    return [{"address": p[2], "blockNumber": hex(p[0] + 1), "logIndex": "0x1",
                             "transactionHash": h32(0xBB00 + p[0]),
                             "topics": [TOPIC_MINT, h32(int(p[3], 16))], "data": "0x"}], None
                return [], None
            addr = (f.get("address") or "").lower()
            if addr in BYTOK and cfg.get("l2b_path") == "logs":
                p = BYTOK[addr]
                if a <= p[0] <= b:
                    return [{"transactionHash": h32(0xEE00 + p[0])}], None
            return [], None
        if method == "eth_getBlockByNumber":
            bn = int(params[0], 16)
            txs = []
            if params[1] and cfg.get("l2b_path") == "degraded":
                # 造一个"很宽"的区块，触发扫描上限
                txs = [{"hash": h32(0x770000 + bn * 1000 + i)} for i in range(200)]
            return {"timestamp": hex(1700000000 + bn * 12), "transactions": txs}, None
        if method == "eth_getTransactionByHash":
            t = params[0]
            if t in BYTX:
                return {"from": BYTX[t][4], "to": chain_cfg()["factory"]}, None
            for p in P:
                if t == h32(0xEE00 + p[0]):
                    to = None if cfg.get("deploy_kind", "direct") == "direct" else p[2]
                    return {"from": p[3], "to": to}, None
                if t == h32(0xBB00 + p[0]):
                    return {"from": p[3], "to": p[2]}, None
            return {"from": ad(0xF1), "to": ad(0xF2)}, None
        if method == "eth_getTransactionReceipt":
            for p in P:
                if params[0] == h32(0xBB00 + p[0]):
                    return {"logs": [{"address": p[2],
                                      "topics": [TOPIC_TRANSFER, h32(0),
                                                 h32(int(p[3], 16))]}]}, None
            return {"contractAddress": None, "logs": []}, None
        if method == "eth_getBlockReceipts":
            if cfg.get("l2b_path") == "receipts":
                bn = int(params[0], 16)
                for p in P:
                    if p[0] == bn:
                        return [{"contractAddress": p[1],
                                 "transactionHash": h32(0xEE00 + p[0])}], None
                return [], None
            return None, "unsupported"
        if method == "eth_getCode":
            a = params[0].lower()
            bn = int(params[1], 16)
            if not cfg.get("archive_ok", True):
                return "0x60", None          # 非归档节点的典型表现：历史块也返回最新状态
            if a in BYTOK:
                return ("0x60" if bn >= BYTOK[a][0] else "0x"), None
            if a == chain_cfg()["factory"].lower():
                return ("0x60" if bn >= 100 else "0x"), None
            return "0x60", None
        if method == "eth_call":
            return h32(120), None
        return None, "unhandled"

    def mscan(module, action, **kw):
        m = cfg.get("etherscan_mode", "ok")
        if m == "fail":
            return None, "status0: NOTOK | Missing/Invalid API Key"
        if m == "badshape":
            return "Max rate limit reached", None      # result 是字符串，不是 list
        if action == "getcontractcreation":
            t = kw.get("contractaddresses", "").lower()
            return (([{"contractCreator": BYTOK[t][3], "txHash": h32(0xDD01)}], None)
                    if t in BYTOK else ([], None))
        if action == "txlist":
            a = kw.get("address", "")
            if cfg.get("l4_page_full"):
                # 分页打满、且一笔入账都没有 → 应判 history_truncated
                return [{"to": ad(0x111), "from": a, "value": "0",
                         "blockNumber": "5"} for _ in range(200)], None
            return [{"to": a, "from": ad(0x999), "value": "1", "blockNumber": "5"},
                    {"to": "", "from": a, "value": "0", "blockNumber": "150"}], None
        if action == "txlistinternal":
            if cfg.get("deploy_page_full"):
                return [{"type": "create", "blockNumber": "160"}] * 5000, None
            return [{"type": "create", "blockNumber": "160"}], None
        return None, "unhandled"

    return mrpc, mscan


def _std_pairs(n=120, start=200, step=10):
    ad = lambda i: "0x" + f"{i:040x}"                                # noqa: E731
    h32 = lambda i: "0x" + f"{i:064x}"                               # noqa: E731
    return [(start + i * step, ad(0x1000 + i), ad(0x2000 + i),
             ad(0xC0 + i % 7), ad(0xE0 + i % 5), h32(0xAA00 + i)) for i in range(n)]


def selftest():
    global rpc, etherscan, ETHERSCAN_KEY, OUTDIR, DB_PATH, POLL_SLEEP, IDLE_SLEEP
    global L2B_USABLE, L2B_NOTE
    import shutil, tempfile, io                                      # noqa: E401
    POLL_SLEEP = IDLE_SLEEP = 0.0
    rpc_limiter.min_gap = scan_limiter.min_gap = 0.0
    ETHERSCAN_KEY = "MOCK"
    passed, failed = [], []

    def check(name, cond, detail=""):
        (passed if cond else failed).append(name)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

    def tmpcon():
        d = tempfile.mkdtemp()
        con = sqlite3.connect(os.path.join(d, "t.sqlite"))
        con.executescript(DDL)
        return con

    ad = lambda i: "0x" + f"{i:040x}"                                # noqa: E731
    h32 = lambda i: "0x" + f"{i:064x}"                               # noqa: E731

    # =====================================================================
    print("\n【场景 1】端到端：backfill + forward + report")
    # =====================================================================
    OUTDIR = "./rt_a_selftest"
    DB_PATH = os.path.join(OUTDIR, "rt_a.sqlite")
    shutil.rmtree(OUTDIR, ignore_errors=True)
    SPEC.update({"candidate_from_block": 1000, "candidate_to_block": 1200,
                 "history_lookback_blocks": 900, "forward_lookback_blocks": 900,
                 "max_candidates": 50,
                 "log_chunk_blocks": 100, "hist_sender_cap": 3000})
    P = _std_pairs()
    # 注入两个前向新池
    for k, i in enumerate((120, 121)):
        P.append((1401 + k, ad(0x1000 + i), ad(0x2000 + i), ad(0xC0), ad(0xE0),
                  h32(0xAA00 + i)))
    # 排程：backfill 与 forward 各自开头的 l2b_self_test 都会消耗 eth_blockNumber，
    # forward 取起点又要一次。不去数具体几次（数错就是上一版自测失败的原因），
    # 改成"前若干次一律 1400，之后链头到 1403"，对调用次数不敏感。
    cfg = {"pairs": P, "l2b_path": "logs", "deploy_kind": "direct",
           "blocknum_sched": [1400] * 12 + [1403]}
    rpc, etherscan = _mk_mocks(cfg)
    L2B_USABLE, L2B_NOTE = None, ""
    backfill()
    forward(0.05)
    report()
    con = sqlite3.connect(DB_PATH)
    nb = con.execute("SELECT COUNT(*) FROM attribution WHERE mode='backfill'").fetchone()[0]
    nf = con.execute("SELECT COUNT(*) FROM attribution WHERE mode='forward'").fetchone()[0]
    check("backfill 有数据", nb > 0, f"{nb} 行")
    check("forward 有数据（v1 崩溃点）", nf == 2, f"{nf} 行，期望 2")
    kinds = dict(con.execute("SELECT deploy_kind, COUNT(*) FROM attribution "
                             "WHERE mode='backfill' GROUP BY deploy_kind").fetchall())
    check("直接部署被判为 direct", kinds.get("direct", 0) == nb, str(kinds))

    # =====================================================================
    print("\n【场景 2】非归档节点：L2b 整条应为 api_failure，不得记 no_history")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "archive_ok": False,
                                "blocknum_sched": [1400]})
    L2B_USABLE, L2B_NOTE = None, ""
    ok, note = l2b_self_test()
    check("l2b_self_test 判定不可用", ok is False, note)
    cr, tx, st, kind = l2b_creator(ad(0x1000), 1, 1000)
    check("L2b 返回 api_failure", st == "api_failure", f"实得 {st}")

    # =====================================================================
    print("\n【场景 3】无 Etherscan key + 历史未全采样")
    print("        → creator_prior_activity_known 必须是 api_failure，不是 history_truncated")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    L2B_USABLE = True
    con2 = tmpcon()
    row = attribute(con2, ad(0x2000), h32(0xAA00), ad(0x1000), 400, 1700000000,
                    hist_from=1, mode="backfill", hist_fully_sampled=False,
                    hist_sampled_floor=None)
    check("hist_status = api_failure（不是 history_truncated）",
          row["creator_prior_activity_known"] == "api_failure",
          f"实得 {row['creator_prior_activity_known']}")
    check("L2a 记 api_failure", row["l2a_status"] == "api_failure", row["l2a_status"])

    # =====================================================================
    print("\n【场景 4】Etherscan 返回字符串（限流）→ 记 api_failure，不得抛异常")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "badshape",
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    try:
        c, e, st = l2a_creator(ad(0x1000))
        n_, eb_, ds = creator_prior_deploys(ad(0xC0), 500)
        i_, ib_, l4 = l4_earliest_inbound(ad(0xC0), 500)
        check("l2a 形状异常 → api_failure", st == "api_failure", st)
        check("历史部署形状异常 → api_failure", ds == "api_failure", str(ds))
        check("l4 形状异常 → api_failure", l4 == "api_failure", l4)
    except Exception as ex:                                          # noqa: BLE001
        check("形状异常不抛异常", False, f"{type(ex).__name__}: {ex}")

    # =====================================================================
    print("\n【场景 5】L4 分页打满且无入账 → history_truncated，不是 no_history")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "l4_page_full": True,
                                "blocknum_sched": [1400]})
    a_, b_, st = l4_earliest_inbound(ad(0xC0), 500)
    check("L4 → history_truncated", st == "history_truncated", st)

    # =====================================================================
    print("\n【场景 6】工厂部署：L2b 应判 ambiguous，且该地址不得进 token_creator")
    # =====================================================================
    P6 = _std_pairs(3)
    rpc, etherscan = _mk_mocks({"pairs": P6, "l2b_path": "logs",
                                "deploy_kind": "factory", "etherscan_mode": "fail",
                                "blocknum_sched": [1400]})
    L2B_USABLE = True
    cr, tx, st, kind = l2b_creator(P6[0][1], 1, P6[0][0] + 10)
    check("L2b 状态 = ambiguous", st == "ambiguous", st)
    check("deploy_kind = factory", kind == "factory", kind)
    check("值仍保留供人工看", cr is not None, str(cr))
    con6 = tmpcon()
    row6 = attribute(con6, P6[0][2], P6[0][5], P6[0][1], P6[0][0] + 10, 1700000000,
                     hist_from=1, mode="backfill", hist_fully_sampled=True)
    check("token_creator 不采用 ambiguous 值", row6["token_creator"] is None,
          str(row6["token_creator"]))
    check("creator_status = ambiguous", row6["creator_status"] == "ambiguous",
          row6["creator_status"])
    check("l2_agree 不参与比较（None）", row6["l2_agree"] is None, str(row6["l2_agree"]))

    # =====================================================================
    print("\n【场景 7】L2b 便宜路径 2（getBlockReceipts）与退化路径（扫描上限）")
    # =====================================================================
    P7 = _std_pairs(3)
    rpc, etherscan = _mk_mocks({"pairs": P7, "l2b_path": "receipts",
                                "blocknum_sched": [1400]})
    L2B_USABLE = True
    cr, tx, st, kind = l2b_creator(P7[0][1], 1, P7[0][0] + 10)
    check("便宜路径 2 命中 → ok", st == "ok", st)

    _orig_cap = SPEC["l2b_receipt_scan_cap"]
    SPEC["l2b_receipt_scan_cap"] = 5
    rpc, etherscan = _mk_mocks({"pairs": P7, "l2b_path": "degraded",
                                "blocknum_sched": [1400]})
    cr, tx, st, kind = l2b_creator(P7[0][1], 1, P7[0][0] + 10)
    check("退化路径撞上限 → history_truncated（不是 no_history）",
          st == "history_truncated", st)
    SPEC["l2b_receipt_scan_cap"] = _orig_cap

    # =====================================================================
    print("\n【场景 8】自足通道抽样底线高于回看窗口起点 → history_truncated")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    con8 = tmpcon()
    # 外部通道可用但无历史时，走自足通道；这里让外部通道 not_applicable（creator=None）
    row8 = attribute(con8, ad(0x2000), h32(0xAA00), None, 400, 1700000000,
                     hist_from=1, mode="backfill", hist_fully_sampled=True,
                     hist_sampled_floor=300)
    check("抽样底线 300 > 回看起点 1 → history_truncated",
          row8["creator_prior_activity_known"] == "history_truncated",
          row8["creator_prior_activity_known"])

    # =====================================================================
    print("\n【场景 9】创建者历史部署分页打满 → history_truncated，不是 ok/no_history")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "deploy_page_full": True,
                                "blocknum_sched": [1400]})
    cnt, eb, ds = creator_prior_deploys(ad(0xC0), 500)
    check("历史部署 → history_truncated", ds == "history_truncated", str(ds))
    con9 = tmpcon()
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "deploy_page_full": True,
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    L2B_USABLE = True
    row9 = attribute(con9, ad(0x2000), h32(0xAA00), ad(0x1000), 400, 1700000000,
                     hist_from=1, mode="backfill", hist_fully_sampled=True)
    check("外部通道截断 → hist_status 也是 history_truncated",
          row9["creator_prior_activity_known"] == "history_truncated",
          row9["creator_prior_activity_known"])

    # =====================================================================
    print("\n【场景 10】外部通道不可用、但自足通道已确认有前科 → hist_status = ok")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    L2B_USABLE = True
    con10 = tmpcon()
    # 该建池发送者在更早区块出现过（历史区已抓到）
    con10.execute("INSERT INTO hist_sender VALUES (?,?,?)", ("0xold", 150, ad(0xE0)))
    con10.commit()
    row10 = attribute(con10, ad(0x2000), h32(0xAA00), ad(0x1000), 400, 1700000000,
                      hist_from=1, mode="backfill", hist_fully_sampled=False)
    check("自足通道有前科 → hist_status = ok",
          row10["creator_prior_activity_known"] == "ok"
          and row10["sender_prior_pairs"] == 1,
          f"{row10['creator_prior_activity_known']}, prior_s={row10['sender_prior_pairs']}")

    # =====================================================================
    print("\n【场景 11】判不出哪侧是新币 → creator_status 必须是 ambiguous，不是 no_history")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "blocknum_sched": [1400]})
    con11 = tmpcon()
    row11 = attribute(con11, ad(0x2000), h32(0xAA00), None, 400, 1700000000,
                      hist_from=1, mode="backfill", hist_fully_sampled=True)
    check("creator_status = ambiguous（不是 no_history）",
          row11["creator_status"] == "ambiguous", row11["creator_status"])
    check("ambiguous 不计入已判完",
          row11["creator_status"] not in SPEC["decisive_statuses"],
          f"decisive={SPEC['decisive_statuses']}")
    check("token_creator 为空时 l4 主体标为 pair_created_tx_sender",
          row11["l4_subject"] == "pair_created_tx_sender", str(row11["l4_subject"]))
    check("l2_source 与空 token_creator 不矛盾",
          row11["l2_source"] == "none", str(row11["l2_source"]))

    # =====================================================================
    print("\n【场景 12】旧版本建的库：连接时必须补列，不得等写入才崩")
    # =====================================================================
    d12 = tempfile.mkdtemp()
    p12 = os.path.join(d12, "old.sqlite")
    legacy = [c for c in ATTR_COLS
              if c not in ("deploy_kind", "creator_status", "l4_subject")]
    c0_ = sqlite3.connect(p12)
    c0_.executescript("CREATE TABLE attribution (%s);" % ", ".join(
        c + (" TEXT PRIMARY KEY" if c == "pair" else "") for c in legacy))
    c0_.commit()
    c0_.close()
    _saved_db = DB_PATH
    DB_PATH = p12
    con12 = db()                       # 迁移应在这里发生
    DB_PATH = _saved_db
    have12 = {d[1] for d in con12.execute("PRAGMA table_info(attribution)")}
    missing12 = [c for c in ATTR_COLS if c not in have12]
    check("迁移补齐全部新列", not missing12, f"缺 {missing12}" if missing12 else "无缺列")
    try:
        upsert_attr(con12, {"pair": "0xmig", "mode": "backfill",
                            "deploy_kind": "direct", "l4_subject": "creator"})
        con12.commit()
        check("迁移后写入成功（v2 库上这里会抛 no column named deploy_kind）", True)
    except Exception as ex:                                          # noqa: BLE001
        check("迁移后写入成功", False, f"{type(ex).__name__}: {ex}")

    # =====================================================================
    print("\n【场景 13】creator 未取到时，自足通道不得替它宣称 ok / no_history")
    # =====================================================================
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "blocknum_sched": [1400]})
    L2B_USABLE = False                      # creator 两条链路都拿不到
    con13 = tmpcon()
    con13.execute("INSERT INTO hist_sender VALUES (?,?,?)", ("0xold", 150, ad(0xE0)))
    con13.commit()
    # (a) 自足通道命中前科，但 creator 未知 —— 不能记 ok
    row13a = attribute(con13, ad(0x2000), h32(0xAA00), None, 400, 1700000000,
                       hist_from=1, mode="backfill", hist_fully_sampled=True)
    check("creator 未知 + 发送者有前科 → 不是 ok",
          row13a["creator_prior_activity_known"] != "ok",
          f"实得 {row13a['creator_prior_activity_known']}, prior_s={row13a['sender_prior_pairs']}")
    # (b) 历史已全采样、发送者无前科，creator 未知 —— 不能记 no_history
    con13b = tmpcon()
    row13b = attribute(con13b, ad(0x2000), h32(0xAA00), None, 400, 1700000000,
                       hist_from=1, mode="backfill", hist_fully_sampled=True)
    check("creator 未知 + 全采样无前科 → 不是 no_history",
          row13b["creator_prior_activity_known"] != "no_history",
          f"实得 {row13b['creator_prior_activity_known']}")
    check("该状态不计入已判完",
          row13b["creator_prior_activity_known"] not in SPEC["decisive_statuses"],
          row13b["creator_prior_activity_known"])
    # (c) creator 已知时，自足通道兜底仍然生效（v3 的口径不变）
    rpc, etherscan = _mk_mocks({"pairs": _std_pairs(5), "etherscan_mode": "fail",
                                "l2b_path": "logs", "blocknum_sched": [1400]})
    L2B_USABLE = True
    con13c = tmpcon()
    con13c.execute("INSERT INTO hist_sender VALUES (?,?,?)", ("0xold", 150, ad(0xE0)))
    con13c.commit()
    row13c = attribute(con13c, ad(0x2000), h32(0xAA00), ad(0x1000), 400, 1700000000,
                       hist_from=1, mode="backfill", hist_fully_sampled=False)
    check("creator 已知 + 发送者有前科 → 仍是 ok（口径未变）",
          row13c["creator_prior_activity_known"] == "ok",
          row13c["creator_prior_activity_known"])

    # =====================================================================
    print("\n【场景 14】回看窗口分叉告警：行覆盖测不出分支输出，必须断言字面量")
    # =====================================================================
    import contextlib                                                # noqa: E401
    MARK = "两个模式的回看窗口不同"

    def report_text():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report()
        return buf.getvalue()

    _hl, _fl = SPEC["history_lookback_blocks"], SPEC["forward_lookback_blocks"]
    SPEC["history_lookback_blocks"] = SPEC["forward_lookback_blocks"] = 900
    txt_same = report_text()
    check("两窗口相同 → 不出现告警", MARK not in txt_same,
          "未出现" if MARK not in txt_same else "不该出现却出现了")
    SPEC["forward_lookback_blocks"] = 500000
    txt_diff = report_text()
    check("两窗口分叉 → 出现告警", MARK in txt_diff,
          "已出现" if MARK in txt_diff else "该出现却没有")
    check("告警同时出现在两份报告里", txt_diff.count(MARK) == 2,
          f"出现 {txt_diff.count(MARK)} 次，期望 2（backfill + forward 各一）")
    SPEC["history_lookback_blocks"], SPEC["forward_lookback_blocks"] = _hl, _fl

    # =====================================================================
    print(f"\n{'='*70}\n通过 {len(passed)} / 失败 {len(failed)}")
    if failed:
        print("失败项：" + "、".join(failed))
        raise AssertionError(f"SELFTEST FAILED: {failed}")
    print("SELFTEST PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["selftest", "probe", "backfill", "forward", "report"])
    ap.add_argument("--minutes", type=float, default=60)
    a = ap.parse_args()
    if a.step != "selftest":
        ensure_out()
        with open(os.path.join(OUTDIR, "spec_frozen.json"), "w", encoding="utf-8") as f:
            json.dump({"spec": SPEC, "spec_hash": spec_hash(), "frozen_at": now_iso()},
                      f, ensure_ascii=False, indent=2)
    {"selftest": selftest, "probe": probe, "backfill": backfill,
     "forward": lambda: forward(a.minutes), "report": report}[a.step]()


if __name__ == "__main__":
    main()

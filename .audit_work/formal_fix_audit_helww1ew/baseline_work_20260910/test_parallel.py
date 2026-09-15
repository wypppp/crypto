#!/usr/bin/env python3
"""串行 vs 两路并行一致性（离线受控）。

要求：同一冻结样本与状态块下，**状态、金额、分类、证据必须一致**；
耗时与请求顺序允许不同。另验全局限流/预算共享、请求 ID 隔离、断点恢复。
"""
import argparse, contextlib, hashlib, io, json, os, sys, tempfile
from pathlib import Path
import pilot_measure as P
import evidence as E
from fake_chain import FakeRpc

REAL_ETHERSCAN = P.etherscan       # 必须在任何 mock 之前保存真函数引用

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

PAIR, TOKEN = "0x" + "ab"*20, "0x" + "cd"*20
CREATED, MINT = 24_140_000, 24_140_010
N = 6

def run(tmp, tag, parallel, faults=(), sample=None, ckpt=None):
    sample = sample or (tmp/"s.json")
    if not sample.exists():
        sample.write_text(json.dumps({
            "universe_sha256": hashlib.sha256(Path(P.UNIVERSE).read_bytes()).hexdigest(),
            "n": N, "sample": [{"index": i, "pair": PAIR, "token": TOKEN,
                                "created_block": CREATED} for i in range(1, N+1)]},
            ensure_ascii=False), encoding="utf-8")
    cfg = {"head": 25_900_000, "genesis_ts": 0, "entry_block": MINT+1,
           "pair": PAIR, "token": TOKEN, "received": 10**18, "cash": 10**15,
           "slot": 0, "faults": faults,
           "supply": lambda b: 0 if int(b,16) < MINT else 10**6}
    shared = FakeRpc(cfg)
    P.V.RPC = lambda *a, **k: FakeRpc(cfg)      # 每路各自实例，模拟独立连接
    P.etherscan = lambda key, **kw: {"status":"1","message":"OK","result":[
        {"address": PAIR, "blockNumber": hex(MINT), "logIndex": "0x0",
         "topics":[P.MINT_TOPIC, "0x"+"00"*31+"01"], "data":"0x"+"11"*64,
         "transactionHash":"0x"+"22"*32}]}
    P.CUTOFF_BLOCK = 24_781_026
    args = argparse.Namespace(sample=str(sample), out=str(tmp/f"{tag}.json"),
                              evidence=str(tmp/f"{tag}.jsonl"),
                              checkpoint=str(ckpt or tmp/f"{tag}.ck.jsonl"),
                              spec="MEASUREMENT_SPEC.v1.19.md", parallel=parallel,
                              slot_limit=2, max_calls=99999, max_seconds=9999,
                              rps=1000, diagnostics=True)
    os.environ["ETH_RPC_URL"]="https://x.invalid/v2/AAAAAAAAAAAAAAAA"
    os.environ["ETHERSCAN_API_KEY"]="K"*20
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = P.measure(args)
    return code, json.loads((tmp/f"{tag}.json").read_text(encoding="utf-8"))

COMPARE = ("index","state","validation_passed","economic_eligible")
def project(doc):
    out=[]
    for r in doc["results"]:
        d={k:r.get(k) for k in COMPARE}
        d["first_mint"]=(r.get("trigger") or {}).get("first_mint_block")
        d["received"]=(r.get("entry") or {}).get("received")
        d["cash_in"]=(r.get("exit") or {}).get("cash_in")
        c=r.get("cost") or {}
        d["G_main"]=(c.get("G_by_scenario") or {}).get(c.get("main_scenario"))
        d["entry_attempts"]=c.get("entry_attempts")
        d["exit_attempts"]=c.get("exit_attempts")
        d["slot"]=(r.get("model") or {}).get("slot")
        d["identity"]=(r.get("state_validation") or {}).get("identity")
        out.append(d)
    return sorted(out, key=lambda x:x["index"])

tmp = Path(tempfile.mkdtemp())
print("串行基准")
c1, d1 = run(tmp, "serial", 1)
check("退出码 0", c1 == 0, str(c1))
check(f"{N} 个候选", len(d1["results"]) == N, str(len(d1["results"])))
check("parallel=1", d1["parallel"] == 1)

print("\n两路并行（同一冻结样本与状态块）")
c2, d2 = run(tmp, "par2", 2)
check("退出码 0", c2 == 0, str(c2))
check("parallel=2", d2["parallel"] == 2)
check("finalized 快照相同",
      d1["finalized_snapshot"] == d2["finalized_snapshot"], "快照必须一致")

print("\n逐字段比对（耗时与请求顺序允许不同）")
p1, p2 = project(d1), project(d2)
check("候选集合相同", [x["index"] for x in p1] == [x["index"] for x in p2])
diffs = [(a["index"], k, a[k], b[k]) for a, b in zip(p1, p2)
         for k in a if a[k] != b[k]]
check("状态/金额/分类/身份全部一致", not diffs, str(diffs[:3]))
check("联合可用性判定一致",
      [x["validation_passed"] for x in p1] == [x["validation_passed"] for x in p2])

print("\n全局限流与预算共享（不是各分一半）")
g = d2["gate_stats"]
check("闸门有统计", g is not None and g["logical_requests"] > 0, str(g)[:100])
check("两路都经过同一闸门",
      len([k for k in g["logical_per_worker"] if k != "None"]) >= 2,
      str(g["logical_per_worker"]))
tot = sum(sum(v.values()) for v in g["logical_per_worker"].values())
check("闸门逻辑总数 = 各路之和", g["logical_requests"] == tot,
      f"{g['logical_requests']} vs {tot}")
# 受控链没有真实 HTTP，所以 http_sent 应为 0 —— 这本身就说明
# 几个口径是分开记的，不拿"预留额度"或"逻辑请求数"冒充"实际发出次数"
check("实际发出与逻辑请求分开计",
      g["http_sent"] == 0 and g["logical_requests"] > 0,
      f"sent={g['http_sent']} reserved={g['http_reserved']} logical={g['logical_requests']}")
check("串行分支也有闸门统计", d1["gate_stats"] is not None
      and d1["gate_stats"]["logical_requests"] > 0, str(d1["gate_stats"])[:80])
# 注意：上面的并行流程里 P.etherscan 被 mock 整体替换，真函数没跑，
# 所以「Etherscan 走闸门」必须在单元级验证 —— 让真函数执行，只挡住网络。
# 传输层的假实现装在**闸门之下**（install_http_gate 的 transport 注入），
# 这样真实 HTTP 边界仍然经过闸门 —— 而不是把 urlopen 整个换掉从而绕开它。
_gate = E.SharedGate(rps=1000, max_calls=100, max_seconds=60)
_before_http, _before_logical = _gate.sent, _gate.logical
_hits = []


class _Resp:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=None): return b'{"status":"1","result":[]}'


def _transport(*a, **kw):
    _hits.append(1)
    return _Resp()


E.install_http_gate(_gate, transport=_transport)
try:
    REAL_ETHERSCAN("K"*20, log=None, gate=_gate, worker=7,
                   module="stats", action="ethprice")
finally:
    E.uninstall_http_gate()
check("Etherscan 的真实 HTTP 经过闸门并计入实际发出次数",
      _gate.sent == _before_http + 1 and len(_hits) == 1,
      f"sent {_before_http}→{_gate.sent}, 传输命中 {len(_hits)}")
check("Etherscan 同时计入逻辑请求", _gate.logical == _before_logical + 1,
      f"{_before_logical} → {_gate.logical}")
check("按 etherscan 类别单独统计", any(k[1] == "etherscan" for k in _gate.per_worker),
      str(list(_gate.per_worker)))
check("实际 HTTP 也归到发起的 worker",
      any(k == (7, "etherscan") for k in _gate.per_worker_sent),
      str(list(_gate.per_worker_sent)))

print("\n请求 ID 隔离：每条证据带 worker 标签")
recs, diag = E.read_evidence(str(tmp/"par2.jsonl"), report=True)
check("证据完整", diag["complete"] is True, str(diag["bad_lines"]))
workers = {r.get("worker") for r in recs if r["kind"] == "rpc"}
check("RPC 证据带 worker 标签且多于一个", len(workers - {None}) >= 2, str(workers))
per_cand = {}
for r in recs:
    if r["kind"] == "rpc" and r.get("candidate") is not None:
        per_cand.setdefault(r["candidate"], set()).add(r.get("worker"))
check("同一候选的调用不跨 worker", all(len(v) == 1 for v in per_cand.values()),
      str({k: v for k, v in per_cand.items() if len(v) > 1}))

print("\n并行下的断点续跑")
tmp2 = Path(tempfile.mkdtemp())
ck = tmp2/"shared.ck.jsonl"
run(tmp2, "p1", 2, ckpt=ck)
c3, d3 = run(tmp2, "p2", 2, sample=tmp2/"s.json", ckpt=ck)
check("第二次全部跳过", sorted(d3["acceptance"]["skipped_already_completed"]) == list(range(1, N+1)),
      str(d3["acceptance"]["skipped_already_completed"]))
check("resumed=True", d3["acceptance"]["resumed"] is True)

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

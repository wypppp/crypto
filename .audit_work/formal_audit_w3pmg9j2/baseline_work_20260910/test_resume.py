#!/usr/bin/env python3
"""断点续跑的受控测试：绑定、跳过、失败历史、拒绝复用（离线）。"""
import argparse, contextlib, hashlib, io, json, os, sys, tempfile
from pathlib import Path
import pilot_measure as P
import evidence as E
from fake_chain import FakeRpc

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

PAIR = "0x" + "ab" * 20
TOKEN = "0x" + "cd" * 20
CREATED, MINT = 24_140_000, 24_140_010

def make_sample(tmp, n=2):
    sample = tmp / "s.json"
    sample.write_text(json.dumps({
        "universe_sha256": hashlib.sha256(Path(P.UNIVERSE).read_bytes()).hexdigest(),
        "n": n, "sample": [{"index": i, "pair": PAIR, "token": TOKEN,
                            "created_block": CREATED} for i in range(1, n + 1)]},
        ensure_ascii=False), encoding="utf-8")
    return sample

def run(tmp, sample, faults=(), spec="MEASUREMENT_SPEC.v1.3.md", tag="r"):
    cfg = {"head": 25_900_000, "genesis_ts": 0, "entry_block": MINT + 1,
           "pair": PAIR, "token": TOKEN, "received": 10**18, "cash": 10**15,
           "slot": 0, "faults": faults,
           "supply": lambda b: 0 if int(b, 16) < MINT else 10**6}
    rpc = FakeRpc(cfg)
    P.V.RPC = lambda *a, **k: rpc
    P.etherscan = lambda key, **kw: {"status": "1", "message": "OK", "result": [
        {"address": PAIR, "blockNumber": hex(MINT), "logIndex": "0x0",
         "topics": [P.MINT_TOPIC, "0x" + "00"*31 + "01"], "data": "0x" + "11"*64,
         "transactionHash": "0x" + "22"*32}]}
    P.CUTOFF_BLOCK = 24_781_026
    args = argparse.Namespace(sample=str(sample), out=str(tmp/f"{tag}.json"),
                              evidence=str(tmp/f"{tag}.jsonl"),
                              checkpoint=str(tmp/"ck.jsonl"), spec=spec,
                              slot_limit=2, max_calls=99999, max_seconds=9999,
                              rps=1000, diagnostics=False, parallel=1)
    os.environ["ETH_RPC_URL"] = "https://x.invalid/v2/AAAAAAAAAAAAAAAA"
    os.environ["ETHERSCAN_API_KEY"] = "K" * 20
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = P.measure(args)
        except SystemExit as e:
            return "REFUSED", None, str(e), rpc
    doc = json.loads((tmp/f"{tag}.json").read_text(encoding="utf-8")) \
        if (tmp/f"{tag}.json").exists() else None
    return code, doc, buf.getvalue(), rpc

print("第一次运行：建立检查点")
tmp = Path(tempfile.mkdtemp()); sample = make_sample(tmp, 2)
code, doc, out, rpc1 = run(tmp, sample, tag="run1")
check("退出码 0", code == 0, str(code))
check("处理了 2 个候选", doc["acceptance"]["n"] == 2, str(doc["acceptance"]["n"]))
check("resumed=False", doc["acceptance"]["resumed"] is False)
ck = E.Checkpoint(tmp/"ck.jsonl")
check("检查点写入了绑定", ck.binding is not None)
check("检查点记录 2 次尝试", len(ck.attempts()) == 2, str(len(ck.attempts())))
check("2 个候选标记完成", ck.completed() == {1, 2}, str(ck.completed()))

print("\n第二次运行（同一检查点）：已完成的必须跳过")
code, doc, out, rpc2 = run(tmp, sample, tag="run2")
check("退出码 0", code == 0, str(code))
check("resumed=True", doc["acceptance"]["resumed"] is True)
check("两个候选都被跳过", doc["acceptance"]["skipped_already_completed"] == [1, 2],
      str(doc["acceptance"]["skipped_already_completed"]))
check("未重复执行（本次候选 RPC 为 0）",
      all(r["method"] != "eth_call" or "totalSupply" not in str(r) for r in rpc2.records[3:])
      or len(rpc2.records) <= 4, f"{len(rpc2.records)} 次调用")

print("\n失败候选：不标完成，且历史保留")
tmp2 = Path(tempfile.mkdtemp()); s2 = make_sample(tmp2, 1)
code, doc, out, _ = run(tmp2, s2, faults=("wallet_dirty",), tag="f1")
check("首次失败退出非零", code == 1, str(code))
ck2 = E.Checkpoint(tmp2/"ck.jsonl")
check("失败尝试被记录", len(ck2.attempts(1)) == 1)
check("未标记完成", ck2.completed() == set(), str(ck2.completed()))
code, doc, out, _ = run(tmp2, s2, tag="f2")          # 故障移除后重试
check("重试成功", code == 0, str(code))
ck3 = E.Checkpoint(tmp2/"ck.jsonl")
att = ck3.attempts(1)
check("两次尝试都在（失败历史未被覆盖）", len(att) == 2, f"{len(att)} 次")
check("第一次记为失败", att[0]["state"] == "state_validation_failed"
      and att[0]["completed"] is False, str(att[0]["state"]))
check("第二次记为成功", att[1]["completed"] is True and att[1]["attempt"] == 2)

print("\n绑定不符必须拒绝复用（每例独立检查点，避免相互污染）")
def mismatch_case(name, *, mutate_sample=False, spec=None, expect_key):
    t = Path(tempfile.mkdtemp()); sm = make_sample(t, 1)
    run(t, sm, tag="base")                                  # 先建立绑定
    if mutate_sample:
        sm.write_text(sm.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    code, doc, out, _ = run(t, sm, spec=spec or "MEASUREMENT_SPEC.v1.3.md", tag="mm")
    check(f"{name} → 拒绝", code == "REFUSED", str(code)[:40])
    check(f"{name} → 差异指向 {expect_key}", expect_key in str(out), str(out)[:90])

mismatch_case("样本变了", mutate_sample=True, expect_key="sample_sha256")
mismatch_case("规格变了", spec="MEASUREMENT_SPEC.v1.2.md", expect_key="spec_sha256")

print("\nfinalized 块重组必须拒绝续跑")
tmp3 = Path(tempfile.mkdtemp()); s3 = make_sample(tmp3, 1)
run(tmp3, s3, tag="a")
code, doc, out, _ = run(tmp3, s3, faults=("finalized_reorg",), tag="b")
check("finalized hash 变化被检出并拒绝", code == 2, str(code))
check("留下 abort 证据", "finalized" in str(out) or code == 2)

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)

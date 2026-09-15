#!/usr/bin/env python3
"""端到端阻断反例：受控失败必须让完整流程返回非零、产物标记不通过。"""
import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
import pilot_measure as P
import verify_capabilities as V
import evidence as E
from fake_chain import FakeRpc, probe_ret

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

PAIR = "0x" + "ab" * 20
TOKEN = "0x" + "cd" * 20
CREATED = 24_140_000
MINT = 24_140_010

def scenario(faults=(), tmp=None):
    tmp = Path(tmp or tempfile.mkdtemp())
    # 冻结样本 + 台账（run_header 会校验 hash）
    uni = P.UNIVERSE
    sample = tmp / "s.json"
    sample.write_text(json.dumps({
        "declared_at": "x", "seed": 1, "n": 1,
        "universe_sha256": hashlib.sha256(Path(uni).read_bytes()).hexdigest(),
        "universe_weth_rows": 1,
        "sample": [{"index": 1, "pair": PAIR, "token": TOKEN,
                    "created_block": CREATED}]}, ensure_ascii=False), encoding="utf-8")
    cfg = {"head": 25_900_000, "genesis_ts": 0, "entry_block": MINT + 1,
           "pair": PAIR, "token": TOKEN, "received": 10**18, "cash": 10**15,
           "slot": 0, "faults": faults,
           "supply": lambda b: 0 if int(b, 16) < MINT else 10**6}
    rpc = FakeRpc(cfg)
    P.V.RPC = lambda *a, **k: rpc
    P.etherscan = lambda key, **kw: {
        "status": "1", "message": "OK",
        "result": [{"address": PAIR, "blockNumber": hex(MINT), "logIndex": "0x0",
                    "topics": [P.MINT_TOPIC, "0x" + "00"*31 + "01"],
                    "data": "0x" + "11" * 64,
                    "transactionHash": "0x" + "22" * 32}]}
    P.CUTOFF_BLOCK = 24_781_026
    args = argparse.Namespace(sample=str(sample), out=str(tmp/"r.json"),
                              evidence=str(tmp/"e.jsonl"),
                              checkpoint=str(tmp/"ck.jsonl"),
                              spec="MEASUREMENT_SPEC.v1.3.md",
                              slot_limit=2, max_calls=99999, max_seconds=9999,
                              rps=1000, diagnostics=True, parallel=1)
    os.environ["ETH_RPC_URL"] = "https://x.invalid/v2/AAAAAAAAAAAAAAAA"
    os.environ["ETHERSCAN_API_KEY"] = "K" * 20
    import io as _io, contextlib
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = P.measure(args)
    doc = json.loads((tmp/"r.json").read_text(encoding="utf-8")) if (tmp/"r.json").exists() else None
    return code, doc, buf.getvalue(), tmp

def main():
    print("基线：无故障注入")
    code, doc, out, _ = scenario()
    r = doc["results"][0] if doc else None
    check("退出码 0", code == 0, f"code={code}")
    check("state=measured_exit", r and r["state"] == "measured_exit", r and r["state"])
    check("validation_passed=True", r and r["validation_passed"] is True)
    check("acceptance.validation_passed=True", doc["acceptance"]["validation_passed"] is True)
    check("economic_eligible 仍为 False", r and r["economic_eligible"] is False)

    print("\n诊断：卖出 revert 时 size_probe 与 identity_probe 都要跑")
    code, doc, out, _ = scenario(("sell_reverts",))
    r = doc["results"][0]
    check("state=execution_reverted_unknown", r["state"] == "execution_reverted_unknown", r["state"])
    dg = (r.get("model") or {}).get("diagnostics") or {}
    check("size_probe 有结果", "size_probe" in dg, str(list(dg)))
    check("identity_probe 有结果", "identity_probe" in dg, str(dg.get("identity_probe"))[:60])
    ip = dg.get("identity_probe") or {}
    check("identity_probe 记录身份为 CALLER", ip.get("identity") == "CALLER", str(ip.get("identity")))
    check("两个虚拟身份同样失败时不下结论",
      "does NOT exclude" in str(ip.get("note", "")), str(ip.get("note"))[:50])
    check("最小单位 revert 不排除规模机制的注记在", 
      "does NOT exclude" in str(dg["size_probe"].get("note","")))
    check("诊断调用不计为交易尝试",
      r["model"].get("diagnostics_note", "").endswith("NOT transaction attempts"))
    check("成本里退出尝试仍按 stage20 记（swap1/approve2）",
      r["cost"]["exit_attempts"]["swap"] == 1 and r["cost"]["exit_attempts"]["approve"] == 2,
      str(r["cost"]["exit_attempts"]))
    check("R_wei 为 None（未成功卖出不记回收）", r["cost"]["R_wei"] is None, str(r["cost"]["R_wei"]))

    print("\n诊断：两个身份结果不同时也只记录")
    code, doc, out, _ = scenario(("sell_reverts", "identity_ok"))
    ip2 = ((doc["results"][0].get("model") or {}).get("diagnostics") or {}).get("identity_probe") or {}
    check("CALLER 成功、WALLET 失败 → 如实记录 stage 差异", ip2.get("stage") == 0, str(ip2.get("stage")))
    check("状态仍为 execution_reverted_unknown（诊断不改判定）",
      doc["results"][0]["state"] == "execution_reverted_unknown")

    CASES = [
        ("虚拟地址已有代码", ("wallet_dirty",), "state_validation_failed"),
        ("父链接断裂", ("parent_link_broken",), "state_validation_failed"),
        ("pair 两侧不是 WETH+token", ("bad_sides",), "state_validation_failed"),
        ("factory.getPair 回不到本 pair", ("bad_getpair",), "state_validation_failed"),
        ("fresh 复读发现重组", ("reorg_on_fresh",), "state_validation_failed"),
    ]
    for name, faults, want in CASES:
        print(f"\n注入：{name}")
        code, doc, out, _ = scenario(faults)
        r = doc["results"][0] if doc else None
        check("退出码非零", code != 0, f"code={code}")
        check(f"state={want}", r and r["state"] == want, r and r["state"])
        check("validation_passed=False", r and r["validation_passed"] is False)
        check("acceptance 标记未通过",
              doc and doc["acceptance"]["validation_passed"] is False
              and doc["acceptance"]["validation_failed"] == [1])
        recs, diag = E.read_evidence(str(Path(doc["evidence_file"])), report=True)
        check("证据仍完整可读", diag["complete"] is True, str(diag["bad_lines"]))

    print(f"\n通过 {ok} / 失败 {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()

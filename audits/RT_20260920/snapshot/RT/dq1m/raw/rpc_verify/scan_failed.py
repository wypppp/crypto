"""扫描最近的失败交易，检查其内层指令里是否仍带 pump / PumpSwap 事件。"""
import json, subprocess, time
from verify_events import rpc, b58d, TAG, DISC, AMM, PUMP
found = {"pump": [], "amm": []}; stats = {}
for prog, tag in [(PUMP, "pump"), (AMM, "amm")]:
    sigs, before = [], None
    for page in range(2):
        opt = {"limit": 1000}
        if before: opt["before"] = before
        r = rpc("getSignaturesForAddress", [prog, opt], f"scan_sigs_{tag}_{page}") or []
        sigs += r; before = r[-1]["signature"] if r else None
        time.sleep(1)
    failed = [s for s in sigs if s.get("err")]
    stats[tag] = {"scanned": len(sigs), "failed": len(failed)}
    checked = 0
    for s in failed[:40]:
        tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "json"}], f"scan_failed_{tag}_{checked}")
        time.sleep(0.6); checked += 1
        if not tx: continue
        evs = []
        for grp in tx["meta"].get("innerInstructions") or []:
            for ins in grp["instructions"]:
                try: raw = b58d(ins["data"])
                except Exception: continue
                if raw[:8] == TAG and raw[8:16] in DISC: evs.append(DISC[raw[8:16]])
        if evs:
            found[tag].append({"signature": s["signature"], "slot": s["slot"], "block_time": s.get("blockTime"), "events": evs, "err": s["err"]})
    stats[tag]["failed_checked"] = checked
    stats[tag]["failed_with_event"] = len(found[tag])
json.dump({"stats": stats, "found": found}, open("scan_failed_result.json", "w"), indent=1)
print(json.dumps(stats, indent=1))
for tag in found:
    for f in found[tag][:5]: print(tag, f["signature"], f["block_time"], f["events"], str(f["err"])[:80])

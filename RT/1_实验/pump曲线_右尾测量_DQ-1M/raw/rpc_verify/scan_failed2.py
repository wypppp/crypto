"""多抓几笔"失败但仍发出事件"的交易，供 Dune 侧核对。"""
import json, time, datetime
from verify_events import rpc, b58d, TAG, DISC, AMM, PUMP
out = []
for prog, tag in [(AMM, "amm"), (PUMP, "pump")]:
    sigs, before = [], None
    for page in range(3):
        opt = {"limit": 1000}
        if before: opt["before"] = before
        r = rpc("getSignaturesForAddress", [prog, opt], f"s2_{tag}_{page}") or []
        sigs += r; before = r[-1]["signature"] if r else None
        time.sleep(0.8)
    failed = [s for s in sigs if s.get("err")]
    n = 0
    for s in failed:
        if len([o for o in out if o["program"] == tag]) >= 4 or n >= 120: break
        n += 1
        tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "json"}], f"s2tx_{tag}_{n}")
        time.sleep(0.45)
        if not tx: continue
        evs = []
        for grp in tx["meta"].get("innerInstructions") or []:
            for ins in grp["instructions"]:
                try: raw = b58d(ins["data"])
                except Exception: continue
                if raw[:8] == TAG and raw[8:16] in DISC: evs.append(DISC[raw[8:16]])
        if evs:
            bt = s.get("blockTime")
            out.append({"program": tag, "signature": s["signature"], "events": sorted(set(evs)),
                        "block_time": bt, "utc_date": str(datetime.datetime.utcfromtimestamp(bt).date()) if bt else None,
                        "err": str(s["err"])[:60]})
            print("命中", tag, s["signature"][:20], evs, out[-1]["utc_date"])
json.dump(out, open("failed_with_events.json", "w"), indent=1)
print("合计", len(out), "笔")

"""Decode archived Anchor event data and reconcile buy amounts to trades.csv.

Only local gzip archives and checked-in Pump IDLs are read. Amounts are
lamports from TradeEvent.sol_amount or BuyEvent.quote_amount_in_with_lp_fee.
"""
import base64, gzip, json
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parents[3]
CASE = ROOT / "RT/case_timing"
OUT = Path(__file__).parent
IDL_FILES = [ROOT / "RT/dq1m/raw/pumpdocs/pump.json", ROOT / "RT/dq1m/raw/pumpdocs/pump_amm.json"]
PUMP_ID = json.load(open(IDL_FILES[0]))["address"]
AMM_ID = json.load(open(IDL_FILES[1]))["address"]

idls = [json.load(open(p)) for p in IDL_FILES]
events, types = {}, {}
for d in idls:
    for e in d.get("events", []):
        events[bytes(e["discriminator"])] = e["name"]
    for t in d.get("types", []):
        types[t["name"]] = t["type"]

def read_type(buf, pos, typ):
    if typ == "u8": return buf[pos], pos + 1
    if typ == "u16": return int.from_bytes(buf[pos:pos+2], "little"), pos + 2
    if typ == "u64": return int.from_bytes(buf[pos:pos+8], "little"), pos + 8
    if typ == "i64": return int.from_bytes(buf[pos:pos+8], "little", signed=True), pos + 8
    if typ == "i128": return int.from_bytes(buf[pos:pos+16], "little", signed=True), pos + 16
    if typ == "bool": return bool(buf[pos]), pos + 1
    if typ == "pubkey": return buf[pos:pos+32], pos + 32
    if typ == "string":
        n = int.from_bytes(buf[pos:pos+4], "little"); pos += 4
        return buf[pos:pos+n].decode("utf-8", "replace"), pos + n
    if isinstance(typ, dict) and "vec" in typ:
        n = int.from_bytes(buf[pos:pos+4], "little"); pos += 4
        vals = []
        for _ in range(n):
            x, pos = read_type(buf, pos, typ["vec"])
            vals.append(x)
        return vals, pos
    if isinstance(typ, dict) and "defined" in typ:
        spec = types[typ["defined"]["name"]]
    elif isinstance(typ, dict):
        spec = typ
    else:
        raise ValueError(f"unsupported type {typ}")
    if spec["kind"] == "struct":
        out = {}
        for f in spec["fields"]:
            out[f["name"]], pos = read_type(buf, pos, f["type"])
        return out, pos
    raise ValueError(f"unsupported spec {spec}")

def b58(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(raw, "big"); out = ""
    while n: n, r = divmod(n, 58); out = alphabet[r] + out
    return alphabet[0] * (len(raw) - len(raw.lstrip(b"\0"))) + (out or alphabet[0])

def decode_event(data):
    raw = base64.b64decode(data)
    name = events.get(raw[:8])
    if not name:
        return None
    # These two amounts/flags have fixed offsets in the checked-in IDLs.  Use
    # direct offsets so a variable-length shareholder vector cannot invalidate
    # an otherwise valid TradeEvent decode.
    if name == "TradeEvent":
        if len(raw) < 57: raise ValueError("short TradeEvent prefix")
        return name, {"sol_amount": int.from_bytes(raw[8+32:8+40], "little"),
                      "is_buy": bool(raw[56]), "mint": b58(raw[8:40])}
    if name == "BuyEvent":
        if len(raw) < 152: raise ValueError("short BuyEvent prefix")
        return name, {"quote_amount_in_with_lp_fee": int.from_bytes(raw[8+96:8+104], "little"),
                      "pool": b58(raw[120:152])}
    if name in {"SellEvent", "DepositEvent", "WithdrawEvent", "CreatePoolEvent",
                "CompletePumpAmmMigrationEvent", "MigratePoolCoinCreatorEvent",
                "CompleteEvent", "MigrateBondingCurveCreatorEvent"}:
        return name, {}
    spec = types.get(name)
    if not spec:
        return name, {}
    obj, pos = read_type(raw, 8, spec)
    if pos > len(raw):
        raise ValueError(f"short {name}")
    return name, obj

CASE_MINTS = set(pd.read_csv(CASE / "raw/creation_and_counts.csv").mint)
venues = pd.read_csv(CASE / "venues.csv").set_index("mint")
curve_by_mint = venues.curve.to_dict()
pool_by_mint = venues.pool.to_dict()
tx = {}
for path in sorted((CASE / "raw").glob("full24h_*.jsonl.gz")):
    mint = path.name[len("full24h_"):-len(".jsonl.gz")]
    if mint not in CASE_MINTS:
        continue
    with gzip.open(path, "rt") as fh:
        for line in fh:
            x = json.loads(line)
            sig = x["transaction"]["signatures"][0]
            key = (mint, sig)
            rec = tx.setdefault(key, {"mint": mint, "slot": x["slot"], "tx_index": x["transactionIndex"],
                                      "ts": x.get("blockTime"), "sig": sig, "buys": [], "sell_count": 0,
                                      "liquidity_or_migration_count": 0, "event_names": [], "decode_fail": 0})
            stack = []
            for log in x.get("meta", {}).get("logMessages") or []:
                if log.startswith("Program ") and " invoke [" in log:
                    stack.append(log.split(" ", 2)[1]); continue
                if log.startswith("Program ") and (log.endswith(" success") or log.endswith(" failed")):
                    pid = log.split(" ", 2)[1]
                    if stack and stack[-1] == pid: stack.pop()
                    continue
                if not log.startswith("Program data: "): continue
                if not stack or stack[-1] not in {PUMP_ID, AMM_ID}: continue
                try: ev = decode_event(log.split(": ", 1)[1])
                except Exception: rec["decode_fail"] += 1; continue
                if not ev: continue
                name, obj = ev; rec["event_names"].append(name)
                if name == "TradeEvent" and obj.get("mint") == mint and obj.get("is_buy"):
                    rec["buys"].append(int(obj["sol_amount"]))
                elif name == "TradeEvent" and obj.get("mint") == mint and not obj.get("is_buy"):
                    rec["sell_count"] += 1
                elif name == "BuyEvent" and obj.get("pool") == pool_by_mint.get(mint):
                    rec["buys"].append(int(obj["quote_amount_in_with_lp_fee"]))
                elif name == "SellEvent":
                    rec["sell_count"] += 1
                if name in {"DepositEvent", "WithdrawEvent", "CreatePoolEvent", "CompletePumpAmmMigrationEvent",
                            "MigratePoolCoinCreatorEvent", "CompleteEvent", "MigrateBondingCurveCreatorEvent"}:
                    rec["liquidity_or_migration_count"] += 1

rows = []
for rec in tx.values():
    lamports = sum(rec["buys"])
    rows.append({"mint": rec["mint"], "slot": rec["slot"], "tx_index": rec["tx_index"], "ts": rec["ts"],
                 "sig": rec["sig"], "buy_net_lamports": lamports if rec["buys"] else None,
                 "sell_count": rec["sell_count"], "liquidity_or_migration_count": rec["liquidity_or_migration_count"],
                 "amount_valid": bool(rec["buys"]) and rec["decode_fail"] == 0, "event_names": ";".join(rec["event_names"]),
                 "decode_fail": rec["decode_fail"]})
norm = pd.DataFrame(rows).sort_values(["mint", "slot", "tx_index"])
norm.to_csv(OUT / "normalized_events.csv", index=False)

tr = pd.read_csv(CASE / "trades.csv")
tr = tr[tr.mint.isin(CASE_MINTS)].copy()
tr["venue"] = tr["venue"].fillna("")
g = tr.groupby(["mint", "sig"], as_index=False).agg(sol=("sol", "sum"), kinds=("kind", lambda x: ";".join(sorted(set(x)))),
                                                        venue=("venue", lambda x: ";".join(sorted(set(x)))))
g["trade_lamports"] = (g.sol * 1_000_000_000).round().astype("Int64")
g["pure_buy"] = g.kinds.eq("buy")
g["curve_or_pool"] = g.venue.isin(["curve", "pool"])
cmp = g.merge(norm[["mint", "sig", "buy_net_lamports", "sell_count", "liquidity_or_migration_count", "amount_valid"]], on=["mint", "sig"], how="left")
cmp["eligible"] = cmp.pure_buy & cmp.curve_or_pool & cmp.sell_count.eq(0) & cmp.liquidity_or_migration_count.eq(0) & cmp.amount_valid
cmp["delta_lamports"] = cmp.buy_net_lamports - cmp.trade_lamports
cmp.to_csv(OUT / "event_trade_reconciliation.csv", index=False)
eligible = cmp[cmp.eligible]
report = [
    f"archive tx rows decoded: {len(norm)}",
    f"rows with recognized buy amount: {int(norm.amount_valid.sum())}",
    f"rows with sell events: {int(norm.sell_count.gt(0).sum())}",
    f"rows with liquidity/migration events: {int(norm.liquidity_or_migration_count.gt(0).sum())}",
    f"pure buy curve/pool eligible comparisons: {len(eligible)}",
    f"eligible exact lamport matches: {int(eligible.delta_lamports.eq(0).sum())}",
    f"eligible nonzero differences: {int(eligible.delta_lamports.ne(0).sum())}",
    f"eligible unsupported/missing amount: {int((cmp.pure_buy & cmp.curve_or_pool & ~cmp.amount_valid).sum())}",
    f"max absolute eligible difference lamports: {int(eligible.delta_lamports.abs().max()) if len(eligible) else 'n/a'}",
]
(OUT / "event_decode_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report))

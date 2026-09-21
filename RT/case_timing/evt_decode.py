"""Pump / PumpAMM Anchor events from INNER-INSTRUCTION CPI data (emit_cpi), as Dune decodes them.
Log-based decoding misses events when a transaction's logs are truncated (F103)."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[2]
IDLS = [json.load(open(ROOT / "RT/dq1m/raw/pumpdocs/pump.json")), json.load(open(ROOT / "RT/dq1m/raw/pumpdocs/pump_amm.json"))]
PUMP, AMM = IDLS[0]["address"], IDLS[1]["address"]
EVENTS = {bytes(e["discriminator"]): e["name"] for d in IDLS for e in d.get("events", [])}
CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")  # anchor event-CPI instruction tag
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58e(raw):
    n = int.from_bytes(raw, "big"); out = ""
    while n: n, r = divmod(n, 58); out = ALPH[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out

def b58d(t):
    n = 0
    for ch in t: n = n * 58 + ALPH.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(t) - len(t.lstrip("1"))) + raw

def account_keys(x):
    la = x["meta"].get("loadedAddresses") or {}
    return x["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])

def u64(raw, o):
    return int.from_bytes(raw[o:o + 8], "little")


def iter_events(x):
    """Yield dicts: name, outer_program, and decoded fields used by H1 (fixed offsets from the checked-in IDLs)."""
    keys = account_keys(x)
    top = x["transaction"]["message"]["instructions"]
    for grp in x["meta"].get("innerInstructions") or []:
        outer = keys[top[grp["index"]]["programIdIndex"]]
        for ii, ins in enumerate(grp["instructions"]):
            if keys[ins["programIdIndex"]] not in (PUMP, AMM):
                continue
            d = b58d(ins["data"])
            if d[:8] != CPI_TAG:
                continue
            raw = d[8:]; name = EVENTS.get(raw[:8])
            if not name:
                continue
            e = {"name": name, "outer": outer, "oix": grp["index"], "iix": ii}
            if name == "TradeEvent":
                e.update(mint=b58e(raw[8:40]), sol_amount=u64(raw, 40), token_amount=u64(raw, 48), is_buy=bool(raw[56]),
                         user=b58e(raw[57:89]), virtual_sol_reserves=u64(raw, 97), virtual_token_reserves=u64(raw, 105),
                         real_sol_reserves=u64(raw, 113), fee_basis_points=u64(raw, 161), creator_fee_basis_points=u64(raw, 209))
            elif name in ("BuyEvent", "SellEvent"):
                e.update(pool=b58e(raw[120:152]), user=b58e(raw[152:184]), pool_base_token_reserves=u64(raw, 48),
                         pool_quote_token_reserves=u64(raw, 56), lp_fee_basis_points=u64(raw, 72), lp_fee=u64(raw, 80),
                         protocol_fee_basis_points=u64(raw, 88), protocol_fee=u64(raw, 96), coin_creator_fee_basis_points=u64(raw, 344))
                if name == "BuyEvent":
                    e.update(quote_amount_in=u64(raw, 64), quote_amount_in_with_lp_fee=u64(raw, 104), base_amount_out=u64(raw, 16))
                else:
                    e.update(quote_amount_out=u64(raw, 64), base_amount_in=u64(raw, 16))
            elif name in ("DepositEvent", "WithdrawEvent"):
                e["pool"] = b58e(raw[96:128])
            elif name == "CompletePumpAmmMigrationEvent":
                e["mint"] = b58e(raw[40:72])
            elif name == "CreatePoolEvent":
                e.update(index=int.from_bytes(raw[16:18], "little"), base_mint=b58e(raw[50:82]), pool=b58e(raw[173:205]))
            yield e

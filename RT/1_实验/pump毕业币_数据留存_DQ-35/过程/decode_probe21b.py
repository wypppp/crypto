#!/usr/bin/env python3
"""DQ-35 v2.1 探针 PROBE21b 的离线解码（10-04）：按 borsh 顺序解析 PumpSwap 买卖事件的原始字节，
先与解码表的已有列逐字段对齐（确认偏移），再读出解码表没有的尾部字段。只看字段布局与费用值。

python 过程/decode_probe21b.py  → 打印对齐结果与尾部字段
"""

import csv
import gzip
import struct
from collections import Counter
from pathlib import Path

H = Path(__file__).resolve().parent.parent
TAG = bytes.fromhex("e445a52e51cb9a1d")
DISC = {"B": bytes.fromhex("67f4521f2cf57777"), "S": bytes.fromhex("3e2f370aa503dc2a")}
U64_HEAD = {
    # 时间戳之后的 13 个 u64，按解码表列序
    "B": [
        "base_amount_out",
        "max_quote_amount_in",
        "user_base_token_reserves",
        "user_quote_token_reserves",
        "pool_base_token_reserves",
        "pool_quote_token_reserves",
        "quote_amount_in",
        "lp_fee_basis_points",
        "lp_fee",
        "protocol_fee_basis_points",
        "protocol_fee",
        "quote_amount_in_with_lp_fee",
        "user_quote_amount_in",
    ],
    "S": [
        "base_amount_in",
        "min_quote_amount_out",
        "user_base_token_reserves",
        "user_quote_token_reserves",
        "pool_base_token_reserves",
        "pool_quote_token_reserves",
        "quote_amount_out",
        "lp_fee_basis_points",
        "lp_fee",
        "protocol_fee_basis_points",
        "protocol_fee",
        "quote_amount_out_without_lp_fee",
        "user_quote_amount_out",
    ],
}


class R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def take(self, n):
        v = self.b[self.i : self.i + n]
        self.i += n
        return v

    def u64(self):
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]


def decode(side, raw):
    b = bytes.fromhex(raw)
    r = R(b)
    assert r.take(8) == TAG
    disc = r.take(8)
    d = {"disc_ok": disc == DISC[side], "timestamp": r.i64()}
    for k in U64_HEAD[side]:
        d[k] = r.u64()
    r.take(
        32 * 7
    )  # pool, user, 两个用户代币账户, 协议费收款人及其代币账户, coin_creator
    d["coin_creator_fee_basis_points"] = r.u64()
    d["coin_creator_fee"] = r.u64()
    if side == "B":
        d["track_volume"] = r.take(1)[0]
        for k in (
            "total_unclaimed_tokens",
            "total_claimed_tokens",
            "current_sol_volume",
        ):
            d[k] = r.u64()
        d["last_update_timestamp"] = r.i64()
        d["min_base_amount_out"] = r.u64()
        n = struct.unpack("<I", r.take(4))[0]
        d["ix_name"] = r.take(n).decode()
    d["tail_offset"] = r.i
    for k in (
        "cashback_fee_basis_points",
        "cashback",
        "buyback_fee_basis_points",
        "buyback_fee",
    ):
        d[k] = r.u64()
    d["rest_hex"] = b[r.i :].hex()
    d["nbytes"] = len(b)
    return d


def main():
    rows = list(csv.DictReader(gzip.open(H / "raw" / "dune" / "PROBE21b.csv.gz", "rt")))
    dec = {}
    for x in rows:
        if x["src"] == "dec":
            dec.setdefault((x["side"], x["tx_id"]), []).append(x)
    chk = Counter()
    out = []
    for x in rows:
        if x["src"] != "raw":
            continue
        s = x["side"]
        d = decode(s, x["raw"])
        chk["disc_ok_%s" % s] += d["disc_ok"]
        cands = dec.get((s, x["tx_id"]), [])
        f1 = "base_amount_out" if s == "B" else "base_amount_in"
        f6 = "user_quote_amount_in" if s == "B" else "user_quote_amount_out"
        m = [
            c
            for c in cands
            if int(c["a1"]) == d[f1] and int(c["a2"]) == d["pool_quote_token_reserves"]
        ]
        if len(m) != 1:
            chk["unmatched_%s" % s] += 1
            continue
        c = m[0]
        ok = (
            int(c["a3"]) == d["lp_fee"]
            and int(c["a4"]) == d["protocol_fee"]
            and int(c["a5"]) == d["coin_creator_fee"]
            and int(c["a6"]) == d[f6]
        )
        if s == "B":
            ok = (
                ok
                and int(c["a7"]) == d["min_base_amount_out"]
                and c["a8"] == d["ix_name"]
            )
        else:
            ok = ok and int(c["a7"]) == d["min_quote_amount_out"]
            tail_ok = all(
                int(c[k]) == d[v]
                for k, v in (
                    ("cb_bps", "cashback_fee_basis_points"),
                    ("cb", "cashback"),
                    ("bb_bps", "buyback_fee_basis_points"),
                    ("bb", "buyback_fee"),
                )
            )
            chk["sell_tail_matches_decoded"] += tail_ok
        chk["head_fields_match_%s" % s] += ok
        out.append((s, d))
    print("核对：", dict(chk))
    for s in ("B", "S"):
        ds = [d for t, d in out if t == s]
        print(
            "\n== %s：%d 笔；字节数 %s；尾部偏移 %s"
            % (
                s,
                len(ds),
                Counter(d["nbytes"] for d in ds),
                Counter(d["tail_offset"] for d in ds),
            )
        )
        print("cashback_bps", Counter(d["cashback_fee_basis_points"] for d in ds))
        print("cashback>0 笔数", sum(d["cashback"] > 0 for d in ds))
        print("buyback_bps", Counter(d["buyback_fee_basis_points"] for d in ds))
        # 回购费＝协议费×bps/1e4（向下取整）？
        print(
            "buyback == floor(protocol_fee*bps/1e4)：%d / %d"
            % (
                sum(
                    d["buyback_fee"]
                    == d["protocol_fee"] * d["buyback_fee_basis_points"] // 10000
                    for d in ds
                ),
                len(ds),
            )
        )
        print(
            "cashback == floor(q*bps/1e4)（q＝不含 LP 费的报价量）：%d / %d"
            % (
                sum(
                    d["cashback"]
                    == (d["quote_amount_in"] if s == "B" else d["quote_amount_out"])
                    * d["cashback_fee_basis_points"]
                    // 10000
                    for d in ds
                ),
                len(ds),
            )
        )
        print("尾部剩余字节（前 3 例）：", [d["rest_hex"] for d in ds[:3]])


if __name__ == "__main__":
    main()

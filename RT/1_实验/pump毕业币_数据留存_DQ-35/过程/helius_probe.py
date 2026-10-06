#!/usr/bin/env python3
"""Helius 可用性探针（10-06；总控第二十一轮第二节第 2 条）：getTransactionsForAddress 能否调用、返回什么。

python 过程/helius_probe.py <池地址> <起 epoch 秒> <止 epoch 秒>  → runs/helius_probe.json
- 两次调用：只取签名（limit 5）与完整交易（limit 3），都按 blockTime 区间、升序、只要成功的交易。
- 计费（官方文档 10-06）：只取签名每次 10 credits；完整交易每 100 笔 10 credits，最低 10；失败调用不计费。本探针至多 20。
- 密钥按键名从 .env 正则读取，不打印。只记录状态、条数与字段名，不保存交易内容。
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent.parent
ENV = H.parents[2] / ".env"


def rpc_url():
    m = re.search(r"^\s*helius_RPC_URL\s*=\s*['\"]?([^'\"\s]+)", ENV.read_text(), re.M)
    return m.group(1)


def call(addr, cfg):
    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getTransactionsForAddress",
        "params": [addr, cfg],
    }
    req = urllib.request.Request(
        rpc_url(),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read()[:300].decode("utf-8", "replace")}


def main():
    addr, t0, t1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    flt = {"blockTime": {"gte": t0, "lt": t1}, "status": "succeeded"}
    out = {}
    for name, cfg in (
        (
            "signatures",
            {
                "transactionDetails": "signatures",
                "sortOrder": "asc",
                "limit": 5,
                "filters": flt,
            },
        ),
        (
            "full",
            {
                "transactionDetails": "full",
                "sortOrder": "asc",
                "limit": 3,
                "filters": flt,
            },
        ),
    ):
        r = call(addr, cfg)
        res = r.get("result") if isinstance(r, dict) else None
        rec = {
            "ok": res is not None,
            "error": r.get("error") or r.get("http_error"),
            "detail": r.get("body"),
        }
        if res:
            data = res.get("data") or []
            rec["n"] = len(data)
            rec["has_pagination_token"] = res.get("paginationToken") is not None
            rec["first_keys"] = sorted(data[0].keys()) if data else []
            if name == "full" and data:
                tx = data[0]
                meta = tx.get("meta") or {}
                rec["meta_keys"] = sorted(meta.keys())
                rec["n_inner_groups"] = len(meta.get("innerInstructions") or [])
                rec["blockTimes"] = [d.get("blockTime") for d in data]
            else:
                rec["blockTimes"] = [d.get("blockTime") for d in data]
        out[name] = rec
    (H / "runs" / "helius_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

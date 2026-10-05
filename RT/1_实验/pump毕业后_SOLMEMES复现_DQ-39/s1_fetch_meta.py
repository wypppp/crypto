#!/usr/bin/env python3
"""DQ-39 S1：开发 token 的链上元数据文本（10-06；总控第二十轮第五节“链上重建的正确文本”）。

python s1_fetch_meta.py  → raw/ipfs_meta.jsonl（只追加，可续传；不入库）
- 只取开发类 token（s0_structure.classify，先排除检验周、留出同名、范围外、无链上记录）。
- 名称、代号以链上创建事件为准（sql/S0_链上时间锚.sql）；描述在链下，按数据的 token_uri 取 IPFS 上的元数据 JSON。
  token_uri 跟着本行 token（每个 token 一个 uri；共用元数据的行 uri 各不相同，见 S0b_错位诊断.md），所以可用。
- 每条记录：token、cid、网关、状态、JSON 里的 name／symbol／description、原始字节的 sha256。不取图片。
"""

import concurrent.futures as cf
import hashlib
import json
import time
import urllib.request

import s0_structure as s0
import s0b_misalign as s

OUT = s.H / "raw" / "ipfs_meta.jsonl"
GATEWAYS = [
    "https://pump.mypinata.cloud/ipfs/",  # pump 自己的网关（10-06 实测：公共 Pinata 对部分 CID 返回 403）
    "https://gateway.pinata.cloud/ipfs/",
    "https://dweb.link/ipfs/",
    "https://w3s.link/ipfs/",
]
UA = {"User-Agent": "Mozilla/5.0 (research; DQ-39)"}


def cid_of(uri):
    for p in ("/ipfs/", "ipfs://"):
        if p in uri:
            return uri.split(p, 1)[1].split("?")[0]
    return None


def fetch(token, uri):
    cid = cid_of(uri or "")
    urls = [gw + cid for gw in GATEWAYS] if cid else []
    if not cid and (uri or "").startswith("http"):
        urls = [uri]  # 不是 IPFS 的 uri（irys、自建服务器等）：按原地址取
    if not urls:
        return dict(token=token, uri=uri, cid=None, status="no_uri")
    last = ""
    for url in urls:
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    b = r.read(200_000)
                j = json.loads(b.decode("utf-8", "replace"))
                return dict(
                    token=token,
                    uri=uri,
                    cid=cid,
                    status="ok",
                    gateway=url[: -len(cid)] if cid else url,
                    sha256=hashlib.sha256(b).hexdigest(),
                    name=j.get("name"),
                    symbol=j.get("symbol"),
                    description=j.get("description"),
                )
            except Exception as e:  # 网关失败、限流、内容不是 JSON：换下一个
                last = "%s: %s" % (type(e).__name__, str(e)[:120])
                time.sleep(1.5 * (attempt + 1))
    return dict(token=token, uri=uri, cid=cid, status="fail", error=last)


def main():
    m, anc = s.load()
    excl, _ = s0.holdout_names()
    uri = {}
    for i, t in enumerate(m["token"]):
        uri.setdefault(t, m["token_uri"][i])
    dev = sorted(t for t in uri if s0.classify(anc[t], excl) == "dev")
    done = set()
    if OUT.exists():
        with open(OUT) as f:
            for line in f:
                r = json.loads(line)
                if r["status"] == "ok":
                    done.add(r["token"])
    todo = [t for t in dev if t not in done]
    print(
        "开发 token %d，已取 %d，待取 %d" % (len(dev), len(done), len(todo)), flush=True
    )
    n = 0
    with open(OUT, "a") as f, cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(lambda t: fetch(t, uri[t]), todo):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 200 == 0:
                print(n, flush=True)
    print("完成 %d" % n, flush=True)


if __name__ == "__main__":
    main()

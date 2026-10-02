#!/usr/bin/env python3
"""DQ-34 写卡前三问之③的历史部分：从 Hydromancer Reservoir（requester-pays S3）列目录与下载（10-02；用户 10-02 批准，单项上限 $10）。

python hydromancer_get.py list <前缀>                 列目录（文件数、总字节），清单存 raw/hydromancer/listing_*.json
python hydromancer_get.py get <前缀> <字节上限GB>     下载前缀下全部对象；已下载且大小一致的跳过；累计超过上限即停

只用标准库（SigV4 签名自己实现，`selftest` 用 AWS 文档的官方示例核对）。密钥按键名用正则从工作区 .env 读取
（AWS_ACCESS_KEY_ID、AWS_SECRET_ACCESS_KEY），不打印、不写出。每个请求都带 x-amz-request-payer: requester。
预算告警有数小时延迟，所以脚本自己按字节封顶：东京区外网流量约 $0.114/GB，默认上限 40 GB 约 $4.6。
"""

import datetime as dt
import hashlib
import hmac
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
OUT = H / "raw" / "hydromancer"
BUCKET = "hydromancer-reservoir"
REGION = "ap-northeast-1"
HOST = f"{BUCKET}.s3.{REGION}.amazonaws.com"
EMPTY = hashlib.sha256(b"").hexdigest()


def keys() -> tuple:
    env = (H.parents[2] / ".env").read_text()
    out = []
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        m = re.search(rf"^\s*{name}\s*=\s*['\"]?([^'\"\s]+)", env, re.M)
        if m is None:
            raise RuntimeError(f"{name} not found in .env")
        out.append(m.group(1))
    return tuple(out)


def q(s: str, safe: str = "") -> str:
    return urllib.parse.quote(s, safe="-_.~" + safe)


def auth(method, host, path, query, headers, region, ak, sk, amzdate) -> str:
    """返回 Authorization 头（AWS SigV4，服务 s3）。headers 须含 host、x-amz-date、x-amz-content-sha256。"""
    day = amzdate[:8]
    cq = "&".join(f"{q(k)}={q(v)}" for k, v in sorted(query.items()))
    hs = {k.lower(): str(v).strip() for k, v in headers.items()}
    signed = ";".join(sorted(hs))
    canon = "\n".join(
        [
            method,
            q(path, "/"),
            cq,
            "".join(f"{k}:{hs[k]}\n" for k in sorted(hs)),
            signed,
            hs["x-amz-content-sha256"],
        ]
    )
    scope = f"{day}/{region}/s3/aws4_request"
    sts = "\n".join(
        ["AWS4-HMAC-SHA256", amzdate, scope, hashlib.sha256(canon.encode()).hexdigest()]
    )
    k = ("AWS4" + sk).encode()
    for part in (day, region, "s3", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, SignedHeaders={signed}, Signature={sig}"


def selftest() -> None:
    """AWS 文档“Signature Calculations … GET Object”示例。"""
    hdr = {
        "host": "examplebucket.s3.amazonaws.com",
        "range": "bytes=0-9",
        "x-amz-content-sha256": EMPTY,
        "x-amz-date": "20130524T000000Z",
    }
    a = auth(
        "GET",
        "examplebucket.s3.amazonaws.com",
        "/test.txt",
        {},
        hdr,
        "us-east-1",
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "20130524T000000Z",
    )
    exp = "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    assert a.endswith("Signature=" + exp), a
    print("selftest ok")


def request(path: str, query: dict) -> bytes:
    ak, sk = keys()
    for attempt in range(5):
        amzdate = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        hdr = {
            "host": HOST,
            "x-amz-content-sha256": EMPTY,
            "x-amz-date": amzdate,
            "x-amz-request-payer": "requester",
        }
        hdr["Authorization"] = auth(
            "GET", HOST, path, query, hdr, REGION, ak, sk, amzdate
        )
        url = f"https://{HOST}{q(path, '/')}"
        if query:
            url += "?" + "&".join(f"{q(k)}={q(v)}" for k, v in sorted(query.items()))
        req = urllib.request.Request(
            url, headers={k: v for k, v in hdr.items() if k != "host"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404) or attempt == 4:
                raise RuntimeError(f"HTTP {e.code} {e.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 4:
                raise
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def listing(prefix: str) -> list:
    out, token = [], None
    while True:
        query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        x = request("/", query).decode()
        out += [
            {"key": k, "size": int(s)}
            for k, s in re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", x, re.S)
        ]
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x)
        if not m:
            return out
        token = m.group(1)


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "selftest":
        selftest()
        return
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = sys.argv[2]
    objs = listing(prefix)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (OUT / f"listing_{stamp}.json").write_text(
        json.dumps({"prefix": prefix, "objects": objs})
    )
    total = sum(o["size"] for o in objs)
    print(f"{len(objs)} objects, {total / 1e9:.3f} GB", flush=True)
    if cmd != "get":
        return
    cap = float(sys.argv[3]) * 1e9
    got = 0
    log = open(OUT / "download_log.csv", "a")
    for o in objs:
        dest = OUT / "objects" / o["key"]
        if dest.exists() and dest.stat().st_size == o["size"]:
            continue
        if got + o["size"] > cap:
            print(f"停止：再下 {o['key']} 将超过上限 {cap / 1e9:.1f} GB", flush=True)
            break
        data = request("/" + o["key"], {})
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        got += len(data)
        log.write(
            f"{stamp},{o['key']},{len(data)},{hashlib.sha256(data).hexdigest()}\n"
        )
        log.flush()
    print(f"downloaded {got / 1e9:.3f} GB this run", flush=True)


if __name__ == "__main__":
    main()

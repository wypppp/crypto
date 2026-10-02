#!/usr/bin/env python3
"""DQ-22 留出暴露审计 v2 的扫描脚本（10-02；门 1 复核第 5 项）。只输出计数与脱敏上下文，不显示币名。

python 过程/exposure_scan_v2.py ROOT [ROOT ...] → 过程/exposure_scan_v2_{UTC}.json
扫描：①路径名（目录与文件名）；②文本文件（md、sql、py、ipynb、log、txt、csv、tsv、json、jsonl、yaml）与 .gz 内的文本；
.zip 只看文件名（币安归档的 zip 内容是不带币名的 K 线）。
匹配形式：交易对写法（BASE+USDT/USDC/BUSD/FDUSD，可带 / - _ 分隔，可带 1000、1000000 前缀，大小写不敏感）、
JSON 或表头字段 symbol/base_asset/baseAsset/base/coin/asset/ticker/token_symbol/sym/cexCoinName 等于 BASE。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path

H = Path(__file__).resolve().parent
MASTER = (
    H.parents[2] / "5_参考" / "旧债务" / "direction" / "v1.8.40" / "L_u_master.json"
)
TEXT = {
    ".md",
    ".sql",
    ".py",
    ".ipynb",
    ".log",
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".sqlpart",
}
MAXB = 400_000_000


def names() -> list[str]:
    return [e["base_asset"] for e in json.loads(MASTER.read_text())["embargo_metadata"]]


def compile_res(bases: list[str]) -> tuple[re.Pattern, re.Pattern]:
    alt = "|".join(sorted((re.escape(b) for b in bases), key=len, reverse=True))
    pair = re.compile(
        rf"(?<![A-Za-z0-9])(?:1000000|1000)?({alt})[/_\-]?(?:USDT|USDC|BUSD|FDUSD)(?![A-Za-z0-9])",
        re.I,
    )
    field = re.compile(
        rf"[\"']?(?:symbol|base_asset|baseAsset|base|coin|asset|ticker|token_symbol|sym|cexCoinName)[\"']?\s*[:=,]\s*[\"']({alt})[\"']",
        re.I,
    )
    return pair, field


def mask(s: str, bases: list[str]) -> str:
    for b in sorted(bases, key=len, reverse=True):
        s = re.sub(re.escape(b), "<H>", s, flags=re.I)
    return re.sub(r"\d", "#", s)  # 数字也遮住：上下文里可能有留出币的价格


def main() -> None:
    bases = names()
    tag = {b.upper(): hashlib.sha256(b.encode()).hexdigest()[:6] for b in bases}
    pair, field = compile_res(bases)
    roots = [Path(r) for r in sys.argv[1:]]
    out = {
        "roots": [str(r) for r in roots],
        "path_hits": {},
        "content_hits": {},
        "errors": [],
        "n_files": 0,
    }
    skip_dirs = {".git", "__pycache__", "node_modules"}
    for root in roots:
        for p in root.rglob("*"):
            if any(x in skip_dirs for x in p.parts):
                continue
            m = pair.search(p.name)
            if m:
                out["path_hits"].setdefault(str(p.parent), set()).add(
                    tag[m.group(1).upper()]
                )
            if not p.is_file():
                continue
            out["n_files"] += 1
            suf = (
                p.suffixes[-2]
                if p.suffix == ".gz" and len(p.suffixes) > 1
                else p.suffix
            )
            if suf not in TEXT:
                continue
            try:
                if p.stat().st_size > MAXB:
                    out["errors"].append(f"skip_large {p}")
                    continue
                opener = gzip.open if p.suffix == ".gz" else open
                hits, ctx = set(), []
                with opener(p, "rt", errors="ignore") as f:
                    for line in f:
                        for rx in (pair, field):
                            for m in rx.finditer(line):
                                hits.add(tag[m.group(1).upper()])
                                if len(ctx) < 3:
                                    a = max(0, m.start() - 80)
                                    ctx.append(mask(line[a : m.end() + 80], bases))
                if hits:
                    out["content_hits"][str(p)] = {
                        "n_holdout_names": len(hits),
                        "tags": sorted(hits),
                        "context_masked": ctx,
                    }
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"{p}: {e!r}"[:200])
    out["path_hits"] = {k: sorted(v) for k, v in out["path_hits"].items()}
    dest = H / f"exposure_scan_v2_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(
        dest,
        out["n_files"],
        len(out["path_hits"]),
        len(out["content_hits"]),
        len(out["errors"]),
    )


if __name__ == "__main__":
    main()

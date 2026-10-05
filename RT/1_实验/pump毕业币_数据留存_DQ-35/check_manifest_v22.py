#!/usr/bin/env python3
"""DQ-35 v2.2：按预期片表核对重取是否齐全，并做内容验收（10-05；GPT 批 1a-i 第 3、4 条）。

python check_manifest_v22.py [--content]  → runs/manifest_v22_check.csv；有任何阻断问题返回码 1
预期片表＝GRAD 四层＋PRE 两层 × 39 个半月片。每片核对：清单有该片；最后一行的 SQL 哈希＝当前生成器输出；
清单、状态文件、台账三方的 query_id 与 execution_id 一致；状态完成；下载状态 ok；状态行数＝CSV 解析行数；文件哈希未变；
同一片多次完成执行另报。--content 再读文件做内容验收（只数计数列与键，不看价格或收益）：
越界计数、vq 缺失／溢出、交叉核对越界、片内键重复、M 层 identity_gap，任一不为 0 即阻断。
"""

import csv
import gzip
import sys
from collections import Counter, defaultdict

from dune_get import H
from run_all_v21 import halves
from run_all_v22 import (
    LAYERS,
    build_sql,
    file_info,
    label,
    ledger_rows,
    read_manifest,
    row_ok,
    sha,
    status_info,
)
from check_manifest_v21 import check_slices


def audit(expected, manifest, sql_sha, finfo, sinfo, ledger):
    """纯函数：返回 {标签: 问题列表}（空列表＝齐；以“注：”开头的不阻断）。"""
    by = defaultdict(list)
    for r in manifest:
        by[r["label"]].append(r)
    out = {}
    for lab in expected:
        rs = by.get(lab, [])
        probs = []
        if not rs:
            out[lab] = ["缺片"]
            continue
        r = rs[-1]
        led = ledger.get(lab)
        qid, eid, _, _ = sinfo.get(lab, (None, None, None, None))
        if r["sql_sha256"] != sql_sha[lab]:
            probs.append("SQL 已变（清单里的不是当前冻结版本）")
        if r["state"] != "QUERY_STATE_COMPLETED":
            probs.append("状态 %s" % r["state"])
        if r["download"] != "ok":
            probs.append("下载状态 %s" % r["download"])
        if led is None:
            probs.append("台账无此 SQL")
        else:
            if not (r["query_id"] == qid == led["query_id"]):
                probs.append(
                    "query_id 不符（清单 %s／状态 %s／台账 %s）"
                    % (r["query_id"], qid, led["query_id"])
                )
            if not (r["execution_id"] == eid == led["execution_id"]):
                probs.append("执行号不符")
        if not probs and not row_ok(
            r,
            sql_sha[lab],
            finfo.get(lab, (None, None)),
            sinfo.get(lab, (None, None, None, None)),
            led,
        ):
            probs.append("行数或文件哈希不符")
        done = [x for x in rs if x["state"] == "QUERY_STATE_COMPLETED"]
        if len(set(x["execution_id"] for x in done)) > 1:
            probs.append("注：%d 次完成执行，以最后一次为准" % len(done))
        out[lab] = probs
    for lab in sorted(set(by) - set(expected)):
        out[lab] = ["清单里有、预期片表里没有"]
    return out


def content(lab, layer, family):
    """内容验收（只数计数列与键）：返回问题列表。"""
    p = H / "raw" / "dune" / ("%s.csv.gz" % lab)
    if not p.exists():
        return []
    probs = []
    with gzip.open(p, "rt", newline="") as f:
        rows = list(csv.DictReader(f))
    if family == "GRAD" and layer == "B":
        for c in ("n_ord_overflow", "n_vq_null", "n_vq_ovf", "n_xchk_fail"):
            s = sum(int(float(r[c] or 0)) for r in rows)
            if s:
                probs.append("%s 合计 %d" % (c, s))
        k = Counter((r["kind"], r["pool"], r["bkey"], r["straddle"]) for r in rows)
    elif family == "GRAD" and layer == "L":
        s = sum(int(float(r["ovf"] or 0)) for r in rows)
        if s:
            probs.append("ovf 合计 %d" % s)
        k = Counter(
            (r["pool"], r["slot"], r["txi"], r["oix"], r["iix"], r["kind"])
            for r in rows
        )
    elif layer == "M":
        if rows and int(float(rows[0]["identity_gap"])) != 0:
            probs.append("identity_gap %s" % rows[0]["identity_gap"])
        k = Counter()
    elif family == "GRAD" and layer == "P":
        k = Counter(r["pool"] for r in rows)
    else:
        s = sum(int(float(r["n_ord_overflow"] or 0)) for r in rows)
        if s:
            probs.append("n_ord_overflow 合计 %d" % s)
        k = Counter((r["mint"], r["bkey"]) for r in rows)
    d = sum(v - 1 for v in k.values() if v > 1)
    if d:
        probs.append("片内键重复 %d" % d)
    return probs


def main():
    do_content = "--content" in sys.argv
    sl = halves()
    probs = check_slices(sl)
    expected, sql_sha, finfo, sinfo, ledger, lay = [], {}, {}, {}, {}, {}
    for fam, layers in LAYERS.items():
        for layer in layers:
            for ym, s, e in sl:
                lab = label(fam, layer, ym)
                expected.append(lab)
                lay[lab] = (fam, layer)
                sql_sha[lab] = sha(build_sql(fam, layer, s, e))
                finfo[lab] = file_info(lab)
                sinfo[lab] = status_info(lab)
                ledger[lab] = (ledger_rows("sql/%s.sql" % lab) or [None])[-1]
    res = audit(expected, read_manifest(), sql_sha, finfo, sinfo, ledger)
    if do_content:
        for lab in expected:
            if not res[lab] or all(p.startswith("注") for p in res[lab]):
                res[lab] += content(lab, lay[lab][1], lay[lab][0])
    bad = {k: v for k, v in res.items() if any(not p.startswith("注") for p in v)}
    with open(H / "runs" / "manifest_v22_check.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chain", "label", "problems"])
        for k, v in res.items():
            w.writerow(["solana", k, "；".join(v)])
    print(
        "片表：%d 片 × 6 层＝%d；片表问题：%s；不齐或验收不过 %d"
        % (len(sl), len(expected), probs or "无", len(bad))
    )
    for k, v in list(bad.items())[:20]:
        print(" ", k, "；".join(v))
    sys.exit(1 if bad or probs else 0)


if __name__ == "__main__":
    main()

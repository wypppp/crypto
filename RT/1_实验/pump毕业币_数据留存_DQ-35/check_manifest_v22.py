#!/usr/bin/env python3
"""DQ-35 v2.2：按预期片表核对重取是否齐全，并做内容验收（10-05；GPT 批 1a-i 第 3、4 条）。

python check_manifest_v22.py [--no-content]  → runs/manifest_v22_check.csv；有任何阻断问题返回码 1
预期片表＝GRAD 四层＋PRE 两层 × 39 个半月片。每片核对：清单有该片；最后一行的 SQL 哈希＝当前生成器输出；
清单、状态文件、台账三方的 query_id 与 execution_id 一致；状态完成；下载状态 ok；状态行数＝CSV 解析行数；文件哈希未变；
同一片多次完成执行另报。内容验收默认开启（10-06，GPT 批 1a-i 增量复核③；--no-content 只用于排查，结果不算验收）：
只数计数列与键，不看价格或收益。B 层：越界、vq 缺失／溢出／未知布局／对不上原始字节、交叉核对越界、源事件键重复；
L 层：越界、事件键（不含 kind）重复；P 层：池键重复、7 天源事件键重复、vq 未知或缺失、coverage 取值、target_time＝建池＋o；
M 层 identity_gap；所有层 chain＝solana。任一不为 0 即阻断。
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
from build_grad_sql_v22 import OFFSETS

COVERAGE = {"ok", "gap", "partial", "unverified", "no_next", "immature"}


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
    """内容验收（只数计数列与键）：返回问题列表。零行结果没有文件，返回空。"""
    p = H / "raw" / "dune" / ("%s.csv.gz" % lab)
    if not p.exists():
        return []
    with gzip.open(p, "rt", newline="") as f:
        return content_rows(list(csv.DictReader(f)), layer, family)


def content_rows(rows, layer, family):
    """纯函数：对已读入的行做内容验收。"""
    probs = []
    bad_chain = sum(r.get("chain") != "solana" for r in rows)
    if bad_chain:
        probs.append("chain 不是 solana 的行 %d" % bad_chain)

    def total(cols):
        for c in cols:
            s = sum(int(float(r[c] or 0)) for r in rows)
            if s:
                probs.append("%s 合计 %d" % (c, s))

    if family == "GRAD" and layer == "B":
        total(
            (
                "n_ord_overflow",
                "n_vq_null",
                "n_vq_ovf",
                "n_xchk_fail",
                "n_src_dup",
                "n_vq_unknown",
                "n_vq_missing",
            )
        )
        k = Counter((r["kind"], r["pool"], r["bkey"], r["straddle"]) for r in rows)
    elif family == "GRAD" and layer == "L":
        total(("ovf",))
        # 唯一键不含 kind：同一事件键标成两类也算重复
        k = Counter((r["pool"], r["slot"], r["txi"], r["oix"], r["iix"]) for r in rows)
    elif layer == "M":
        if rows and int(float(rows[0]["identity_gap"])) != 0:
            probs.append("identity_gap %s" % rows[0]["identity_gap"])
        k = Counter()
    elif family == "GRAD" and layer == "P":
        total(("n_src_dup_7d", "n_vq_bad_7d"))
        nbad_cov = nbad_tt = 0
        for r in rows:
            c0 = float(r["created_t"])
            for o in OFFSETS:
                nbad_cov += r["coverage%d" % o] not in COVERAGE
                nbad_tt += abs(float(r["target%d_time" % o]) - (c0 + o)) > 1e-3
        if nbad_cov:
            probs.append("coverage 取值不在六类里 %d" % nbad_cov)
        if nbad_tt:
            probs.append("target_time 不等于建池＋o %d" % nbad_tt)
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
    do_content = "--no-content" not in sys.argv
    if not do_content:
        print("注意：--no-content 只做清单核对，结果不算验收")
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

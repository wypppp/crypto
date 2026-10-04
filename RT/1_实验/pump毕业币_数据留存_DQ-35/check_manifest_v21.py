#!/usr/bin/env python3
"""DQ-35 v2.1：按预期片表核对重取是否齐全（10-04；GPT 10-04 复核第 6 条）。不读数据内容，只数行、算哈希。

python check_manifest_v21.py  → runs/manifest_v21_check.csv；有任何问题返回码 1
预期片表＝两族全部层 × 39 个半月片（2025-03-15～2026-10-04，run_all_v21.halves），先核片表本身首尾与连续。
每片核对：清单里有该片；最后一行的 SQL 哈希＝当前生成器对该片的输出；状态完成；台账执行号＝下载时状态文件的执行号；
状态行数＝文件行数（零行片无文件）；文件 sha256 未变。同一片有多次完成执行时另报（以最后一次为准）。
"""

import csv
import datetime as dt
import sys
from collections import defaultdict

from dune_get import H
from run_all_v21 import (
    FIRST,
    LAST,
    LAYERS,
    build_sql,
    file_info,
    halves,
    label,
    read_manifest,
    row_ok,
    sha,
    status_info,
)


def check_slices(sl, first=FIRST, last=LAST):
    """片表首尾与连续性：首片起于 first，末片止于 last，相邻片首尾相接、无重叠无空隙。"""
    probs = []
    if sl[0][1] != first:
        probs.append("首片起日 %s≠%s" % (sl[0][1], first))
    if sl[-1][2] != last:
        probs.append("末片止日 %s≠%s" % (sl[-1][2], last))
    for (_, _, e1), (ym, s2, _) in zip(sl, sl[1:]):
        if s2 != e1 + dt.timedelta(days=1):
            probs.append("%s 与上一片不相接" % ym)
    return probs


def audit(expected, manifest, sql_sha, finfo, sinfo):
    """纯函数：expected＝[标签]；manifest＝清单行；sql_sha／finfo／sinfo＝按标签的当前 SQL 哈希、(文件行数, 文件哈希)、(执行号, 状态行数)。
    返回 {标签: 问题列表}（空列表＝齐）。"""
    by = defaultdict(list)
    for r in manifest:
        by[r["label"]].append(r)
    out = {}
    for lab in expected:
        rs = by.get(lab, [])
        probs = []
        if not rs:
            probs.append("缺片")
        else:
            r = rs[-1]
            nf, fs = finfo.get(lab, (None, None))
            eid, n = sinfo.get(lab, (None, None))
            if r["sql_sha256"] != sql_sha[lab]:
                probs.append("SQL 已变（清单里的不是当前冻结版本）")
            if r["state"] != "QUERY_STATE_COMPLETED":
                probs.append("状态 %s" % r["state"])
            if r["execution_id"] != eid:
                probs.append("下载的执行号与台账不符")
            if not row_ok(r, sql_sha[lab], nf, fs, eid, n) and not probs:
                probs.append("行数或文件哈希不符")
            done = [x for x in rs if x["state"] == "QUERY_STATE_COMPLETED"]
            if len(set(x["execution_id"] for x in done)) > 1:
                probs.append("注：%d 次完成执行，以最后一次为准" % len(done))
        out[lab] = probs
    extra = sorted(set(by) - set(expected))
    for lab in extra:
        out[lab] = ["清单里有、预期片表里没有"]
    return out


def main():
    sl = halves()
    probs = check_slices(sl)
    expected, sql_sha, finfo, sinfo = [], {}, {}, {}
    for fam, layers in LAYERS.items():
        for layer in layers:
            for ym, s, e in sl:
                lab = label(fam, layer, ym)
                expected.append(lab)
                sql_sha[lab] = sha(build_sql(fam, layer, s, e))
                finfo[lab] = file_info(lab)
                sinfo[lab] = status_info(lab)
    res = audit(expected, read_manifest(), sql_sha, finfo, sinfo)
    bad = {k: v for k, v in res.items() if any(not p.startswith("注") for p in v)}
    with open(H / "runs" / "manifest_v21_check.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "problems"])
        for k, v in res.items():
            w.writerow([k, "；".join(v)])
    print(
        "片表：%d 片 × %d 层＝%d；片表问题：%s；不齐 %d"
        % (len(sl), len(expected) // len(sl), len(expected), probs or "无", len(bad))
    )
    for k, v in list(bad.items())[:20]:
        print(" ", k, "；".join(v))
    sys.exit(1 if bad or probs else 0)


if __name__ == "__main__":
    main()

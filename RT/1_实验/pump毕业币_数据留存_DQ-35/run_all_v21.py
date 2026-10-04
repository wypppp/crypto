#!/usr/bin/env python3
"""DQ-35 v2.1：按半月分片依次重取，逐片写清单（10-04；GPT 10-04 复核第 6 条；GPT 批 1a-i 审过后才运行）。

python run_all_v21.py <族 GRAD|PRE> <层> <累计上限 credits> [起片标签 止片标签]
  GRAD 的层：B（分桶，按事件日期分片）、P（池头与快照，按建池日期分片）、L（加撤池，按事件日期）、M（母体计数，按建池日期）
  PRE 的层：B（分桶，按完成日期分片）、M（母体计数，按完成日期）
范围：2025-03-15（PumpSwap 上线）～2026-10-04（R3 事件止日），每月两片（前半月 1～15 日），共 39 片；标签 GRAD21{层}_{年月}{a|b}、PRE21{层}_…。

清单 runs/manifest_v21.csv 每次执行追加一行：标签、族、层、起止日、冻结 SQL 的 sha256、query_id、execution_id、状态、费用、
Dune 状态里的行数、下载文件行数与 sha256、下载状态。跳过一片的条件是清单最后一行同标签、同 SQL 哈希、状态完成、
下载的执行号与台账一致、文件哈希与行数都对得上；零行的片同样按状态与执行号核对（无文件）。
其余情况一律重跑，不凭“文件已存在”跳过（v2 的 R54 问题）。累计费用超过上限即停。
"""

import csv
import datetime as dt
import gzip
import hashlib
import json
import subprocess
import sys

from dune_get import H

FIRST = dt.date(2025, 3, 15)
LAST = dt.date(2026, 10, 4)
LAYERS = {"GRAD": ("B", "P", "L", "M"), "PRE": ("B", "M")}
FIELDS = [
    "label",
    "family",
    "layer",
    "start",
    "end",
    "sql_sha256",
    "query_id",
    "execution_id",
    "state",
    "credits",
    "rows_status",
    "rows_file",
    "file_sha256",
    "download",
]


def halves(first=FIRST, last=LAST):
    """半月分片 [起, 止]（含两端）：每月 1～15 日、16 日～月末；首片从 first、末片到 last 截断。"""
    out = []
    y, m = first.year, first.month
    while dt.date(y, m, 1) <= last:
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        for tag, s, e in (
            ("a", dt.date(y, m, 1), dt.date(y, m, 15)),
            ("b", dt.date(y, m, 16), nxt - dt.timedelta(days=1)),
        ):
            s, e = max(s, first), min(e, last)
            if s <= e:
                out.append(("%04d%02d%s" % (y, m, tag), s, e))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def label(family, layer, ym):
    return "%s21%s_%s" % (family, layer, ym)


def build_sql(family, layer, s, e):
    if family == "GRAD":
        import build_grad_sql_v21 as g

        return g.build(layer, s, e)
    import build_gradpre_sql_v21 as g

    return g.build(layer, s, e)


def sha(text_or_bytes):
    b = text_or_bytes.encode() if isinstance(text_or_bytes, str) else text_or_bytes
    return hashlib.sha256(b).hexdigest()


def file_info(lab):
    """下载文件的行数（不含表头）与 sha256；无文件时返回 (None, None)。"""
    p = H / "raw" / "dune" / ("%s.csv.gz" % lab)
    if not p.exists():
        return None, None
    with gzip.open(p, "rt", newline="") as f:
        n = sum(1 for _ in f) - 1
    return n, sha(p.read_bytes())


def status_info(lab):
    """Dune 执行状态（下载时保存）：执行号与行数。"""
    p = H / "raw" / "dune" / ("%s_status.json" % lab)
    if not p.exists():
        return None, None
    st = json.loads(p.read_text())
    return st.get("execution_id"), (st.get("result_metadata") or {}).get(
        "total_row_count"
    )


def read_manifest():
    p = H / "runs" / "manifest_v21.csv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def row_ok(r, sql_sha, rows_file, file_sha, st_eid, st_rows):
    """清单行是否证明该片已完整取回（核对用的纯函数，见 test_run_all_v21.py）。"""
    if r is None or r["sql_sha256"] != sql_sha or r["state"] != "QUERY_STATE_COMPLETED":
        return False
    if not r["execution_id"] or r["execution_id"] != st_eid:
        return False
    if st_rows is None or str(st_rows) != r["rows_status"]:
        return False
    if st_rows == 0 and rows_file is None:
        return r["file_sha256"] == ""
    return (
        rows_file is not None
        and rows_file == st_rows
        and str(rows_file) == r["rows_file"]
        and file_sha == r["file_sha256"]
    )


def ledger_last(sql_file):
    with open(H / "runs" / "dune_ledger.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["sql_file"] == sql_file]
    return rows[-1] if rows else None


def main():
    a = sys.argv[1:]
    family, layer, cap = a[0], a[1], float(a[2])
    if layer not in LAYERS[family]:
        raise SystemExit("层不对")
    window = a[3:5] if len(a) >= 5 else None
    man = read_manifest()
    last_by = {r["label"]: r for r in man}
    spent = 0.0
    on = window is None
    for ym, s, e in halves():
        lab = label(family, layer, ym)
        if window and lab == window[0]:
            on = True
        if not on:
            continue
        sql = build_sql(family, layer, s, e)
        sql_sha = sha(sql)
        rows_file, file_sha = file_info(lab)
        st_eid, st_rows = status_info(lab)
        if row_ok(last_by.get(lab), sql_sha, rows_file, file_sha, st_eid, st_rows):
            print(lab, "已齐，跳过", flush=True)
        else:
            sql_file = "sql/%s.sql" % lab
            (H / sql_file).write_text(sql)
            rc = subprocess.run(
                [sys.executable, "run_dune.py", lab, sql_file], cwd=H
            ).returncode
            led = ledger_last(sql_file) or {}
            rows_file, file_sha = file_info(lab)
            st_eid, st_rows = status_info(lab)
            rec = dict(
                label=lab,
                family=family,
                layer=layer,
                start=s.isoformat(),
                end=e.isoformat(),
                sql_sha256=sql_sha,
                query_id=led.get("query_id", ""),
                execution_id=led.get("execution_id", ""),
                state=led.get("state", ""),
                credits=led.get("credits", ""),
                rows_status="" if st_rows is None else st_rows,
                rows_file="" if rows_file is None else rows_file,
                file_sha256=file_sha or "",
                # 零行结果：dune_get_stream 不写文件、返回非零，改按状态 0 行与执行号核对
                download="ok"
                if (rc == 0 or st_rows == 0) and st_eid == led.get("execution_id")
                else "失败或执行号不符",
            )
            new = not (H / "runs" / "manifest_v21.csv").exists()
            with open(H / "runs" / "manifest_v21.csv", "a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow(rec)
            spent += float(led.get("credits") or 0)
            print(lab, rec["state"], rec["credits"], "累计 %.2f" % spent, flush=True)
            if spent > cap:
                print("停止：累计超过上限", flush=True)
                break
        if window and lab == window[1]:
            break


if __name__ == "__main__":
    main()

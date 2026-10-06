#!/usr/bin/env python3
"""DQ-35 v2.2：按半月分片依次重取，逐片写清单（10-05；GPT 批 1a-i 第 4 条；GPT 增量复核通过后才运行）。

python run_all_v22.py <族 GRAD|PRE> <层> <档位 trial|plus> [起片标签 止片标签] [--ack-report]
  GRAD 的层：B（按事件日期分片）、P（按建池日期）、L（按事件日期）、M（按建池日期）；PRE 的层：B、M（按完成日期）。
范围：2025-03-15～2026-10-04，每月两片（前半月 1～15 日），共 39 片；标签 GRAD22{层}_{年月}{a|b}、PRE22{层}_…；链 solana。

每片：
1. 清单 runs/manifest_v22.csv 最后一行若已证明取齐（row_ok：SQL 哈希、清单／状态文件／台账三方的 query_id 与 execution_id、
   下载状态、状态行数＝CSV 解析行数、文件哈希都对），跳过；
2. 若查询已完成但下载失败或文件不符，**续传**：对同一 query_id 重新下载同一次执行的结果，不重跑查询；
3. 否则先过预算控制器（budget_v22.check：账户读数＋该片上沿执行费＋预计导出费，越线即停、先报），再执行；
   执行前后读账户用量，差值减去执行费记为实测导出费，与执行费、失败、重取分别入 runs/budget_v22.csv。
"""

import csv
import gzip
import hashlib
import json
import subprocess
import sys

import budget_v22 as bud
from dune_get import H
from run_all_v21 import halves

LAYERS = {"GRAD": ("B", "P", "L", "M"), "PRE": ("B", "M")}
FIELDS = [
    "chain",
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
    "export_credits",
    "rows_status",
    "rows_file",
    "file_sha256",
    "download",
]
# 每片上沿执行费（credits；本轮样本与 VOL21 探针的最大值×5，保守）与每片预计结果 MB（VOL21 外推×1.5）
EST_EXEC = {"B": 150.0, "P": 200.0, "L": 60.0, "M": 10.0}
EST_MB = {"B": 400.0, "P": 15.0, "L": 1.0, "M": 0.0}


def label(family, layer, ym):
    return "%s22%s_%s" % (family, layer, ym)


def build_sql(family, layer, s, e):
    if family == "GRAD":
        import build_grad_sql_v22 as g

        return g.build(layer, s, e)
    import build_gradpre_sql_v22 as g

    return g.build(layer, s, e)


def sha(b):
    return hashlib.sha256(b.encode() if isinstance(b, str) else b).hexdigest()


def file_info(lab):
    """下载文件的记录数（用 CSV 解析，字段里有换行也只算一行，不含表头）与 sha256；无文件返回 (None, None)。"""
    p = H / "raw" / "dune" / ("%s.csv.gz" % lab)
    if not p.exists():
        return None, None
    with gzip.open(p, "rt", newline="") as f:
        n = sum(1 for _ in csv.reader(f)) - 1
    return n, sha(p.read_bytes())


def status_info(lab):
    """下载时保存的 Dune 状态：(query_id, execution_id, 状态, 行数)。"""
    p = H / "raw" / "dune" / ("%s_status.json" % lab)
    if not p.exists():
        return None, None, None, None
    st = json.loads(p.read_text())
    return (
        str(st.get("query_id")),
        st.get("execution_id"),
        st.get("state"),
        (st.get("result_metadata") or {}).get("total_row_count"),
    )


def ledger_rows(sql_file):
    with open(H / "runs" / "dune_ledger.csv") as f:
        return [r for r in csv.DictReader(f) if r["sql_file"] == sql_file]


def read_manifest():
    p = H / "runs" / "manifest_v22.csv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def row_ok(r, sql_sha, finfo, sinfo, led):
    """清单行是否证明该片已完整取回（纯函数，见 test_run_all_v22.py）。
    finfo＝(文件记录数, 文件哈希)；sinfo＝状态文件 (query_id, execution_id, 状态, 行数)；led＝台账里该 SQL 的最后一行。"""
    if r is None or led is None or r["sql_sha256"] != sql_sha:
        return False
    if r["state"] != "QUERY_STATE_COMPLETED" or r["download"] != "ok":
        return False
    qid, eid, st, n = sinfo
    if not (r["query_id"] == qid == led["query_id"]):
        return False
    if not (r["execution_id"] == eid == led["execution_id"]):
        return False
    if st != "QUERY_STATE_COMPLETED" or led["state"] != "QUERY_STATE_COMPLETED":
        return False  # 10-06：状态文件缺失或未完成都不放行（GPT 批 1a-i 增量复核④）
    if n is None or str(n) != r["rows_status"]:
        return False
    nf, fs = finfo
    if n == 0 and nf is None:
        return r["file_sha256"] == ""
    return (
        nf is not None
        and nf == n
        and str(nf) == r["rows_file"]
        and fs == r["file_sha256"]
    )


def resume_precheck(sql, layer, plan, u0, ack=False):
    """续传前的预算预检（纯函数）：执行费 0、导出费按该层预计 MB；读不到用量或越线都不续传。"""
    return bud.check(bud.task_of_sql(sql), 0.0, EST_MB[layer], plan, u0, ack_report=ack)


def append(rec):
    p = H / "runs" / "manifest_v22.csv"
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(rec)


# 取数挡板（10-06，总控第二十二轮第三节；GPT 清单确认 ③ 不通过）：状态事件的排序键拼成固定位宽的数
# slot×10^10＋txi×10^5＋oix×10^3＋iix，分量越界会碰撞（(txi,oix,iix)＝(1,100,0) 与 (2,0,0) 同值），
# P 层验收查不出。改用多列元组排序或全键范围检查、补回归测试、经 GPT 只确认 ③ 之前，运行器拒绝运行。
GATE3_FIXED = False


def main():
    if not GATE3_FIXED:
        raise SystemExit(
            "取数挡板：DQ-35 ③（状态事件键位宽碰撞）未修复并经 GPT 确认，拒绝运行（README §1g）"
        )
    with bud.run_lock():
        _main()


def _main():
    a = sys.argv[1:]
    ack = "--ack-report" in a
    a = [x for x in a if x != "--ack-report"]
    family, layer, plan = a[0], a[1], a[2]
    if layer not in LAYERS[family] or plan not in bud.EXPORT_PER_MB:
        raise SystemExit("族、层或档位不对")
    window = a[3:5] if len(a) >= 5 else None
    last_by = {r["label"]: r for r in read_manifest()}
    on = window is None
    for ym, s, e in halves():
        lab = label(family, layer, ym)
        if window and lab == window[0]:
            on = True
        if not on:
            continue
        sql = build_sql(family, layer, s, e)
        sql_file = "sql/%s.sql" % lab
        led = (ledger_rows(sql_file) or [None])[-1]
        r = last_by.get(lab)
        if row_ok(r, sha(sql), file_info(lab), status_info(lab), led):
            print(lab, "已齐，跳过", flush=True)
        elif (
            r
            and r["sql_sha256"] == sha(sql)
            and r["state"] == "QUERY_STATE_COMPLETED"
            and r["query_id"]
        ):
            # 续传：同一 query_id 的同一次执行（锁定清单里冻结的 execution_id），重新下载，不重跑；先过预算预检
            task = bud.task_of_sql(sql)
            u0 = bud.usage()
            go, why = resume_precheck(sql, layer, plan, u0, ack)
            if not go:
                print("停止（续传前预检）：%s" % why, flush=True)
                break
            rc = subprocess.run(
                [
                    sys.executable,
                    "dune_get_stream.py",
                    r["query_id"],
                    lab,
                    sql_file,
                    r["execution_id"],
                ],
                cwd=H,
            ).returncode
            u1 = bud.usage()
            nf, fs = file_info(lab)
            qid, eid, _, n = status_info(lab)
            ok = (rc == 0 or n == 0) and eid == r["execution_id"]
            if u0 is not None and u1 is not None:
                bud.record(task, lab, "export", max(0.0, u1 - u0), u0, u1, "续传下载")
            append(
                dict(
                    r,
                    rows_status="" if n is None else n,
                    rows_file="" if nf is None else nf,
                    file_sha256=fs or "",
                    download="ok" if ok else "续传失败",
                    export_credits="",
                )
            )
            print(lab, "续传", "ok" if ok else "失败", flush=True)
        else:
            task = bud.task_of_sql(sql)
            u0 = bud.usage()
            go, why = bud.check(
                task, EST_EXEC[layer], EST_MB[layer], plan, u0, ack_report=ack
            )
            print(lab, why, flush=True)
            if not go:
                print("停止：%s" % why, flush=True)
                break
            (H / sql_file).write_text(sql)
            rc = subprocess.run(
                [sys.executable, "run_dune.py", lab, sql_file], cwd=H
            ).returncode
            u1 = bud.usage()
            led = (ledger_rows(sql_file) or [{}])[-1]
            cost = float(led.get("credits") or 0)
            export = (
                max(0.0, (u1 - u0) - cost)
                if (u0 is not None and u1 is not None)
                else None
            )
            kind = (
                "rerun"
                if r
                else (
                    "execute"
                    if led.get("state") == "QUERY_STATE_COMPLETED"
                    else "failed"
                )
            )
            bud.record(task, lab, kind, cost, u0, u1, "执行")
            if export is not None:
                bud.record(
                    task,
                    lab,
                    "export",
                    export,
                    u0,
                    u1,
                    "实测导出费（用量差−执行费）",
                )
            nf, fs = file_info(lab)
            qid, eid, _, n = status_info(lab)
            dl = (
                "ok"
                if (rc == 0 or n == 0)
                and eid == led.get("execution_id")
                and qid == led.get("query_id")
                else "失败或执行号不符"
            )
            append(
                dict(
                    chain="solana",
                    label=lab,
                    family=family,
                    layer=layer,
                    start=s.isoformat(),
                    end=e.isoformat(),
                    sql_sha256=sha(sql),
                    query_id=led.get("query_id", ""),
                    execution_id=led.get("execution_id", ""),
                    state=led.get("state", ""),
                    credits=led.get("credits", ""),
                    export_credits="" if export is None else "%.3f" % export,
                    rows_status="" if n is None else n,
                    rows_file="" if nf is None else nf,
                    file_sha256=fs or "",
                    download=dl,
                )
            )
            print(lab, led.get("state"), cost, "导出", export, flush=True)
        if window and lab == window[1]:
            break


if __name__ == "__main__":
    main()

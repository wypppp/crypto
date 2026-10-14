#!/usr/bin/env python3
"""DQ-43：执行一条已入库、已获批准的 Dune SQL（公开查询）→ 台账 → 流式下载。

python run_dune.py <标签> <sql 文件> --approve=<批准编号> [--engine=medium|large] [--max-min=12]
结果 raw/dune/<标签>.csv.gz；费用记 runs/dune_ledger.csv；批准与使用记 runs/付费批准.csv、runs/付费批准_已用.csv。

10-14 总控第六轮（EDGE 冒烟白扣 1,241.8 credits 之后）：
- 没有批准不跑（paid_guard.check：编号存在、SQL 的 sha256 与批准时一致、未用过）；执行与下载共用这一条批准。
- 同一时间只跑一条（paid_guard.one_at_a_time，本机文件锁，拿不到就拒绝）；不自动重试、不自动提交下一条。
- 预算只看用量接口的实时读数：读不到，或“已用＋本条执行费上限”超过本期额度，都不跑。
- 运行中每 10 秒读已扣费用，超过批准的上限就在 Dune 上取消；按时间取消只作第二道。
- 结果大于批准的下载上限（MB）就不下载，只报大小。
"""

import csv
import datetime as dt
import json
import sys
import time

import paid_guard as PG
from dune_get import H, get
from dune_get_stream import fetch


def call(method: str, path: str, body: dict, ticket=None) -> dict:
    """经 paid_guard.request：付费接口（执行等）要锁内的批准。"""
    return PG.request(method, path, body, ticket)


def usage():
    """账户本计费期（今天所在的那一期）的（已用, 额度）；读不到返回 None（同 DQ-35 budget_v22.usage 的取期办法）。"""
    try:
        d = call("POST", "/usage", {})
    except Exception:
        return None
    today = dt.datetime.now(dt.timezone.utc).date()
    hit = [
        p
        for p in d.get("billing_periods") or []
        if dt.date.fromisoformat(p["start_date"])
        <= today
        < dt.date.fromisoformat(p["end_date"])
    ]
    if len(hit) != 1:
        return None
    return float(hit[0]["credits_used"]), float(hit[0]["credits_included"])


def budget_gate(u, cap: float) -> str:
    """u＝(已用, 本期额度)，来自用量接口的实时读数。返回空串表示可以跑；否则返回不跑的原因。"""
    if u is None:
        return "读不到账户用量，不跑"
    used, included = u
    if used + cap > included:
        return "已用 %.1f＋本条上限 %.0f 超过本期额度 %.0f，不跑" % (
            used,
            cap,
            included,
        )
    return ""


def main() -> None:
    a = sys.argv[1:]
    opt = {
        x.split("=")[0]: x.split("=", 1)[1]
        for x in a
        if x.startswith("--") and "=" in x
    }
    label, sql_file = [x for x in a if not x.startswith("--")][:2]
    engine = opt.get("--engine", "medium")
    max_min = float(opt.get("--max-min", "12"))
    if engine not in ("medium", "large"):
        raise SystemExit("引擎只能是 medium 或 large")
    approval = opt.get("--approve")
    if not approval:
        raise SystemExit(
            "没有 --approve=<批准编号>，不跑（总控第六轮：没有明确批准不跑任何付费查询）"
        )
    ap = PG.check(approval, sql_file)
    with PG.one_at_a_time(ap):
        u0 = usage()
        why = budget_gate(u0, ap["cap"])
        if why:
            raise SystemExit(why)
        sql = (H / sql_file).read_text()
        qid = call(
            "POST",
            "/query",
            {"name": f"DQ-43 {label}", "query_sql": sql, "is_private": False},
        )["query_id"]
        eid = call("POST", f"/query/{qid}/execute", {"performance": engine}, ap)[
            "execution_id"
        ]
        PG.mark_used(approval, eid, "执行中")
        print(label, "批准", approval, "query", qid, "execution", eid, flush=True)
        t0, cancelled = time.time(), ""
        while True:
            st = get(f"/execution/{eid}/status")
            if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
                break
            spent = float(st.get("execution_cost_credits") or 0)
            if not cancelled and spent > ap["cap"]:
                call("POST", f"/execution/{eid}/cancel", {})
                cancelled = "运行中费用超过批准上限，主动取消"
                print(
                    label,
                    "已扣 %.1f，超过批准上限 %.0f，已请求取消" % (spent, ap["cap"]),
                    flush=True,
                )
            elif not cancelled and time.time() - t0 > max_min * 60:
                call("POST", f"/execution/{eid}/cancel", {})
                cancelled = "超时主动取消"
                print(label, f"超过 {max_min:g} 分钟，已请求取消", flush=True)
            time.sleep(10)
        cost = st.get("execution_cost_credits")
        with open(H / "runs" / "dune_ledger.csv", "a", newline="") as f:
            note = "公开查询；引擎 %s；批准 %s%s；执行前用量 %.3f" % (
                engine,
                approval,
                "；" + cancelled if cancelled else "",
                u0[0],
            )
            csv.writer(f).writerow([qid, sql_file, eid, st["state"], cost, "", note])
        print(label, qid, st["state"], cost, flush=True)
        if st["state"] != "QUERY_STATE_COMPLETED":
            print(json.dumps(st.get("error"), ensure_ascii=False), flush=True)
            sys.exit(1)
        mb = float((st.get("result_metadata") or {}).get("result_set_bytes") or 0) / 1e6
        if mb > ap["max_mb"]:
            raise SystemExit(
                "结果 %.1f MB 超过批准的下载上限 %.1f MB，不下载；先报批"
                % (mb, ap["max_mb"])
            )
        fetch(str(qid), label, sql_file, ap)
        u1 = usage()
        print(
            label,
            "用量 %.3f → %s" % (u0[0], "读不到" if u1 is None else "%.3f" % u1[0]),
            flush=True,
        )


if __name__ == "__main__":
    main()

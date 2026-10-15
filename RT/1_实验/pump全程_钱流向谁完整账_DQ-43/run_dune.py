#!/usr/bin/env python3
"""DQ-43：执行一条已入库、已获批准的 Dune SQL（公开查询）→ 台账 → 流式下载。

python run_dune.py <标签> <sql 文件> --approve=<批准编号> [--engine=medium|large] [--max-min=12] [--query-id=已核查询号]
结果 raw/dune/<标签>.csv.gz；费用记 runs/dune_ledger.csv；批准与使用记 runs/付费批准.csv、runs/付费批准_已用.csv。

10-14 总控第六轮（EDGE 冒烟白扣 1,241.8 credits 之后）：
- 没有批准不跑（paid_guard.check：编号存在、SQL 的 sha256 与批准时一致、未用过）；执行与下载共用这一条批准。
- 同一时间只跑一条（paid_guard.one_at_a_time，本机文件锁，拿不到就拒绝）；不自动重试、不自动提交下一条。
- 预算只看用量接口的实时读数：读不到，或“已用＋本条执行费上限”超过本期额度，都不跑。
- 运行中每 2 秒读费用，到执行批准的 85% 请求取消；状态与撤单有延迟，不能保证硬上限。
- 同一双跑组首条因费用取消，配对条在创建查询前自动跳过。
- 结果大于批准的下载上限（MB）就不下载，只报大小。
- 总控第七轮：同来源的已实耗＋本条执行上限＋下载上限 5 超过 50 就不提交；实耗缺失也拒绝。
"""

import csv
import datetime as dt
import json
import math
import sys
import time
from decimal import Decimal

import paid_guard as PG
from dune_get import H, get
from dune_get_stream import fetch

STATES = H / "runs/付费执行状态.csv"


def execution_state(approval, eid, state, cause):
    new = not STATES.exists()
    with STATES.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["编号", "execution_id", "平台状态", "原因"])
        w.writerow([approval, eid, state, cause])


def pair_gate(approval):
    """双跑组明确登记；费用取消记录先于配对条的任何 API 请求。"""
    rows = PG._rows(PG.APPROVALS)
    hit = next((r for r in rows if r["编号"] == approval), {})
    group = hit.get("双跑组")
    if not group:
        return ""
    pair = [r for r in rows if r.get("双跑组") == group]
    if len(pair) != 2 or len({r["SQL_sha256"] for r in pair}) != 1:
        return "双跑组须恰好两条且 SQL 相同，不跑"
    ids = {r["编号"] for r in pair} - {approval}
    if any(
        r["编号"] in ids and r["原因"] in ("费用取消", "费用越界完成")
        for r in PG._rows(STATES)
    ):
        return "配对查询因费用停止，自动跳过；停下报告"
    return ""


def cancel_threshold(cap):
    return Decimal(str(cap)) * Decimal("0.85")


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
    if not all(math.isfinite(v) and v >= 0 for v in (used, included, cap)):
        return "账户用量或本条上限无效，不跑"
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
        PG.execution_review_gate(ap)
        if PG.halt_gate():
            raise PG.Refused(PG.halt_gate())
        why = pair_gate(approval)
        if why:
            execution_state(approval, "", "SKIPPED", why)
            raise SystemExit(why)
        u0 = usage()
        if ap.source.startswith(("总控第九轮", "总控第十轮", "用户小页试跑")):
            PG.idle_usage_gate(u0)
        why = budget_gate(u0, ap["cap"] + ap.download_cap)
        why = why or PG.s3_period_gate(u0, ap["cap"] + ap.download_cap)
        if why:
            raise SystemExit(why)
        why = PG.round_gate(approval)
        if why:
            raise SystemExit(why)
        sql = (H / sql_file).read_text()
        if ap.source.startswith(("总控第九轮", "总控第十轮", "用户小页试跑")):
            from sql_determinism import check

            check(sql)
        query_id = opt.get("--query-id")
        if query_id is not None:
            if not query_id.isdigit() or int(query_id) <= 0:
                raise PG.Refused("复用查询号须为正整数")
            qid = int(query_id)
            if get(f"/query/{qid}").get("query_sql") != sql:
                raise PG.Refused("复用查询SQL与批准文本逐字不同，不提交")
        else:
            qid = call(
                "POST",
                "/query",
                {"name": f"DQ-43 {label}", "query_sql": sql, "is_private": False},
            )["query_id"]
        small_trial = ap.source.startswith("用户小页试跑")
        if small_trial:
            # 提交超时也不能复用批准；先落查询号，随后只作人工恢复。
            PG.mark_used(approval, "待返回执行号", "执行提交中；不自动重试")
            (H / "runs" / (label + "_submission.json")).write_text(
                json.dumps(
                    {
                        "approval": approval,
                        "query_id": qid,
                        "sql_file": sql_file,
                        "sql_sha256": ap.sql_sha,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        try:
            eid = call("POST", f"/query/{qid}/execute", {"performance": engine}, ap)[
                "execution_id"
            ]
        except Exception as exc:
            if small_trial:
                # HTTP 500/超时不等于未执行。保留未知实耗并封锁下一条。
                after = usage()
                unknown = {
                    "at_utc": dt.datetime.now(dt.UTC).isoformat(),
                    "active": True,
                    "reason": "执行提交未返回执行号；禁止重试，须找回原执行",
                    "approval": approval,
                    "query_id": qid,
                    "sql_sha256": ap.sql_sha,
                    "before": u0,
                    "after": after,
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "code", None),
                    "http_diagnostic": getattr(exc, "dune_diagnostic", None),
                }
                PG.HALT.write_text(json.dumps(unknown, ensure_ascii=False, indent=2))
                (H / "runs" / (label + "_submission_unknown.json")).write_text(
                    json.dumps(unknown, ensure_ascii=False, indent=2)
                )
                execution_state(approval, "", "SUBMISSION_UNKNOWN", unknown["reason"])
                PG.record_actual(
                    approval, "", u0[0], None if after is None else after[0], None
                )
            raise
        if not small_trial:
            PG.mark_used(approval, eid, "执行中")
        else:
            (H / "runs" / (label + "_started.json")).write_text(
                json.dumps(
                    {
                        "approval": approval,
                        "query_id": qid,
                        "execution_id": eid,
                        "sql_file": sql_file,
                        "sql_sha256": ap.sql_sha,
                        "usage_before": u0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        print(label, "批准", approval, "query", qid, "execution", eid, flush=True)
        cost, settled = None, False
        try:
            t0, cancelled, cause = time.time(), "", ""
            while True:
                st = get(f"/execution/{eid}/status")
                if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
                    break
                spent = float(st.get("execution_cost_credits") or 0)
                if not cancelled and Decimal(str(spent)) >= cancel_threshold(ap["cap"]):
                    call("POST", f"/execution/{eid}/cancel", {})
                    cause = "费用取消"
                    cancelled = "运行中费用到批准上限85%，主动取消"
                    execution_state(approval, eid, st["state"], cause)
                    print(
                        label,
                        "已扣 %.3f，触发点 %s，已请求取消"
                        % (spent, cancel_threshold(ap["cap"])),
                        flush=True,
                    )
                elif not cancelled and time.time() - t0 > max_min * 60:
                    call("POST", f"/execution/{eid}/cancel", {})
                    cancelled = "超时主动取消"
                    cause = "超时取消"
                    print(label, f"超过 {max_min:g} 分钟，已请求取消", flush=True)
                time.sleep(2)
            cost = st.get("execution_cost_credits")
            if cost is not None and float(cost) > ap["cap"] and not cause:
                cause = "费用越界完成"
            execution_state(approval, eid, st["state"], cause or st["state"])
            with open(H / "runs" / "dune_ledger.csv", "a", newline="") as f:
                note = "公开查询；引擎 %s；批准 %s%s；执行前用量 %.3f" % (
                    engine,
                    approval,
                    "；" + cancelled if cancelled else "",
                    u0[0],
                )
                csv.writer(f).writerow(
                    [qid, sql_file, eid, st["state"], cost, "", note]
                )
            print(label, qid, st["state"], cost, flush=True)
            if st["state"] != "QUERY_STATE_COMPLETED":
                print(json.dumps(st.get("error"), ensure_ascii=False), flush=True)
                sys.exit(1)
            if cost is None or float(cost) > ap["cap"]:
                raise SystemExit("完成费用未知或超过批准上限，停止下载并报告")
            if small_trial:
                from dune_get_json import settle_execution

                settle_execution(u0, cost, label)
                settled = True
                metadata = st.get("result_metadata") or {}
                (H / "runs" / (label + "_completed.json")).write_text(
                    json.dumps(
                        {
                            "approval": approval,
                            "query_id": qid,
                            "execution_id": eid,
                            "sql_file": sql_file,
                            "sql_sha256": ap.sql_sha,
                            "state": st["state"],
                            "execution_cost_credits": cost,
                            "result_metadata": metadata,
                            "downloaded": False,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                print(
                    label,
                    "执行费已核到账；结果元数据已存；下载须另登记批准",
                    flush=True,
                )
                return
            mb = (
                float((st.get("result_metadata") or {}).get("result_set_bytes") or 0)
                / 1e6
            )
            if mb > ap["max_mb"]:
                raise SystemExit(
                    "结果 %.1f MB 超过批准的下载上限 %.1f MB，不下载；先报批"
                    % (mb, ap["max_mb"])
                )
            if ap.source.startswith("总控第十轮"):
                from dune_get_json import fetch as fetch_json
                from dune_get_json import settle_execution

                settle_execution(u0, cost, label)
                fetch_json(str(qid), label, sql_file, ap, eid)
            elif ap.source.startswith("总控第九轮"):
                raise PG.Refused("旧CSV路线已停用，不下载")
            else:
                fetch(str(qid), label, sql_file, ap)
        finally:
            try:
                if small_trial and cost is not None and not settled:
                    from dune_get_json import settle_execution

                    settle_execution(u0, cost, label)
            finally:
                u1 = usage()
                PG.record_actual(
                    approval,
                    eid,
                    u0[0],
                    None if u1 is None else u1[0],
                    cost,
                    execution_only=small_trial,
                )
                print(
                    label,
                    "用量 %.3f → %s"
                    % (u0[0], "读不到" if u1 is None else "%.3f" % u1[0]),
                    flush=True,
                )


if __name__ == "__main__":
    main()

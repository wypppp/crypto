#!/usr/bin/env python3
"""DQ-43（10-13 复制自 DQ-37）：执行一条已入库的 Dune SQL（公开查询）→ 台账 → 流式下载（10-02；同 DQ-34 hl_dune.py）。
python run_dune.py <标签> <sql 文件> [medium|large] [最长分钟数] [本条预计 credits]；结果 raw/dune/<标签>.csv.gz，费用记 runs/dune_ledger.csv。
单条预计 >100 credits 的查询须先经用户批准，不在这里跑；实际费用 >100 时打印警告。
10-13：引擎按查询大小选（总控第三轮），默认 medium；扫原始指令表或交易表的重查询显式传 large。台账备注记引擎。
10-14（总控第四轮第四节）：执行超过“最长分钟数”（默认 12）就主动取消，避免再出现 30 分钟超时仍扣 104 credits；
取消后仍记台账（状态与已扣费用照实）。
10-14（总控第五轮第三节）：本期上限 22,000，硬停 24,000。执行前读账户本计费期用量（用量接口不耗 credits）：
读不到、已到上限、或“已用＋本条预计（默认 100）”超过硬停，都不跑；接口显示的本期额度更低时以额度为准。
执行前的读数记在台账备注里，下载后再读一次并打印。
"""

import csv
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.request

from dune_get import API, H, KEY, get


def call(method: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"X-Dune-API-Key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


PERIOD_CAP = 22_000.0
HARD_STOP = 24_000.0


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


def budget_gate(u, est: float) -> str:
    """u＝(已用, 额度)。返回空串表示可以跑；否则返回不跑的原因。
    10-14：接口显示的本期额度低于计划时，以额度为准（不进超额计费）。"""
    if u is None:
        return "读不到账户用量，不跑"
    used, included = u
    cap, hard = min(PERIOD_CAP, included), min(HARD_STOP, included)
    if used >= cap:
        return "本期已用 %.1f，已到上限 %.0f，先报用户" % (used, cap)
    if used + est > hard:
        return "已用 %.1f＋本条预计 %.0f 超过硬停 %.0f" % (used, est, hard)
    return ""


def main() -> None:
    label, sql_file = sys.argv[1], sys.argv[2]
    engine = sys.argv[3] if len(sys.argv) > 3 else "medium"
    max_min = float(sys.argv[4]) if len(sys.argv) > 4 else 12.0
    est = float(sys.argv[5]) if len(sys.argv) > 5 else 100.0
    if engine not in ("medium", "large"):
        raise SystemExit("引擎只能是 medium 或 large")
    u0 = usage()
    why = budget_gate(u0, est)
    if why:
        raise SystemExit(why)
    sql = (H / sql_file).read_text()
    qid = call(
        "POST",
        "/query",
        {"name": f"DQ-43 {label}", "query_sql": sql, "is_private": False},
    )["query_id"]
    eid = call("POST", f"/query/{qid}/execute", {"performance": engine})["execution_id"]
    t0 = time.time()
    cancelled = False
    while True:
        st = get(f"/execution/{eid}/status")
        if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
            break
        if not cancelled and time.time() - t0 > max_min * 60:
            call("POST", f"/execution/{eid}/cancel", {})
            cancelled = True
            print(label, f"超过 {max_min:g} 分钟，已请求取消", flush=True)
        time.sleep(15)
    cost = st.get("execution_cost_credits")
    with open(H / "runs" / "dune_ledger.csv", "a", newline="") as f:
        csv.writer(f).writerow(
            [
                qid,
                sql_file,
                eid,
                st["state"],
                cost,
                "",
                "公开查询；引擎 "
                + engine
                + ("；超时主动取消" if cancelled else "")
                + "；执行前用量 %.3f" % u0[0],
            ]
        )
    print(label, qid, st["state"], cost, flush=True)
    if st["state"] != "QUERY_STATE_COMPLETED":
        print(json.dumps(st.get("error"), ensure_ascii=False), flush=True)
        sys.exit(1)
    if cost is not None and float(cost) > 100:
        print("警告：单条费用超过审批阈值 100", flush=True)
    subprocess.run(
        [sys.executable, "dune_get_stream.py", str(qid), label, sql_file],
        cwd=H,
        check=True,
    )
    u1 = usage()
    print(
        label,
        "用量 %.3f → %s" % (u0[0], "读不到" if u1 is None else "%.3f" % u1[0]),
        flush=True,
    )


if __name__ == "__main__":
    main()

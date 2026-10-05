#!/usr/bin/env python3
"""DQ-35 v2.2 预算控制器（10-05；GPT 批 1a-i 第 4 条、总控第十九轮第三节第 4 条）。

跨任务、跨进程累计 Dune 费用：执行费、导出费、失败与重取，统一记在 runs/budget_v22.csv（只追加），
真实累计以 Dune 用量接口（POST /api/v1/usage，元数据接口，不耗 credits）为准，本地账只做分类与预估。

用法（被 run_all_v22.py 调用；也可单独看）：
  python budget_v22.py              → 打印各类累计、账户读数与各阈值余量
规则（总控第十九轮；“超额”的读法是执行决定，可推翻）：
- 账户本计费期用量到 20,000 先停、先报（REPORT_AT）；报过之后带 ack_report=True 才继续；
- “预批 DQ-35 超额 ≤15,000”读作：Plus 含 25,000 之外，DQ-35 重取还可再用至多 15,000；
  “加 vq 解码 ≤3,000”读作 vq 解码任务本身累计不超过 3,000。所以账户硬线＝25,000＋15,000＋3,000＝43,000，
  vq 任务另有 3,000 的任务线；其他任务没有预批，一律先报；
- 每次执行前用“该片上沿费用＋预计导出费”预检：任何一条会越线就不跑，先报；
- 导出费：付费档按每 MB 计（Plus 2 credits/MB）。“试用期导出不计费”只在本次下载前后用量读数的差里核实，
  每次下载都核一次，不外推：差值超过执行费的部分记为实测导出费。
"""

import csv
import datetime as dt
import json
import sys
import urllib.request

from dune_get import API, H, KEY

LEDGER = H / "runs" / "budget_v22.csv"
FIELDS = [
    "time",
    "task",
    "label",
    "kind",
    "credits",
    "usage_before",
    "usage_after",
    "note",
]
KINDS = ("execute", "export", "failed", "rerun", "probe")
REPORT_AT = 20_000.0
PLAN_INCLUDED = 25_000.0
OVER_REFETCH = 15_000.0
CAP_VQ = 3_000.0
ACCOUNT_HARD = PLAN_INCLUDED + OVER_REFETCH + CAP_VQ
EXPORT_PER_MB = {"plus": 2.0, "analyst": 10.0, "trial": 0.0}


def usage():
    """账户本计费期已用 credits（Dune 用量接口；不耗 credits）。失败时返回 None，调用方按“读不到即停”处理。"""
    req = urllib.request.Request(
        API + "/usage",
        data=b"{}",
        method="POST",
        headers={"X-Dune-API-Key": KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
    except Exception:
        return None
    return current_used(d, dt.datetime.utcnow().date())


def current_used(d, today):
    """从用量接口的返回里取“今天所在计费期”的已用 credits；找不到或不唯一返回 None。
    10-06 修：接口的键是 billing_periods（原读 billingPeriods，永远读不到）；而且会多返回一个起止颠倒、用量为 0 的
    下一期（实测 start 10-13、end 10-05），原来取最后一期会把用量读成 0。"""
    bp = d.get("billing_periods") or []
    hit = [
        p
        for p in bp
        if dt.date.fromisoformat(p["start_date"])
        <= today
        < dt.date.fromisoformat(p["end_date"])
    ]
    return float(hit[0]["credits_used"]) if len(hit) == 1 else None


def rows():
    if not LEDGER.exists():
        return []
    with open(LEDGER, newline="") as f:
        return list(csv.DictReader(f))


def record(task, label, kind, credits, before=None, after=None, note=""):
    assert kind in KINDS, kind
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(
            dict(
                time=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                task=task,
                label=label,
                kind=kind,
                credits="%.6f" % credits,
                usage_before="" if before is None else "%.3f" % before,
                usage_after="" if after is None else "%.3f" % after,
                note=note,
            )
        )


def spent(task=None, rs=None):
    """本地账累计（可按任务过滤）：{kind: credits}。"""
    out = {k: 0.0 for k in KINDS}
    for r in rows() if rs is None else rs:
        if task is None or r["task"] == task:
            out[r["kind"]] += float(r["credits"] or 0)
    return out


def check(task, est_exec, est_export_mb, plan, account_used, ack_report=False, rs=None):
    """纯函数：预检一次执行。返回 (能否执行, 原因)。account_used 为账户读数（None＝读不到）。
    est_exec 用该片的上沿估计；导出费按档位每 MB 计；任一条线会越过就不执行。"""
    if account_used is None:
        return False, "读不到账户用量，停"
    if task not in ("refetch", "vq"):
        return False, "任务 %s 没有预批额度，先报" % task
    est = est_exec + est_export_mb * EXPORT_PER_MB[plan]
    if account_used + est >= REPORT_AT and not ack_report:
        return (
            False,
            "账户用量将到 %.0f（先报线），停；报过后带 ack_report 继续" % REPORT_AT,
        )
    if account_used + est > ACCOUNT_HARD:
        return False, "账户用量将超硬线 %.0f，停" % ACCOUNT_HARD
    if task == "vq":
        s = sum(spent("vq", rs).values())
        if s + est > CAP_VQ:
            return False, "vq 解码累计 %.1f＋本次上沿 %.1f 将超 %.0f，停" % (
                s,
                est,
                CAP_VQ,
            )
    return True, "可执行：账户 %.1f，本次上沿 %.1f" % (account_used, est)


def main():
    u = usage()
    print("账户本计费期用量：", u)
    for task in ("refetch", "vq", "probe", None):
        s = spent(task)
        print(
            "任务",
            task or "全部",
            {k: round(v, 3) for k, v in s.items()},
            "合计 %.3f" % sum(s.values()),
        )
    print(
        "线：先报 %.0f；账户硬线 %.0f；vq 解码任务线 %.0f"
        % (REPORT_AT, ACCOUNT_HARD, CAP_VQ)
    )
    sys.exit(0)


if __name__ == "__main__":
    main()

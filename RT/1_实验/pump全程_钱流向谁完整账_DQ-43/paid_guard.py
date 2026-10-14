"""付费查询的批准与互斥（10-14，总控第六轮第二节；02 §10.9 补注）。

规则：
- 没有总控或用户的明确批准，不跑任何付费查询（执行与下载都算付费）。
- 每条批准记在 runs/付费批准.csv：编号、批准日期、批准来源（review 原文的存档路径）、SQL 文件、SQL 的 sha256、
  执行费上限 credits、下载上限 MB、范围说明。一条批准只用一次；SQL 内容与批准时的 sha256 不一致就不跑。
- 新形状的查询先在 1% 以内的范围上跑一次（例如 1 小时或不超过 100 个币），按实耗外推，报批后才放大。
- 同一时间只跑一条付费查询（本机文件锁）；不用自动重试或自动提交的脚本。
- 要停一条执行：先在 Dune 上取消，再结束本机进程。
"""

from __future__ import annotations

import csv
import datetime as dt
import fcntl
import hashlib
from pathlib import Path

H = Path(__file__).resolve().parent
APPROVALS = H / "runs" / "付费批准.csv"
USED = H / "runs" / "付费批准_已用.csv"
LOCK = Path.home() / ".cache" / "rt_dune_paid.lock"
FIELDS = [
    "编号",
    "批准日期",
    "批准来源",
    "SQL文件",
    "SQL_sha256",
    "执行费上限",
    "下载上限MB",
    "范围说明",
]


class Refused(SystemExit):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def check(
    approval: str, sql_file: str, approvals: Path = APPROVALS, used: Path = USED
) -> dict:
    """返回这条批准（执行费上限、下载上限）；不合格就拒绝。"""
    hit = [r for r in _rows(approvals) if r["编号"] == approval]
    if len(hit) != 1:
        raise Refused("没有批准编号 %s（runs/付费批准.csv），不跑" % approval)
    r = hit[0]
    if r["SQL文件"] != sql_file:
        raise Refused(
            "批准 %s 对应的是 %s，不是 %s" % (approval, r["SQL文件"], sql_file)
        )
    if sha(H / sql_file) != r["SQL_sha256"]:
        raise Refused("%s 的内容与批准时不一致（sha256 不同），不跑" % sql_file)
    if any(u["编号"] == approval for u in _rows(used)):
        raise Refused("批准 %s 已经用过；一条批准只用一次" % approval)
    return {"cap": float(r["执行费上限"]), "max_mb": float(r["下载上限MB"])}


def mark_used(approval: str, execution_id: str, cost, used: Path = USED) -> None:
    new = not used.exists()
    with open(used, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["编号", "使用时间", "execution_id", "执行费"])
        w.writerow(
            [
                approval,
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                execution_id,
                cost,
            ]
        )


class one_at_a_time:
    """本机文件锁：同一时间只允许一条付费查询（执行或下载）。拿不到锁直接拒绝，不排队。"""

    def __init__(self, path: Path = LOCK):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.f.close()
            raise Refused("已有一条付费查询在跑；同一时间只跑一条") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False

"""付费查询的批准与互斥（10-14，总控第六轮第二节；02 §10.9 补注）。

规则：
- 没有总控或用户的明确批准，不跑任何付费查询（执行与下载都算付费）。
- 每条批准记在 runs/付费批准.csv：编号、批准日期、批准来源（review 原文的存档路径）、SQL 文件、SQL 的 sha256、
  执行费上限 credits、下载上限 MB、范围说明。一条批准只用一次；SQL 内容与批准时的 sha256 不一致就不跑。
- 新形状的查询先在 1% 以内的范围上跑一次（例如 1 小时或不超过 100 个币），按实耗外推，报批后才放大。
- 同一时间只跑一条付费查询（本机文件锁）；不用自动重试或自动提交的脚本。
- 要停一条执行：先在 Dune 上取消，再结束本机进程。

10-14 总控第七轮补 1：密钥与付费接口只经本模块。
- .env 里的 Dune 密钥改名为 KEY_NAME，只有本模块按这个键名读取；旧脚本按旧键名 DUNE_API_KEY 读不到，一运行就报错退出。
- request() 是访问 Dune 的唯一入口。执行、结果、上传等付费接口必须带 check() 发出的批准，且在 one_at_a_time 锁内；
  用量、状态、取消、建查询、读查询文本不扣费，不要批准。
- test_no_direct_dune.py 扫描 RT 下全部 .py：新键名只许出现在本文件；直接写 Dune 地址的脚本拿不到密钥。
"""

from __future__ import annotations

import csv
import datetime as dt
import fcntl
import hashlib
import json
import math
import re
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

H = Path(__file__).resolve().parent
APPROVALS = H / "runs" / "付费批准.csv"
USED = H / "runs" / "付费批准_已用.csv"
ACTUAL = H / "runs" / "付费实耗.csv"
HALT = H / "runs" / "非执行费异常.json"
LOCK = Path.home() / ".cache" / "rt_dune_paid.lock"
ENV = H.parents[2] / ".env"
KEY_NAME = "DUNE_KEY_VIA_PAID_GUARD"
API = "https://api.dune.com/api/v1"
# 不扣费的接口（方法, 路径）；其余一律按付费处理，要批准
FREE = (
    ("POST", re.compile(r"^/usage$")),
    ("GET", re.compile(r"^/execution/[^/?]+/status$")),
    ("POST", re.compile(r"^/execution/[^/?]+/cancel$")),
    ("POST", re.compile(r"^/query$")),
    ("GET", re.compile(r"^/query/\d+$")),
)
FIELDS = [
    "编号",
    "批准日期",
    "批准来源",
    "SQL文件",
    "SQL_sha256",
    "执行费上限",
    "下载上限MB",
    "范围说明",
    "预计 credits",
    "下载费上限",
]


def round_gate(approval: str, approvals=None, used=None, actual=None) -> str:
    """各轮独立：第七、八轮50，第九轮25；实耗＋本条上限。锁内调用。"""
    approvals = APPROVALS if approvals is None else approvals
    used = USED if used is None else used
    actual = ACTUAL if actual is None else actual
    rows = _rows(approvals)
    hit = [r for r in rows if r["编号"] == approval]
    if len(hit) != 1:
        return "批准编号不存在或重复，不跑"
    source = next(
        (
            s
            for s in ("总控第七轮", "总控第八轮", "总控第九轮")
            if hit[0]["批准来源"].startswith(s)
        ),
        None,
    )
    if source is None:
        return ""
    group = {r["编号"]: r for r in rows if r["批准来源"].startswith(source)}
    spent = {r["编号"]: r for r in _rows(actual)}
    total = Decimal(0)
    for k in {r["编号"] for r in _rows(used)} & group.keys():
        try:
            value = Decimal(spent[k]["合计实耗"])
            if not value.is_finite() or value < 0:
                raise ValueError
        except (KeyError, InvalidOperation, ValueError):
            return "批准 %s 的实耗未核清，不跑" % k
        total += value
    # 原批准下载费 ≤5；用户追加的下载额度单独登记。预计值不作为批准上限。
    download_cap = Decimal(group[approval].get("下载费上限") or "5")
    cap = Decimal(group[approval]["执行费上限"]) + download_cap
    if (
        not cap.is_finite()
        or not download_cap.is_finite()
        or cap < 0
        or download_cap < 0
    ):
        return "本条上限无效，不跑"
    limit = 25 if source == "总控第九轮" else 50
    if total + cap > limit:
        return f"{source}已实耗 {total}＋本条上限 {cap} 超过 {limit}，不跑"
    return ""


def halt_gate():
    if HALT.exists():
        return "存在未核清的非执行费增量，停止付费并报告"
    return ""


def check_download_usage(before, after, label):
    """无执行的下载区间：任何可辨识的正增量立刻封住后续付费动作。"""
    if before is None or after is None:
        raise Refused("下载前后用量缺失，停下报告")
    delta = Decimal(str(after[0])) - Decimal(str(before[0]))
    if delta > 0:
        HALT.write_text(
            json.dumps(
                {
                    "at_utc": dt.datetime.now(dt.UTC).isoformat(),
                    "label": label,
                    "before": before[0],
                    "after": after[0],
                    "non_execution_delta": str(delta),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise Refused(f"下载区间出现非执行费增量 {delta}，停止并报告")
    if delta < 0:
        raise Refused("账户用量倒退，停下核对")


def request_bytes(path, ticket, destination, encoding="gzip", max_bytes=None):
    """CSV/JSON 响应体按原始传输编码落盘，记录字节与分页头；不重试。"""
    if not isinstance(ticket, Ticket) or not ticket.locked:
        raise Refused("传输下载没有锁内批准")
    if not re.fullmatch(r"/execution/[^/?]+/results(?:/csv)?\?.+", path):
        raise Refused("只允许已有执行的分页下载路径")
    if encoding not in ("gzip", "identity"):
        raise Refused("传输编码无效")
    if halt_gate():
        raise Refused(halt_gate())
    req = urllib.request.Request(
        API + path,
        method="GET",
        headers={"X-Dune-API-Key": _key(), "Accept-Encoding": encoding},
    )
    cap = max_bytes if max_bytes is not None else int(ticket["max_mb"] * 2e6) + 65536
    part = destination.with_suffix(destination.suffix + ".part")
    total = 0
    with urllib.request.urlopen(req, timeout=90) as r, part.open("wb") as f:
        headers = {
            k.lower(): v
            for k, v in r.headers.items()
            if k.lower()
            in (
                "content-encoding",
                "content-type",
                "content-length",
                "x-dune-next-offset",
            )
        }
        while chunk := r.read(65536):
            total += len(chunk)
            if total > cap:
                raise Refused("HTTP响应体超过传输保护上限")
            f.write(chunk)
    part.replace(destination)
    return dict(headers, wire_bytes=total)


def record_actual(approval, execution_id, before, after, cost, actual=None):
    """按用量接口增量记执行与下载实耗；用量或执行费缺失时留空，阻止下一条。"""
    actual = ACTUAL if actual is None else actual
    delta = None if after is None else Decimal(str(after)) - Decimal(str(before))
    exec_cost = None if cost is None else Decimal(str(cost))
    known = (
        delta is not None
        and delta.is_finite()
        and exec_cost is not None
        and exec_cost.is_finite()
        and delta >= 0
        and exec_cost >= 0
        and delta + Decimal("0.01") >= exec_cost
    )
    new = not actual.exists()
    with open(actual, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(
                [
                    "编号",
                    "execution_id",
                    "用量前",
                    "用量后",
                    "执行费",
                    "下载费",
                    "合计实耗",
                ]
            )
        total = max(delta, exec_cost) if known else ""
        w.writerow(
            [
                approval,
                execution_id,
                before,
                after,
                cost,
                total - exec_cost if known else "",
                total,
            ]
        )


class Refused(SystemExit):
    pass


class Ticket(dict):
    """check() 发出的批准：{cap, max_mb}，另记编号；只在 one_at_a_time(ticket) 锁内有效。"""

    def __init__(self, approval: str, cap: float, max_mb: float):
        super().__init__(cap=cap, max_mb=max_mb)
        self.approval = approval
        self.locked = False
        self.download_cap = 5.0
        self.source = ""


def is_free(method: str, path: str) -> bool:
    return any(m == method and r.match(path) for m, r in FREE)


def _key() -> str:
    m = re.search(r"^\s*%s\s*=\s*['\"]?([^'\"\s]+)" % KEY_NAME, ENV.read_text(), re.M)
    if m is None:
        raise Refused("工作区 .env 里没有 %s" % KEY_NAME)
    return m.group(1)


def request(method: str, path: str, body=None, ticket=None):
    """访问 Dune 的唯一入口。付费接口要有效批准（check() 发出、且在锁内）；不重试。"""
    if not is_free(method, path):
        if halt_gate():
            raise Refused(halt_gate())
        if not isinstance(ticket, Ticket) or not ticket.locked:
            raise Refused("%s %s 是付费接口：没有锁内的批准，不访问" % (method, path))
    req = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"X-Dune-API-Key": _key(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def check(
    approval: str, sql_file: str, approvals: Path = APPROVALS, used: Path = USED
) -> Ticket:
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
    ticket = Ticket(approval, float(r["执行费上限"]), float(r["下载上限MB"]))
    ticket.download_cap = float(r.get("下载费上限") or "5")
    ticket.source = r["批准来源"]
    if not all(
        math.isfinite(v) and v >= 0
        for v in (ticket["cap"], ticket["max_mb"], ticket.download_cap)
    ):
        raise Refused("批准上限须为有限非负数，不跑")
    return ticket


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

    def __init__(self, ticket=None, path: Path = LOCK):
        if isinstance(ticket, Path):  # 兼容 one_at_a_time(path)
            ticket, path = None, ticket
        self.ticket, self.path = ticket, path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.f.close()
            raise Refused("已有一条付费查询在跑；同一时间只跑一条") from None
        if self.ticket is not None:
            self.ticket.locked = True
        return self

    def __exit__(self, *exc):
        if self.ticket is not None:
            self.ticket.locked = False
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False

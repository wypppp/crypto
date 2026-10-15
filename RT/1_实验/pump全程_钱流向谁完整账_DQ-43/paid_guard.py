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
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, unquote, urlsplit
from decimal import Decimal, InvalidOperation
from pathlib import Path

H = Path(__file__).resolve().parent
APPROVALS = H / "runs" / "付费批准.csv"
USED = H / "runs" / "付费批准_已用.csv"
ACTUAL = H / "runs" / "付费实耗.csv"
HALT = H / "runs" / "非执行费异常.json"
S3_POLICY = H / "runs" / "S3_第十轮执行政策.json"
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
    # 第十一轮零费用可行性核查：这里只读MV元数据，不创建、不刷新。
    (
        "GET",
        re.compile(
            r"^/materialized-views(?:/[^/?]+)?(?:\?limit=\d+(?:&offset=\d+)?)?$"
        ),
    ),
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
            for s in (
                "总控第七轮",
                "总控第八轮",
                "总控第九轮",
                "总控第十轮",
                "用户小页试跑",
            )
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
    limit = 25 if source in ("总控第九轮", "总控第十轮", "用户小页试跑") else 50
    if total + cap > limit:
        return f"{source}已实耗 {total}＋本条上限 {cap} 超过 {limit}，不跑"
    return ""


def halt_gate():
    if HALT.exists():
        try:
            resolved = json.loads(HALT.read_text())
            if resolved.get("active") is False and S3_POLICY.exists():
                return ""
            if resolved.get("reason"):
                return resolved["reason"] + "；停止付费并报告"
        except (ValueError, OSError):
            pass
        return "存在未核清的非执行费增量，停止付费并报告"
    return ""


def csv_gate(path):
    if "/results/csv" in unquote(urlsplit(path).path):
        raise Refused("总控第十轮：CSV导出禁用，只用JSON结果接口")


def active_source(ticket):
    policy = json.loads(S3_POLICY.read_text()) if S3_POLICY.exists() else {}
    return ticket.source.startswith(
        policy.get("active_paid_source_prefix", "总控第十轮")
    )


def small_download_binding(ticket, eid=None, qid=None):
    """小页批准还须绑定固定查询、执行、结果体积和预计费用。"""
    if not ticket.source.startswith("用户小页试跑"):
        return None
    if not S3_POLICY.exists() or not active_source(ticket):
        raise Refused("小页批准不是当前付费来源")
    policy = json.loads(S3_POLICY.read_text())
    binding = policy.get("download_bindings", {}).get(ticket.approval)
    if not binding or ticket["cap"] != 0 or binding.get("sql_sha256") != ticket.sql_sha:
        raise Refused("下载批准缺少SQL/固定执行绑定")
    if (eid is not None and str(eid) != binding["execution_id"]) or (
        qid is not None and str(qid) != str(binding["query_id"])
    ):
        raise Refused("下载执行号或查询号与批准不同")
    expected = Decimal(str(binding["expected_credits"]))
    size = binding["metadata_bytes"]
    if (
        not expected.is_finite()
        or expected < 0
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or expected != Decimal(size) * 2 / 1_000_000
        or expected * 2 != Decimal(str(ticket.download_cap))
        or binding.get("page_rows") != 1000
    ):
        raise Refused("下载预算须为2/MB、上限预计乘2、每页1000行")
    return binding


def execution_review_gate(ticket):
    if not S3_POLICY.exists():
        return
    policy = json.loads(S3_POLICY.read_text())
    if not active_source(ticket) or ticket["cap"] <= 0:
        raise Refused("当前只准现行来源登记的执行；旧批准不再使用")
    if ticket.source.startswith("用户小页试跑") and (
        ticket.download_cap or ticket["max_mb"]
    ):
        raise Refused("小页试跑执行和下载须分开批准")
    if not policy.get("gpt_review_passed"):
        raise Refused("GPT三处复审尚未通过，不创建或提交查询")
    if ticket.sql_sha not in policy.get("reviewed_trial_sql_sha256", []):
        raise Refused("SQL不在已通过复审的清单里")


def s3_period_gate(current, cap):
    if not S3_POLICY.exists():
        return ""
    p = json.loads(S3_POLICY.read_text())
    today = dt.datetime.now(dt.UTC).date().isoformat()
    if not p["period_start"] <= today < p["period_end"]:
        return "第十轮400 credits政策已跨计费期，停下报告"
    if current is None:
        return "读不到用量，不能核S3本期上限"
    used = Decimal(str(current[0])) - Decimal(str(p["baseline_used"]))
    if not used.is_finite() or used < 0:
        return "S3本期基线无效，停下报告"
    if used + Decimal(str(cap)) > Decimal(str(p["limit_credits"])):
        return "S3从第十轮起已用加本条上限超过400，停下报告"
    return ""


def check_download_usage(before, after, label, expected=0):
    """下载区间实扣超出登记预计就封锁；跨动作未知增量仍按0容许。"""
    if before is None or after is None:
        raise Refused("下载前后用量缺失，停下报告")
    delta = Decimal(str(after[0])) - Decimal(str(before[0]))
    allowance = Decimal(str(expected))
    if not allowance.is_finite() or allowance < 0:
        raise Refused("下载预计费用无效，停止")
    if delta > allowance:
        HALT.write_text(
            json.dumps(
                {
                    "at_utc": dt.datetime.now(dt.UTC).isoformat(),
                    "label": label,
                    "before": before[0],
                    "after": after[0],
                    "non_execution_delta": str(delta),
                    "expected_credits": str(allowance),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise Refused(
            f"下载区间出现非执行费增量 {delta}，超预计 {allowance}，停止并报告"
        )
    if delta < 0:
        raise Refused("账户用量倒退，停下核对")


def idle_usage_gate(current):
    """同计费期连续操作：前条末值到本条初值也必须核对，堵住延迟计费。

    余额变化来源尚未核清时先停；跨计费期须重新登记账户基线。
    """
    if current is None:
        raise Refused("读不到提交前用量")
    previous = _rows(ACTUAL)
    if not previous:
        return
    last = previous[-1].get("用量后")
    if last in (None, ""):
        raise Refused("前条末用量缺失，停下核对")
    check_download_usage(
        (float(last), current[1]), current, "跨动作延迟计费或未核清增量"
    )


def request_bytes(path, ticket, destination, encoding="gzip", max_bytes=None):
    """CSV/JSON 响应体按原始传输编码落盘，记录字节与分页头；不重试。"""
    csv_gate(path)
    if not isinstance(ticket, Ticket) or not ticket.locked:
        raise Refused("传输下载没有锁内批准")
    if not re.fullmatch(r"/execution/[^/?]+/results\?.+", path):
        raise Refused("只允许已有执行的分页下载路径")
    if S3_POLICY.exists() and not active_source(ticket):
        raise Refused("JSON通道只对现行来源的新批准解除异常封锁")
    if ticket.source.startswith("用户小页试跑"):
        parts = urlsplit(path)
        eid = parts.path.split("/")[2]
        small_download_binding(ticket, eid=eid)
        args = parse_qs(parts.query)
        if (
            set(args) != {"limit", "offset"}
            or args["limit"] != ["1000"]
            or not (len(args["offset"]) == 1 and args["offset"][0].isdigit())
        ):
            raise Refused("小页通道只许固定1000行及非负offset，不允许部分结果")
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
    with open_http(req, timeout=90) as r, part.open("wb") as f:
        headers = {
            k.lower(): v
            for k, v in r.headers.items()
            if k.lower()
            in (
                "content-encoding",
                "content-type",
                "content-length",
                "x-dune-next-offset",
                "date",
            )
        }
        while True:
            if total >= cap:
                raise Refused("HTTP响应体达到保护上限，停止，不读更多字节")
            chunk = r.read(min(65536, cap - total))
            if not chunk:
                break
            total += len(chunk)
            f.write(chunk)
    part.replace(destination)
    return dict(headers, wire_bytes=total)


def record_actual(
    approval, execution_id, before, after, cost, actual=None, *, execution_only=False
):
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
    if execution_only and known:
        # 用量仅三位小数，执行费用精度更高；小额舍入差不是下载。
        known = abs(delta - exec_cost) <= Decimal("0.001")
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
                (0 if execution_only else total - exec_cost) if known else "",
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
        self.sql_sha = ""


def is_free(method: str, path: str) -> bool:
    return any(m == method and r.match(path) for m, r in FREE)


def _key() -> str:
    m = re.search(r"^\s*%s\s*=\s*['\"]?([^'\"\s]+)" % KEY_NAME, ENV.read_text(), re.M)
    if m is None:
        raise Refused("工作区 .env 里没有 %s" % KEY_NAME)
    return m.group(1)


def open_http(req, timeout=90):
    """仅改变到同一官方HTTPS主机的传输路由；不重试、不回落、不关TLS验证。"""
    policy = json.loads(S3_POLICY.read_text()) if S3_POLICY.exists() else {}
    route = policy.get("http_transport", "system")
    if route == "direct":
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            req, timeout=timeout
        )
    if route != "system":
        raise Refused("HTTP传输路由无效")
    return urllib.request.urlopen(req, timeout=timeout)


def http_failure(exc, method, path, api_key):
    """保留服务端错误证据，密钥脱敏；正文仅放raw，公开日志只留错误字段。"""
    record = {
        "at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "method": method,
        "path": path,
        "error_type": type(exc).__name__,
        "http_status": getattr(exc, "code", None),
    }
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read(16385)
        safe = body[:16384].decode(errors="replace").replace(api_key, "[REDACTED]")
        record["response_headers"] = {
            k.lower(): v.replace(api_key, "[REDACTED]")
            for k, v in (exc.headers or {}).items()
            if k.lower()
            in {
                "server",
                "date",
                "content-type",
                "via",
                "cf-ray",
                "retry-after",
                "x-request-id",
                "x-correlation-id",
                "x-amzn-trace-id",
                "x-cache",
            }
        }
        record["body_truncated"] = len(body) > 16384
        try:
            parsed = json.loads(safe)
        except ValueError:
            parsed = {}
        if isinstance(parsed, dict):
            record["error_fields"] = {
                k: v[:2048]
                for k, v in parsed.items()
                if k
                in {"error", "message", "detail", "type", "request_id", "execution_id"}
                and isinstance(v, str)
            }
        if not record.get("error_fields"):
            title = re.search(r"<title[^>]*>(.*?)</title>", safe, re.I | re.S)
            record["response_title"] = title[1][:150] if title else ""
        destination = H / "raw/dune/http_errors" / f"{time.time_ns()}.txt"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(safe)
            record["private_response"] = str(destination.relative_to(H))
            record["private_response_sha256"] = sha(destination)
        except OSError:
            record["private_response_save_failed"] = True
    else:
        record["transport_error"] = str(exc).replace(api_key, "[REDACTED]")[:512]
    exc.dune_diagnostic = record
    try:
        log = H / "runs/dune_http_failures.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 日志失败不能吞掉原始网络异常。


def request(method: str, path: str, body=None, ticket=None):
    """访问 Dune 的唯一入口。付费接口要有效批准（check() 发出、且在锁内）；不重试。"""
    csv_gate(path)
    if not is_free(method, path):
        if halt_gate():
            raise Refused(halt_gate())
        if not isinstance(ticket, Ticket) or not ticket.locked:
            raise Refused("%s %s 是付费接口：没有锁内的批准，不访问" % (method, path))
        if S3_POLICY.exists():
            if not active_source(ticket):
                raise Refused("当前通道只允许现行来源新批准")
            if re.fullmatch(r"/query/\d+/execute", path):
                execution_review_gate(ticket)
            elif re.fullmatch(r"/execution/[^/?]+/results\?.+", path):
                raise Refused("第十轮JSON下载须用分段核账入口，禁用旧直接分页")
            else:
                raise Refused("其他付费接口不在第十轮批准内")
    api_key = _key()
    req = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"X-Dune-API-Key": api_key, "Content-Type": "application/json"},
    )
    try:
        with open_http(req, timeout=90) as r:
            return json.load(r)
    except (OSError, ValueError) as exc:
        http_failure(exc, method, path, api_key)
        raise


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
    ticket.sql_sha = r["SQL_sha256"]
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

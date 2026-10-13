#!/usr/bin/env python3
"""DQ-42 前向录制：公开 HTTP 接口轮询（10-13）。只用标准库。只录不读。

python g_http.py            常驻运行（按来源决定表里“录”的来源）
python g_http.py --once K   对来源 K 只请求一次（排错用；输出只有状态码与计数）

每次请求记一行 kind=request：请求发出与收到的 UTC 与单调钟时刻、HTTP 状态、错误、
缓存与限速相关的响应头、响应体 sha256 与长度、字段结构指纹、原始响应体（与上一次相同时只记哈希）。
每个条目按稳定标识记 kind=item：首次出现、核心字段改动、从列表消失（墓碑）、重新出现；
价格、成交量等估值字段不进核心哈希，单独记哈希。不补录：backfill 恒为 false。
“首次出现”只表示“这个来源、在这个频率下的首次出现”，不表示市场里第一次发生。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from g_store import (
    RAW,
    SCHEMA,
    STATE,
    DayWriter,
    Heartbeat,
    now,
    pending_manifest_days,
    write_manifest,
    write_pid,
)

UA = "RT-DQ42-forward-recorder/1 (non-commercial research; read-only polling of public endpoints)"
KEEP_HEADERS = (
    "date",
    "age",
    "cache-control",
    "etag",
    "last-modified",
    "expires",
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-used",
    "x-ratelimit-resource",
    "cf-cache-status",
    "content-type",
    "link",
    "x-github-request-id",
    "x-cache",
    "x-served-by",
)
# 估值类字段：变化频繁，不进核心哈希（单独记 h_val）
VAL_RE = re.compile(
    r"(price|marketcap|market_cap|mcap|fdv|volume|liquidity|reserve|txns|change|score|holder|"
    r"usd|buys|sells|stats|tvl|amount|count|trending|rank|audit|fees)",
    re.I,
)
# 时间类字段：记进 src_times，也不进核心哈希
TIME_RE = re.compile(r"(date|time|created|updated|_at$|At$|timestamp)", re.I)


@dataclass
class Source:
    key: str  # 流名，也是健康检查里的来源名
    url: str
    every_s: int
    host: str
    id_fields: tuple = ()  # 稳定标识的字段；空则用核心哈希
    items: str = "auto"  # auto：响应是列表就用列表，是字典就取 data 列表
    conditional: bool = False  # 用 ETag 条件请求
    headers: dict = field(default_factory=dict)  # 额外请求头（不放密钥）


@dataclass
class HostGate:
    """同一主机两次请求之间的最小间隔，以及 429 之后的冷却。"""

    min_gap_s: float
    next_ok: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, sleep=time.sleep, clock=time.time) -> None:
        with self.lock:
            t = clock()
            if t < self.next_ok:
                sleep(self.next_ok - t)
            self.next_ok = max(clock(), self.next_ok) + self.min_gap_s

    def cool(self, seconds: float, clock=time.time) -> None:
        with self.lock:
            self.next_ok = max(self.next_ok, clock() + seconds)


# ---------- 纯函数（有手算测试） ----------


def struct_fp(obj) -> tuple[str, int]:
    """字段结构指纹：键路径与类型的集合（不含值），返回 (sha256 前 16 位, 路径数)。"""
    paths: set[str] = set()

    def walk(o, p):
        if isinstance(o, dict):
            paths.add(p + ":obj")
            for k, v in o.items():
                walk(v, f"{p}.{k}")
        elif isinstance(o, list):
            paths.add(p + ":list")
            for v in o:
                walk(v, p + "[]")
        else:
            paths.add(f"{p}:{type(o).__name__}")

    walk(obj, "$")
    s = "\n".join(sorted(paths))
    return hashlib.sha256(s.encode()).hexdigest()[:16], len(paths)


def split_fields(item, prefix=""):
    """把条目拆成 (核心, 估值, 时间) 三部分，键用点号路径。"""
    core, val, tim = {}, {}, {}
    if not isinstance(item, dict):
        return {"$": item}, {}, {}
    for k, v in item.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            c, va, ti = split_fields(v, path + ".")
            if VAL_RE.search(k):
                val[path] = v
            else:
                core.update(c)
                val.update(va)
                tim.update(ti)
        elif TIME_RE.search(k):
            tim[path] = v
        elif VAL_RE.search(k):
            val[path] = v
        else:
            core[path] = v
    return core, val, tim


def h(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def item_id(item, id_fields: tuple) -> str:
    if isinstance(item, dict) and id_fields and all(f in item for f in id_fields):
        return "|".join(str(item[f]) for f in id_fields)
    core, _, _ = split_fields(item)
    return "h:" + h(core)


def items_of(body, mode: str = "auto") -> list | None:
    if mode == "auto":
        if isinstance(body, list):
            return body
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            return body["data"]
        return None
    return None


def diff_items(prev: dict, items: list, id_fields: tuple) -> tuple[list[dict], dict]:
    """prev：{id: {"c": 核心哈希, "on": 是否在上一次列表里}}。
    返回 (条目事件, 新状态)。事件：first_seen、changed、absent、reappeared。"""
    events = []
    state = {k: dict(v, on=False) for k, v in prev.items()}
    seen = set()
    for pos, it in enumerate(items):
        iid = item_id(it, id_fields)
        if iid in seen:  # 同一次响应里重复出现的标识只记第一次
            continue
        seen.add(iid)
        core, val, tim = split_fields(it)
        hc, hv = h(core), h(val)
        old = prev.get(iid)
        if old is None:
            ev = "first_seen"
        elif not old["on"]:
            ev = "reappeared"
        elif old["c"] != hc:
            ev = "changed"
        else:
            ev = None
        if ev:
            events.append(
                {
                    "id": iid,
                    "event": ev,
                    "pos": pos,
                    "h_core": hc,
                    "h_val": hv,
                    "src_times": tim,
                }
            )
        state[iid] = {"c": hc, "on": True}
    for iid, v in prev.items():
        if v["on"] and iid not in seen:
            events.append(
                {
                    "id": iid,
                    "event": "absent",
                    "pos": None,
                    "h_core": v["c"],
                    "h_val": None,
                    "src_times": {},
                }
            )
    return events, state


def backoff_s(
    attempt: int, retry_after: str | None, base: float = 2.0, cap: float = 120.0
) -> float:
    """第 attempt 次失败后等待的秒数：有 Retry-After（秒）就照它，否则 base·2^(attempt-1)，封顶 cap。"""
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 900.0)
        except ValueError:
            pass
    return min(base * 2 ** (attempt - 1), cap)


# ---------- I/O ----------


def http_get(
    url: str, headers: dict | None = None, timeout: float = 20.0
) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return (
            e.code,
            {k.lower(): v for k, v in (e.headers or {}).items()},
            e.read() or b"",
        )


class Poller:
    def __init__(
        self,
        src: Source,
        gate: HostGate,
        root: Path = RAW,
        state_dir: Path = STATE,
        get=http_get,
        sleep=time.sleep,
        max_attempts: int = 3,
        conditional: bool = False,
    ):
        self.src = src
        self.gate = gate
        self.w = DayWriter(root, f"http/{src.key}")
        self.state_path = state_dir / f"http_{src.key}.json"
        self.get = get
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.items_state: dict = {}
        self.last_body_sha: str | None = None
        self.etag: str | None = None  # 只用于 conditional 来源（GitHub：304 不计配额）
        self.conditional = conditional
        self.n_ok = 0
        self.n_fail = 0
        self._load()

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                d = json.loads(self.state_path.read_text())
                self.items_state = d.get("items", {})
                self.last_body_sha = d.get("last_body_sha")
                self.etag = d.get("etag")
            except (OSError, ValueError):
                pass

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "items": self.items_state,
                    "last_body_sha": self.last_body_sha,
                    "etag": self.etag,
                }
            )
        )
        tmp.replace(self.state_path)

    def poll(
        self, url: str | None = None, tag: str | None = None
    ) -> tuple[int | None, object]:
        """请求一次（含重试）。返回 (最后的状态码, 解析后的 JSON 或 None)。"""
        url = url or self.src.url
        status, parsed = None, None
        for attempt in range(1, self.max_attempts + 1):
            self.gate.wait(self.sleep)
            u0, m0 = now()
            err = None
            try:
                cond = (
                    {"If-None-Match": self.etag}
                    if self.conditional and tag is None and self.etag
                    else None
                )
                status, hdr, body = self.get(
                    url, {**self.src.headers, **(cond or {})} or None
                )
            except Exception as e:  # 断网、超时、DNS
                status, hdr, body = None, {}, b""
                err = repr(e)[:300]
            u1, m1 = now()
            sha = hashlib.sha256(body).hexdigest()
            rec = {
                "v": SCHEMA,
                "kind": "request",
                "src": self.src.key,
                "tag": tag,
                "url": url,
                "attempt": attempt,
                "t_req_utc_ns": u0,
                "t_req_mono_ns": m0,
                "t_resp_utc_ns": u1,
                "t_resp_mono_ns": m1,
                "status": status,
                "err": err,
                "hdr": {k: hdr[k] for k in KEEP_HEADERS if k in hdr},
                "body_sha256": sha,
                "body_len": len(body),
                "backfill": False,
            }
            parsed = None
            if status == 304:  # 未变：等同于与上一次相同的响应体
                self.n_ok += 1
                rec["body_same_as_prev"] = True
                rec["n_items"] = None
                self.w.write(rec, u0)
                self.w.flush()
                return status, None
            if status == 200:
                try:
                    parsed = json.loads(body)
                except ValueError:
                    rec["err"] = "json_decode_error"
                if parsed is not None:
                    rec["struct_fp"], rec["struct_n"] = struct_fp(parsed)
            same = tag is None and sha == self.last_body_sha and status == 200
            rec["body_same_as_prev"] = same
            if not same and body:
                try:
                    rec["body"] = body.decode("utf-8")
                except UnicodeDecodeError:
                    rec["body_b64"] = base64.b64encode(body).decode()
            items = items_of(parsed, self.src.items) if parsed is not None else None
            rec["n_items"] = None if items is None else len(items)
            self.w.write(rec, u0)
            if status == 200 and parsed is not None:
                self.n_ok += 1
                if tag is None:
                    self.last_body_sha = sha
                    if self.conditional and hdr.get("etag"):
                        self.etag = hdr["etag"]
                    if items is not None:
                        events, self.items_state = diff_items(
                            self.items_state, items, self.src.id_fields
                        )
                        for ev in events:
                            self.w.write(
                                {
                                    "v": SCHEMA,
                                    "kind": "item",
                                    "src": self.src.key,
                                    "t_req_utc_ns": u0,
                                    "backfill": False,
                                    **ev,
                                },
                                u0,
                            )
                    self._save()
                self.w.flush()
                return status, parsed
            self.n_fail += 1
            retry = status is None or status == 429 or status >= 500
            if not retry or attempt == self.max_attempts:
                if status == 429:
                    self.gate.cool(
                        backoff_s(attempt, hdr.get("retry-after"), base=30.0)
                    )
                break
            if status == 429:  # 限速：冷却整个主机，下一次 gate.wait 自然等够
                self.gate.cool(backoff_s(attempt, hdr.get("retry-after"), base=30.0))
            else:
                self.sleep(backoff_s(attempt, hdr.get("retry-after")))
        self.w.flush()
        return status, parsed


# ---------- GitHub 微博热搜存档：提交列表 + 新提交的 raw 文件 ----------


class GitHubArchive:
    """每 5 分钟拉一次提交列表；新提交记首次看到的时刻，并下载它改动的 raw/*.json。"""

    def __init__(
        self, poller_list: Poller, poller_files: Poller, max_new_per_poll: int = 5
    ):
        self.pl = poller_list
        self.pf = poller_files

        self.max_new = max_new_per_poll

    def poll(self) -> None:
        before = {k for k, v in self.pl.items_state.items()}
        status, commits = self.pl.poll()
        if status != 200 or not isinstance(commits, list):
            return
        new = [
            c
            for c in commits
            if isinstance(c, dict) and c.get("sha") and c["sha"] not in before
        ]
        if not before:  # 第一次运行：只记基线，不回取旧提交
            return
        for c in new[: self.max_new]:
            st, detail = self.pf.poll(url=c.get("url"), tag="commit")
            if st != 200 or not isinstance(detail, dict):
                continue
            for f in detail.get("files") or []:
                name = f.get("filename") or ""
                if (
                    name.startswith("raw/")
                    and name.endswith(".json")
                    and f.get("raw_url")
                ):
                    self.pf.poll(url=f["raw_url"], tag="raw_file")


# ---------- 运行 ----------


def load_sources(path: Path) -> tuple[list[Source], dict]:
    d = json.loads(path.read_text())
    return [
        Source(
            key=s["key"],
            url=s["url"],
            every_s=s["every_s"],
            host=s["host"],
            id_fields=tuple(s.get("id_fields", ())),
            items=s.get("items", "auto"),
            conditional=s.get("conditional", False),
            headers=s.get("headers", {}),
        )
        for s in d["sources"]
        if s.get("decision") == "录"
    ], d.get("host_min_gap_s", {})


def host_loop(pollers: list, gh: GitHubArchive | None, stop: threading.Event) -> None:
    due = {id(p): 0.0 for p in pollers}
    while not stop.is_set():
        t = time.time()
        for p in pollers:
            if t >= due[id(p)]:
                every = p.src.every_s
                due[id(p)] = (
                    int(t) // every + 1
                ) * every  # 按墙钟对齐，主机睡眠后过点即补
                try:
                    if gh is not None and p is gh.pl:
                        gh.poll()
                    else:
                        p.poll()
                except Exception as e:  # 记录器不因单个来源出错退出
                    u, _ = now()
                    p.w.write(
                        {
                            "v": SCHEMA,
                            "kind": "loop_error",
                            "src": p.src.key,
                            "t_utc_ns": u,
                            "err": repr(e)[:300],
                        },
                        u,
                    )
                    p.w.flush()
        stop.wait(0.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(Path(__file__).with_name("sources.json")))
    ap.add_argument("--once", default=None)
    a = ap.parse_args()
    sources, gaps = load_sources(Path(a.config))
    gates = {s.host: HostGate(gaps.get(s.host, 1.5)) for s in sources}
    pollers = {
        s.key: Poller(s, gates[s.host], conditional=s.conditional) for s in sources
    }
    if a.once:
        st, body = pollers[a.once].poll()
        n = len(items_of(body) or []) if body is not None else None
        print(json.dumps({"src": a.once, "status": st, "n_items": n}))
        return
    write_pid("g_http")
    gh = None
    if "gh_weibo_commits" in pollers and "gh_weibo_files" in pollers:
        gh = GitHubArchive(pollers["gh_weibo_commits"], pollers.pop("gh_weibo_files"))
    by_host: dict[str, list] = {}
    for p in pollers.values():
        by_host.setdefault(p.src.host, []).append(p)
    stop = threading.Event()
    threads = [
        threading.Thread(target=host_loop, args=(ps, gh, stop), daemon=True, name=h_)
        for h_, ps in by_host.items()
    ]
    for th in threads:
        th.start()
    all_p = list(pollers.values()) + ([gh.pf] if gh else [])
    hb = Heartbeat("g_http", lambda: {p.src.key: [p.n_ok, p.n_fail] for p in all_p})
    hb.tick(force=True)
    try:
        while True:
            hb.tick()
            for d in pending_manifest_days():
                write_manifest(d)
            alive = sum(th.is_alive() for th in threads)
            if alive < len(threads):
                raise SystemExit("轮询线程退出")
            time.sleep(5)
    finally:
        stop.set()
        for p in all_p:
            p.w.flush()


if __name__ == "__main__":
    main()

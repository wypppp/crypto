#!/usr/bin/env python3
"""DQ-42 前向录制的存储层（10-13）。只用标准库。

- 只追加的压缩 JSONL：每个流按 UTC 日一个文件 `raw/<流>/YYYY-MM-DD.jsonl.gz`；
  每次 flush 写一个独立的 gzip 成员（多成员 gzip 合法），写完不改。
- 每条记录带 UTC 纳秒与本机单调钟纳秒两个时刻。
- 每日清单：已结束的 UTC 日，逐文件记行数、字节数、sha256，写到 `manifests/rec/YYYY-MM-DD.json`（入库）。
  已存在的清单不覆盖；文件在清单之后被改动，由健康检查发现。
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import threading
import time
from pathlib import Path

UTC = dt.timezone.utc
SCHEMA = 1  # 录制行的结构版本；字段含义变了就加 1

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
STATE = HERE / "state"
MANIFESTS = HERE / "manifests"


def now() -> tuple[int, int]:
    """(UTC 纳秒, 单调钟纳秒)。"""
    return time.time_ns(), time.monotonic_ns()


def utc_day(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns // 1_000_000_000, UTC).strftime("%Y-%m-%d")


def iso(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def dumps(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, separators=(",", ":"))


class DayWriter:
    """一个流的只追加写入器。线程安全；记录按自身时刻归入 UTC 日文件。"""

    def __init__(self, root: Path, stream: str):
        self.dir = root / stream
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.buf: list[str] = []
        self.day: str | None = None
        self.lines = 0  # 本进程已落盘的行数

    def write(self, rec: dict, ts_ns: int) -> None:
        line = dumps(rec)
        day = utc_day(ts_ns)
        with self.lock:
            if self.day is not None and day != self.day:
                self._flush()
            self.day = day
            self.buf.append(line)

    def flush(self) -> None:
        with self.lock:
            self._flush()

    def _flush(self) -> None:
        if not self.buf:
            return
        data = ("\n".join(self.buf) + "\n").encode("utf-8")
        path = self.dir / f"{self.day}.jsonl.gz"
        with open(path, "ab") as f:
            f.write(gzip.compress(data))
            f.flush()
            os.fsync(f.fileno())
        self.lines += len(self.buf)
        self.buf = []


def file_stats(path: Path) -> dict:
    """行数（解压后的换行数）、字节数、sha256。不解析内容。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    lines = 0
    with gzip.open(path, "rb") as g:
        for chunk in iter(lambda: g.read(1 << 20), b""):
            lines += chunk.count(b"\n")
    return {"bytes": path.stat().st_size, "lines": lines, "sha256": h.hexdigest()}


def write_manifest(
    day: str, raw: Path = RAW, out: Path = MANIFESTS / "rec"
) -> Path | None:
    """为一个已结束的 UTC 日写清单；已存在则不覆盖，返回 None。"""
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{day}.json"
    if target.exists():
        return None
    files = sorted(raw.rglob(f"{day}.jsonl.gz"))
    entries = [{"path": str(p.relative_to(raw)), **file_stats(p)} for p in files]
    doc = {
        "day": day,
        "generated_utc": iso(time.time_ns()),
        "schema": SCHEMA,
        "n_files": len(entries),
        "files": entries,
    }
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(target)
    return target


def pending_manifest_days(
    raw: Path = RAW,
    out: Path = MANIFESTS / "rec",
    now_ns: int | None = None,
    settle_s: int = 600,
) -> list[str]:
    """已结束且过了 settle_s 秒、还没有清单的 UTC 日。"""
    now_ns = time.time_ns() if now_ns is None else now_ns
    today = utc_day(now_ns)
    sec_into_day = (now_ns // 1_000_000_000) % 86400
    days = sorted({p.name[:10] for p in raw.rglob("*.jsonl.gz")})
    done = {p.stem for p in out.glob("*.json")} if out.exists() else set()
    res = []
    for d in days:
        if d in done or d > today:
            continue
        if d == today:
            continue
        # 刚过零点的前一天，等 settle_s 秒，让各写入器把前一天的缓冲落盘
        yesterday = utc_day(now_ns - 86400 * 1_000_000_000)
        if d == yesterday and sec_into_day < settle_s:
            continue
        res.append(d)
    return res


class Heartbeat:
    """每分钟一行心跳，写到 `raw/heartbeat/<进程名>/`。counters 由调用方提供（只放计数）。"""

    def __init__(self, proc: str, counters, root: Path = RAW, every_s: int = 60):
        self.w = DayWriter(root, f"heartbeat/{proc}")
        self.proc = proc
        self.counters = counters
        self.every = every_s
        self.next_due = 0.0
        self.started = time.time_ns()

    def tick(self, force: bool = False) -> bool:
        t = time.time()
        if not force and t < self.next_due:
            return False
        self.next_due = (int(t) // self.every + 1) * self.every
        u, m = now()
        self.w.write(
            {
                "v": SCHEMA,
                "kind": "heartbeat",
                "proc": self.proc,
                "pid": os.getpid(),
                "t_utc_ns": u,
                "t_mono_ns": m,
                "started_utc_ns": self.started,
                "counters": self.counters(),
            },
            u,
        )
        self.w.flush()
        return True


def write_pid(name: str) -> Path:
    """防重复运行：pid 文件里的进程还活着就退出。"""
    STATE.mkdir(parents=True, exist_ok=True)
    pid_path = STATE / f"{name}.pid"
    if pid_path.exists():
        try:
            old = int(pid_path.read_text().strip())
            os.kill(old, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        else:
            raise SystemExit(f"{name} 已在运行（pid {old}）")
    pid_path.write_text(str(os.getpid()))
    return pid_path

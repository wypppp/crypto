#!/usr/bin/env python3
"""断档提醒（10-13，总控 10-13 意见第 3 条）。只用标准库；只读心跳与 pid 文件，不读录到的内容。

python g_gaps.py        列出全部记录器的状态；有断档时退出码为 1

判定（任一条成立即“断档”）：
- 进程不在了（pid 文件里的进程不存在）；
- 最近一次心跳早于门槛：分钟级心跳的记录器 30 分钟；DQ-34 整点记录器平时每小时才写一次心跳，门槛 90 分钟。
obs.py 每次运行时调用 warn_text()，有断档就先在屏幕上提示；g_health.py 把结果写进健康检查。
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
D34 = HERE.parent / "股票上链_周末休市定价_DQ-34" / "raw"

# 名称、pid 文件、心跳来源、门槛（秒）
RECORDERS = [
    ("g_http", HERE / "state" / "g_http.pid", ("dq42", "g_http"), 1800),
    (
        "g_chain_mainnet",
        HERE / "state" / "g_chain_mainnet.pid",
        ("dq42", "g_chain_mainnet"),
        1800,
    ),
    (
        "dq34_trades",
        D34 / "trades" / "trades.pid",
        ("txt", D34 / "trades" / "heartbeat.txt"),
        1800,
    ),
    (
        "dq34_recorder",
        D34 / "recorder" / "recorder.pid",
        ("txt", D34 / "recorder" / "heartbeat.txt"),
        5400,
    ),
]


def pid_alive(pid_file: Path) -> bool:
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def last_beat(src: tuple, raw: Path = HERE / "raw") -> float | None:
    """最近一次心跳的 UTC epoch 秒。"""
    kind, where = src
    if kind == "txt":
        try:
            s = Path(where).read_text().split()[0]
            return dt.datetime.fromisoformat(s).timestamp()
        except (OSError, ValueError, IndexError):
            return None
    files = sorted((raw / "heartbeat" / where).glob("*.jsonl.gz"))
    for p in reversed(files):
        try:
            with gzip.open(p, "rt") as f:
                last = None
                for line in f:
                    last = line
        except (OSError, EOFError):
            continue
        if last:
            return json.loads(last)["t_utc_ns"] / 1e9
    return None


def status(
    now: float | None = None, recorders=RECORDERS, raw: Path = HERE / "raw"
) -> list[dict]:
    now = time.time() if now is None else now
    out = []
    for name, pid_file, src, limit in recorders:
        alive = pid_alive(pid_file)
        beat = last_beat(src, raw)
        age = None if beat is None else now - beat
        gap = (not alive) or age is None or age > limit
        out.append(
            {
                "name": name,
                "alive": alive,
                "beat_age_s": age,
                "limit_s": limit,
                "gap": gap,
            }
        )
    return out


def warn_text(st: list[dict] | None = None) -> str:
    st = status() if st is None else st
    bad = [s for s in st if s["gap"]]
    if not bad:
        return ""
    parts = []
    for s in bad:
        why = (
            "进程不在"
            if not s["alive"]
            else "没有心跳记录"
            if s["beat_age_s"] is None
            else ("%d 分钟没有心跳" % (s["beat_age_s"] // 60))
        )
        parts.append(f"{s['name']}（{why}）")
    return (
        "！！记录器断档："
        + "；".join(parts)
        + "。请运行 sh /home/ancillary/RT/1_实验/跨场所_前向录制_DQ-42/start_all.sh"
    )


if __name__ == "__main__":
    st = status()
    for s in st:
        age = "无" if s["beat_age_s"] is None else "%.0f 秒" % s["beat_age_s"]
        print(
            f"{s['name']}: 进程{'在' if s['alive'] else '不在'}，心跳距今 {age}，门槛 {s['limit_s']} 秒，"
            f"{'断档' if s['gap'] else '正常'}"
        )
    sys.exit(1 if any(s["gap"] for s in st) else 0)

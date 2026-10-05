#!/usr/bin/env python3
"""DQ-35 v2.2 开发拒读入口（10-05；GPT 批 1a-i 第 3 条、DQ-37 前向批次预登记 §2 第 12 条“过滤在数据入口统一执行”）。

开发读取只能经由这里：
1. 先只读母体元数据（逐笔样本的 'C' 行，或正式数据的 P 层池头列），按曲线创建时刻定出开发池：
   DQ-37 开发周（weeks.is_dev）、且不属前向批次（forward.is_forward，2026-10-05 起创建）。
2. 再读数值文件：按行流式解析，**解析当行就丢掉**非开发池的行与 2026-10-05 起的成交（R3），
   被丢掉的行不进入任何列表、聚合、特征或标签；只返回丢弃计数。
weeks.py、forward.py 冻结，这里只调用。
"""

import csv
import datetime as dt
import gzip
import sys
from decimal import Decimal
from pathlib import Path

H = Path(__file__).resolve().parent
# 追加到末尾：DQ-37 也有 dune_get.py，插到前面会让调用方的 `from dune_get import H` 解析成 DQ-37 的目录（10-05 修）
sys.path.append(str(H.parent / "发射台_前期右尾评测底座_DQ-37"))
import forward  # noqa: E402
import weeks  # noqa: E402

RAW = H / "raw" / "dune"
CUTOFF_EPOCH = (forward.TRADE_CUTOFF - dt.date(1970, 1, 1)).days * 86400


def to_epoch(s):
    """数值文本（含 Dune 以浮点文本返回的整数）或 'YYYY-MM-DD HH:MM:SS.fff UTC' → epoch 秒（float）。"""
    s = str(s).strip()
    if s[:4].isdigit() and s[4:5] == "-":
        d = dt.datetime.strptime(s.replace(" UTC", "")[:19], "%Y-%m-%d %H:%M:%S")
        return (d - dt.datetime(1970, 1, 1)).total_seconds()
    return float(Decimal(s))


def is_dev_created(epoch_s):
    """曲线创建 epoch 秒 → 是否开发池（开发周且不属前向批次）。"""
    d = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=epoch_s)).date()
    return weeks.is_dev(d.isoformat()) and not forward.is_forward(epoch_s)


def dev_ids_from_meta(meta_rows, id_col, created_col):
    """母体元数据 → (开发池集合, 剔除计数)。只看创建时刻，不看任何数值列。"""
    keep, drop = set(), 0
    for r in meta_rows:
        c = r.get(created_col, "")
        if c not in ("", None) and is_dev_created(to_epoch(c)):
            keep.add(r[id_col])
        else:
            drop += 1
    return keep, drop


def stream(label, id_col, keep, time_col=None, path=None):
    """流式读一个数值文件：只返回 id 在 keep 里、且（给了 time_col 时）成交早于 2026-10-05 的行。
    返回 (行列表, 丢弃计数)。文件不存在（零行结果）返回 ([], 0)。"""
    p = path or RAW / ("%s.csv.gz" % label)
    if not p.exists():
        return [], 0
    out, drop = [], 0
    with gzip.open(p, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r.get(id_col) not in keep:
                drop += 1
                continue
            if (
                time_col
                and r.get(time_col) not in ("", None)
                and to_epoch(r[time_col]) >= CUTOFF_EPOCH
            ):
                drop += 1
                continue
            out.append(r)
    return out, drop


def read_meta(label, kind_col, id_col):
    """逐笔样本只取 'C'（纳入）与 'X'（排除计数）行；不保留任何数值事件行。"""
    p = RAW / ("%s.csv.gz" % label)
    c, x = [], []
    with gzip.open(p, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r[kind_col] == "C":
                c.append(r)
            elif r[kind_col] == "X":
                x.append(r)
    return c, x

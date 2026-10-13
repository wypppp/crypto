#!/usr/bin/env python3
"""DQ-42 用户热点观察记录（G v2 §2.3，10-13）。只用标准库。用法见《观察记录使用说明.md》。

python obs.py                      交互式记一条（逐项提问）
python obs.py add --where 微博热搜 --what "某某事件" --coin 是 --names "关键词1,关键词2" \
       --venue four.meme --conf 3 [--note ...]
python obs.py add ... --transcribed --orig-time "2026-10-13 21:05" --orig-carrier "微信文件传输助手"
python obs.py add ... --corrects 12  更正第 12 条（新加一行，不改旧行）
python obs.py verify               核对哈希链（只输出条数与通过／失败）
python obs.py manifest             写清单（条数、文件 sha256、末行哈希）到 manifests/obs/，可入库

记录只追加：每行带前一行的 sha256（prev），改动任何一行都会让后面的链断掉。
时刻由工具写入（UTC 与北京时间），不手填。记录文件在 observations/，不进公开仓库。
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "observations" / "observations.jsonl"
MANIFEST_DIR = HERE / "manifests" / "obs"
UTC = dt.timezone.utc
BJ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")  # 北京时间无夏令时
GENESIS = "0" * 64
SCHEMA = 1
COIN = {"是": "是", "否": "否", "不确定": "不确定", "y": "是", "n": "否", "?": "不确定"}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_orig_time(s: str, now_utc: dt.datetime) -> dt.datetime:
    """转录的原始时刻，按北京时间理解：'YYYY-MM-DD HH:MM'、'MM-DD HH:MM' 或 'HH:MM'（当天）。"""
    s = s.strip().replace("/", "-").replace("T", " ")
    today = now_utc.astimezone(BJ)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=BJ)
        except ValueError:
            pass
    for fmt in ("%m-%d %H:%M",):
        try:
            t = dt.datetime.strptime(s, fmt)
            return t.replace(year=today.year, tzinfo=BJ)
        except ValueError:
            pass
    t = dt.datetime.strptime(s, "%H:%M")
    r = today.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if r > today:  # 过了零点才转录前一天的消息
        r -= dt.timedelta(days=1)
    return r


def build(fields: dict, seq: int, prev: str, now_utc: dt.datetime) -> dict:
    """组一条记录。字段已校验。"""
    rec = {
        "v": SCHEMA,
        "seq": seq,
        "utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "beijing": now_utc.astimezone(BJ).strftime("%Y-%m-%d %H:%M:%S"),
        **fields,
        "prev": prev,
    }
    return rec


def validate(f: dict) -> dict:
    if not f.get("where") or not f.get("what"):
        raise ValueError("“在哪看到”和“看到了什么”不能空")
    coin = COIN.get(str(f.get("coin", "")).strip())
    if coin is None:
        raise ValueError("“会不会出币”只能填 是、否、不确定")
    conf = int(f.get("conf"))
    if not 1 <= conf <= 5:
        raise ValueError("“把握”只能填 1～5")
    names = f.get("names") or []
    if isinstance(names, str):
        names = [x.strip() for x in names.replace("，", ",").split(",") if x.strip()]
    out = {
        "where": f["where"].strip(),
        "what": f["what"].strip(),
        "coin": coin,
        "names": names,
        "venue": (f.get("venue") or "不确定").strip(),
        "conf": conf,
        "mode": "转录" if f.get("transcribed") else "直接记录",
        "note": (f.get("note") or "").strip(),
    }
    if f.get("transcribed"):
        if not f.get("orig_time") or not f.get("orig_carrier"):
            raise ValueError("转录要写原始时刻和原始载体")
        out["orig_beijing"] = f["orig_time_bj"]
        out["orig_utc"] = f["orig_time_utc"]
        out["orig_carrier"] = f["orig_carrier"].strip()
    if f.get("corrects") is not None:
        out["corrects"] = int(f["corrects"])
    return out


def last_line(path: Path) -> tuple[int, str]:
    """(条数, 末行原文)。"""
    if not path.exists():
        return 0, ""
    n, last = 0, ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
                last = line.rstrip("\n")
    return n, last


def append(fields: dict, path: Path = LOG, now_utc: dt.datetime | None = None) -> dict:
    now_utc = now_utc or dt.datetime.now(UTC)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        n, last = last_line(path)
        rec = build(fields, n + 1, sha(last) if last else GENESIS, now_utc)
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
    return rec


def verify(path: Path = LOG) -> dict:
    """核对哈希链与序号。只返回条数、通过与否、第一处断开的序号。"""
    if not path.exists():
        return {"lines": 0, "result": "pass", "first_bad_seq": None}
    prev, n = GENESIS, 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            n += 1
            try:
                d = json.loads(line)
            except ValueError:
                return {"lines": n, "result": "fail", "first_bad_seq": n}
            if d.get("prev") != prev or d.get("seq") != n:
                return {"lines": n, "result": "fail", "first_bad_seq": n}
            prev = sha(line)
    return {"lines": n, "result": "pass", "first_bad_seq": None}


def manifest(
    path: Path = LOG, out: Path = MANIFEST_DIR, now_utc: dt.datetime | None = None
) -> Path:
    now_utc = now_utc or dt.datetime.now(UTC)
    v = verify(path)
    data = path.read_bytes() if path.exists() else b""
    _, last = last_line(path)
    doc = {
        "generated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lines": v["lines"],
        "chain": v["result"],
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "last_line_sha256": sha(last) if last else None,
    }
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{now_utc.strftime('%Y-%m-%d')}.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return target


def ask(prompt: str, default: str | None = None) -> str:
    s = input(f"{prompt}{f'（回车＝{default}）' if default else ''}：").strip()
    return s or (default or "")


def interactive() -> dict:
    print("记一条热点观察。先记再查：还没查任何币、价格或链上数据之前记。")
    f = {
        "where": ask("在哪看到（平台、群、账号或链接）"),
        "what": ask("看到了什么（一句话）"),
        "coin": ask("会不会出币（是／否／不确定）", "不确定"),
        "names": ask("预计的币名或关键词（逗号分隔，可空）"),
        "venue": ask("预计在哪（链与平台，例如 pump.fun、four.meme）", "不确定"),
        "conf": ask("把握（1～5）", "3"),
        "note": ask("备注（可空）"),
    }
    if ask("这是转录吗（手机上先发给自己的）？y／n", "n").lower().startswith("y"):
        f["transcribed"] = True
        f["orig_time"] = ask("原始时刻（北京时间，例如 21:05 或 2026-10-13 21:05）")
        f["orig_carrier"] = ask("原始载体（例如 微信文件传输助手）")
    return f


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="热点观察记录（只追加）")
    sp = ap.add_subparsers(dest="cmd")
    a_add = sp.add_parser("add")
    a_add.add_argument("--where", required=True)
    a_add.add_argument("--what", required=True)
    a_add.add_argument("--coin", required=True)
    a_add.add_argument("--names", default="")
    a_add.add_argument("--venue", default="不确定")
    a_add.add_argument("--conf", required=True, type=int)
    a_add.add_argument("--note", default="")
    a_add.add_argument("--transcribed", action="store_true")
    a_add.add_argument("--orig-time", dest="orig_time")
    a_add.add_argument("--orig-carrier", dest="orig_carrier")
    a_add.add_argument("--corrects", type=int)
    sp.add_parser("verify")
    sp.add_parser("manifest")
    a = ap.parse_args(argv)
    try:  # 断档提醒（总控 10-13 第 3 条）；检查本身出错不影响记录
        from g_gaps import warn_text

        w = warn_text()
        if w:
            print(w)
    except Exception:
        pass
    if a.cmd == "verify":
        print(json.dumps(verify(), ensure_ascii=False))
        return
    if a.cmd == "manifest":
        print(manifest())
        return
    f = (
        interactive()
        if a.cmd is None
        else {k: v for k, v in vars(a).items() if k != "cmd"}
    )
    now_utc = dt.datetime.now(UTC)
    if f.get("transcribed"):
        ot = parse_orig_time(f.get("orig_time") or "", now_utc)
        f["orig_time_bj"] = ot.strftime("%Y-%m-%d %H:%M")
        f["orig_time_utc"] = ot.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        fields = validate(f)
    except (ValueError, TypeError) as e:
        sys.exit(f"没有记录：{e}")
    rec = append(fields, now_utc=now_utc)
    print(f"已记第 {rec['seq']} 条（北京 {rec['beijing']}，UTC {rec['utc'][:19]}）")


if __name__ == "__main__":
    main()

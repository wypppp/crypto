"""DQ-18 D 段离线合并：把各时间块的压缩路径拼成每个信号的结果（第一层）并列出需要 RPC 估值的成交。

输入：raw/d/D_*.json（make_d_block.py 输出）。输出：raw/d/signals.csv（每信号一行）、raw/d/need_tx.txt。
规则（预登记 §2–§3）：
- 入场（主口径 L=10 秒）：穿越小时行（rt=E）的 x_*，即 t_s 之后 10 秒起主池第一笔；5 分钟、60 分钟为 e5_*、e60_*。
- b50：按时间遍历路径行，M = max(入场市值, 各行 c 与 segmax)；首个 c ≤ 0.5·M 的行触发，
  以该行 x_*（该小时结束后主池下一笔）为退出成交。180 天内未触发：以 D180 那一行的 x_* 退出。
- 固定时点 H：取 h+1h ≤ t_s+H 的最后一个路径小时的 c（带 hz 标签的行或块末行）。
- 上界：各块 maxc 的最大值。
"""
import csv
import glob
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HZ = {"D1": 1, "D7": 7, "D30": 30, "D90": 90, "D180": 180}


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S") if s else None


def main():
    rows = defaultdict(list)
    entry = {}
    for f in sorted(glob.glob(str(ROOT / "raw" / "d" / "D_*.json"))):
        if f.endswith("_status.json"):
            continue
        for r in json.load(open(f))["rows"]:
            k = (r["mint"], int(float(r["tier"])), r["signal_time"][:19])
            if r["rt"] == "E":
                entry[k] = r
            else:
                rows[k].append(r)
    sample = {r["mint"]: r for r in csv.DictReader(open(ROOT / "raw" / "census" / "sample_D.csv"))}
    frame = [r for r in csv.DictReader(open(ROOT / "raw" / "census" / "first_crossings.csv"))
             if r["mint"] in sample and "2024-06-01" <= r["hour_start"][:10] <= "2026-03-15"]
    out, need = [], set()
    for fr in frame:
        k = (fr["mint"], int(fr["threshold_usd"]), fr["signal_time"][:19])
        st = ts(k[2])
        e = entry.get(k)
        path = sorted(rows.get(k, []), key=lambda r: r["h"])
        rec = {"mint": k[0], "tier": k[1], "signal_time": k[2], "stratum": sample[k[0]]["stratum"],
               "weight": sample[k[0]]["weight"], "validation": sample[k[0]]["validation"],
               "has_entry": bool(e), "n_path_rows": len(path)}
        if e:
            rec.update({"entry_pool": e["pool"], "entry_is_cp": e["is_cp"], "entry_tx": e["x_tx"],
                        "entry_time": e["x_time"], "entry_cap_print": e["x_cap"],
                        "cross_hour_vwap": e["c"],
                        "e5_tx": e["e5_tx"], "e5_cap_print": e["e5_cap"],
                        "e60_tx": e["e60_tx"], "e60_cap_print": e["e60_cap"]})
            if e["x_tx"]:
                need.add(e["x_tx"])
        m = (e or {}).get("x_cap") or 0.0
        trig = None
        for r in path:
            m = max(m, r["segmax"] or 0.0, r["c"] or 0.0) if r["kind"] == "hi" else max(m, r["segmax"] or 0.0)
            if r["c"] is not None and r["c"] <= 0.5 * m and trig is None:
                trig = r
                break
        hz = {}
        for lab, d in HZ.items():
            cands = [r for r in path if ts(r["h"]) + timedelta(hours=1) <= st + timedelta(days=d)
                     and (lab in (r["hz"] or "").split(",") or r["is_last"])]
            if cands:
                hz[lab] = max(cands, key=lambda r: r["h"])
        exit_row = trig or hz.get("D180") or (path[-1] if path else None)
        exit_kind = "b50" if trig else ("D180" if "D180" in hz else ("last" if path else "none"))
        # 退出成交缺失（块末无下一笔）：用其后第一条路径行的 c 作代理并标记
        nxt = None
        if exit_row and not exit_row["x_tx"]:
            later = [r for r in path if r["h"] > exit_row["h"]]
            nxt = later[0] if later else None
        rec.update({
            "b50_triggered": bool(trig),
            "b50_trigger_h": trig["h"][:19] if trig else "",
            "b50_trigger_c": trig["c"] if trig else "",
            "exit_kind": exit_kind,
            "exit_proxy_c": (nxt["c"] if nxt else "") if exit_row and not exit_row["x_tx"] else "",
            "exit_tx": exit_row["x_tx"] if exit_row else "",
            "exit_time": exit_row["x_time"] if exit_row else "",
            "exit_cap_print": exit_row["x_cap"] if exit_row else "",
            "exit_pool": exit_row["pool"] if exit_row else "",
            "max_cap": max([r["maxc"] or 0 for r in path] or [0]),
            **{"c_" + lab: (hz[lab]["c"] if lab in hz else "") for lab in HZ},
        })
        if exit_row and exit_row["x_tx"]:
            need.add(exit_row["x_tx"])
        out.append(rec)
    keys = sorted({k for r in out for k in r})
    with open(ROOT / "raw" / "d" / "signals.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    (ROOT / "raw" / "d" / "need_tx.txt").write_text("\n".join(sorted(need)))
    print("signals", len(out), "with entry", sum(r["has_entry"] for r in out),
          "triggered", sum(r.get("b50_triggered", False) for r in out), "tx needed", len(need))


if __name__ == "__main__":
    main()

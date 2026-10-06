#!/usr/bin/env python3
"""DQ-41 第 4 天 O3 来源与时点审计：微博热搜存档 × four.meme 中文名币（10-06）。

python o3_weibo_audit.py → results/o3_weibo_events.csv、results/o3_weibo_summary.json
只用开发周 A 周（2026-06-01～07）的源记录与币的元数据（名称、代号、创建时刻、开盘时刻），不读价格、成交与毕业列。
- 事件＝一个热搜标题；决策时刻＝它第一次出现在存档提交里的时刻（最早可验证的存档可得时点）。
- 上榜时刻只知道区间：(上一次提交, 首次出现的提交]。
- 候选币：决策时刻之前 7 天内创建、且开盘时刻（有记录时）不晚于决策时刻的中文名币；创建时刻先过入口过滤。
  名称或代号规范化后（只留汉字、字母、数字，小写），长度 ≥2 且是标题的子串，记宽松候选；长度 ≥4 记严格候选。
- 另记“抢在存档前”的候选：创建于上榜区间内（上一次提交之后、首次出现之前）的币。
全部事件都进分母，没有候选的事件照样计数。
"""

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

import screen_gate as G

H = Path(__file__).resolve().parent
META = (
    H.parent / "BSC_four.meme数据留存与冒烟_DQ-29" / "raw" / "dune" / "SAVE_META.csv.gz"
)
WIN = dt.timedelta(days=7)
KEEP = re.compile(r"[0-9a-z一-鿿]+")


def norm(s):
    return "".join(KEEP.findall(str(s).lower()))


def ts(s):
    s = str(s).replace(" UTC", "")
    if re.fullmatch(r"\d+(\.\d+)?", s):  # four.meme 的开盘时刻是 Unix 秒
        return pd.Timestamp(float(s), unit="s")
    return pd.Timestamp(s).tz_localize(None)


def events():
    """全周按提交时刻排序、按标题去重：同一标题跨日出现只算一次。上榜区间的下界取全局上一次提交；
    全周第一次提交里的标题没有下界（左截断），留在分母里，不进时滞统计。"""
    log = json.load(open(H / "raw" / "weibo" / "commits.json"))
    cs = sorted([r for r in log if r["gate_ok"]], key=lambda r: r["committer_date"])
    rows, seen, prev_t = [], set(), None
    for r in cs:
        t = ts(r["committer_date"].replace("Z", ""))
        for x in json.load(
            open(H / "raw" / "weibo" / r["day"] / ("%s.json" % r["sha"]))
        ):
            if x["title"] not in seen:
                seen.add(x["title"])
                rows.append(
                    {
                        "day": r["day"],
                        "title": x["title"],
                        "first_seen": t,
                        "prev_commit": prev_t,
                    }
                )
        prev_t = t
    return pd.DataFrame(rows)


def coins(t0, t1):
    """先只读时刻列过入口与窗口，再读这些行的名称、代号。"""
    h = pd.read_csv(META, usecols=["created_at", "launch_time", "cjk"], dtype=str)
    c = h["created_at"].map(ts)
    ok = (
        (c >= t0)
        & (c < t1)
        & h["cjk"].str.lower().isin(["true", "1"])
        & c.map(G.date_ok)
    )
    skip = [i + 1 for i in h.index[~ok]]
    m = pd.read_csv(
        META,
        usecols=["token", "name", "symbol", "created_at", "launch_time"],
        skiprows=skip,
        dtype=str,
    )
    m["created"] = m["created_at"].map(ts)
    m["launch"] = m["launch_time"].map(
        lambda x: ts(x) if isinstance(x, str) and x else pd.NaT
    )
    m["n_name"], m["n_sym"] = m["name"].map(norm), m["symbol"].map(norm)
    return m, int((~ok).sum())


def main():
    ev = events()
    m, n_out = coins(ev["first_seen"].min() - WIN, ev["first_seen"].max())
    out, lead = [], []
    for e in ev.itertuples():
        tn = norm(e.title)
        w = m[(m["created"] < e.first_seen) & (m["created"] >= e.first_seen - WIN)]
        w = w[w["launch"].isna() | (w["launch"] <= e.first_seen)]
        pairs = list(zip(w["n_name"], w["n_sym"]))

        def hit(k):
            return w[
                [
                    (len(a) >= k and a in tn) or (len(b) >= k and b in tn)
                    for a, b in pairs
                ]
            ]

        loose, strict = hit(2), hit(4)
        if pd.notna(
            e.prev_commit
        ):  # 严格候选里创建在上榜区间内的币：早于存档首现多少小时
            for c in strict["created"][strict["created"] > e.prev_commit]:
                lead.append((e.title, (e.first_seen - c).total_seconds() / 3600))
        early = (
            loose[loose["created"] > e.prev_commit]
            if pd.notna(e.prev_commit)
            else loose.iloc[0:0]
        )
        out.append(
            {
                "day": e.day,
                "title": e.title,
                "first_seen": e.first_seen,
                "window_h": None
                if pd.isna(e.prev_commit)
                else (e.first_seen - e.prev_commit).total_seconds() / 3600,
                "n_loose": len(loose),
                "n_strict": len(strict),
                "n_loose_in_window": len(early),
            }
        )
    df = pd.DataFrame(out)
    (H / "results").mkdir(exist_ok=True)
    df.to_csv(H / "results" / "o3_weibo_events.csv", index=False)
    s = {
        "events": len(df),
        "coins_in_window": len(m),
        "coins_gated_out_or_outside": n_out,
        "events_left_censored": int(df["window_h"].isna().sum()),
        "window_h_median": float(df["window_h"].median()),
        "window_h_max": float(df["window_h"].max()),
        "loose_zero": int((df["n_loose"] == 0).sum()),
        "strict_zero": int((df["n_strict"] == 0).sum()),
        "loose_ge1": int((df["n_loose"] >= 1).sum()),
        "strict_ge1": int((df["n_strict"] >= 1).sum()),
        "loose_median_if_ge1": float(df.loc[df["n_loose"] >= 1, "n_loose"].median()),
        "strict_median_if_ge1": float(df.loc[df["n_strict"] >= 1, "n_strict"].median())
        if (df["n_strict"] >= 1).any()
        else None,
        "events_with_loose_created_in_window": int(
            (df["n_loose_in_window"] >= 1).sum()
        ),
    }
    nc = df["window_h"].notna()
    ld = pd.DataFrame(lead, columns=["title", "lead_h"])
    s["strict_events_not_censored"] = int(((df["n_strict"] >= 1) & nc).sum())
    s["strict_events_with_coin_created_in_window"] = int(ld["title"].nunique())
    s["strict_coins_created_in_window"] = len(ld)
    s["lead_h_q10_q50_q90"] = [
        round(float(ld["lead_h"].quantile(q)), 2) for q in (0.1, 0.5, 0.9)
    ]
    (H / "results" / "o3_weibo_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=1)
    )
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

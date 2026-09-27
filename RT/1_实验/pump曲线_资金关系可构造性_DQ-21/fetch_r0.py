"""DQ-21 R0 取数（README v1.2 §4、§7）。可断点续跑：已存的走查不重取。

python fetch_r0.py r0a --cap 9500      R0a：sample.csv 中 r0a=True 的币；K=30、P=3
python fetch_r0.py r0b --cap N --K 30 --P 5   R0b（K、P、cap 按 过程/R0b_预算与门槛.md）：
    先主样本（random）、再 winner、再 matched；R0a 中被 P=3 截断的 back 走查续翻到 P（__ext）。
09-27 R0b 起的改动（不影响解析）：一页不满 100 条即停（R0a 中 78 次第 2 页为空）；续翻；按层排序。

三类走查，完整交易存 raw/helius/（不提交），索引存 raw/helius_index.csv：
- coin：币地址在 [创建, 创建+30 分钟) 的全部成功交易（升序，最多 30 页），只用于 R0a 核对早买名单；F101 六币用 H1 本地数据，不取；
- back：钱包（早买者或创建者）从锚点交易所在秒往前翻，窗口 [锚点−7 天, 锚点]，降序，最多 P 页；
- fwd：创建者在 [创建, 创建+30 分钟) 的交易，升序，最多 P 页（创建者与早买者在买入后、t 之前的往来）。
同一钱包已有的 back 走查若已完整覆盖新锚点的 7 天窗口，就复用，不再取。
"""
import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import helius as HL

H = Path(__file__).resolve().parent
RAW = H / "raw" / "helius"
IDX = H / "raw" / "helius_index.csv"
H1RAW = H.parent / "pump曲线_案例时序与点火跟随_H1" / "raw"
WEEK = 7 * 86400


def _key(kind, addr, anchor_ts):
    return f"{kind}__{addr}__{int(anchor_ts)}"


def walk(kind, addr, gte, lt, order, max_pages):
    pages, txs, token, lat0 = 0, [], None, len(HL.STATE["lat"])
    t0 = time.time()
    budget_stop = False
    while pages < max_pages:
        try:
            r = HL.gtfa(addr, gte, lt, order, token)
        except HL.BudgetExceeded:
            if pages == 0:
                raise
            budget_stop = True
            break
        pages += 1
        txs += r.get("data", [])
        token = r.get("paginationToken")
        if not token or len(r.get("data", [])) < 100:
            token = None
            break
    complete = token is None
    ts = [x.get("blockTime") for x in txs if x.get("blockTime")]
    return txs, {"kind": kind, "addr": addr, "gte": int(gte), "lt": int(lt), "pages": pages, "complete": complete,
                 "n_tx": len(txs), "min_ts": min(ts) if ts else None, "max_ts": max(ts) if ts else None,
                 "wall_s": round(time.time() - t0, 2), "budget_stop": budget_stop}


def run_task(t):
    f = RAW / f"{t['key']}.jsonl.gz"
    if f.exists():
        return None
    try:
        txs, meta = walk(t["kind"], t["addr"], t["gte"], t["lt"], t["order"], t["max_pages"])
    except HL.BudgetExceeded as e:
        return {"key": t["key"], "error": str(e)}
    with gzip.open(f, "wt") as g:
        for x in txs:
            g.write(json.dumps(x) + "\n")
    return {"key": t["key"], **meta}


def covered(done, addr, gte, lt):
    """已有的 back 走查是否完整覆盖 [gte, lt)。"""
    for m in done.get(addr, []):
        if m["gte"] <= gte and m["lt"] >= lt and m["complete"]:
            return m["key"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["r0a", "r0b"])
    ap.add_argument("--cap", type=int, required=True)
    ap.add_argument("--K", type=int, default=30)
    ap.add_argument("--P", type=int, default=3)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--dry", action="store_true", help="只列任务与最大可能花费，不调用")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    idx = pd.read_csv(IDX) if IDX.exists() else pd.DataFrame(columns=["key"])
    spent = int(idx.get("pages", pd.Series(dtype=float)).fillna(0).sum()) * HL.CREDITS_PER_CALL
    HL.STATE["cap"] = a.cap - spent
    print("already spent (index)", spent, "remaining cap", HL.STATE["cap"])

    S = pd.read_csv(H / "sample.csv")
    coins = S[S.r0a].mint.unique() if a.stage == "r0a" else S[~S.r0a].mint.unique()
    q = pd.read_csv(H / "raw" / "dune" / "Q_buyers.csv.gz")
    q["t"] = pd.to_datetime(q.ts).astype("int64") // 10**9
    cr = q[(q.kind == "create") & q.mint.isin(coins)]
    by = q[(q.kind == "buy") & q.mint.isin(coins) & (q.buyer_rank <= a.K)]
    local = {p.name.split("_", 1)[1].split(".")[0] for p in H1RAW.glob("full24h_*.jsonl.gz")}

    tasks = []
    if a.stage == "r0b":
        prio = {"random": 0, "winner": 1, "matched": 2}
        rank = S[~S.r0a].drop_duplicates("mint").set_index("mint").stratum.map(prio)
        cr = cr.assign(p=cr.mint.map(rank)).sort_values(["p", "mint"])
        by = by.assign(p=by.mint.map(rank)).sort_values(["p", "mint", "buyer_rank"])
        # R0a 中被截断的 back 走查：从已取到的最早时刻续翻到 P 页
        old = idx[(idx.kind == "back") & (idx.get("stage") == "r0a") & (idx.complete.astype(str) != "True")] if len(idx) else idx
        for m in old.itertuples():
            tasks.append({"key": f"{m.key}__ext", "kind": "back_ext", "addr": m.addr, "gte": m.gte,
                          "lt": int(m.min_ts) + 1, "order": "desc", "max_pages": a.P - int(m.pages)})
    if a.stage == "r0a":
        for r in cr.itertuples():
            if r.mint not in local:
                tasks.append({"key": _key("coin", r.mint, r.t), "kind": "coin", "addr": r.mint,
                              "gte": r.t, "lt": r.t + 1800, "order": "asc", "max_pages": 30})
    for r in cr.itertuples():
        tasks.append({"key": _key("back", r.usr, r.t), "kind": "back", "addr": r.usr,
                      "gte": r.t - WEEK, "lt": r.t + 1, "order": "desc", "max_pages": a.P})
        tasks.append({"key": _key("fwd", r.usr, r.t), "kind": "fwd", "addr": r.usr,
                      "gte": r.t, "lt": r.t + 1800, "order": "asc", "max_pages": a.P})
    # 早买者：同一钱包按锚点从晚到早，已完整覆盖的窗口复用
    back = [{"addr": r.usr, "t": r.t} for r in by.itertuples()]
    if a.stage == "r0a":
        back = sorted(back, key=lambda d: (d["addr"], -d["t"]))
    tasks += [{"key": _key("back", b["addr"], b["t"]), "kind": "back", "addr": b["addr"],
               "gte": b["t"] - WEEK, "lt": b["t"] + 1, "order": "desc", "max_pages": a.P} for b in back]
    seen, uniq = set(), []
    for t in tasks:
        if t["key"] not in seen:
            seen.add(t["key"]); uniq.append(t)
    print("tasks", len(uniq), {k: sum(t["kind"] == k for t in uniq) for k in ("coin", "back", "fwd", "back_ext")},
          "buyer pairs", len(by), "coins", len(coins))

    if a.dry:
        mx = sum(t["max_pages"] for t in uniq) * HL.CREDITS_PER_CALL
        print("dry run: max credits if every walk hits its page cap", mx)
        return
    done = {}
    for m in idx.to_dict("records"):
        if m.get("kind") == "back" and m.get("complete") in (True, "True"):
            done.setdefault(m["addr"], []).append(m)
    rows, reused = [], []
    # 先跑非复用的：第一轮按钱包的最晚锚点，其余在第二轮判断能否复用
    first, rest = [], []
    last_addr = None
    for t in uniq:
        if t["kind"] == "back" and t["addr"] == last_addr:
            rest.append(t)
        else:
            first.append(t)
        if t["kind"] == "back":
            last_addr = t["addr"]
    with ThreadPoolExecutor(a.threads) as ex:
        for res in ex.map(run_task, first):
            if res:
                rows.append(res)
                if res.get("kind") == "back" and res.get("complete"):
                    done.setdefault(res["addr"], []).append(res)
    for t in rest:
        k = covered(done, t["addr"], t["gte"], t["lt"])
        if k:
            reused.append({"key": t["key"], "reused_from": k})
            continue
        res = run_task(t)
        if res:
            rows.append(res)
            if res.get("kind") == "back" and res.get("complete"):
                done.setdefault(res["addr"], []).append(res)
    new = pd.DataFrame(rows)
    if len(new):
        new["stage"] = a.stage
    idx = pd.concat([idx, new], ignore_index=True) if len(idx) else new
    idx.to_csv(IDX, index=False)
    if reused:
        rf = H / "raw" / "helius_reuse.csv"
        old = pd.read_csv(rf) if rf.exists() else pd.DataFrame()
        pd.concat([old, pd.DataFrame(reused).assign(stage=a.stage)], ignore_index=True).to_csv(rf, index=False)
    lat = HL.STATE["lat"]
    print("new calls", HL.STATE["calls"], "credits (10/call)", HL.STATE["credits"], "reused", len(reused),
          "errors", int(new.get("error", pd.Series(dtype=object)).notna().sum()) if len(new) else 0,
          "latency p50/p90", (round(pd.Series(lat).quantile(.5), 2), round(pd.Series(lat).quantile(.9), 2)) if lat else None)


if __name__ == "__main__":
    main()

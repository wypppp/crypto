#!/usr/bin/env python3
"""DQ-39 SOLMEMES S1：三种文本对照（10-06；预登记 S1_预登记.md，读结果前提交于 7e23e1b9）。

运行环境：/home/claude/.venvs/s1（Python 3.12，CPU 版 torch、transformers、catboost；项目代码仍按 Python 3.8 语法写）。
  /home/claude/.venvs/s1/bin/python s1_run.py  → S1_结果.md、raw/s1_results.json
入口过滤：先按 S0 分类定开发 token，价格列读入后立即只保留开发 token 的行，其余行不进入任何计算。
变体：V1 时间＋链上文本；V2 时间＋发布数据的错位文本；V3 时间＋同周打乱的链上文本；V4 只用时间。
"""

import datetime as dt
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch
from catboost import CatBoostClassifier
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    precision_score,
    recall_score,
)
from transformers import AutoModel, AutoTokenizer

import s0_structure as s0
import s0b_misalign as s

H = Path(__file__).resolve().parent
MODEL_DIR = Path(
    "/home/claude/.cache/huggingface/hub/models--answerdotai--ModernBERT-base/snapshots/"
    "8949b909ec900327062f0ebf497f51aef5e6f0c8"
)
SEED = 20261006
REPS = 1000
SPLIT = "2025-04-07"
FMT = "The name of the token is = {}, its symbol = {} and Description = {}"


def week_of(epoch_s):
    import datetime as dt

    d = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=epoch_s)).date()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def roi_adj(r):
    """论文的调整收益，读作投入 1 SOL：卖出 r SOL×(1−2%) − 买入 1 SOL×(1+5%) − 固定 0.00241 − DEX 费 (1+r)·0.3%，除以 1.05。"""
    return (r * 0.98 - 1.05 - 0.00241 - (1 + r) * 0.003) / 1.05


def ipfs_desc():
    out = {}
    p = H / "raw" / "ipfs_meta.jsonl"
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            if r["status"] == "ok":
                out[r["token"]] = r
    return out


def embed(texts, tok, model, bs=32):
    """按词元长度排序后分批（补齐的计算量约降到随机分批的 1/4），算完按原顺序放回；每 20 批打印一次进度。"""
    lens = [len(tok(t, truncation=True, max_length=256)["input_ids"]) for t in texts]
    order = sorted(range(len(texts)), key=lambda k: lens[k])
    out = np.zeros((len(texts), model.config.hidden_size), dtype=np.float32)
    with torch.no_grad():
        for b, i in enumerate(range(0, len(order), bs)):
            ix = order[i : i + bs]
            enc = tok(
                [texts[k] for k in ix],
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            h = model(**enc).last_hidden_state
            m = enc["attention_mask"].unsqueeze(-1).float()
            out[ix] = ((h * m).sum(1) / m.sum(1)).numpy()
            if b % 20 == 0:
                print("embed %d/%d" % (i, len(texts)), flush=True)
    return out


def metrics(y, p, roi, roia, rng):
    pred = (p > 0.5).astype(int)
    sel = pred == 1
    res = {
        "AP": float(average_precision_score(y, p)),
        "acc": float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "trades": int(sel.sum()),
        "roi15_mean": float(roi[sel].mean()) if sel.any() else None,
        "roi_adj_mean": float(roia[sel].mean()) if sel.any() else None,
    }
    if sel.any():
        act = roia[sel].mean()
        ge = 0
        for _ in range(REPS):
            perm = roia[rng.permutation(len(roia))]
            ge += perm[sel].mean() >= act
        res["perm_p"] = ge / REPS
    return res


def main():
    torch.set_num_threads(8)
    m, anc = s.load()
    excl, _ = s0.holdout_names()
    first = {}
    for i, t in enumerate(m["token"]):
        first.setdefault(t, i)
    dev = sorted(t for t in first if s0.classify(anc[t], excl) == "dev")
    # 价格列只从开发 token 的价格文件读（s0_dev_prices.py 用行过滤生成；10-06，GPT 批 1b D）；每个 token 取第一行
    dp = pq.read_table(H / "raw" / "dev_prices.parquet").to_pydict()
    assert set(dp["token"]) <= set(dev), "价格文件里有非开发 token"
    k_of = {}
    for k, t in enumerate(dp["token"]):
        k_of.setdefault(t, k)
    p0, p14, desc_row = dp["average_price_0"], dp["average_price_14"], dp["description"]
    gd_dev = dp["graduated_date"]

    ip = ipfs_desc()
    cl = s.claims(m, anc)
    claimed_desc = {}
    d_all = (
        pq.read_table(s.PARQ, columns=["description"]).column("description").to_pylist()
    )
    for i, (c, j) in enumerate(cl):
        if j and j not in claimed_desc:
            claimed_desc[j] = d_all[i]  # 元数据块里的描述（与名称、代号一起错位到 j）
    del d_all

    recs, n_missing_label = [], 0
    src = Counter()
    agree = Counter()
    n_immature = 0
    split_dt = dt.datetime.fromisoformat(SPLIT)
    for t in dev:
        i = first[t]
        k = k_of[t]
        a, b = p0[k], p14[k]
        if a is None or b is None or not a or a <= 0 or b < 0:
            n_missing_label += 1
            continue
        cr = float(anc[t]["curve_created_t"])
        ca, gd = m["created_at"][i], m["graduated_date"][i]
        # 训练标签必须在测试期开始前成熟：毕业＋15 分钟早于切分日；没有毕业时刻的币，标签时点不明，也不进训练
        if week_of(cr) < SPLIT and (
            gd_dev[k] is None or gd_dev[k] + dt.timedelta(minutes=15) > split_dt
        ):
            n_immature += 1
            continue
        ttg = (gd - ca).total_seconds() if (ca and gd) else float("nan")
        name, sym = anc[t]["c_name"], anc[t]["c_symbol"]
        if t in ip:
            desc = ip[t].get("description") or ""
            src["IPFS"] += 1
            if t in claimed_desc:
                agree[(claimed_desc[t] or "") == desc] += 1
        elif t in claimed_desc:
            desc = claimed_desc[t] or ""
            src["数据里认领到的元数据块"] += 1
        else:
            desc = ""
            src["空"] += 1
        r = b / a
        recs.append(
            dict(
                token=t,
                week=week_of(cr),
                train=week_of(cr) < SPLIT,
                created=cr,
                ttg=ttg,
                y=int(b > a),
                roi=r - 1,
                roia=roi_adj(r),
                t1=FMT.format(name, sym, desc),
                t2=FMT.format(m["name"][i], m["symbol"][i], desc_row[k] or ""),
            )
        )
    # V3：V1 文本在同一创建周内随机打乱
    rng0 = random.Random(SEED)
    by_wk = defaultdict(list)
    for j, r in enumerate(recs):
        by_wk[r["week"]].append(j)
    perm = list(range(len(recs)))
    for wk, ix in sorted(by_wk.items()):
        sh = ix[:]
        rng0.shuffle(sh)
        for a_, b_ in zip(ix, sh):
            perm[a_] = b_

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModel.from_pretrained(str(MODEL_DIR)).eval()
    e1 = embed([r["t1"] for r in recs], tok, model)
    e2 = embed([r["t2"] for r in recs], tok, model)
    e3 = e1[perm]

    tr = np.array([r["train"] for r in recs])
    te = ~tr
    y = np.array([r["y"] for r in recs])
    tm = np.array([[r["ttg"], r["created"]] for r in recs], dtype=float)
    roi = np.array([r["roi"] for r in recs])
    roia = np.array([r["roia"] for r in recs])

    def feats(e):
        if e is None:
            return tm
        pca = PCA(n_components=128, random_state=0).fit(e[tr])
        return np.hstack([pca.transform(e), tm])

    probs, res = {}, {}
    for v, e in (("V1", e1), ("V2", e2), ("V3", e3), ("V4", None)):
        X = feats(e)
        clf = CatBoostClassifier(random_seed=0, verbose=0, thread_count=8)
        clf.fit(X[tr], y[tr])
        probs[v] = clf.predict_proba(X[te])[:, 1]
        res[v] = metrics(
            y[te], probs[v], roi[te], roia[te], np.random.default_rng(SEED)
        )
    # 测试集按 token 自助：AP 差的 95% 区间
    rng = np.random.default_rng(SEED)
    yt = y[te]
    diffs = defaultdict(list)
    for _ in range(REPS):
        b = rng.integers(0, len(yt), len(yt))
        if yt[b].sum() == 0:
            continue
        ap = {v: average_precision_score(yt[b], probs[v][b]) for v in probs}
        for o in ("V2", "V3", "V4"):
            diffs["V1-" + o].append(ap["V1"] - ap[o])
    ci = {}
    for k, xs in diffs.items():
        xs.sort()
        ci[k] = [float(xs[int(0.025 * len(xs))]), float(xs[int(0.975 * len(xs)) - 1])]
    out = dict(
        n_dev=len(dev),
        n_missing_label=n_missing_label,
        n_train_label_immature=n_immature,
        n_train=int(tr.sum()),
        n_test=int(te.sum()),
        pos_rate_train=float(y[tr].mean()),
        pos_rate_test=float(y[te].mean()),
        desc_source=dict(src),
        ipfs_vs_claimed_desc_equal=dict((str(k), v) for k, v in agree.items()),
        model_dir=str(MODEL_DIR),
        model_sha256=hashlib.sha256(
            (MODEL_DIR / "model.safetensors").read_bytes()
        ).hexdigest(),
        results=res,
        ap_diff_ci95=ci,
    )
    (H / "raw" / "s1_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

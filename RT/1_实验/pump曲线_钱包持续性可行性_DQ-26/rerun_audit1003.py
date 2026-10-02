#!/usr/bin/env python3
"""代码审计 10-03 第 3 处：F128（step1.py）的新旧并列重跑。原脚本与原始数据不改。

python rerun_audit1003.py <0|b> → runs/audit1003/<版本>/（step1 的全部输出）
python rerun_audit1003.py compare → runs/audit1003/compare.json
  0：原版原样（核对复现）；
  b：曲线成交的实际费用不再加 buyback_fee。做法：RANK_D_R 的 fee_evt（fee＋creator_fee＋buyback_fee）换成 fee_calc
     （按事件自带费率 fee_basis_points＋creator_fee_basis_points 推算），使 fee_extra＝0。依据：F59（链上逐笔：回购费是协议费的
     一半，交易者实付＝协议费＋创作者费）、官方 IDL（buyback_basis_points ≤10,000，是比例）、本实验 G1b 的 317 笔曲线成交
     残差中位 +0.46%、卖出侧恰为 +0.483%＝协议费一半被多扣一次。
其余输入（BOOK_*、RANK_C、实体表）原样链接。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import step1 as S  # noqa: E402

OUT = H / "runs" / "audit1003"


def run(v: str) -> None:
    runs = OUT / v
    raw = runs / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    shutil.copy(S.RUNS / "entities_R.csv", runs / "entities_R.csv")
    for f in S.RAW.glob("*_R.csv.gz"):
        dst = raw / f.name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        if v == "b" and f.name == "RANK_D_R.csv.gz":
            d = pd.read_csv(f)
            d["fee_evt"] = d["fee_calc"]
            d.to_csv(dst, index=False)
        else:
            dst.symlink_to(f)
    S.RAW, S.RUNS = raw, runs
    S.main()


def compare() -> None:
    res = {}
    old_top = pd.read_csv(H / "runs" / "top50_entities.csv").entity.tolist()
    old_rank = pd.read_csv(H / "runs" / "entity_rank.csv", index_col=0)
    for v in ("0", "b"):
        d = OUT / v
        if not (d / "step1.json").exists():
            continue
        top = pd.read_csv(d / "top50_entities.csv").entity.tolist()
        rank = pd.read_csv(d / "entity_rank.csv", index_col=0)
        j = rank.join(old_rank[["net_attr", "rank"]], rsuffix="_old")
        res[v] = {
            "top50_same_order": top == old_top,
            "top50_overlap": len(set(top) & set(old_top)),
            "top50_new": [e for e in top if e not in old_top],
            "top50_dropped": [e for e in old_top if e not in top],
            "net_attr_sum": float(rank.net_attr.sum()),
            "net_attr_sum_old": float(old_rank.net_attr.sum()),
            "n_positive": int((rank.net_attr > 0).sum()),
            "n_positive_old": int((old_rank.net_attr > 0).sum()),
            "top50_net_attr": float(rank.head(50).net_attr.sum()),
            "top50_net_attr_old": float(old_rank.head(50).net_attr.sum()),
            "max_abs_net_change": float((j.net_attr - j.net_attr_old).abs().max()),
            "step1": json.loads((d / "step1.json").read_text()),
        }
    (OUT / "compare.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    for v, r in res.items():
        print(v, {k: r[k] for k in r if k != "step1"})


if __name__ == "__main__":
    compare() if sys.argv[1] == "compare" else run(sys.argv[1])

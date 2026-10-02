#!/usr/bin/env python3
"""代码审计 10-03：F130（ss.py＋posthoc_split.py）的新旧并列重跑（离线部分）。

python rerun_audit1003.py <0|b|b3> → runs/audit1003/<版本>/runs/（ss.json、ss_cells.csv、posthoc_split.json）
python rerun_audit1003.py compare
  0：原版原样；b3：只修第 3 处（现金用 pay_rate、recv_rate）；b：第 1 处离线部分＋第 3 处（ss_v2_offline.py）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import posthoc_split as PS  # noqa: E402
import ss  # noqa: E402
import ss_v2_offline as V  # noqa: E402

OUT = H / "runs" / "audit1003"


def run(v: str) -> None:
    d = OUT / v
    (d / "runs").mkdir(parents=True, exist_ok=True)
    ss.H = PS.H = d
    if v in ("b", "b3"):
        ss.load = V.load_v2
    if v == "b":
        ss.classify = V.classify_v2
    ss.main()
    PS.main()


def compare() -> None:
    res = {}
    for v in ("原入库", "0", "b3", "b"):
        d = H if v == "原入库" else OUT / v
        if not (d / "runs" / "ss.json").exists():
            continue
        a = json.loads((d / "runs" / "ss.json").read_text())
        p = json.loads((d / "runs" / "posthoc_split.json").read_text())
        res[v] = {
            "classes": {
                k: {x: c.get(x) for x in ("n_cells", "R_full", "R_full_ci95_by_wallet")}
                for k, c in a["classes"].items()
            },
            "reading": a["reading"],
            "posthoc": {
                k: {x: c.get(x) for x in ("n_cells", "R_full", "R_full_ci95_by_wallet")}
                for k, c in p.items()
                if isinstance(c, dict)
            },
        }
    (OUT / "compare.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    )
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    compare() if sys.argv[1] == "compare" else run(sys.argv[1])

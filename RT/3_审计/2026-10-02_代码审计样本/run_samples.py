"""审计方运行：离线用样本重跑两个共用函数，与预期输出逐项比较。

用法（在仓库根目录或任意位置）：python3 run_samples.py
要求：仓库检出在代码审计索引所在的提交；Python 3.8+，numpy、pandas。不联网。
1. perp/：调用 `1_实验/币安新币_上线后做空_DQ-22/perp_replicate.py:event`，归档文件读 perp/archive/，
   S3 目录列表读 perp/s3_listing.json，现货对照关闭（只作描述，不在样本内）；与 perp/expected.csv
   （冻结结果 runs/events.csv 的对应行）比较：状态与爆仓逐字相同，数值差 ≤1e-12。
2. valuation/：调用 `1_实验/pump曲线_检查点动态决策_DQ-8A/analyze_dq8a.py:buy_tok、sell_ratio`，
   与 valuation/expected.csv 比较（相对差 ≤1e-12，NaN 对 NaN）。
"""

import csv
import json
import math
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
RT = H.parent.parent
FIELDS = ("status", "liq", "funding", "n_funding", "r_px", "r")


def close(a: float, b: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= 1e-12 * max(1.0, abs(b))


def run_perp() -> int:
    sys.path.insert(0, str(RT / "1_实验" / "币安新币_上线后做空_DQ-22"))
    import perp_replicate as P

    listing = json.loads((H / "perp" / "s3_listing.json").read_text())

    def no_net(url: str):
        raise RuntimeError(f"样本缺文件，试图联网：{url}")

    P.RAW = H / "perp" / "archive"
    P.get = no_net
    P.s3_keys = lambda prefix: listing[prefix]
    P.D.daily_rows = lambda sym, d1, d2: {}
    bad = 0
    with open(H / "perp" / "expected.csv") as f:
        for e in csv.DictReader(f):
            got = P.event(
                {"base": e["base"], "symbol": e["symbol"], "T0_day": e["T0_day"]}
            )
            for h in (30, 7):
                for fld in FIELDS:
                    k = f"H{h}_{fld}"
                    g, x = got.get(k), e[k]
                    if fld == "status":
                        ok = g == x
                    elif fld == "liq":
                        ok = bool(g) == (x == "True")
                    else:
                        ok = close(float(g), float(x))
                    if not ok:
                        bad += 1
                        print("perp 不一致", e["base"], k, g, x)
    return bad


def run_valuation() -> int:
    sys.path.insert(0, str(RT / "1_实验" / "pump曲线_检查点动态决策_DQ-8A"))
    import analyze_dq8a as A

    bad = 0
    with open(H / "valuation" / "expected.csv") as f:
        for r in csv.DictReader(f):
            v = {
                k: float(r[k]) if r[k] != "" else float("nan") for k in r if k != "mint"
            }
            tok = float(A.buy_tok(v["entry_x"], v["entry_y"], v["entry_fee_bps"]))
            sr = float(
                A.sell_ratio(
                    v["x"],
                    v["y"],
                    v["xr"],
                    v["venue"],
                    v["fee_bps"],
                    tok,
                    v["entry_fee_bps"],
                )
            )
            for name, g, x in (
                ("tok", tok, v["expected_tok"]),
                ("sell_ratio", sr, v["expected_sell_ratio"]),
            ):
                if not close(g, x):
                    bad += 1
                    print("valuation 不一致", r["mint"], r["iv"], name, g, x)
    return bad


if __name__ == "__main__":
    b1, b2 = run_perp(), run_valuation()
    print(f"perp 不一致 {b1} 项；valuation 不一致 {b2} 项")
    sys.exit(1 if b1 or b2 else 0)

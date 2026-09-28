#!/usr/bin/env python3
"""核对单日双口径 S1：A 列须与修正版单日结果逐币相同，B 列（_b）须与旧版单日结果逐币相同。

python check_s1_dual.py raw/s1/S1_SMOKE_20260601_dual.csv.gz → 同名 _check.json
通过后，A/B 两周的双口径结果才可以使用 _b 列；A 列不受本核对影响（与已验证版本同一表达式）。
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
S1 = H / "raw" / "s1"
RULES = [f"ret_{d}_{h}" for d in ("d5", "d30", "d120") for h in ("30s", "2m", "10m", "1h")] + \
        [f"b50_ret_{d}" for d in ("d5", "d30", "d120")]


def same(a, b):
    a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    both_na = a.isna() & b.isna()
    close = np.isclose(a, b, rtol=1e-9, atol=1e-12)
    return int((~(both_na | close)).sum())


def main():
    dual = pd.read_csv(sys.argv[1])
    old = pd.read_csv(S1 / "S1_SMOKE_20260601.csv.gz")          # 旧版（口径 B）
    new = pd.read_csv(S1 / "S1_SMOKE_20260601_corrected.csv.gz")  # 修正版（口径 A）
    out = {"rows": len(dual), "mints_match": sorted(dual.mint) == sorted(new.mint) == sorted(old.mint), "mismatch": {}}
    d = dual.set_index("mint")
    for r in RULES:
        out["mismatch"][r + "_A_vs_corrected"] = same(d[r], new.set_index("mint")[r].reindex(d.index))
        out["mismatch"][r + "_b_vs_old"] = same(d[r + "_b"], old.set_index("mint")[r].reindex(d.index))
    out["pass"] = bool(out["mints_match"] and not any(out["mismatch"].values()))
    Path(sys.argv[1].replace(".csv.gz", "_check.json")).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

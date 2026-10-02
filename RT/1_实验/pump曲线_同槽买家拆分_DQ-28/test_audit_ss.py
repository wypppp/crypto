"""代码审计 10-03 第 1 处（离线部分）的永久测试：PumpSwap 成交没有交易号时，same_tx 为空。
原版 classify 用 astype(bool) 把空值判成 B（同交易）；ss_v2_offline.classify_v2 判为 U（无法判定）。
SQL 一侧（成交链给 PumpSwap 成交带上交易号）在 DQ-31 审计重跑的 build_sn_sql_v2.CHAIN_REPL，测试见那里的 test_audit_sn_v2.py。

python -m pytest test_audit_ss.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss  # noqa: E402
import ss_v2_offline as V  # noqa: E402

CELLS = pd.DataFrame(
    {
        # 格 1：只有独立的 PumpSwap 买入（SQL 里 tx_id 为空 → same_tx 为空）；格 2：真正与创建同交易；格 3：曲线独立买入
        "same_tx": [np.nan, True, False],
        "n_link": [0, 0, 0],
        "tok_out": [0.0, 0.0, 0.0],
        "tok_in": [0.0, 0.0, 0.0],
        "tok_s": [0.0, 0.0, 0.0],
        "tok_b": [100.0, 100.0, 100.0],
    }
)


def test_1_old_reproduces_bug():
    assert ss.classify(CELLS).tolist() == ["B", "B", "I"]


def test_1_fixed_hand_value():
    assert V.classify_v2(CELLS).tolist() == ["U", "B", "I"]

#!/usr/bin/env python3
"""代码审计 10-03 第 1、3 处在 DQ-28（F130）上的离线部分修正。原 ss.py、posthoc_split.py 与原始数据不改。

第 1 处（离线能修的一半）：PumpSwap 成交没有交易号，`same_tx` 为空时原版 astype(bool) 判成 B；v2 判为 U（无法判定，单列），
    再按 L、X、I 顺序判定的格不变。另一半（AMM 买后再卖、AMM 买实际与创建同交易）要等 SQL 带上交易号才能修。
第 3 处：曲线成交的现金不再加 buyback_fee——改用 SS_CELLS 已有的按事件费率推算的现金 pay_rate、recv_rate
    （曲线：sol ± ceiling(sol×(fee_bps＋creator_bps)/1e4)；PumpSwap：用户实付/实收），与 F59、DQ-26 G1b 残差一致。
第 7 处（辅助格只由曲线成交构造）离线修不了，见 SQL v2。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import ss

_load_v1 = ss.load  # 原版，避免被替换后递归


def load_v2() -> pd.DataFrame:
    t = _load_v1()
    t["pay_v1"], t["recv_v1"] = t.pay, t.recv
    t["pay"], t["recv"] = t.pay_rate, t.recv_rate
    return t


def classify_v2(t: pd.DataFrame) -> pd.Series:
    xo = t.tok_out > t.tok_s * 1.001 + 1
    xi = t.tok_in > t.tok_b * 1.001 + 1
    xs = t.tok_s > t.tok_b * 1.001
    st = t.same_tx
    return pd.Series(
        np.select(
            [st.isna(), st.fillna(False).astype(bool), t.n_link > 0, xo | xi | xs],
            ["U", "B", "L", "X"],
            default="I",
        ),
        index=t.index,
    )

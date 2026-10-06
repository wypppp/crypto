#!/usr/bin/env python3
"""DQ-39：只含开发 token 的价格文件（10-06；GPT 批 1b D、总控第二十一轮第四节 D 第 1 条“修读取边界”）。

python s0_dev_prices.py  → raw/dev_prices.parquet（不入库）
顺序：先只读元数据列（token 与链上时间锚）定开发 token；再用 pyarrow 的行过滤条件（token in 开发集合）读价格与成交列，
非开发 token 的行不进入返回的表。S0 第 4 节与 S1 都只读这个文件，不再读原 parquet 的价格列。
同时写入同一行的名称、代号、描述、毕业与创建时刻（元数据），供 S1 的“发布文本”与标签成熟度核对使用。
"""

import pyarrow.parquet as pq

import s0_structure as s0
import s0b_misalign as s

OUT = s.H / "raw" / "dev_prices.parquet"


def dev_tokens():
    m, anc = s.load()  # 只读元数据列与链上锚
    excl, _ = s0.holdout_names()
    return sorted(t for t in set(m["token"]) if s0.classify(anc[t], excl) == "dev")


def main():
    dev = dev_tokens()
    cols = [
        "token",
        "created_at",
        "graduated_date",
        "name",
        "symbol",
        "description",
    ] + s0.PRICE_COLS
    tab = pq.read_table(s.PARQ, columns=cols, filters=[("token", "in", dev)])
    pq.write_table(tab, OUT)
    print("开发 token %d 个，写出 %d 行 → %s" % (len(dev), tab.num_rows, OUT.name))


if __name__ == "__main__":
    main()

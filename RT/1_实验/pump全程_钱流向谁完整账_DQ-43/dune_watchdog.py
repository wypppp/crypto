#!/usr/bin/env python3
"""Dune 执行看门狗（10-14：EDGE 冒烟 12 分钟扣 1,087.6 credits 之后加）。

python dune_watchdog.py <execution_id> <上限 credits>
每 15 秒读一次执行状态里的已扣费用（运行中也有读数）；超过上限就取消。执行结束即退出。
"""

import sys
import time

import run_dune as R
from dune_get import get


def main():
    eid, cap = sys.argv[1], float(sys.argv[2])
    while True:
        st = get(f"/execution/{eid}/status")
        cost = float(st.get("execution_cost_credits") or 0)
        if st.get("state") not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
            print(eid, st.get("state"), cost, flush=True)
            return
        if cost > cap:
            R.call("POST", f"/execution/{eid}/cancel", {})
            print(eid, "费用 %.1f 超过上限 %.0f，已取消" % (cost, cap), flush=True)
            return
        time.sleep(15)


if __name__ == "__main__":
    main()

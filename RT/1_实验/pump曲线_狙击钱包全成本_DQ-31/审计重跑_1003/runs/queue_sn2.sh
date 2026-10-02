#!/bin/bash
# 等 C1 v2 的 run_weeks.py（进程号作为参数）结束后，依次执行三条 SN2 查询
while kill -0 "$1" 2>/dev/null; do sleep 30; done
for q in SN2_TRADES SN2_FEES SN2_TIP; do python3 run_dune.py "$q" "sql/$q.sql" || break; done
echo done

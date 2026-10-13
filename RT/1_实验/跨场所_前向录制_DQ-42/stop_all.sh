#!/bin/sh
# 停掉 DQ-42 与 DQ-34 的四个常驻记录器（10-13 总控第三轮：前向采集暂停）。
# 先发 SIGINT（g_http 有 finally 收尾），等 20 秒；还在的再发 SIGTERM。已录数据保留，存而不读。
# 用法：sh stop_all.sh
H="$(cd "$(dirname "$0")" && pwd)"
D34="$H/../股票上链_周末休市定价_DQ-34"
PIDS=""
for f in "$H/state/g_http.pid" "$H/state/g_chain_mainnet.pid" \
         "$D34/raw/recorder/recorder.pid" "$D34/raw/trades/trades.pid"; do
  [ -f "$f" ] || continue
  p=$(cat "$f")
  if kill -0 "$p" 2>/dev/null; then kill -INT "$p" && PIDS="$PIDS $p" && echo "发 SIGINT：$(basename "$f") pid=$p"; fi
done
for _ in $(seq 1 20); do
  left=""; for p in $PIDS; do kill -0 "$p" 2>/dev/null && left="$left $p"; done
  [ -z "$left" ] && break; sleep 1
done
for p in $left; do kill -TERM "$p" 2>/dev/null && echo "SIGTERM：pid=$p"; done
pkill -f rt_keepalive.sh 2>/dev/null
echo "完成。核对：python3 $H/g_gaps.py（四行都应是“进程不在”）"

#!/bin/sh
# DQ-42 与 DQ-34 的常驻记录器：没在跑的才启动（各程序自带 pid 文件防重复）。
# 用法：sh start_all.sh    电脑重启或 WSL 重开之后运行一次。
H="$(cd "$(dirname "$0")" && pwd)"
PY=/home/ancillary/.venv/bin/python
D34="$H/../股票上链_周末休市定价_DQ-34"
mkdir -p "$H/logs"
alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
start() { # $1 pid 文件  $2 日志  其余：命令
  pidf=$1; log=$2; shift 2
  if alive "$pidf"; then echo "在跑：$(basename "$pidf")"; else (cd "$(dirname "$2")" && setsid nohup "$@" >>"$log" 2>&1 &) ; echo "启动：$(basename "$2")"; fi
}
start "$H/state/g_http.pid" "$H/logs/g_http.out" "$PY" "$H/g_http.py"
start "$H/state/g_chain_mainnet.pid" "$H/logs/g_chain.out" "$PY" "$H/g_chain.py" --endpoint mainnet
start "$D34/raw/recorder/recorder.pid" "$D34/raw/recorder_stdout.log" "$PY" "$D34/hl_recorder.py"
start "$D34/raw/trades/trades.pid" "$D34/raw/trades_stdout.log" "$PY" "$D34/hl_trades_ws.py"

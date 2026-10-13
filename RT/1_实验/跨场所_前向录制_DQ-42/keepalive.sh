#!/bin/sh
# DQ-42 常驻守护（10-13，总控 10-13 第 2 条）。由 Windows 计划任务在登录时用 wsl.exe 拉起，并一直挂着：
# - wsl.exe 不退出，WSL 实例就不会因为“没有 WSL 进程”而被关掉（systemd 服务不保活，见微软 WSL 文档）；
# - 每 5 分钟运行一次 start_all.sh：没在跑的记录器重新拉起，在跑的不动。
# 同一时刻只允许一个守护（flock）。日志：logs/keepalive.out。
H="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
mkdir -p "$H/logs"
exec 9>/tmp/rt_dq42_keepalive.lock
flock -n 9 || { echo "$(date -u +%FT%TZ) 已有守护在跑，退出" >>"$H/logs/keepalive.out"; exit 0; }
echo "$(date -u +%FT%TZ) 守护启动 pid=$$" >>"$H/logs/keepalive.out"
while true; do
  sh "$H/start_all.sh" 2>&1 | grep 启动 | sed "s/^/$(date -u +%FT%TZ) /" >>"$H/logs/keepalive.out"
  sleep 300
done

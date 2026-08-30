#!/bin/bash
# 等到 21:00 ET 执行 observe。只读，无下单代码。随时可 kill。
while true; do
  H=$(TZ=America/New_York date +%H); M=$(TZ=America/New_York date +%M)
  CUR=$((10#$H*60 + 10#$M))
  if [ $CUR -ge 1260 ]; then break; fi          # 1260 = 21:00 ET
  if [ $CUR -gt 1350 ]; then echo "已过 22:30 ET，放弃本窗口"; exit 1; fi
  sleep 20
done
echo "=== $(TZ=America/New_York date '+%Y-%m-%d %H:%M %Z') 触发 observe ==="
python3 -u collect.py observe

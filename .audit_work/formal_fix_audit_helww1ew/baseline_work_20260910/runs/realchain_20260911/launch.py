"""从 /home/ancillary/.env 读凭据，**只经环境变量**交给子进程。
凭据不出现在命令行参数、进程列表、日志或本脚本输出里。
用法：python3 launch.py -- <要执行的命令...>
"""
import os, sys, subprocess
from pathlib import Path

ENV = Path("/home/ancillary/.env")
vals = {}
for line in ENV.read_text(encoding="utf-8").splitlines():
    if ":" not in line:
        continue
    k, v = line.split(":", 1)
    vals[k.strip().lower()] = v.strip()
url = next((v for k, v in vals.items() if "endpoint" in k), None)
key = next((v for k, v in vals.items() if "etherscan" in k), None)
if not url or not key:
    sys.exit("launch: .env 里找不到 alchemy endpoint URL 或 Etherscan key")
if not url.startswith("https://"):
    sys.exit("launch: RPC URL 不是 https")
env = dict(os.environ, ETH_RPC_URL=url, ETHERSCAN_API_KEY=key)
cmd = sys.argv[sys.argv.index("--") + 1:]
sys.exit(subprocess.call(cmd, env=env))

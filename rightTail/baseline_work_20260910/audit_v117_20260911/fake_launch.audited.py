#!/usr/bin/env python3
"""驱动测试用的 launch 替身。**不读 .env、不设真实凭据、不发任何网络请求。**

与真 launch 同一调用约定：`fake_launch.py -- python3 pilot_measure.py measure ...`。
按 `--out` 的文件名取运行标签，查环境变量 RT_FAKE_PLAN（JSON：标签 → 动作）：

  "measure"        用受控假链跑真的 pilot_measure CLI（默认）
  "flaky"          同上，但候选 1 在出场校验取代码时遇到一次传输错误 ⇒ 该次运行退出 1
  "exit:N"         不测量，直接以 N 退出（模拟前置失败 / 崩溃）
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

W = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[argv.index("--out") + 1]
tag = Path(out).name[:-len(".json")]
action = json.loads(os.environ.get("RT_FAKE_PLAN", "{}")).get(tag, "measure")
print(f"fake_launch: tag={tag} action={action}", flush=True)
if action.startswith("exit:"):
    print("CONTROLLED_FAILURE", file=sys.stderr)
    sys.exit(int(action.split(":", 1)[1]))

sys.path.insert(0, str(W))
os.chdir(W)
import evidence as E  # noqa: E402
import pilot_measure as P  # noqa: E402
from fake_chain import FakeRpc  # noqa: E402

PAIR, TOKEN, MINT = "0x" + "ab" * 20, "0x" + "cd" * 20, 24140010
CFG = dict(head=25900000, genesis_ts=0, entry_block=MINT + 1, pair=PAIR, token=TOKEN,
           chain_id=1, received=10 ** 18, cash=10 ** 15, slot=0,
           supply=lambda b: 0 if int(b, 16) < MINT else 10 ** 6)


def scan(*a, **k):
    return dict(status="1", result=[dict(address=PAIR, blockNumber=hex(MINT),
                                         topics=[P.MINT_TOPIC, "0x" + "0" * 64],
                                         data="0x" + "1" * 128,
                                         transactionHash="0x" + "2" * 64, logIndex="0x0")])


patches = [patch.object(P.V, "RPC", side_effect=lambda *a, **k: FakeRpc(CFG)),
           patch.object(P, "etherscan", side_effect=scan)]
if action == "flaky":
    _mark, _req, fired = E.RpcTap.mark, FakeRpc.request, []

    def mark(self, *a, **k):
        r = _mark(self, *a, **k)
        self.rpc._fs, self.rpc._fc = self.stage, self.candidate
        return r

    def request(self, method, params):
        if (not fired and getattr(self, "_fc", None) == 1
                and getattr(self, "_fs", None) == "state_validation_exit"):
            fired.append(1)
            self.records.append({"method": method, "params": params,
                                 "error": {"kind": "transport", "message": "controlled"}})
            raise P.V.RpcFailure("transport", "controlled TLS EOF")
        return _req(self, method, params)
    patches += [patch.object(E.RpcTap, "mark", mark), patch.object(FakeRpc, "request", request)]

os.environ["ETH_RPC_URL"] = "https://x.invalid/test/FAKE_ONLY_KEY"
os.environ["ETHERSCAN_API_KEY"] = "FAKE_ONLY_SCAN_KEY"
sys.argv = argv[1:]
for p_ in patches:
    p_.start()
P.main()

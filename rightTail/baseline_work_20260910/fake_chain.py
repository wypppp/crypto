#!/usr/bin/env python3
"""受控假链：让 measure() 的完整流程可以在无网络下跑通，并按需注入失败。

只实现 pilot_measure 真正用到的调用；任何未预期的调用都抛错，
避免"因为没实现而恰好没触发"这种假通过。
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "baseline_20260909"))
import verify_capabilities as V

W = lambda x: f"{x:064x}"
def probe_ret(stage, b0, b1, e0, e1, reason=b""):
    body = "".join(W(x) for x in (stage, b0, b1, e0, e1, 192))
    body += W(len(reason)) + (reason.hex() + "00" * ((32 - len(reason) % 32) % 32)
                              if reason else "")
    return "0x" + body

def addr_word(a):
    return "0x" + "0" * 24 + a.lower().replace("0x", "")


class FakeRpc:
    """faults: 可注入的失败开关集合。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.faults = set(cfg.get("faults", ()))
        self.records = []
        self.block_hits = {}          # 同一块被请求的次数 —— 重组按次数模拟

    # —— 基础 ——
    def _block(self, n):
        ts = self.cfg["genesis_ts"] + n * 12
        h = "0x" + f"{n:064x}"
        parent = "0x" + f"{n-1:064x}"
        if "parent_link_broken" in self.faults and n == self.cfg["entry_block"]:
            parent = "0x" + "ff" * 32
        # fresh=True 只是绕过本地缓存，RPC 请求本身完全一样；
        # 真实重组表现为【同一块的后续请求返回不同 hash】，按次数模拟才忠实。
        self.block_hits[n] = self.block_hits.get(n, 0) + 1
        if "reorg_on_fresh" in self.faults and self.block_hits[n] > 1:
            h = "0x" + "ee" * 32
        # 跨进程的重组：该块从第一次请求起就是另一个 hash
        if "finalized_reorg" in self.faults:
            h = "0x" + "dd" * 32
        return {"number": hex(n), "hash": h, "parentHash": parent,
                "timestamp": hex(ts), "baseFeePerGas": hex(10 ** 9)}

    def request(self, method, params):
        self.records.append({"method": method, "params": params})
        if method == "eth_chainId":
            return hex(self.cfg.get("chain_id", 1))
        if method == "eth_getBlockByNumber":
            tag = params[0]
            n = self.cfg["head"] if tag == "finalized" else int(tag, 16)
            return self._block(n)
        if method == "eth_getCode":
            a = params[0].lower()
            if a in (V.WALLET, V.CALLER):
                return "0x60" if "wallet_dirty" in self.faults else "0x"
            return "0x6001"                       # 协议合约都有代码
        if method == "eth_getBalance":
            return hex(0)
        raise AssertionError(f"未预期的 RPC 方法: {method}")

    def call(self, to, data, block, overrides=None):
        # 真 RPC.call 收 int 后自己 hex()，这里对齐同一语义
        blk_hex = block if isinstance(block, str) else hex(block)
        self.records.append({"method": "eth_call", "params": [to, data[:10], blk_hex]})
        block = blk_hex
        sel = data[2:10]           # V.selector() 不带 0x 前缀
        cfg, pair, token = self.cfg, self.cfg["pair"], self.cfg["token"]
        if sel == V.selector("totalSupply()"):
            return "0x" + W(cfg["supply"](block))
        if sel == V.selector("token0()"):
            return addr_word(V.WETH if not self.faults & {"bad_sides"} else "0x" + "99" * 20)
        if sel == V.selector("token1()"):
            return addr_word(token)
        if sel == V.selector("getPair(address,address)"):
            return addr_word("0x" + "77" * 20 if "bad_getpair" in self.faults else pair)
        if sel == V.selector("factory()"):
            return addr_word(V.FACTORY)
        if sel == V.selector("WETH()"):
            return addr_word(V.WETH)
        if sel == V.selector("balanceOf(address)"):
            ov = (overrides or {}).get(token, {}).get("stateDiff", {})
            who = V.WALLET if data[10:].endswith(V.WALLET[-8:]) else None
            for holder in (V.WALLET, V.CALLER):
                if data[10:].lower().endswith(holder[2:].lower()):
                    who = holder
                    break
            key = V.mapping_key(who or V.WALLET, cfg.get("slot", 0))
            if key in ov:
                return "0x" + ov[key][2:]
            return "0x" + W(0)
        if to.lower() in (V.WALLET, V.CALLER):    # Probe.buy / Probe.sell
            if sel == V.selector("buy(address,address,uint256,uint256)"):
                return probe_ret(0, 0, cfg["received"], 10**20, 10**20 - V.AMOUNT)
            if "sell_reverts" in self.faults:
                # identity_probe 由 CALLER 发起；可单独设定它的结果
                if to.lower() == V.CALLER and "identity_ok" in self.faults:
                    return probe_ret(0, cfg["received"], 0, 10**20, 10**20 + cfg["cash"])
                return probe_ret(20, cfg["received"], cfg["received"],
                                 10**20, 10**20, bytes.fromhex("08c379a0"))
            return probe_ret(0, cfg["received"], 0, 10**20, 10**20 + cfg["cash"])
        raise AssertionError(f"未预期的 eth_call selector: {sel}")

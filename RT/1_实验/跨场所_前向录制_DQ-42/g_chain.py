#!/usr/bin/env python3
"""DQ-42 前向录制：链上事件到达时刻（G v2 §2.2，10-13）。只收不发。

python g_chain.py --endpoint mainnet   常驻：订阅 pump 曲线程序与 PumpSwap 程序的日志（logsSubscribe，processed）

每个通知记一行 kind=event：程序、交易签名、slot、是否失败、本机收到时刻（UTC 纳秒与单调钟纳秒）。
来源端点见文件路径 raw/chain/<端点>/；订阅号记在 conn 行（每秒约 500 行，所以事件行只留必要字段）。
不存日志正文（只要到达时刻；链上内容以后可从 Dune 补）。
连接事件记 kind=conn：open、subscribed、rpc_error、error、close、stall、wait。断线照实记录，不补造。
依赖 websocket-client（项目 .venv 里有）。不构造、不签名、不发送任何交易。
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time

from g_store import RAW, SCHEMA, DayWriter, Heartbeat, now, write_pid

PROGRAMS = {
    "pump": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pumpswap": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
}
ENDPOINTS = {
    "mainnet": "wss://api.mainnet-beta.solana.com",
    "publicnode": "wss://solana-rpc.publicnode.com",
}
STALL_S = 60  # 连上之后这么久没有任何消息，就断开重连并记 stall


def sub_request(req_id: int, program: str, commitment: str = "processed") -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "logsSubscribe",
            "params": [{"mentions": [program]}, {"commitment": commitment}],
        }
    )


_FAST = re.compile(
    r'^\{"jsonrpc":"2\.0","method":"logsNotification","params":\{"result":\{"context":\{"slot":(\d+)\},'
    r'"value":\{"signature":"([1-9A-HJ-NP-Za-km-z]+)","err":(null|.)'
)
_SUB = re.compile(r'"subscription":(\d+)\}\}$')


def parse(msg: str) -> dict:
    """把一条消息归成 event / subscribed / rpc_error / other。纯函数，有测试。
    通知走快路径：只用正则取 slot、签名、err 是否为 null、订阅号（每秒约 500 条，完整解析太慢）；
    快路径对不上就整条解析。日志正文里的引号都被转义，结构层的键不会被正文冒充。"""
    m = _FAST.match(msg)
    if m:
        sub = _SUB.search(msg)
        if sub:
            return {
                "type": "event",
                "sub": int(sub.group(1)),
                "sig": m.group(2),
                "slot": int(m.group(1)),
                "err": m.group(3) != "null",
            }
    try:
        d = json.loads(msg)
    except ValueError:
        return {"type": "other", "why": "json"}
    if d.get("method") == "logsNotification":
        p = d.get("params") or {}
        r = p.get("result") or {}
        v = r.get("value") or {}
        ctx = r.get("context") or {}
        return {
            "type": "event",
            "sub": p.get("subscription"),
            "sig": v.get("signature"),
            "slot": ctx.get("slot"),
            "err": v.get("err") is not None,
        }
    if "id" in d and "result" in d and isinstance(d["result"], int):
        return {"type": "subscribed", "req_id": d["id"], "sub": d["result"]}
    if "error" in d:
        e = d["error"] or {}
        return {
            "type": "rpc_error",
            "req_id": d.get("id"),
            "code": e.get("code"),
            "message": str(e.get("message"))[:200],
        }
    return {"type": "other", "why": "shape"}


def wait_s(fails: int, cap: float = 60.0) -> float:
    """连续第 fails 次失败后重连前等待：1、2、4 … 秒，封顶 cap。"""
    return min(2 ** max(fails - 1, 0), cap)


class ChainRecorder:
    def __init__(
        self, label: str, url: str, programs: dict, root=RAW, flush_every_s: float = 5.0
    ):
        self.label, self.url, self.programs = label, url, programs
        self.w = DayWriter(root, f"chain/{label}")
        self.req2prog = {i + 1: name for i, name in enumerate(programs)}
        self.sub2prog: dict = {}
        self.n_event = 0
        self.n_conn = 0
        self.n_err = 0
        self.last_msg_mono = 0.0
        self.connected = False
        self.ws = None
        self.flush_every = flush_every_s
        self.stop = threading.Event()

    def conn(self, what: str, **kw) -> None:
        u, m = now()
        self.w.write(
            {
                "v": SCHEMA,
                "kind": "conn",
                "ep": self.label,
                "what": what,
                "t_utc_ns": u,
                "t_mono_ns": m,
                **kw,
            },
            u,
        )
        self.w.flush()

    # websocket-client 回调
    def on_open(self, ws) -> None:
        self.connected = True
        self.n_conn += 1
        self.last_msg_mono = time.monotonic()
        self.sub2prog = {}
        self.conn("open")
        for rid, name in self.req2prog.items():
            ws.send(sub_request(rid, self.programs[name]))

    def on_message(self, ws, msg) -> None:
        if isinstance(msg, bytes):  # skip_utf8_validation=True 时收到的是字节
            msg = msg.decode("utf-8", "replace")
        u, m = now()
        self.last_msg_mono = time.monotonic()
        p = parse(msg)
        if p["type"] == "event":
            self.n_event += 1
            self.w.write(
                {
                    "v": SCHEMA,
                    "kind": "event",
                    "prog": self.sub2prog.get(p["sub"]),
                    "sig": p["sig"],
                    "slot": p["slot"],
                    "err": p["err"],
                    "t_utc_ns": u,
                    "t_mono_ns": m,
                },
                u,
            )
        elif p["type"] == "subscribed":
            self.sub2prog[p["sub"]] = self.req2prog.get(p["req_id"])
            self.conn("subscribed", prog=self.req2prog.get(p["req_id"]), sub=p["sub"])
        elif p["type"] == "rpc_error":
            self.n_err += 1
            self.conn(
                "rpc_error", code=p["code"], message=p["message"], req_id=p["req_id"]
            )

    def on_error(self, ws, e) -> None:
        self.n_err += 1
        self.conn("error", err=repr(e)[:300])

    def on_close(self, ws, code=None, reason=None) -> None:
        self.connected = False
        self.w.flush()
        self.conn("close", code=code, reason=str(reason)[:200] if reason else None)

    def watchdog(self) -> None:
        """定时落盘；连上后 STALL_S 秒无消息就断开（run_forever 返回后重连）。"""
        while not self.stop.is_set():
            self.stop.wait(self.flush_every)
            self.w.flush()
            if (
                self.connected
                and time.monotonic() - self.last_msg_mono > STALL_S
                and self.ws is not None
            ):
                self.conn(
                    "stall", silent_s=round(time.monotonic() - self.last_msg_mono, 1)
                )
                try:
                    self.ws.close()
                except Exception:
                    pass

    def run(self) -> None:
        import websocket  # websocket-client

        threading.Thread(target=self.watchdog, daemon=True).start()
        fails = 0
        while not self.stop.is_set():
            n0 = self.n_event
            self.ws = websocket.WebSocketApp(
                self.url,
                header={
                    "User-Agent": "RT-DQ42-forward-recorder/1 (research; read-only)"
                },
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
            )
            try:
                self.ws.run_forever(
                    ping_interval=30, ping_timeout=10, skip_utf8_validation=True
                )
            except Exception as e:
                self.on_error(None, e)
            self.connected = False
            # 这次连接收到过事件，说明是对端断开而不是连不上：退避清零，约 1 秒后重连
            fails = 1 if self.n_event > n0 else fails + 1
            w = wait_s(fails)
            self.conn("wait", seconds=w, fails=fails)
            self.stop.wait(w)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="mainnet", choices=sorted(ENDPOINTS))
    a = ap.parse_args()
    write_pid(f"g_chain_{a.endpoint}")
    rec = ChainRecorder(a.endpoint, ENDPOINTS[a.endpoint], PROGRAMS)
    hb = Heartbeat(
        f"g_chain_{a.endpoint}",
        lambda: {
            "events": rec.n_event,
            "connects": rec.n_conn,
            "errors": rec.n_err,
            "connected": rec.connected,
        },
    )
    threading.Thread(target=rec.run, daemon=True).start()
    hb.tick(force=True)
    while True:
        hb.tick()
        time.sleep(5)


if __name__ == "__main__":
    main()

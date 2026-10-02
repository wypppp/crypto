"""HIP-3 全部市场的逐笔成交（含买卖双方地址）前向记录器：只存不分析。

用途：写卡前三问之③“谁付钱”——周末成交的对手方构成。`recentTrades` 只给最近 10 笔，
轮询抓不全，所以订阅公开 websocket 的 `trades` 频道（无密钥、只读）。
只用标准库（websocket 帧自己实现），可直接搬到服务器。每个 UTC 日一个 JSONL，
旧日压缩；每天换日时重连一次以刷新市场列表；单实例（pid 文件）；
90 秒收不到任何消息（含 pong）即重连，主机睡眠醒来后会自动恢复。
订阅时服务器会先推一批最近成交，分析时按 (coin, tid) 去重。
"""

import base64
import datetime as dt
import gzip
import json
import os
import shutil
import socket
import ssl
import struct
import sys
import time
import urllib.request
from pathlib import Path

HOST = "api.hyperliquid.xyz"
OUT = Path(__file__).resolve().parent / "raw" / "trades"
UTC = dt.timezone.utc


def info(body: dict) -> object:
    req = urllib.request.Request(
        f"https://{HOST}/info",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "rt-dq34-trades"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def hip3_coins() -> list:
    coins = []
    for d in info({"type": "perpDexs"}):
        if not d:
            continue
        meta = info({"type": "meta", "dex": d["name"]})
        coins += [u["name"] for u in meta["universe"] if not u.get("isDelisted")]
    return coins


def log(msg: str) -> None:
    with open(OUT / "trades.log", "a") as f:
        f.write(dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + " " + msg + "\n")


def compress_old(today: str) -> None:
    for p in OUT.glob("*.jsonl"):
        if p.stem < today:
            with open(p, "rb") as src:
                with gzip.open(p.with_suffix(".jsonl.gz"), "wb") as dst:
                    shutil.copyfileobj(src, dst)
            p.unlink()


class WS:
    def __init__(self) -> None:
        raw = socket.create_connection((HOST, 443), timeout=30)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(
            (
                f"GET /ws HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\nUser-Agent: rt-dq34-trades\r\n\r\n"
            ).encode()
        )
        self.buf, self.parts = b"", []
        while b"\r\n\r\n" not in self.buf:
            self._fill()
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head[:200])
        self.s.settimeout(10)

    def _fill(self) -> None:
        chunk = self.s.recv(65536)
        if not chunk:
            raise EOFError("closed")
        self.buf += chunk

    def _frame(self) -> "tuple | None":
        """从缓冲区解析一帧；不完整时返回 None 且不消耗缓冲区（超时不会弄乱帧边界）。"""
        b = self.buf
        if len(b) < 2:
            return None
        n, i = b[1] & 0x7F, 2
        if n == 126:
            if len(b) < 4:
                return None
            n, i = struct.unpack(">H", b[2:4])[0], 4
        elif n == 127:
            if len(b) < 10:
                return None
            n, i = struct.unpack(">Q", b[2:10])[0], 10
        mask = None
        if b[1] & 0x80:
            if len(b) < i + 4:
                return None
            mask, i = b[i : i + 4], i + 4
        if len(b) < i + n:
            return None
        data, self.buf = b[i : i + n], b[i + n :]
        if mask:
            data = bytes(x ^ mask[j % 4] for j, x in enumerate(data))
        return b[0], data

    def send(self, payload: bytes, op: int = 0x1) -> None:
        n = len(payload)
        hdr = bytes([0x80 | op])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.s.sendall(hdr + mask + body)

    def recv(self) -> bytes:
        """返回一条完整的文本消息；超时抛 socket.timeout（已收到的部分保留）。"""
        while True:
            fr = self._frame()
            if fr is None:
                self._fill()
                continue
            b0, data = fr
            op = b0 & 0x0F
            if op == 0x9:
                self.send(data, 0xA)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise EOFError("server close")
            self.parts.append(data)
            if b0 & 0x80:
                msg, self.parts = b"".join(self.parts), []
                return msg

    def close(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass


def run_day(day: str) -> None:
    """连接、订阅全部 HIP-3 市场，记录到 UTC 日期变化或连接失效为止。"""
    coins = hip3_coins()
    ws = WS()
    try:
        for c in coins:
            ws.send(
                json.dumps(
                    {
                        "method": "subscribe",
                        "subscription": {"type": "trades", "coin": c},
                    }
                ).encode()
            )
        log(f"subscribed {len(coins)}")
        n_msg = n_tr = 0
        last_rx = last_ping = last_flush = time.time()
        with open(OUT / f"{day}.jsonl", "a") as f:
            while dt.datetime.now(UTC).strftime("%Y-%m-%d") == day:
                now = time.time()
                if now - last_ping > 25:
                    ws.send(b'{"method":"ping"}')
                    last_ping = now
                if now - last_rx > 90:
                    raise TimeoutError("no message for 90s")
                if now - last_flush > 30:
                    f.flush()
                    (OUT / "heartbeat.txt").write_text(
                        f"{dt.datetime.now(UTC).isoformat()} msgs={n_msg} trades={n_tr}\n"
                    )
                    last_flush = now
                try:
                    msg = ws.recv()
                except socket.timeout:
                    continue
                last_rx = time.time()
                d = json.loads(msg)
                if d.get("channel") != "trades":
                    continue
                n_msg += 1
                n_tr += len(d["data"])
                f.write(
                    json.dumps(
                        {"t_recv_ms": int(last_rx * 1000), "data": d["data"]},
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        log(f"day end msgs={n_msg} trades={n_tr}")
    finally:
        ws.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pid = OUT / "trades.pid"
    if pid.exists():
        try:
            os.kill(int(pid.read_text()), 0)
            sys.exit("already running")
        except (ProcessLookupError, ValueError):
            pass
    pid.write_text(str(os.getpid()))
    log("start")
    backoff = 5
    while True:
        day = dt.datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            compress_old(day)
            run_day(day)
            backoff = 5
        except Exception as e:  # noqa: BLE001 —— 记录后重连
            log(f"error {e!r}"[:300])
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    main()

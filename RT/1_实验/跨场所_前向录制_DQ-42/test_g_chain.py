"""g_chain 的构造消息测试（10-13）：消息分类、订阅号映射、事件行字段、重连退避。不联网。"""

import gzip
import json

import g_chain as C


def test_sub_request_shape():
    d = json.loads(C.sub_request(1, "P"))
    assert d["method"] == "logsSubscribe"
    assert d["params"] == [{"mentions": ["P"]}, {"commitment": "processed"}]


def test_parse_kinds():
    n = {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "subscription": 7,
            "result": {
                "context": {"slot": 99},
                "value": {"signature": "S", "err": None, "logs": ["x"]},
            },
        },
    }
    assert C.parse(json.dumps(n)) == {
        "type": "event",
        "sub": 7,
        "sig": "S",
        "slot": 99,
        "err": False,
    }
    n["params"]["result"]["value"]["err"] = {"InstructionError": [0, "x"]}
    assert C.parse(json.dumps(n))["err"] is True
    assert C.parse('{"jsonrpc":"2.0","id":2,"result":41}') == {
        "type": "subscribed",
        "req_id": 2,
        "sub": 41,
    }
    e = C.parse(
        '{"jsonrpc":"2.0","id":1,"error":{"code":-32005,"message":"rate limited"}}'
    )
    assert e["type"] == "rpc_error" and e["code"] == -32005
    assert C.parse("not json")["type"] == "other"


def test_wait_hand():
    assert [C.wait_s(k) for k in (1, 2, 3, 4, 7, 8)] == [1, 2, 4, 8, 60, 60]


class FakeWS:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(json.loads(m))


def test_recorder_maps_subscriptions_and_writes_events(tmp_path):
    r = C.ChainRecorder("t", "wss://x", {"pump": "P1", "pumpswap": "P2"}, root=tmp_path)
    ws = FakeWS()
    r.on_open(ws)
    assert [m["params"][0]["mentions"][0] for m in ws.sent] == ["P1", "P2"]
    r.on_message(ws, '{"jsonrpc":"2.0","id":2,"result":11}')
    r.on_message(
        ws,
        json.dumps(
            {
                "method": "logsNotification",
                "params": {
                    "subscription": 11,
                    "result": {
                        "context": {"slot": 5},
                        "value": {"signature": "S1", "err": None},
                    },
                },
            }
        ),
    )
    r.on_close(ws, 1006, "gone")
    rows = [
        json.loads(x)
        for p in (tmp_path / "chain" / "t").glob("*.jsonl.gz")
        for x in gzip.open(p, "rt").read().splitlines()
    ]
    ev = [x for x in rows if x["kind"] == "event"]
    assert (
        len(ev) == 1
        and ev[0]["prog"] == "pumpswap"
        and ev[0]["sig"] == "S1"
        and ev[0]["slot"] == 5
    )
    assert (
        "logs" not in ev[0]
        and "sub" not in ev[0]
        and ev[0]["t_utc_ns"] > 0
        and ev[0]["t_mono_ns"] > 0
    )
    assert [x["what"] for x in rows if x["kind"] == "conn"] == [
        "open",
        "subscribed",
        "close",
    ]
    assert r.n_event == 1 and r.n_conn == 1 and r.connected is False


def test_fast_path_matches_full_parse():
    base = {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 99},
                "value": {
                    "signature": "5Kx9Ab",
                    "err": None,
                    "logs": ['Program log: "signature":"FAKE"', "x"],
                },
            },
            "subscription": 7,
        },
    }
    msg = json.dumps(base, separators=(",", ":"))
    assert C._FAST.match(msg)  # 走快路径
    assert C.parse(msg) == {
        "type": "event",
        "sub": 7,
        "sig": "5Kx9Ab",
        "slot": 99,
        "err": False,
    }
    base["params"]["result"]["value"]["err"] = {"InstructionError": [0, {"Custom": 1}]}
    msg2 = json.dumps(base, separators=(",", ":"))
    assert C.parse(msg2)["err"] is True and C.parse(msg2)["sig"] == "5Kx9Ab"
    spaced = json.dumps(base)  # 带空格：快路径对不上，整条解析，结果一样
    assert not C._FAST.match(spaced) and C.parse(spaced)["sig"] == "5Kx9Ab"


def test_bytes_message(tmp_path):
    r = C.ChainRecorder("t", "wss://x", {"pump": "P1"}, root=tmp_path)
    r.on_message(None, b'{"jsonrpc":"2.0","id":1,"result":5}')
    r.on_message(
        None,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "context": {"slot": 3},
                        "value": {"signature": "S", "err": None},
                    },
                    "subscription": 5,
                },
            },
            separators=(",", ":"),
        ).encode(),
    )
    assert r.n_event == 1 and r.n_err == 0


def test_window_schedule_hand():
    import hashlib

    h = 1791856800  # 2026-10-13 02:00 UTC
    off = (
        hashlib.sha256(b"RT-DQ42-chain-sample-v1|2026-10-13T02:00:00Z").digest()[0] % 51
    )
    assert C.window_for_hour(h) == (h + off * 60, h + off * 60 + 600)
    s, e = C.window_for_hour(h)
    assert C.current_window(h) == (s, e) or h < s
    assert C.current_window(e) == C.window_for_hour(
        h + 3600
    )  # 本小时的窗过了，给下一小时
    assert 0 <= off <= 50

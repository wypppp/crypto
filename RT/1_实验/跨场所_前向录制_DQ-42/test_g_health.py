"""g_health 的手算预期值测试（10-13）：成功率、最大缺口、白名单过滤、清单篡改。构造数据，不读真实录制。"""

import json

import g_health as G
import g_store as S

NS = 1_000_000_000
T0 = 1760313600 * NS  # 构造时刻 2025-10-13 00:00 UTC


def req(t, status, fp="f1"):
    return {
        "kind": "request",
        "src": "dexs_a",
        "tag": None,
        "t_req_utc_ns": t,
        "status": status,
        "struct_fp": fp,
        "body": "这里是标题正文",
    }


def build(tmp_path):
    raw = tmp_path / "raw"
    w = S.DayWriter(raw, "http/dexs_a")
    # 10 次请求，每 60 秒一次；第 5 次失败（503）
    for i in range(10):
        w.write(
            req(T0 + i * 60 * NS, 503 if i == 4 else 200, "f1" if i < 8 else "f2"),
            T0 + i * 60 * NS,
        )
    w.flush()
    c = S.DayWriter(raw, "chain/mainnet")
    for t in (10, 20, 200):
        c.write(
            {"kind": "event", "t_utc_ns": T0 + t * NS, "err": t == 20, "sig": "SIG"},
            T0 + t * NS,
        )
    c.write({"kind": "conn", "what": "open", "t_utc_ns": T0 + 5 * NS}, T0 + 5 * NS)
    c.flush()
    hb = S.DayWriter(raw, "heartbeat/g_http")
    for t in (0, 60, 120, 180, 240, 300, 360, 420, 480, 540):
        hb.write({"t_utc_ns": T0 + t * NS}, T0 + t * NS)
    hb.flush()
    return raw


def test_report_hand(tmp_path):
    raw = build(tmp_path)
    cfg = tmp_path / "sources.json"
    cfg.write_text(json.dumps({"sources": [{"key": "dexs_a", "every_s": 60}]}))
    r = G.report(
        hours=600 / 3600, raw=raw, mdir=tmp_path / "m", config=cfg, now_ns=T0 + 600 * NS
    )
    h = r["http"]["dexs_a"]
    assert (h["requests"], h["ok"], h["fail"]) == (10, 9, 1)
    assert h["success_rate"] == 0.9
    assert h["status_counts"] == {"200": 9, "503": 1}
    assert h["max_gap_s"] == 120.0  # 第 4 次（180 秒）到第 6 次（300 秒）
    assert h["struct_fps"] == 2 and h["result"] == "pass"
    ch = r["chain"]["mainnet"]
    assert (ch["events"], ch["connects"]) == (3, 1) and "events_err" not in ch
    assert ch["max_silent_s"] == 400.0 and ch["result"] == "fail"  # 200 秒到窗末 600 秒
    assert r["heartbeat"]["g_http"]["max_gap_s"] == 60.0
    assert r["overall"] == "fail" and r["dropped"] == 0
    text = json.dumps(r, ensure_ascii=False)
    assert "标题" not in text and "SIG" not in text


def test_whitelist_drops_content():
    dropped = []
    out = G.whitelist(
        {
            "http": {"dexs_a": {"ok": 1, "result": "pass", "title": "某币"}},
            "overall": "某币暴涨",
        },
        {"dexs_a"},
        dropped,
    )
    assert out == {"http": {"dexs_a": {"ok": 1, "result": "pass"}}, "overall": None}
    assert len(dropped) == 2


def test_manifest_tamper_detected(tmp_path):
    raw = build(tmp_path)
    S.write_manifest("2025-10-13", raw, tmp_path / "m")
    assert G.check_manifests(raw, tmp_path / "m") == {
        "checked": 3,
        "mismatch": 0,
        "result": "pass",
    }
    p = raw / "http" / "dexs_a" / "2025-10-13.jsonl.gz"
    p.write_bytes(p.read_bytes() + b"x")
    assert G.check_manifests(raw, tmp_path / "m")["mismatch"] == 1


def test_not_modified_counts_as_ok(tmp_path):
    raw = tmp_path / "raw"
    w = S.DayWriter(raw, "http/gh")
    for i, st in enumerate((200, 304, 304)):
        w.write(
            {
                "kind": "request",
                "src": "gh",
                "tag": None,
                "t_req_utc_ns": T0 + i * 300 * NS,
                "status": st,
                "struct_fp": None,
            },
            T0 + i * 300 * NS,
        )
    w.flush()
    r = G.check_http(raw, T0, T0 + 900 * NS, {"gh": 300})
    assert r["gh"]["ok"] == 3 and r["gh"]["success_rate"] == 1.0


def test_chain_windows_and_missed(tmp_path):
    import g_chain

    raw = tmp_path / "raw"
    h0 = 1791856800  # 2026-10-13 02:00 UTC
    (a1, b1), (a2, b2) = g_chain.window_for_hour(h0), g_chain.window_for_hour(h0 + 3600)
    c = S.DayWriter(raw, "chain/mainnet")
    c.write(
        {
            "kind": "conn",
            "what": "window_open",
            "t_utc_ns": a1 * NS,
            "start": a1,
            "end": b1,
        },
        a1 * NS,
    )
    for t in range(a1, b1, 30):  # 窗内每 30 秒一条
        c.write({"kind": "event", "t_utc_ns": t * NS}, t * NS)
    c.flush()
    r = G.check_chain(raw, h0 * NS, (h0 + 7200) * NS)["mainnet"]
    # 第二小时的窗应开没开：漏 1 个窗；窗外的 50 分钟不算沉默
    assert r["windows"] == 1 and r["missed_windows"] == 1 and r["max_silent_s"] == 30.0
    assert r["result"] == "fail"
    _ = (a2, b2)

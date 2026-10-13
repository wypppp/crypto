"""g_gaps 的构造数据测试（10-13）：进程不在、心跳超时、两种心跳格式、提示文字。"""

import os

import g_gaps as G
import g_store as S

NS = 1_000_000_000


def test_status_hand(tmp_path):
    raw = tmp_path / "raw"
    hb = S.DayWriter(raw, "heartbeat/p1")
    hb.write({"t_utc_ns": 1_000 * NS}, 1_000 * NS)
    hb.flush()
    alive = tmp_path / "alive.pid"
    alive.write_text(str(os.getpid()))
    dead = tmp_path / "dead.pid"
    dead.write_text("999999999")
    txt = tmp_path / "hb.txt"
    txt.write_text("1970-01-01T00:20:00+00:00 ok=1/1\n")  # epoch 1200 秒
    recs = [
        ("a", alive, ("dq42", "p1"), 1800),
        ("b", dead, ("dq42", "p1"), 1800),
        ("c", alive, ("txt", txt), 5400),
        ("d", alive, ("dq42", "none"), 1800),
    ]
    st = {s["name"]: s for s in G.status(now=1_000 + 1_000, recorders=recs, raw=raw)}
    assert st["a"]["beat_age_s"] == 1000 and not st["a"]["gap"]
    assert st["b"]["gap"] and not st["b"]["alive"]  # 进程不在
    assert st["c"]["beat_age_s"] == 800 and not st["c"]["gap"]
    assert st["d"]["gap"] and st["d"]["beat_age_s"] is None  # 没有心跳
    st2 = {s["name"]: s for s in G.status(now=1_000 + 1_801, recorders=recs, raw=raw)}
    assert st2["a"]["gap"]  # 超过 30 分钟
    w = G.warn_text(list(st2.values()))
    assert "a（30 分钟没有心跳）" in w and "b（进程不在）" in w and "start_all.sh" in w
    assert G.warn_text([s for s in st.values() if not s["gap"]]) == ""

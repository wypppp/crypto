"""obs.py 的手算预期值测试（10-13）：时刻换算、哈希链、篡改与删行可发现、转录时刻、输入校验。"""

import datetime as dt
import hashlib
import json

import pytest

import obs as O

UTC = dt.timezone.utc


def f(**kw):
    base = {
        "where": "微博",
        "what": "某事",
        "coin": "是",
        "names": "甲,乙",
        "venue": "four.meme",
        "conf": 3,
    }
    base.update(kw)
    return O.validate(base)


def test_times_hand(tmp_path):
    p = tmp_path / "o.jsonl"
    r = O.append(f(), p, dt.datetime(2026, 10, 13, 16, 30, tzinfo=UTC))
    assert r["utc"] == "2026-10-13T16:30:00.000000Z"
    assert r["beijing"] == "2026-10-14 00:30:00"
    assert r["seq"] == 1 and r["prev"] == "0" * 64 and r["names"] == ["甲", "乙"]


def test_chain_hand_and_tamper(tmp_path):
    p = tmp_path / "o.jsonl"
    t = dt.datetime(2026, 10, 13, 1, 0, tzinfo=UTC)
    for _ in range(3):
        O.append(f(), p, t)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["prev"] == hashlib.sha256(lines[0].encode()).hexdigest()
    assert O.verify(p) == {"lines": 3, "result": "pass", "first_bad_seq": None}
    # 改第 2 行：第 3 行的 prev 对不上
    lines2 = lines[:]
    lines2[1] = lines2[1].replace("某事", "别的")
    p.write_text("\n".join(lines2) + "\n", encoding="utf-8")
    assert O.verify(p) == {"lines": 3, "result": "fail", "first_bad_seq": 3}
    # 删第 2 行：序号与链都断在新的第 2 行
    p.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert O.verify(p)["first_bad_seq"] == 2


def test_orig_time_parsing():
    now = dt.datetime(2026, 10, 13, 14, 0, tzinfo=UTC)  # 北京 22:00
    assert O.parse_orig_time("21:05", now).astimezone(UTC) == dt.datetime(
        2026, 10, 13, 13, 5, tzinfo=UTC
    )
    early = dt.datetime(
        2026, 10, 14, 0, 0, tzinfo=UTC
    )  # 北京 10-14 08:00，转录前一晚 23:50
    assert (
        O.parse_orig_time("23:50", early).strftime("%Y-%m-%d %H:%M")
        == "2026-10-13 23:50"
    )
    assert O.parse_orig_time("2026-10-12 09:30", now).astimezone(UTC).hour == 1


def test_validate_rejects():
    with pytest.raises(ValueError):
        f(coin="可能")
    with pytest.raises(ValueError):
        f(conf=6)
    with pytest.raises(ValueError):
        f(what="")
    with pytest.raises(ValueError):
        O.validate(
            {"where": "w", "what": "x", "coin": "是", "conf": 2, "transcribed": True}
        )


def test_correction_is_new_line(tmp_path):
    p = tmp_path / "o.jsonl"
    t = dt.datetime(2026, 10, 13, tzinfo=UTC)
    O.append(f(), p, t)
    r = O.append(f(corrects=1, note="币名写错"), p, t)
    assert r["seq"] == 2 and r["corrects"] == 1 and O.verify(p)["result"] == "pass"


def test_manifest(tmp_path):
    p = tmp_path / "o.jsonl"
    t = dt.datetime(2026, 10, 13, tzinfo=UTC)
    O.append(f(), p, t)
    m = json.loads(O.manifest(p, tmp_path / "m", t).read_text())
    assert m["lines"] == 1 and m["chain"] == "pass"
    assert m["file_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert "what" not in json.dumps(m, ensure_ascii=False)

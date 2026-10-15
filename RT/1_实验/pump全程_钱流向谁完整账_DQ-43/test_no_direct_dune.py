"""付费查询只经 paid_guard（10-14，总控第七轮补 1）。

扫描 RT 下全部 .py：
1. .env 里没有旧键名 DUNE_API_KEY，Dune 密钥只用 paid_guard.KEY_NAME 这个键名；
2. 新键名只出现在 paid_guard.py；
3. 直接写 Dune 地址或用 dune_client 的脚本（旧实验约 30 个）不能导入 paid_guard，也读不到任何现存的 Dune 键名；
4. paid_guard.request 对付费接口：没有批准、或批准不在锁内，都拒绝，且不发出请求。
"""

import io
import json
import re
from urllib.error import HTTPError
from pathlib import Path

import pytest

import paid_guard as PG

RT = PG.H.parents[1]
DIRECT = re.compile(r"api\.dune\.com|dune_client|DuneClient")
DUNE_KEYS = re.compile(r"DUNE[A-Za-z0-9_]*")


@pytest.fixture(autouse=True)
def isolate_operational_halt(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")


def _py_files():
    """RT 下全部 .py，本测试文件除外（它为了扫描而写出这些模式）。"""
    me = Path(__file__).resolve()
    return [
        p
        for p in RT.rglob("*.py")
        if "__pycache__" not in p.parts and p.resolve() != me
    ]


def _env_keys():
    return re.findall(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", PG.ENV.read_text(), re.M
    )


def test_env_has_only_guarded_dune_key():
    dune = [k for k in _env_keys() if k.upper().startswith("DUNE")]
    assert dune == [PG.KEY_NAME]


def test_guarded_key_name_only_in_paid_guard():
    hits = [p for p in _py_files() if PG.KEY_NAME in p.read_text(errors="ignore")]
    assert hits == [PG.H / "paid_guard.py"]


def test_direct_dune_scripts_cannot_get_a_key():
    env = set(_env_keys())
    direct = []
    for p in _py_files():
        if p == PG.H / "paid_guard.py":
            continue
        s = p.read_text(errors="ignore")
        if not DIRECT.search(s):
            continue
        direct.append(p)
        assert not re.search(r"^\s*(import|from)\s+paid_guard\b", s, re.M), p
        assert not (set(DUNE_KEYS.findall(s)) & env), p
    assert len(direct) >= 29  # 旧实验的直连脚本都在扫描范围内


def test_scripts_using_paid_guard_do_not_call_dune_directly():
    for p in _py_files():
        s = p.read_text(errors="ignore")
        if p.name != "paid_guard.py" and re.search(
            r"^\s*(import|from)\s+paid_guard\b", s, re.M
        ):
            assert not DIRECT.search(s), p
            assert "urlopen" not in s and "requests." not in s, p


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/query/1/execute"),
        ("GET", "/execution/x/results?limit=10&offset=0"),
        ("GET", "/query/1/results?limit=1"),
        ("POST", "/sql/execute"),
        ("POST", "/uploads/csv"),
        ("POST", "/uploads/ns/t/insert"),
    ],
)
def test_paid_endpoints_need_locked_ticket(monkeypatch, tmp_path, method, path):
    def boom(*a, **k):
        raise AssertionError("不该发出请求")

    monkeypatch.setattr(PG.urllib.request, "urlopen", boom)
    assert not PG.is_free(method, path)
    with pytest.raises(SystemExit):
        PG.request(method, path)  # 没有批准
    t = PG.Ticket("A1", 5.0, 1.0)
    with pytest.raises(SystemExit):
        PG.request(method, path, ticket=t)  # 批准不在锁内
    with PG.one_at_a_time(t, tmp_path / "lock"):
        assert t.locked
        with pytest.raises(AssertionError):
            PG.request(method, path, ticket=t)  # 锁内才会真的发请求
    assert not t.locked


def test_free_endpoints_hand():
    for m, p in [
        ("POST", "/usage"),
        ("GET", "/execution/01ABC/status"),
        ("POST", "/execution/01ABC/cancel"),
        ("POST", "/query"),
        ("GET", "/query/123"),
    ]:
        assert PG.is_free(m, p)
    assert not PG.is_free("GET", "/usage")
    assert not PG.is_free("POST", "/query/123")


def test_request_records_error_and_never_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "H", tmp_path)
    monkeypatch.setattr(PG, "_key", lambda: "test-secret")
    calls = []

    def fail(req, timeout):
        calls.append(req.full_url)
        raise HTTPError(
            req.full_url,
            404,
            "not found",
            {},
            io.BytesIO(b'{"error":"Object not found"}'),
        )

    monkeypatch.setattr(PG.urllib.request, "urlopen", fail)
    with pytest.raises(HTTPError) as caught:
        PG.request("GET", "/query/2147483647")
    assert len(calls) == 1
    assert caught.value.dune_diagnostic["error_fields"]["error"] == "Object not found"


def test_429_persists_retry_after_without_resubmission(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "H", tmp_path)
    monkeypatch.setattr(PG, "LOCK", tmp_path / "paid.lock")
    monkeypatch.setattr(PG, "_key", lambda: "test-secret")
    calls = []

    def fail(req, timeout):
        calls.append(req.full_url)
        raise HTTPError(
            req.full_url,
            429,
            "limited",
            {"Retry-After": "180"},
            io.BytesIO(b'{"error":"rate limited"}'),
        )

    monkeypatch.setattr(PG.urllib.request, "urlopen", fail)
    before = PG.time.time()
    with pytest.raises(HTTPError):
        PG.request("GET", "/query/123")
    assert len(calls) == 1
    clock = json.loads((tmp_path / "rt_dune_http_clock.json").read_text())
    assert clock["not_before"] >= before + 180


def test_global_rate_gate_applies_to_direct_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "LOCK", tmp_path / "paid.lock")
    PG.S3_POLICY.write_text(
        json.dumps({"http_min_interval_seconds": 1.05, "http_transport": "direct"})
    )
    now, sleeps, opened = [100.0], [], []
    monkeypatch.setattr(PG.time, "time", lambda: now[0])

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(PG.time, "sleep", sleep)

    class Opener:
        def open(self, req, timeout):
            opened.append(req)
            return object()

    monkeypatch.setattr(PG.urllib.request, "build_opener", lambda *_: Opener())
    PG.open_http(object())
    PG.open_http(object())
    assert len(opened) == 2
    assert sleeps == pytest.approx([1.05])


def test_low_requests_keep_their_own_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "LOCK", tmp_path / "paid.lock")
    PG.S3_POLICY.write_text(
        json.dumps(
            {
                "http_min_interval_seconds": 0.35,
                "http_low_min_interval_seconds": 1.05,
                "http_transport": "direct",
            }
        )
    )
    now, sleeps = [100.0], []
    monkeypatch.setattr(PG.time, "time", lambda: now[0])

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(PG.time, "sleep", sleep)

    class Opener:
        def open(self, req, timeout):
            return object()

    class Low:
        method, full_url = "POST", "https://example.invalid/usage"

    monkeypatch.setattr(PG.urllib.request, "build_opener", lambda *_: Opener())
    PG.open_http(object())
    PG.open_http(Low())
    PG.open_http(Low())
    assert sleeps == pytest.approx([0.35, 1.05])

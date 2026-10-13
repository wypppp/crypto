"""g_http 的构造返回内容测试（10-13）：结构指纹、字段拆分、墓碑、退避、断网重试、限速冷却、
响应体去重、日切换、GitHub 存档的新提交下载。全部用构造的返回内容，不联网。"""

import gzip
import hashlib
import json

import g_http as H

NS = 1_000_000_000


def read_rows(root, key):
    out = []
    for p in sorted((root / "http" / key).glob("*.jsonl.gz")):
        out += [json.loads(x) for x in gzip.open(p, "rt").read().splitlines()]
    return out


def test_struct_fp_hand():
    fp, n = H.struct_fp({"a": 1, "b": [{"c": "x"}]})
    paths = sorted(["$:obj", "$.a:int", "$.b:list", "$.b[]:obj", "$.b[].c:str"])
    assert n == 5
    assert fp == hashlib.sha256("\n".join(paths).encode()).hexdigest()[:16]
    # 值变了指纹不变，类型变了指纹变
    assert H.struct_fp({"a": 2, "b": [{"c": "y"}]})[0] == fp
    assert H.struct_fp({"a": "2", "b": [{"c": "y"}]})[0] != fp


def test_split_fields_hand():
    item = {
        "chainId": "solana",
        "tokenAddress": "T",
        "priceUsd": "1.2",
        "claimDate": "2026-10-13",
        "links": [{"url": "u"}],
        "liquidity": {"usd": 5},
        "info": {"name": "N", "updatedAt": 7},
    }
    core, val, tim = H.split_fields(item)
    assert core == {
        "chainId": "solana",
        "tokenAddress": "T",
        "links": [{"url": "u"}],
        "info.name": "N",
    }
    assert val == {"priceUsd": "1.2", "liquidity": {"usd": 5}}
    assert tim == {"claimDate": "2026-10-13", "info.updatedAt": 7}


def test_item_id():
    assert (
        H.item_id(
            {"chainId": "solana", "tokenAddress": "T"}, ("chainId", "tokenAddress")
        )
        == "solana|T"
    )
    assert H.item_id({"x": 1}, ("id",)).startswith("h:")


def test_diff_items_tombstones():
    f = ("id",)
    ev, st = H.diff_items({}, [{"id": "A", "n": 1}, {"id": "B", "n": 1}], f)
    assert [(e["id"], e["event"]) for e in ev] == [
        ("A", "first_seen"),
        ("B", "first_seen"),
    ]
    # A 只有估值字段变：不记事件
    ev, st = H.diff_items(
        st, [{"id": "A", "n": 1, "priceUsd": 9}, {"id": "B", "n": 1}], f
    )
    assert ev == []
    # A 核心字段变；B 消失（墓碑）
    ev, st = H.diff_items(st, [{"id": "A", "n": 2}], f)
    assert [(e["id"], e["event"]) for e in ev] == [("A", "changed"), ("B", "absent")]
    # B 重新出现；A 消失
    ev, st = H.diff_items(st, [{"id": "B", "n": 1}], f)
    assert [(e["id"], e["event"]) for e in ev] == [("B", "reappeared"), ("A", "absent")]
    # 已消失的 A 不重复记墓碑
    ev, st = H.diff_items(st, [{"id": "B", "n": 1}], f)
    assert ev == []


def test_backoff_hand():
    assert [H.backoff_s(a, None) for a in (1, 2, 3)] == [2.0, 4.0, 8.0]
    assert H.backoff_s(10, None) == 120.0
    assert H.backoff_s(1, "7") == 7.0
    assert H.backoff_s(2, "soon") == 4.0
    assert H.backoff_s(1, "99999") == 900.0


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_host_gate_spacing_and_cooldown():
    c = FakeClock()
    g = H.HostGate(1.5)
    g.wait(c.sleep, c)
    g.wait(c.sleep, c)
    assert c.slept == [1.5]
    g.cool(30, c)
    g.wait(c.sleep, c)
    assert c.slept[-1] == 30


def make_poller(tmp_path, responses, every=60, id_fields=("id",)):
    calls = []
    seq = list(responses)

    def get(url, headers=None):
        calls.append(url)
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    slept = []
    src = H.Source("s", "https://x/api", every, "x", id_fields)
    gate = H.HostGate(0.0)
    p = H.Poller(
        src,
        gate,
        root=tmp_path / "raw",
        state_dir=tmp_path / "state",
        get=get,
        sleep=slept.append,
    )
    return p, calls, slept


def ok(body, hdr=None):
    return 200, hdr or {}, json.dumps(body).encode()


def test_network_error_then_success(tmp_path):
    p, calls, slept = make_poller(tmp_path, [OSError("down"), ok([{"id": "A"}])])
    st, body = p.poll()
    assert st == 200 and len(calls) == 2 and slept == [2.0]
    rows = read_rows(tmp_path / "raw", "s")
    req = [r for r in rows if r["kind"] == "request"]
    assert [(r["attempt"], r["status"], r["err"] is not None) for r in req] == [
        (1, None, True),
        (2, 200, False),
    ]
    assert req[1]["n_items"] == 1 and req[1]["backfill"] is False
    assert [r["event"] for r in rows if r["kind"] == "item"] == ["first_seen"]
    assert p.n_ok == 1 and p.n_fail == 1


def test_rate_limit_honours_retry_after_and_cools_host(tmp_path):
    p, calls, slept = make_poller(tmp_path, [(429, {"retry-after": "7"}, b""), ok([])])
    p.poll()
    assert len(slept) == 1 and abs(slept[0] - 7.0) < 0.5  # 只等一次：主机冷却 7 秒


def test_client_error_not_retried(tmp_path):
    p, calls, slept = make_poller(tmp_path, [(404, {}, b"no")])
    st, body = p.poll()
    assert st == 404 and len(calls) == 1 and slept == []


def test_all_attempts_fail(tmp_path):
    p, calls, slept = make_poller(
        tmp_path, [(503, {}, b""), (503, {}, b""), (503, {}, b"")]
    )
    p.poll()
    assert len(calls) == 3 and slept == [2.0, 4.0] and p.n_fail == 3


def test_identical_body_stored_once(tmp_path):
    p, _, _ = make_poller(tmp_path, [ok([{"id": "A"}]), ok([{"id": "A"}])])
    p.poll()
    p.poll()
    req = [r for r in read_rows(tmp_path / "raw", "s") if r["kind"] == "request"]
    assert "body" in req[0] and req[0]["body_same_as_prev"] is False
    assert "body" not in req[1] and req[1]["body_same_as_prev"] is True
    assert req[0]["body_sha256"] == req[1]["body_sha256"]


def test_state_survives_restart(tmp_path):
    p, _, _ = make_poller(tmp_path, [ok([{"id": "A"}])])
    p.poll()
    p2, _, _ = make_poller(tmp_path, [ok([{"id": "A"}, {"id": "B"}])])
    p2.poll()
    ev = [
        (r["id"], r["event"])
        for r in read_rows(tmp_path / "raw", "s")
        if r["kind"] == "item"
    ]
    assert ev == [("A", "first_seen"), ("B", "first_seen")]


def test_day_rollover(tmp_path, monkeypatch):
    times = iter(
        [
            (1760313599 * NS, 1),
            (1760313599 * NS + 5, 2),
            (1760313600 * NS, 3),
            (1760313600 * NS + 5, 4),
        ]
    )
    monkeypatch.setattr(H, "now", lambda: next(times))
    p, _, _ = make_poller(tmp_path, [ok([]), ok([{"id": "A"}])])
    p.poll()
    p.poll()
    names = sorted(x.name for x in (tmp_path / "raw" / "http" / "s").glob("*.jsonl.gz"))
    assert names == ["2025-10-12.jsonl.gz", "2025-10-13.jsonl.gz"]


def test_github_archive_fetches_new_commit_files(tmp_path):
    commits1 = [{"sha": "c1", "url": "https://api/commits/c1"}]
    commits2 = [{"sha": "c2", "url": "https://api/commits/c2"}] + commits1
    detail = {
        "sha": "c2",
        "files": [
            {"filename": "raw/2026-10-13.json", "raw_url": "https://raw/c2/x.json"},
            {"filename": "README.md", "raw_url": "https://raw/c2/README.md"},
        ],
    }
    seq = {
        "https://gh/commits": [ok(commits1), ok(commits2)],
        "https://api/commits/c2": [ok(detail)],
        "https://raw/c2/x.json": [ok({"t": 1})],
    }
    calls = []

    def get(url, headers=None):
        calls.append(url)
        return seq[url].pop(0)

    gate = H.HostGate(0.0)
    pl = H.Poller(
        H.Source("gh_weibo_commits", "https://gh/commits", 300, "gh", ("sha",)),
        gate,
        root=tmp_path / "raw",
        state_dir=tmp_path / "st",
        get=get,
        sleep=lambda s: None,
    )
    pf = H.Poller(
        H.Source("gh_weibo_files", "-", 300, "gh"),
        gate,
        root=tmp_path / "raw",
        state_dir=tmp_path / "st",
        get=get,
        sleep=lambda s: None,
    )
    gh = H.GitHubArchive(pl, pf)
    gh.poll()  # 基线：不回取旧提交
    assert calls == ["https://gh/commits"]
    gh.poll()
    assert calls[1:] == [
        "https://gh/commits",
        "https://api/commits/c2",
        "https://raw/c2/x.json",
    ]
    tags = [r["tag"] for r in read_rows(tmp_path / "raw", "gh_weibo_files")]
    assert tags == ["commit", "raw_file"]


def test_etag_conditional_304(tmp_path):
    sent = []
    seq = [
        (200, {"etag": 'W/"e1"'}, b'[{"sha": "c1"}]'),
        (304, {"etag": 'W/"e1"'}, b""),
    ]

    def get(url, headers=None):
        sent.append(headers)
        return seq.pop(0)

    p = H.Poller(
        H.Source("g", "https://gh", 300, "gh", ("sha",)),
        H.HostGate(0.0),
        root=tmp_path / "raw",
        state_dir=tmp_path / "st",
        get=get,
        sleep=lambda s: None,
        conditional=True,
    )
    assert p.poll()[0] == 200
    st, body = p.poll()
    assert st == 304 and body is None
    assert sent == [None, {"If-None-Match": 'W/"e1"'}]
    req = [r for r in read_rows(tmp_path / "raw", "g") if r["kind"] == "request"]
    assert req[1]["body_same_as_prev"] is True and p.n_ok == 2 and p.n_fail == 0

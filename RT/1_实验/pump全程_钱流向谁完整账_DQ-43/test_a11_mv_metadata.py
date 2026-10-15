"""MV只读元数据白名单；创建、刷新和执行仍受原付费封锁。"""

import pytest

import paid_guard as PG


@pytest.mark.parametrize(
    "path",
    [
        "/materialized-views",
        "/materialized-views?limit=100&offset=0",
        "/materialized-views/dune.example.result_smoke",
    ],
)
def test_mv_metadata_get_only(path):
    assert PG.is_free("GET", path)
    assert not PG.is_free("POST", path)
    assert not PG.is_free("DELETE", path)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/materialized-views"),
        ("POST", "/materialized-views/dune.example.result_smoke/refresh"),
        ("GET", "/materialized-views/dune.example.result_smoke/refresh"),
        ("GET", "/materialized-views?limit=1&unexpected=execute"),
        ("GET", "/execution/e/results?limit=1"),
    ],
)
def test_mv_mutation_and_results_still_refused(monkeypatch, method, path):
    monkeypatch.setattr(PG, "_key", lambda: pytest.fail("不该读取密钥或访问网络"))
    assert not PG.is_free(method, path)
    with pytest.raises(PG.Refused, match="没有锁内的批准"):
        PG.request(method, path)

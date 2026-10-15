"""离线测试的付费控制文件独立于真实账户；不改变真实封锁或审查状态。"""

import pytest

import paid_guard as PG


@pytest.fixture(autouse=True)
def isolated_account_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(PG, "S3_POLICY", tmp_path / "policy.json")
    monkeypatch.setattr(PG, "HALT", tmp_path / "halt.json")

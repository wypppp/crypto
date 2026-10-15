"""HTTP错误要保留诊断证据、脱敏，并保证执行POST只发送一次。"""

import io
import json
from urllib.error import HTTPError, URLError


import paid_guard as P


def test_http_error_preserves_status_and_request_id_but_redacts_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(P, "H", tmp_path)
    secret = "test-credential-sentinel"
    error = HTTPError(
        "unused",
        500,
        "failed",
        {
            "x-request-id": "request-123",
            "set-cookie": secret,
        },
        io.BytesIO(json.dumps({"error": "failure with " + secret}).encode()),
    )
    P.http_failure(error, "POST", "/query/1/execute", secret)
    record = error.dune_diagnostic
    assert record["http_status"] == 500
    assert record["response_headers"] == {"x-request-id": "request-123"}
    assert record["error_fields"]["error"] == "failure with [REDACTED]"
    assert secret not in (tmp_path / record["private_response"]).read_text()
    assert secret not in (tmp_path / "runs/dune_http_failures.jsonl").read_text()


def test_transport_error_is_recorded_without_masking_type(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "H", tmp_path)
    error = URLError("closed test-secret")
    P.http_failure(error, "GET", "/query/1", "test-secret")
    assert error.dune_diagnostic["http_status"] is None
    assert error.dune_diagnostic["error_type"] == "URLError"
    assert "test-secret" not in json.dumps(error.dune_diagnostic)


def test_direct_transport_disables_only_proxy_and_does_not_fallback(monkeypatch):
    from types import SimpleNamespace

    P.S3_POLICY.write_text(json.dumps({"http_transport": "direct"}))
    monkeypatch.setattr(P, "_key", lambda: "test-secret")
    calls = []

    def build(handler):
        assert handler.proxies == {}

        def open_once(req, timeout):
            calls.append(req.full_url)
            return io.BytesIO(b'{"query_id":1}')

        return SimpleNamespace(open=open_once)

    monkeypatch.setattr(P.urllib.request, "build_opener", build)
    assert P.request("GET", "/query/1") == {"query_id": 1}
    assert len(calls) == 1

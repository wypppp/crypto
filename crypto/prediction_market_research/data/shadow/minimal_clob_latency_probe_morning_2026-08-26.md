# Local morning CLOB WebSocket probe — 2026-08-26

- Environment: local machine; HTTP(S)/ALL proxy variables present; no authenticated APIs; no orders.
- Intended run: the existing single-socket BTC 5-minute public CLOB probe for 420 seconds.
- Pre-run tests: 43 passed.

## Attempt 1

- The connection opened and the subscription was sent.
- After approximately 55 seconds, `recv()` raised
  `WebSocketConnectionClosedException: Connection to remote host was lost.`
- The probe did not reach normal return, so no latency quantiles were emitted.

## Immediate retry

- The WebSocket did not finish its TLS handshake.
- Error: `ssl.SSLEOFError: UNEXPECTED_EOF_WHILE_READING`.

## Control checks

- Proxied `https://clob.polymarket.com/time`: HTTP 200; TLS 0.468 s; total 0.839 s.
- Proxied `https://gamma-api.polymarket.com/markets?limit=1`: HTTP 200; TLS 0.562 s; total 0.862 s.
- Direct (proxy-bypassed) `https://clob.polymarket.com/time`: timed out after 10 seconds; HTTP 000.

## Frozen interpretation

- Quality gate: **fail**. The local path could not sustain the requested seven-minute public WebSocket session, even during the proposed better morning window.
- The result rules out “the local path is reliably usable this morning”; it does not by itself distinguish the local proxy/ISP path from the CLOB WebSocket service.
- Healthy proxied HTTPS but failing WebSocket narrows the fault to the WebSocket-specific path or endpoint. A simultaneous identical cloud-versus-local run is required for causal attribution.
- No P50/P95/P99 latency claim is made because the failed process did not return its in-memory observations.

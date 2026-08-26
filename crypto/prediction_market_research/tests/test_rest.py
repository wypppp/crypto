from shadow_mm.rest import PublicRestClient


def test_gamma_pagination_respects_server_cap() -> None:
    client = PublicRestClient("https://gamma", "https://clob", "https://coinbase")
    calls = []

    def fake_get(url, params=None):
        calls.append(dict(params))
        offset = params["offset"]
        count = 100 if offset < 200 else 3
        return [
            {
                "conditionId": "condition-{}".format(offset + index),
                "question": "Bitcoin Up or Down - 5 minutes",
                "clobTokenIds": '["a","b"]',
                "outcomes": '["Up","Down"]',
            }
            for index in range(count)
        ]

    client._get = fake_get
    markets = client.gamma_markets(page_size=500, pages=10)
    client.close()
    assert len(markets) == 203
    assert [call["offset"] for call in calls] == [0, 100, 200]
    assert all(call["limit"] == 100 for call in calls)
    assert all(call["order"] == "endDate" for call in calls)


def test_gamma_condition_batch_uses_array_filter() -> None:
    client = PublicRestClient("https://gamma", "https://clob", "https://coinbase")
    calls = []

    def fake_get(url, params=None):
        calls.append((url, params))
        return [{"conditionId": "a"}, {"conditionId": "b"}]

    client._get = fake_get
    rows = client.gamma_markets_by_condition_ids(["a", "b"])
    client.close()
    assert [row.condition_id for row in rows] == ["a", "b"]
    assert calls[0][1]["condition_ids"] == ["a", "b"]
    assert calls[0][1]["closed"] == "true"

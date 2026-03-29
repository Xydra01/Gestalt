from __future__ import annotations

import json
import os
from unittest.mock import patch


class _FakeRequestsResp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_get_amazon_price_uses_serper_when_rainforest_missing(monkeypatch) -> None:
    from amazon_api import SERPER_API_KEY_ENV, get_amazon_price

    monkeypatch.delenv("RAINFOREST_API_KEY", raising=False)
    monkeypatch.setenv(SERPER_API_KEY_ENV, "serper-key")

    serper_payload = {
        "organic": [
            {
                "title": "AMD Ryzen 5 7600X - Amazon.com",
                "link": "https://www.amazon.com/dp/B0BBBBBBB",
                "snippet": "Great CPU from $199.99 today.",
            }
        ]
    }

    with patch(
        "amazon_api.requests.post",
        return_value=_FakeRequestsResp(200, serper_payload),
    ) as p:
        out = get_amazon_price("Ryzen 5 7600X", amazon_key=None)

    assert p.called
    assert out is not None
    assert out["source"] == "amazon"
    assert out["url"].startswith("https://www.amazon.com/")
    assert isinstance(out["price"], int)
    assert out["price"] == 200  # rounded from 199.99


def test_get_amazon_price_prefers_rainforest_when_available(monkeypatch) -> None:
    from amazon_api import get_amazon_price

    monkeypatch.setenv("RAINFOREST_API_KEY", "rainforest-key")
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")

    with patch("amazon_api.search_amazon", return_value=(123, "T", "U")) as s:
        with patch("amazon_api.requests.post") as p:
            out = get_amazon_price("X", amazon_key=None)

    assert s.called
    assert not p.called  # should not hit Serper when Rainforest works
    assert out == {"source": "amazon", "price": 123, "title": "T", "url": "U"}


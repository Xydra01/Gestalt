from __future__ import annotations

import json
import os
from unittest.mock import patch


class _FakeResp:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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

    with patch("amazon_api.urlopen", return_value=_FakeResp(json.dumps(serper_payload))) as u:
        out = get_amazon_price("Ryzen 5 7600X", amazon_key=None)

    assert u.called
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
        with patch("amazon_api.urlopen") as u:
            out = get_amazon_price("X", amazon_key=None)

    assert s.called
    assert not u.called  # should not hit Serper/urlopen when Rainforest works
    assert out == {"source": "amazon", "price": 123, "title": "T", "url": "U"}


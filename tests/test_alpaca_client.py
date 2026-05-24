import json
import ssl
import urllib.error

import pytest

from same_day_lab.config import load_config
from same_day_lab.ingest import alpaca


def test_ssl_context_verifies():
    ctx = alpaca._ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


class _Resp:
    def __init__(self, body):
        self._b = json.dumps(body).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "msg", headers or {}, None)


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")


def test_builds_iex_raw_request_and_paginates(monkeypatch):
    pages = [
        {"bars": [{"t": "2025-06-16T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "vw": 1, "n": 1}],
         "next_page_token": "TOK"},
        {"bars": [{"t": "2025-06-16T13:31:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "vw": 1, "n": 1}],
         "next_page_token": None},
    ]
    seen = []

    def fake_urlopen(req, timeout=30, **kw):
        seen.append(req.full_url)
        return _Resp(pages[len(seen) - 1])

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = alpaca.fetch_bars("AAPL", "2025-06-16", load_config())

    assert len(out["bars"]) == 2 and out["feed"] == "iex"
    assert "timeframe=1Min" in seen[0]
    assert "feed=iex" in seen[0]
    assert "adjustment=raw" in seen[0]
    assert "limit=10000" in seen[0]
    assert "page_token=TOK" in seen[1]


@pytest.mark.parametrize("code", [401, 403])
def test_bad_creds_mapped(monkeypatch, code):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30, **kw: (_ for _ in ()).throw(_http_error(code)))
    with pytest.raises(alpaca.AlpacaError) as e:
        alpaca.fetch_bars("AAPL", "2025-06-16", load_config())
    assert "credential" in str(e.value).lower()


def test_429_retries_once_honoring_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(alpaca.time, "sleep", lambda s: sleeps.append(s))
    seq = [_http_error(429, {"Retry-After": "2"}),
           _Resp({"bars": [{"t": "2025-06-16T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "vw": 1, "n": 1}],
                  "next_page_token": None})]

    def fake(req, timeout=30, **kw):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    monkeypatch.setattr("urllib.request.urlopen", fake)
    out = alpaca.fetch_bars("AAPL", "2025-06-16", load_config())
    assert len(out["bars"]) == 1
    assert sleeps == [2.0]


def test_429_twice_raises(monkeypatch):
    monkeypatch.setattr(alpaca.time, "sleep", lambda s: None)
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30, **kw: (_ for _ in ()).throw(_http_error(429, {"Retry-After": "1"})))
    with pytest.raises(alpaca.AlpacaError) as e:
        alpaca.fetch_bars("AAPL", "2025-06-16", load_config())
    assert "rate limit" in str(e.value).lower()


def test_empty_bars_mapped(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30, **kw: _Resp({"bars": [], "next_page_token": None}))
    with pytest.raises(alpaca.AlpacaError) as e:
        alpaca.fetch_bars("AAPL", "2025-06-16", load_config())
    assert "no bars" in str(e.value).lower()

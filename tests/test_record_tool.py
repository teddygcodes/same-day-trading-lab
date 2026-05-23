import importlib.util
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_tool():
    path = os.path.join(REPO_ROOT, "tools", "record_real_day.py")
    spec = importlib.util.spec_from_file_location("record_real_day", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_tool_writes_fixture_shaped_file(tmp_path, monkeypatch):
    from same_day_lab.ingest import alpaca

    canned = {
        "symbol": "AAPL", "session_date": "2025-06-16", "timeframe": "1Min",
        "feed": "iex", "is_half_day": False,
        "bars": [{"t": "2025-06-16T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "vw": 1, "n": 1}],
    }
    monkeypatch.setattr(alpaca, "fetch_bars", lambda *a, **k: canned)

    tool = _load_tool()
    out = tmp_path / "real_aapl_2025-06-16_iex.json"
    assert tool.main(["--symbol", "AAPL", "--date", "2025-06-16", "--out", str(out)]) == 0

    data = json.loads(out.read_text())
    assert {"symbol", "session_date", "timeframe", "feed", "is_half_day", "bars"} <= set(data)
    assert data["feed"] == "iex" and len(data["bars"]) == 1
    blob = json.dumps(data).lower()
    assert "alpaca_api_key" not in blob and "secret" not in blob

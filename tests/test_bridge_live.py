"""REST endpoint smoke tests. Requires bridge running on port 9876/9877."""
import json
import datetime
import pytest
from conftest import rpc, bridge_running


def test_account_info(bridge_running):
    r = rpc("account_info")
    result = r.get("result")
    assert result is not None, f"account_info failed: {r}"
    assert result["login"] == 3000100276
    assert result["balance"] > 0
    assert result["server"] == "Darwinex-Demo"
    assert result["currency"] == "USD"


def test_symbols_count(bridge_running):
    r = rpc("symbols_get")
    syms = r.get("result")
    assert isinstance(syms, list)
    assert len(syms) > 100  # Darwinex has ~853 symbols


def test_symbols_have_forex(bridge_running):
    r = rpc("symbols_get")
    syms = r.get("result", [])
    names = {s["name"] for s in syms}
    assert "EURUSD" in names
    assert "GBPCHF" in names
    assert "XAUUSD" in names


def test_copy_rates_range(bridge_running):
    now = datetime.datetime.now()
    r = rpc("copy_rates_range", {
        "symbol": "EURUSD", "timeframe": 1,
        "date_from": int((now - datetime.timedelta(hours=1)).timestamp()),
        "date_to": int(now.timestamp()),
    })
    bars = r.get("result", [])
    assert len(bars) > 0, "No bars returned"
    bar = bars[-1]
    for field in ("time", "open", "high", "low", "close", "tick_volume"):
        assert field in bar, f"Missing field {field}"
        assert isinstance(bar[field], (int, float)), f"{field} wrong type"


def test_copy_rates_from_pos(bridge_running):
    r = rpc("copy_rates_from_pos", {
        "symbol": "EURUSD", "timeframe": 1,
        "start_pos": 0, "count": 5,
    })
    bars = r.get("result", [])
    assert len(bars) == 5, f"Expected 5 bars, got {len(bars)}"


def test_positions_empty(bridge_running):
    r = rpc("positions_get")
    pos = r.get("result", [])
    assert isinstance(pos, list)

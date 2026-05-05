"""Order placement round-trip on Darwinex demo. Requires bridge + algo trading enabled."""
import json
import urllib.request
import pytest
from conftest import rpc, bridge_running


def rpc_result(method, params=None):
    return rpc(method, params).get("result")


def test_account_balance(bridge_running):
    info = rpc_result("account_info")
    assert info["login"] == 3000100276
    assert info["trade_allowed"] is True
    assert info["trade_expert"] is True


def test_order_round_trip(bridge_running):
    """Place EURUSD BUY 0.01 lots → verify position → close."""
    # Place
    result = rpc_result("order_send", {
        "request": {
            "action": 1, "symbol": "EURUSD", "volume": 0.01, "type": 0,
            "price": 0.0, "sl": 0.0, "tp": 0.0, "deviation": 10,
            "magic": 123456, "comment": "pytest round-trip",
            "type_time": 0, "type_filling": 1,
        }
    })
    assert result["retcode"] == 10009, f"Order failed: {result}"
    ticket = result["order"]
    entry_price = result["price"]
    assert ticket > 0
    assert entry_price > 0

    # Verify position
    pos = rpc_result("positions_get", {"symbol": "EURUSD"})
    assert len(pos) > 0, "No position after fill"
    assert pos[0]["symbol"] == "EURUSD"
    assert pos[0]["volume"] == 0.01

    # Close
    close = rpc_result("order_send", {
        "request": {
            "action": 1, "symbol": "EURUSD", "volume": 0.01, "type": 1,
            "position": ticket, "price": 0.0, "deviation": 10,
            "magic": 123456, "comment": "pytest close",
            "type_time": 0, "type_filling": 1,
        }
    })
    assert close["retcode"] == 10009, f"Close failed: {close}"
    assert close["price"] > 0

    # Verify position closed
    pos_after = rpc_result("positions_get", {"symbol": "EURUSD"})
    matching = [p for p in pos_after if p.get("ticket") == ticket or p.get("position") == ticket]
    assert len(matching) == 0, "Position still open after close"

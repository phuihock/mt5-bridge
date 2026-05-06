"""Order placement round-trips on Darwinex demo. Requires bridge + algo trading enabled."""
import MetaTrader5 as mt5
import pytest
from conftest import rpc, bridge_running


def rpc_result(method, params=None):
    return rpc(method, params).get("result")


def test_account_balance(bridge_running):
    info = rpc_result("account_info")
    assert info["login"] == 3000100276
    assert info["trade_allowed"] is True
    assert info["trade_expert"] is True


# ── Helpers ───────────────────────────────────────────────────────────

def _place_market(order_type, suffix: str = ""):
    """Place a market order, 0.01 lots EURUSD."""
    return rpc_result("order_send", {
        "request": {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "EURUSD", "volume": 0.01, "type": order_type,
            "price": 0.0, "sl": 0.0, "tp": 0.0, "deviation": 10,
            "magic": 123456, "comment": f"pytest market {suffix}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
    })


def _close_market(ticket: int, close_type, suffix: str = ""):
    """Close a position by ticket. Uses opposite order type."""
    return rpc_result("order_send", {
        "request": {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "EURUSD", "volume": 0.01, "type": close_type,
            "position": ticket, "price": 0.0, "deviation": 10,
            "magic": 123456, "comment": f"pytest close {suffix}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
    })


def _place_pending(order_type, price_offset: float, suffix: str = ""):
    """Place a pending limit order offset from current price."""
    info = rpc_result("symbol_info", {"symbol": "EURUSD"})
    bid = info["bid"]
    ask = info["ask"]
    price = ask + price_offset if order_type == mt5.ORDER_TYPE_SELL_LIMIT else bid - abs(price_offset)
    price = round(price, 5)
    return rpc_result("order_send", {
        "request": {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": "EURUSD", "volume": 0.01, "type": order_type,
            "price": price, "sl": 0.0, "tp": 0.0, "deviation": 10,
            "magic": 123456, "comment": f"pytest pending {suffix}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
    })


def _cancel_pending(ticket: int, suffix: str = ""):
    """Cancel a pending order by ticket."""
    return rpc_result("order_send", {
        "request": {
            "action": mt5.TRADE_ACTION_REMOVE, "order": ticket,
        }
    })


# ── Round trip tests ─────────────────────────────────────────────────

def test_round_trip_market_long(bridge_running):
    """Market BUY → verify position → close (SELL closes BUY)."""
    result = _place_market(mt5.ORDER_TYPE_BUY, "long")
    assert result["retcode"] == mt5.TRADE_RETCODE_DONE, f"Market long failed: {result}"
    ticket = result["order"]
    assert ticket > 0

    pos = rpc_result("positions_get", {"symbol": "EURUSD"})
    matching = [p for p in pos if p.get("ticket") == ticket]
    assert len(matching) == 1, f"Position not found for ticket {ticket}"
    assert matching[0]["symbol"] == "EURUSD"

    close = _close_market(ticket, mt5.ORDER_TYPE_SELL, "long")
    assert close["retcode"] == mt5.TRADE_RETCODE_DONE, f"Close long failed: {close}"

    pos_after = rpc_result("positions_get", {"symbol": "EURUSD"})
    matching_after = [p for p in pos_after if p.get("ticket") == ticket]
    assert len(matching_after) == 0, "Long position still open after close"


def test_round_trip_market_short(bridge_running):
    """Market SELL → verify position → close (BUY closes SELL)."""
    result = _place_market(mt5.ORDER_TYPE_SELL, "short")
    assert result["retcode"] == mt5.TRADE_RETCODE_DONE, f"Market short failed: {result}"
    ticket = result["order"]
    assert ticket > 0

    pos = rpc_result("positions_get", {"symbol": "EURUSD"})
    matching = [p for p in pos if p.get("ticket") == ticket]
    assert len(matching) == 1, f"Position not found for ticket {ticket}"
    assert matching[0]["symbol"] == "EURUSD"

    close = _close_market(ticket, mt5.ORDER_TYPE_BUY, "short")
    assert close["retcode"] == mt5.TRADE_RETCODE_DONE, f"Close short failed: {close}"

    pos_after = rpc_result("positions_get", {"symbol": "EURUSD"})
    matching_after = [p for p in pos_after if p.get("ticket") == ticket]
    assert len(matching_after) == 0, "Short position still open after close"


def test_round_trip_pending_limit_long(bridge_running):
    """BUY_LIMIT (below market) → verify → cancel."""
    result = _place_pending(mt5.ORDER_TYPE_BUY_LIMIT, -0.0010, "limit-long")
    assert result["retcode"] == mt5.TRADE_RETCODE_DONE, f"BUY_LIMIT failed: {result}"
    ticket = result["order"]
    assert ticket > 0
    # MT5 returns price=0.0 in OrderSendResult for pending orders
    orders = rpc_result("orders_get", {"symbol": "EURUSD"})
    matching = [o for o in orders if o.get("ticket") == ticket]
    assert len(matching) == 1, f"Pending order not found for ticket {ticket}"
    assert matching[0]["type"] == mt5.ORDER_TYPE_BUY_LIMIT

    cancel = _cancel_pending(ticket, "limit-long")
    assert cancel["retcode"] == mt5.TRADE_RETCODE_DONE, f"Cancel BUY_LIMIT failed: {cancel}"

    orders_after = rpc_result("orders_get", {"symbol": "EURUSD"})
    matching_after = [o for o in orders_after if o.get("ticket") == ticket]
    assert len(matching_after) == 0, "BUY_LIMIT still open after cancel"


def test_round_trip_pending_limit_short(bridge_running):
    """SELL_LIMIT (above market) → verify → cancel."""
    result = _place_pending(mt5.ORDER_TYPE_SELL_LIMIT, 0.0010, "limit-short")
    assert result["retcode"] == mt5.TRADE_RETCODE_DONE, f"SELL_LIMIT failed: {result}"
    ticket = result["order"]
    assert ticket > 0
    # MT5 returns price=0.0 in OrderSendResult for pending orders
    orders = rpc_result("orders_get", {"symbol": "EURUSD"})
    matching = [o for o in orders if o.get("ticket") == ticket]
    assert len(matching) == 1, f"Pending order not found for ticket {ticket}"
    assert matching[0]["type"] == mt5.ORDER_TYPE_SELL_LIMIT

    cancel = _cancel_pending(ticket, "limit-short")
    assert cancel["retcode"] == mt5.TRADE_RETCODE_DONE, f"Cancel SELL_LIMIT failed: {cancel}"

    orders_after = rpc_result("orders_get", {"symbol": "EURUSD"})
    matching_after = [o for o in orders_after if o.get("ticket") == ticket]
    assert len(matching_after) == 0, "SELL_LIMIT still open after cancel"

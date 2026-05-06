"""DOM subscription test — calls bridge REST, no direct MT5 connection."""
import pytest
from conftest import rpc, bridge_running


def test_dom_subscribe_and_read(bridge_running):
    symbol = "EURUSD"
    r = rpc("market_book_add", {"symbol": symbol})
    assert r.get("result") is True, f"market_book_add failed: {r}"

    import time
    time.sleep(1)

    r = rpc("market_book_get", {"symbol": symbol})
    items = r.get("result")
    assert items is not None, "market_book_get returned None"
    assert len(items) > 0, "No DOM levels"

    bids = [it for it in items if it.get("type") == 2]
    asks = [it for it in items if it.get("type") == 1]
    assert len(bids) > 0, "No bid levels"
    assert len(asks) > 0, "No ask levels"

    best_bid = max(it["price"] for it in bids)
    best_ask = min(it["price"] for it in asks)
    assert best_ask - best_bid > 0, f"Negative spread"

    rpc("market_book_release", {"symbol": symbol})


def test_dom_release(bridge_running):
    r = rpc("market_book_add", {"symbol": "GBPCHF"})
    assert r.get("result") is True
    r = rpc("market_book_release", {"symbol": "GBPCHF"})
    assert r.get("result") is True

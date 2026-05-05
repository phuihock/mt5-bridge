"""Quick DOM subscription test — verifies market_book_add/get/release."""
import pytest
import MetaTrader5 as mt5


@pytest.fixture(scope="module")
def mt5_conn():
    assert mt5.initialize(), f"MT5 init failed: {mt5.last_error()}"
    yield
    mt5.shutdown()


def test_dom_subscribe_and_read(mt5_conn):
    symbol = "EURUSD"
    assert mt5.market_book_add(symbol), f"market_book_add failed: {mt5.last_error()}"

    import time
    time.sleep(1)  # allow DOM to populate

    items = mt5.market_book_get(symbol)
    assert items is not None, "market_book_get returned None"
    assert len(items) > 0, "No DOM levels"

    bids = [it for it in items if it.type == mt5.BOOK_TYPE_BUY]
    asks = [it for it in items if it.type == mt5.BOOK_TYPE_SELL]
    assert len(bids) > 0, "No bid levels"
    assert len(asks) > 0, "No ask levels"

    best_bid = max(it.price for it in bids)
    best_ask = min(it.price for it in asks)
    spread = best_ask - best_bid
    assert spread > 0, f"Negative spread: {spread}"

    mt5.market_book_release(symbol)


def test_dom_release(mt5_conn):
    symbol = "GBPCHF"
    mt5.market_book_add(symbol)
    assert mt5.market_book_release(symbol), "market_book_release failed"

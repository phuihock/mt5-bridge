"""test_dom.py — Quick DOM subscription test for Darwinex MT5."""
import MetaTrader5 as mt5
import time

if not mt5.initialize(path=r'C:\Program Files\Darwinex MetaTrader 5\terminal64.exe'):
    print("MT5 init failed:", mt5.last_error())
    exit()

symbol = "EURUSD"

# Subscribe to DOM
if not mt5.market_book_add(symbol):
    print(f"market_book_add({symbol}) failed:", mt5.last_error())
    mt5.shutdown()
    exit()

print(f"Subscribed to DOM for {symbol}. Polling 15 times (1s apart)...")
for i in range(15):
    items = mt5.market_book_get(symbol)
    if items:
        # MT5 constants: BOOK_TYPE_BUY=2 (bid), BOOK_TYPE_SELL=1 (ask)
        bids = [it for it in items if it.type == mt5.BOOK_TYPE_BUY]
        asks = [it for it in items if it.type == mt5.BOOK_TYPE_SELL]
        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        spread = (best_ask - best_bid) if best_bid and best_ask else None
        print(f"[{i}] levels={len(items)} best_bid={best_bid} best_ask={best_ask} spread={spread}")
        # Show first few levels
        for it in items[:4]:
            side = "BID" if it.type == mt5.BOOK_TYPE_BUY else "ASK"
            print(f"     {side} price={it.price} vol={it.volume_dbl}")
    else:
        print(f"[{i}] No DOM data (None)")
    time.sleep(1)

mt5.market_book_release(symbol)
print("Released DOM subscription.")
mt5.shutdown()
print("Done")

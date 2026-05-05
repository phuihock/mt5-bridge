"""test_order.py — Place a small EURUSD market order and close it."""
import sys
import json
import urllib.request

REST_URL = "http://127.0.0.1:9877/rpc"

def rpc(method, params=None):
    req = urllib.request.Request(
        REST_URL,
        data=json.dumps({"method": method, "params": params or {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["result"]

# 1: Account
info = rpc("account_info")
print(f"Account: {info['login']} Balance={info['balance']} Equity={info.get('equity', 'N/A')}")

# 2: Place BUY 0.01 lots
print("\nPlacing EURUSD BUY 0.01 lots...")
result = rpc("order_send", {
    "request": {
        "action": 1,
        "symbol": "EURUSD",
        "volume": 0.01,
        "type": 0,
        "price": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": 10,
        "magic": 123456,
        "comment": "bridge test",
        "type_time": 0,
        "type_filling": 1,
    }
})
rc = result.get("retcode")
print(f"  Retcode: {rc}")

if rc == 10009:  # DONE
    ticket = result.get("order")
    price = result.get("price")
    print(f"  FILLED! Ticket={ticket} Price={price}")

    # Check position
    pos = rpc("positions_get", {"symbol": "EURUSD"})
    if pos:
        p = pos[0]
        print(f"  Position: vol={p['volume']} profit={p['profit']:.2f} swap={p['swap']:.2f}")
    else:
        print("  No position found")

    # Close
    print("\nClosing position...")
    close = rpc("order_send", {
        "request": {
            "action": 1,
            "symbol": "EURUSD",
            "volume": 0.01,
            "type": 1,
            "position": ticket,
            "price": 0.0,
            "deviation": 10,
            "magic": 123456,
            "comment": "bridge test close",
            "type_time": 0,
            "type_filling": 1,
        }
    })
    print(f"  Close retcode: {close.get('retcode')}")
    if close.get("retcode") == 10009:
        print(f"  Closed at {close.get('price')}")

elif rc == 10006:
    print(f"  REJECTED: {result.get('comment', '')}")
elif rc == 10019:
    print("  NO MONEY (insufficient margin)")
else:
    print(f"  Full result: {json.dumps(result, indent=2, default=str)}")

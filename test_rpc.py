"""test_rpc.py — Quick REST RPC tests for the MT5 bridge."""
import sys
import json
import datetime
try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

REST_URL = "http://127.0.0.1:9877/rpc"

def rpc(method: str, params: dict = None):
    resp = requests.post(REST_URL, json={"method": method, "params": params or {}}, timeout=10)
    data = resp.json()
    if "error" in data:
        print(f"  ERROR [{method}]: {data['error']}")
        return None
    return data["result"]

def test_account():
    print("=== Account Info ===")
    info = rpc("account_info")
    if info:
        print(f"  Login: {info['login']}")
        print(f"  Balance: {info['balance']}")
        print(f"  Equity: {info.get('equity', 'N/A')}")
        print(f"  Server: {info['server']}")
        print(f"  Currency: {info['currency']}")
    print()

def test_symbols():
    print("=== Forex Symbols ===")
    symbols = rpc("symbols_get", {"group": "Forex*"})
    if symbols:
        print(f"  Found {len(symbols)} forex symbols")
        for s in symbols[:5]:
            bid = s.get('bid', 'N/A')
            ask = s.get('ask', 'N/A')
            spread = s.get('spread', 'N/A')
            print(f"  {s['name']}: bid={bid} ask={ask} spread={spread}")
    else:
        symbols = rpc("symbols_get")
        if symbols:
            forex = [s for s in symbols if 'forex' in s.get('path', '').lower() or 'cfd' in s.get('path', '').lower()]
            print(f"  Total symbols: {len(symbols)}, forex/CFD: {len(forex)}")
            for s in forex[:5]:
                print(f"  {s['name']}: path={s.get('path', '')}")
    print()

def test_rates():
    print("=== EURUSD M1 (last 5 bars) ===")
    now = datetime.datetime.now()
    rates = rpc("copy_rates_range", {
        "symbol": "EURUSD",
        "timeframe": 1,  # M1
        "date_from": int((now - datetime.timedelta(hours=1)).timestamp()),
        "date_to": int(now.timestamp()),
    })
    if rates:
        for r in rates[-5:]:
            t = datetime.datetime.fromtimestamp(r['time'])
            print(f"  {t}: O={r['open']:.5f} H={r['high']:.5f} L={r['low']:.5f} C={r['close']:.5f} V={r['tick_volume']}")
    else:
        print("  No rates (might need market hours)")
    print()

def test_place_and_close():
    print("=== Place + Close Market BUY EURUSD (demo) ===")
    result = rpc("order_send", {
        "request": {
            "action": 1,           # TRADE_ACTION_DEAL
            "symbol": "EURUSD",
            "volume": 0.01,
            "type": 0,             # ORDER_TYPE_BUY
            "price": 0.0,          # market
            "sl": 0.0,
            "tp": 0.0,
            "deviation": 10,
            "magic": 123456,
            "comment": "bridge test",
            "type_time": 0,        # GTC
            "type_filling": 1,     # IOC
        }
    })
    if not result:
        print("  No result (likely market closed)")
        return

    retcode = result.get('retcode')
    print(f"  Retcode: {retcode}")
    if retcode == 10009:  # DONE
        ticket = result.get('order')
        price = result.get('price')
        print(f"  FILLED! Ticket={ticket} Price={price}")
        
        # Check position
        positions = rpc("positions_get", {"symbol": "EURUSD"})
        if positions:
            for p in positions:
                print(f"  Position: {p['symbol']} vol={p['volume']} profit={p['profit']:.2f}")
        
        # Close it
        print("  Closing...")
        close = rpc("order_send", {
            "request": {
                "action": 1,
                "symbol": "EURUSD",
                "volume": 0.01,
                "type": 1,         # ORDER_TYPE_SELL
                "position": ticket,
                "price": 0.0,
                "deviation": 10,
                "magic": 123456,
                "comment": "bridge test close",
                "type_time": 0,
                "type_filling": 1,
            }
        })
        if close:
            print(f"  Close retcode: {close.get('retcode')}")
    elif retcode == 10019:
        print("  No money (demo issue)")
    elif retcode == 10006:
        print("  Rejected (off-hours?)")
    print()

if __name__ == "__main__":
    test_account()
    test_symbols()
    test_rates()
    test_place_and_close()

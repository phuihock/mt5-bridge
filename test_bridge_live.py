"""test_bridge_live.py — Quick REST tests for MT5 bridge."""
import sys
import json
import datetime
import urllib.request

REST_URL = "http://127.0.0.1:9877/rpc"

def rpc(method, params=None):
    req = urllib.request.Request(
        REST_URL,
        data=json.dumps({"method": method, "params": params or {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def success(resp):
    return resp.get("result") if "result" in resp else resp

# 1: account
print("=== Account ===")
r = rpc("account_info")
print(json.dumps(r, indent=2))

# 2: symbols
print("\n=== First 10 symbols ===")
r = rpc("symbols_get")
syms = success(r)
for s in (syms or [])[:10]:
    print(f"  {s['name']:<10} bid={s.get('bid','N/A'):>10} ask={s.get('ask','N/A'):>10}")

# 3: rates
print("\n=== EURUSD M1 (last 5) ===")
now = datetime.datetime.now()
r = rpc("copy_rates_range", {
    "symbol": "EURUSD", "timeframe": 1,
    "date_from": int((now - datetime.timedelta(hours=1)).timestamp()),
    "date_to": int(now.timestamp()),
})
rates = success(r)
if rates:
    for bar in rates[-5:]:
        t = datetime.datetime.fromtimestamp(bar['time'])
        print(f"  {t}: O={bar['open']:.5f} H={bar['high']:.5f} L={bar['low']:.5f} C={bar['close']:.5f} V={bar['tick_volume']}")
else:
    print("  None")

print("\nBridge REST OK")

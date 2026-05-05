"""Diagnose the 500 error — capture full response."""
import sys
import json
import datetime
import urllib.request

REST_URL = "http://127.0.0.1:9877/rpc"

# Test each method individually
tests = [
    ("symbols_get", {}),
    ("copy_rates_range", {
        "symbol": "EURUSD", "timeframe": 1,
        "date_from": int((datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp()),
        "date_to": int(datetime.datetime.now().timestamp()),
    }),
]

for method, params in tests:
    req = urllib.request.Request(
        REST_URL,
        data=json.dumps({"method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        result = data.get("result") if "result" in data else data
        if isinstance(result, list):
            print(f"{method}: {len(result)} items")
            if result:
                print(f"  First: {json.dumps(result[0], indent=2)[:200]}")
        else:
            print(f"{method}: {json.dumps(result, indent=2)[:200]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"{method}: HTTP {e.code}")
        print(f"  Body: {body}")
    except Exception as e:
        print(f"{method}: {e}")

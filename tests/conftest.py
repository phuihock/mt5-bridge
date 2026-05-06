"""Shared fixtures for MT5 bridge tests."""
import json
import os
import urllib.request
import pytest

REST_URL = "http://127.0.0.1:9877/rpc"
WS_URL = "ws://127.0.0.1:9876/ws"

# API key from env (bridge started with --api-key or MT5_API_KEY)
API_KEY = os.environ.get("MT5_API_KEY", "")


def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def rpc(method, params=None):
    req = urllib.request.Request(
        REST_URL,
        data=json.dumps({"method": method, "params": params or {}}).encode(),
        headers=_headers(),
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


@pytest.fixture(scope="session")
def bridge_running():
    """Verify bridge is reachable before any tests."""
    try:
        rpc("account_info")
        return True
    except Exception:
        pytest.skip("Bridge not running at " + REST_URL)

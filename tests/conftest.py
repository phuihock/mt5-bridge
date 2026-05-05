"""Shared fixtures for MT5 bridge tests."""
import json
import urllib.request
import pytest

REST_URL = "http://127.0.0.1:9877/rpc"
WS_URL = "ws://127.0.0.1:9876/ws"


def rpc(method, params=None):
    req = urllib.request.Request(
        REST_URL,
        data=json.dumps({"method": method, "params": params or {}}).encode(),
        headers={"Content-Type": "application/json"},
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

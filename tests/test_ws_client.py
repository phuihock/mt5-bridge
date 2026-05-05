"""WebSocket bar subscription test. Requires bridge running + 65s for M1 bar."""
import asyncio
import json
import pytest
from aiohttp import ClientSession, WSMsgType

WS_URL = "ws://127.0.0.1:9876/ws"


async def _drain_ws(ws):
    """Drain initial replay bars that arrive on WS connect."""
    while True:
        try:
            await ws.receive(timeout=0.3)
        except asyncio.TimeoutError:
            return


@pytest.mark.asyncio
async def test_ws_subscribe_confirmed():
    async with ClientSession() as session:
        async with session.ws_connect(WS_URL) as ws:
            await _drain_ws(ws)
            await ws.send_json({"type": "subscribe", "symbol": "EURUSD", "timeframes": [60]})
            msg = await ws.receive(timeout=5)
            data = json.loads(msg.data)
            assert data["type"] == "subscribed"
            assert data["symbol"] == "EURUSD"
            assert data["timeframes"] == [60]
            await ws.send_json({"type": "unsubscribe", "symbol": "EURUSD"})


@pytest.mark.asyncio
async def test_ws_bar_arrives():
    """Wait up to 70s for a completed M1 bar via WS push."""
    async with ClientSession() as session:
        async with session.ws_connect(WS_URL) as ws:
            await ws.send_json({"type": "subscribe", "symbol": "EURUSD", "timeframes": [60]})
            bar_received = False
            for _ in range(70):
                try:
                    msg = await ws.receive(timeout=1)
                    if msg.type == WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data["type"] == "bars" and len(data["data"]) > 0:
                            bar = data["data"][0]
                            assert bar["symbol"] == "EURUSD"
                            assert bar["timeframe_secs"] == 60
                            assert bar["open"] > 0
                            assert bar["close"] > 0
                            bar_received = True
                            break
                except asyncio.TimeoutError:
                    pass
            await ws.send_json({"type": "unsubscribe", "symbol": "EURUSD"})
            assert bar_received, "No M1 bar received within 70s"


@pytest.mark.asyncio
async def test_ws_ping_pong():
    async with ClientSession() as session:
        async with session.ws_connect(WS_URL) as ws:
            await _drain_ws(ws)
            await ws.send_json({"type": "ping"})
            msg = await ws.receive(timeout=5)
            data = json.loads(msg.data)
            assert data["type"] == "pong"

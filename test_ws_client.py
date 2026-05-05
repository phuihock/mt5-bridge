"""test_ws_client.py — Subscribe to DOM bars via WS, watch for 30 seconds."""
import asyncio
import json
import sys
sys.path.insert(0, r'C:\Users\phuih\github\prepbot\bridge')
from aiohttp import ClientSession, WSMsgType

WS_URL = "ws://127.0.0.1:9876/ws"

async def main():
    print(f"Connecting to {WS_URL}...")
    async with ClientSession() as session:
        async with session.ws_connect(WS_URL) as ws:
            print("Connected! Sending subscribe for EURUSD M1...")
            
            await ws.send_json({
                "type": "subscribe",
                "symbol": "EURUSD",
                "timeframes": [60],
            })
            
            print("Waiting for bars. Ctrl+C to stop.\n")
            
            bar_count = 0
            while True:
                msg = await ws.receive(timeout=120)
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data["type"] == "bars":
                        for bar in data["data"]:
                            bar_count += 1
                            ts_s = bar["ts_open_ns"] / 1_000_000_000
                            import datetime
                            t = datetime.datetime.fromtimestamp(ts_s)
                            print(f"  BAR M1 {bar['symbol']} @{t}: "
                                  f"O={bar['open']:.5f} H={bar['high']:.5f} "
                                  f"L={bar['low']:.5f} C={bar['close']:.5f} "
                                  f"V={bar['volume']} ticks={bar.get('tick_count', '?')}")
                    elif data["type"] == "subscribed":
                        print(f"  Subscribed: {data}")
                    elif data["type"] == "error":
                        print(f"  ERROR: {data}")
                elif msg.type == WSMsgType.CLOSED:
                    print("WS closed")
                    break

asyncio.run(main())

"""mt5_ws_bridge.py — Windows-side bridge for Nautilus Trader MT5 adapter.

Architecture:
  - WebSocket ws://0.0.0.0:9876/ws  → push completed bars (from DOM mid-price)
  - REST     http://0.0.0.0:9877/rpc → request/response (orders, positions, symbols)

Usage:
  python mt5_ws_bridge.py
  python mt5_ws_bridge.py --mt5-path "C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"
"""

import asyncio
import os
import time
import logging
import signal
import sys
import argparse
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import orjson
import MetaTrader5 as mt5
from aiohttp import web

logger = logging.getLogger("mt5-bridge")

# ── Serialization helper ──────────────────────────────────────────────

ORJSON_OPT = orjson.OPT_UTC_Z


def _recursive_asdict(o):
    """Recursively convert MT5 structseqs to plain dicts."""
    if hasattr(o, "_asdict"):
        return {k: _recursive_asdict(v) for k, v in o._asdict().items()}
    return o


def to_python(obj):
    """Convert any MT5 return object to plain Python (recursive)."""
    if obj is None:
        return None
    if isinstance(obj, np.ndarray):
        return pd.DataFrame(obj).to_dict(orient="records")
    # _asdict check first — MT5 namedtuples inherit from tuple
    if hasattr(obj, "_asdict"):
        return _recursive_asdict(obj)
    if isinstance(obj, (tuple, list)):
        return [to_python(x) for x in obj]
    return obj


# ── DOM type constants ───────────────────────────────────────────────
# MQL5 ENUM_BOOK_TYPE: BOOK_TYPE_SELL=0 (Offer/ASK), BOOK_TYPE_BUY=1 (Bid)
# Python MetaTrader5 adds 1: BOOK_TYPE_SELL=1, BOOK_TYPE_BUY=2
# This is standard across all brokers — do NOT use price heuristics.
DOM_TYPE_BID = mt5.BOOK_TYPE_BUY  # = 2
DOM_TYPE_ASK = mt5.BOOK_TYPE_SELL  # = 1

# ── Bar Accumulator ────────────────────────────────────────────────────


@dataclass
class BarAccumulator:
    """Accumulates DOM mid-price ticks into OHLCV bars for one symbol/timeframe."""

    symbol: str
    timeframe_secs: int
    open: float = 0.0
    high: float = 0.0
    low: float = float("inf")
    close: float = 0.0
    volume: float = 0.0
    bar_open_ns: int = 0
    tick_count: int = 0
    _pending: list = field(default_factory=list)

    def on_mid_price(self, mid: float, total_vol: float, ts_ns: int):
        tf_ns = self.timeframe_secs * 1_000_000_000
        bar_start = (ts_ns // tf_ns) * tf_ns

        if self.bar_open_ns != 0 and bar_start != self.bar_open_ns:
            self._pending.append(
                {
                    "type": "bar",
                    "symbol": self.symbol,
                    "timeframe_secs": self.timeframe_secs,
                    "open": self.open,
                    "high": self.high,
                    "low": self.low if self.low != float("inf") else self.open,
                    "close": self.close,
                    "volume": int(self.volume),
                    "tick_count": self.tick_count,
                    "ts_open_ns": self.bar_open_ns,
                    "ts_close_ns": ts_ns,
                }
            )
            self.open = mid
            self.high = mid
            self.low = mid
            self.bar_open_ns = bar_start
        elif self.bar_open_ns == 0:
            self.open = mid
            self.high = mid
            self.low = mid
            self.bar_open_ns = bar_start

        self.high = max(self.high, mid)
        self.low = min(self.low, mid)
        self.close = mid
        self.volume += total_vol
        self.tick_count += 1

    def drain(self) -> list:
        out = self._pending
        self._pending = []
        return out


# ── Bridge ─────────────────────────────────────────────────────────────


class MT5WSBridge:
    """Main bridge: MT5 DOM → WS bar push + REST RPC for orders/positions."""

    def __init__(self, ws_port=9876, rest_port=9877, mt5_path: str = None, api_key: str = None):
        self.ws_port = ws_port
        self.rest_port = rest_port
        self.mt5_path = mt5_path
        self._api_key = api_key

        self._running = False
        self._ws_authenticated: set[web.WebSocketResponse] = set()
        self._accumulators: dict[tuple[str, int], BarAccumulator] = {}
        self._last_bars: dict[tuple[str, int], dict] = {}  # for WS reconnect replay

        # DOM type mapping: hard-coded per MQL5 standard
        self._bid_type = DOM_TYPE_BID  # = mt5.BOOK_TYPE_BUY = 2
        self._ask_type = DOM_TYPE_ASK  # = mt5.BOOK_TYPE_SELL = 1

        # Health
        self._mt5_ok = False
        self._last_health_check = 0.0
        self._health_check_interval = 60.0
        self._last_account_info = None

    # ── MT5 lifecycle ──────────────────────────────────────────────

    def mt5_init(self) -> bool:
        # Try auto-detect first (connects to already-running terminal).
        # Fall back to explicit path if auto-detect fails.
        ok = mt5.initialize()
        if not ok:
            logger.warning(f"Auto-detect failed: {mt5.last_error()}")
            if self.mt5_path:
                logger.info(f"Trying explicit path: {self.mt5_path}")
                ok = mt5.initialize(path=self.mt5_path)
        self._mt5_ok = ok
        if ok:
            info = mt5.terminal_info()
            self._last_account_info = mt5.account_info()
            logger.info(f"MT5: {info.name} build={info.build}")
            logger.info(f"Account: {self._last_account_info}")
        else:
            logger.error(f"MT5 init failed: {mt5.last_error()}")
        return ok

    def mt5_shutdown(self):
        try:
            mt5.shutdown()
        except Exception:
            pass
        self._mt5_ok = False
        logger.info("MT5 shut down")

    def _check_api_key(self, provided: str) -> bool:
        if not self._api_key:
            return True  # no key configured = open
        return provided == self._api_key

    def check_health(self):
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return
        self._last_health_check = now
        info = mt5.account_info()
        if info is None:
            logger.warning("Health check: MT5 disconnected, reinitializing...")
            self.mt5_shutdown()
            self.mt5_init()
        else:
            self._last_account_info = info

    # ── DOM subscription ───────────────────────────────────────────

    def subscribe_dom(self, symbol: str, timeframes_secs: list[int]):
        if not mt5.market_book_add(symbol):
            err = mt5.last_error()
            raise RuntimeError(f"market_book_add({symbol}) failed: {err}")

        for tf in timeframes_secs:
            key = (symbol, tf)
            if key not in self._accumulators:
                self._accumulators[key] = BarAccumulator(symbol, tf)
                logger.info(f"Subscribed: {symbol} TF={tf}s")

    def unsubscribe_dom(self, symbol: str):
        try:
            mt5.market_book_release(symbol)
        except Exception:
            pass
        keys = [k for k in self._accumulators if k[0] == symbol]
        for k in keys:
            del self._accumulators[k]
        logger.info(f"Unsubscribed: {symbol}")

    # ── DOM poll loop ──────────────────────────────────────────────

    async def _poll_loop(self):
        """Poll DOM every 50ms, feed accumulators, push bars to WS clients."""
        while self._running:
            try:
                self.check_health()

                symbols = set(k[0] for k in self._accumulators)
                for symbol in symbols:
                    items = mt5.market_book_get(symbol)
                    if items is None:
                        continue

                    # Extract best bid and best ask using detected types
                    best_bid = None
                    best_ask = None
                    total_vol = 0.0
                    for item in items:
                        total_vol += item.volume_dbl
                        if item.type == self._bid_type:
                            if best_bid is None or item.price > best_bid:
                                best_bid = item.price
                        elif item.type == self._ask_type:
                            if best_ask is None or item.price < best_ask:
                                best_ask = item.price

                    if best_bid is None or best_ask is None:
                        continue

                    mid = (best_bid + best_ask) / 2.0
                    ts_ns = time.time_ns()

                    for (sym, tf), acc in self._accumulators.items():
                        if sym == symbol:
                            acc.on_mid_price(mid, total_vol, ts_ns)

                # Drain and push
                all_bars = []
                for key, acc in self._accumulators.items():
                    bars = acc.drain()
                    for bar in bars:
                        self._last_bars[key] = bar
                    all_bars.extend(bars)

                if all_bars:
                    msg = orjson.dumps({"type": "bars", "data": all_bars}, option=ORJSON_OPT).decode()
                    dead = set()
                    for ws in self._ws_authenticated:
                        try:
                            await ws.send_str(msg)
                        except Exception:
                            dead.add(ws)
                    self._ws_authenticated -= dead

            except Exception as e:
                logger.error(f"Poll loop error: {e}", exc_info=True)

            await asyncio.sleep(0.05)

    # ── WebSocket handler ──────────────────────────────────────────

    async def _ws_handler(self, request):
        ws = web.WebSocketResponse(max_msg_size=65536)
        await ws.prepare(request)

        # First message MUST be auth
        try:
            msg = await ws.receive(timeout=10)
            if msg.type != web.WSMsgType.TEXT:
                await ws.close(code=4000, message=b"Auth required")
                return ws
            data = orjson.loads(msg.data)
            if data.get("type") != "auth" or not self._check_api_key(data.get("api_key", "")):
                await ws.send_str(orjson.dumps({"type": "error", "message": "invalid api_key"}, option=ORJSON_OPT).decode())
                await ws.close(code=4001, message=b"Invalid api_key")
                return ws
        except asyncio.TimeoutError:
            await ws.close(code=4000, message=b"Auth timeout")
            return ws

        self._ws_authenticated.add(ws)
        logger.info(f"WS client authenticated ({len(self._ws_authenticated)} total)")

        # Replay last bars for reconnecting client
        if self._last_bars:
            replay = list(self._last_bars.values())
            await ws.send_str(orjson.dumps({"type": "bars", "data": replay}, option=ORJSON_OPT).decode())

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = orjson.loads(msg.data)
                        await self._handle_ws_message(ws, data)
                    except orjson.JSONDecodeError:
                        logger.warning(f"Bad WS JSON: {msg.data}")
                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning(f"WS error: {ws.exception()}")
                    break
        finally:
            self._ws_authenticated.discard(ws)
            logger.info(f"WS client left ({len(self._ws_authenticated)} remaining)")
        return ws

    async def _handle_ws_message(self, ws, data: dict):
        cmd = data.get("type")
        if cmd == "subscribe":
            symbol = data["symbol"]
            timeframes = data.get("timeframes", [60])
            try:
                self.subscribe_dom(symbol, timeframes)
                await ws.send_str(orjson.dumps(
                    {"type": "subscribed", "symbol": symbol, "timeframes": timeframes},
                    option=ORJSON_OPT,
                ).decode())
            except Exception as e:
                await ws.send_str(orjson.dumps(
                    {"type": "error", "message": str(e)},
                    option=ORJSON_OPT,
                ).decode())
        elif cmd == "unsubscribe":
            self.unsubscribe_dom(data["symbol"])
            await ws.send_str(orjson.dumps(
                {"type": "unsubscribed", "symbol": data["symbol"]},
                option=ORJSON_OPT,
            ).decode())
        elif cmd == "ping":
            await ws.send_str(orjson.dumps({"type": "pong"}, option=ORJSON_OPT).decode())
        else:
            logger.warning(f"Unknown WS command: {cmd}")

    # ── REST RPC handler ───────────────────────────────────────────

    async def _rest_handler(self, request):
        # API key via Authorization: Bearer <key> header
        auth = request.headers.get("Authorization", "")
        provided_key = auth.removeprefix("Bearer ").strip()
        if not self._check_api_key(provided_key):
            body = orjson.dumps({"error": "invalid api_key"}, option=ORJSON_OPT)
            return web.Response(body=body, status=401, content_type="application/json")

        try:
            body = await request.json()
        except (ValueError, orjson.JSONDecodeError):
            body = orjson.dumps({"error": "Invalid JSON"}, option=ORJSON_OPT)
            return web.Response(body=body, status=400, content_type="application/json")

        method = body.get("method", "")
        params = body.get("params", {})
        logger.debug(f"RPC: {method}")

        try:
            result = await self._dispatch_rpc(method, params)
            body = orjson.dumps({"result": result}, option=ORJSON_OPT)
            return web.Response(body=body, content_type="application/json")
        except Exception as e:
            logger.error(f"RPC {method} failed: {e}")
            body = orjson.dumps({"error": str(e)}, option=ORJSON_OPT)
            return web.Response(body=body, status=500, content_type="application/json")

    async def _dispatch_rpc(self, method: str, params: dict) -> any:
        if method == "initialize":
            return await asyncio.to_thread(self.mt5_init)

        elif method == "shutdown":
            await asyncio.to_thread(self.mt5_shutdown)
            return True

        elif method == "symbols_get":
            group = params.get("group")
            if group:
                return to_python(await asyncio.to_thread(mt5.symbols_get, group))
            return to_python(await asyncio.to_thread(mt5.symbols_get))

        elif method == "symbol_info":
            info = await asyncio.to_thread(mt5.symbol_info, params["symbol"])
            return to_python(info)

        elif method == "copy_rates_range":
            rates = await asyncio.to_thread(
                mt5.copy_rates_range,
                params["symbol"], params["timeframe"],
                params["date_from"], params["date_to"],
            )
            return to_python(rates)

        elif method == "copy_rates_from_pos":
            rates = await asyncio.to_thread(
                mt5.copy_rates_from_pos,
                params["symbol"], params["timeframe"],
                params.get("start_pos", 0), params.get("count", 100),
            )
            return to_python(rates)

        elif method == "market_book_add":
            ok = await asyncio.to_thread(mt5.market_book_add, params["symbol"])
            if not ok:
                raise RuntimeError(f"market_book_add failed: {mt5.last_error()}")
            return True

        elif method == "market_book_get":
            return to_python(await asyncio.to_thread(mt5.market_book_get, params["symbol"]))

        elif method == "market_book_release":
            return await asyncio.to_thread(mt5.market_book_release, params["symbol"])

        elif method == "order_send":
            res = await asyncio.to_thread(mt5.order_send, params["request"])
            return to_python(res) if res else {"retcode": -1, "comment": str(mt5.last_error())}

        elif method == "orders_get":
            symbol = params.get("symbol")
            if symbol:
                return to_python(await asyncio.to_thread(mt5.orders_get, symbol=symbol))
            return to_python(await asyncio.to_thread(mt5.orders_get))

        elif method == "positions_get":
            symbol = params.get("symbol")
            if symbol:
                return to_python(await asyncio.to_thread(mt5.positions_get, symbol=symbol))
            return to_python(await asyncio.to_thread(mt5.positions_get))

        elif method == "history_deals_get":
            deals = await asyncio.to_thread(
                mt5.history_deals_get, params["date_from"], params["date_to"]
            )
            return to_python(deals)

        elif method == "history_orders_get":
            orders = await asyncio.to_thread(
                mt5.history_orders_get, params["date_from"], params["date_to"]
            )
            return to_python(orders)

        elif method == "account_info":
            return to_python(await asyncio.to_thread(mt5.account_info))

        elif method == "terminal_info":
            return to_python(await asyncio.to_thread(mt5.terminal_info))

        elif method == "last_error":
            return mt5.last_error()

        else:
            raise ValueError(f"Unknown method: {method}")

    # ── Server lifecycle ───────────────────────────────────────────

    async def start(self):
        self._running = True
        if not await asyncio.to_thread(self.mt5_init):
            return False

        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_post("/rpc", self._rest_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        ws_site = web.TCPSite(runner, "0.0.0.0", self.ws_port)
        rest_site = web.TCPSite(runner, "0.0.0.0", self.rest_port)
        await ws_site.start()
        await rest_site.start()

        logger.info(f"Bridge: WS :{self.ws_port}/ws, REST :{self.rest_port}/rpc")

        asyncio.create_task(self._poll_loop())
        return True

    def stop(self):
        self._running = False
        # Close all WS connections
        for ws in set(self._ws_authenticated):
            try:
                ws._resp.close()  # force close underlying response
            except Exception:
                pass
        self._ws_authenticated.clear()
        symbols = set(k[0] for k in self._accumulators)
        for s in symbols:
            try:
                mt5.market_book_release(s)
            except Exception:
                pass
        self.mt5_shutdown()
        logger.info("Bridge stopped")


# ── CLI ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="MT5 Bridge for Nautilus Trader")
    parser.add_argument("--mt5-path", help="Path to terminal64.exe")
    parser.add_argument("--ws-port", type=int, default=9876)
    parser.add_argument("--rest-port", type=int, default=9877)
    parser.add_argument("--api-key", default=None, help="API key for WS & REST auth (default: from MT5_API_KEY env)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = args.api_key or os.environ.get("MT5_API_KEY")
    if api_key:
        logger.info("API key auth enabled")

    bridge = MT5WSBridge(
        ws_port=args.ws_port,
        rest_port=args.rest_port,
        mt5_path=args.mt5_path,
        api_key=api_key,
    )

    async def run():
        started = await bridge.start()
        if not started:
            sys.exit(1)
        while bridge._running:
            await asyncio.sleep(1)

    def handle_signal():
        logger.info("Shutting down...")
        bridge.stop()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_signal)
            except NotImplementedError:
                pass
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        bridge.stop()
    finally:
        loop.close()


if __name__ == "__main__":
    main()

"""Dump all MetaTrader5 integer constants.

Usage:
    python scripts/dump_mt5_constants.py       # JSON to stdout
    python scripts/dump_mt5_constants.py --py  # overwrite constants.py
"""

import json
import os
import re
import sys
import MetaTrader5 as mt5

CONSTANTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "constants.py")

PREFIX_ORDER = [
    "TRADE_ACTION", "ORDER_TYPE", "ORDER_STATE", "ORDER_TIME", "ORDER_FILLING",
    "ORDER_REASON", "POSITION_TYPE", "POSITION_REASON",
    "DEAL_TYPE", "DEAL_ENTRY", "DEAL_REASON",
    "TRADE_RETCODE", "TIMEFRAME", "BOOK_TYPE",
    "SYMBOL_TRADE_EXECUTION", "SYMBOL_TRADE_MODE", "SYMBOL_CALC_MODE",
    "SYMBOL_SWAP_MODE", "SYMBOL_CHART_MODE", "SYMBOL_ORDERS",
    "SYMBOL_OPTION_MODE", "SYMBOL_OPTION_RIGHT",
    "TICK_FLAG", "ACCOUNT_TRADE_MODE", "ACCOUNT_MARGIN_MODE",
    "ACCOUNT_STOPOUT_MODE", "COPY_TICKS", "DAY_OF_WEEK",
    "RES_S", "RES_E",
]


def _is_constant(name: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Z0-9]+(_[A-Z0-9]+)+$", name))


def extract() -> dict[str, int]:
    """Extract all integer constants, returning {name: value}."""
    result = {}
    for name in dir(mt5):
        if not _is_constant(name):
            continue
        val = getattr(mt5, name)
        if isinstance(val, int):
            result[name] = val
    return result


def _sort_key(item):
    name, val = item
    for i, prefix in enumerate(PREFIX_ORDER):
        if name.startswith(prefix):
            return (i, name)
    return (len(PREFIX_ORDER), name)


def dump_json():
    data = extract()
    print(json.dumps(data, indent=2, sort_keys=True))


def dump_py(out=None):
    """Write Python module to *out* (file-like object or path string)."""
    close = False
    if isinstance(out, str):
        out = open(out, "w", newline="")
        close = True
    elif out is None:
        out = sys.stdout
    data = extract()
    items = sorted(data.items(), key=_sort_key)

    def w(s=""):
        out.write(s)
        out.write("\n")

    w(f"# Auto-generated from MetaTrader5 {mt5.__version__}")
    w(f"# Python {mt5.__version__}")
    w()

    last_prefix = None
    for name, val in items:
        prefix = None
        for p in sorted(PREFIX_ORDER, key=len, reverse=True):
            if name.startswith(p):
                prefix = p
                break

        if prefix != last_prefix and prefix:
            w()
            w(f"# ── {prefix} ──")
            last_prefix = prefix

        w(f"{name} = {val}")
    w()

    if close:
        out.close()


if __name__ == "__main__":
    if "--py" in sys.argv:
        dump_py(CONSTANTS_PATH)
        print(f"Wrote {CONSTANTS_PATH}")
    else:
        dump_json()

"""Dump all MetaTrader5 integer constants to stdout as JSON or Python module.

Usage:
    python scripts/dump_mt5_constants.py             # pretty JSON
    python scripts/dump_mt5_constants.py --compact   # compact JSON
    python scripts/dump_mt5_constants.py --py        # Python module
"""

import argparse
import json
import re
import MetaTrader5 as mt5


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


def dump_json(compact: bool = False):
    data = extract()
    print(json.dumps(data, indent=None if compact else 2, sort_keys=True))


def dump_py():
    data = extract()
    items = sorted(data.items(), key=_sort_key)

    print(f"# Auto-generated from MetaTrader5 {mt5.__version__}")
    print(f"# Python {mt5.__version__}")
    print()

    last_prefix = None
    for name, val in items:
        # Find the longest matching prefix for a section header
        prefix = None
        for p in sorted(PREFIX_ORDER, key=len, reverse=True):
            if name.startswith(p):
                prefix = p
                break

        if prefix != last_prefix and prefix:
            print()
            print(f"# ── {prefix} ──")
            last_prefix = prefix

        print(f"{name} = {val}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dump MT5 constants")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--py", action="store_true")
    args = parser.parse_args()

    if args.py:
        dump_py()
    else:
        dump_json(compact=args.compact)

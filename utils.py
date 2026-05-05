"""Fix: numpy types in dict need conversion to Python native for JSON."""
import json
import numpy as np

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

def dict_from_mt5_row(r):
    """Convert an mt5 result row (namedtuple or numpy.void) to JSON-safe dict."""
    if hasattr(r, "_asdict"):
        d = dict(r._asdict())
    elif hasattr(r, "dtype"):
        d = {name: r[name] for name in r.dtype.names}
    else:
        d = dict(r)
    # Convert numpy types to Python natives
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        elif isinstance(v, np.bool_):
            out[k] = bool(v)
        else:
            out[k] = v
    return out

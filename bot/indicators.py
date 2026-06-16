import numpy as np


def true_range(high, low, close):
    high, low, close = map(np.asarray, (high, low, close))
    prev_close = np.roll(close, 1)
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    tr[0] = high[0] - low[0]
    return tr


def wilder(x, period):
    """Wilder's smoothing (RMA). Seeds index period-1 with the SMA of the first `period` values."""
    x = np.asarray(x, dtype=float)
    out = np.zeros_like(x)
    if len(x) < period:
        return out
    out[period - 1] = x[:period].mean()
    for i in range(period, len(x)):
        out[i] = (out[i - 1] * (period - 1) + x[i]) / period
    return out

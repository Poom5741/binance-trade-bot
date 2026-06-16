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


def supertrend(high, low, close, length=10, mult=3.0):
    high, low, close = map(lambda a: np.asarray(a, dtype=float), (high, low, close))
    n = len(close)
    hl2 = (high + low) / 2.0
    atr = wilder(true_range(high, low, close), length)
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    trend = np.ones(n, dtype=int)
    line = np.zeros(n, dtype=float)
    for i in range(1, n):
        lower[i] = max(lower[i], lower[i - 1]) if close[i - 1] > lower[i - 1] else lower[i]
        upper[i] = min(upper[i], upper[i - 1]) if close[i - 1] < upper[i - 1] else upper[i]
        if trend[i - 1] == -1 and close[i] > upper[i - 1]:
            trend[i] = 1
        elif trend[i - 1] == 1 and close[i] < lower[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
        line[i] = lower[i] if trend[i] == 1 else upper[i]
    line[0] = lower[0]
    return trend, line

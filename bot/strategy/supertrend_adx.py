import numpy as np
from bot.indicators import supertrend, dmi_adx

LONG, SHORT, FLAT = 1, -1, 0


def signal(high, low, close, st_len=10, st_mult=3.0, adx_period=14, adx_thresh=25.0):
    """Per-bar signal: LONG/SHORT when supertrend direction agrees and ADX>thresh, else FLAT."""
    trend, _ = supertrend(high, low, close, st_len, st_mult)
    _, _, adx = dmi_adx(high, low, close, adx_period)
    strong = adx > adx_thresh
    sig = np.where(strong, trend, FLAT).astype(int)
    return sig

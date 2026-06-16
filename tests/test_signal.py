import numpy as np
from bot.strategy.supertrend_adx import signal


def test_signal_long_in_uptrend_flat_in_chop():
    n = 80
    up = np.linspace(100, 250, n)
    high = up + 1.0
    low = up - 1.0
    sig = signal(high, low, up, st_len=10, st_mult=3.0, adx_period=14, adx_thresh=25)
    assert sig.shape == up.shape
    assert sig[-1] == 1

    chop = 100 + np.tile([0.0, 1.0, 0.0, -1.0], n // 4)
    h = chop + 1.0
    l = chop - 1.0
    sig_c = signal(h, l, chop, st_len=10, st_mult=3.0, adx_period=14, adx_thresh=25)
    assert sig_c[-1] == 0

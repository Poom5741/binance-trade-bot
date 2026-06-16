import numpy as np
from bot.indicators import true_range, wilder, supertrend, dmi_adx


def test_true_range_basic():
    high = np.array([10.0, 11.0, 12.0])
    low = np.array([9.0, 9.5, 11.0])
    close = np.array([9.5, 10.5, 11.5])
    tr = true_range(high, low, close)
    assert tr.shape == (3,)
    assert np.isclose(tr[0], 1.0)
    assert np.isclose(tr[1], 1.5)
    assert np.isclose(tr[2], 1.5)


def test_wilder_seeds_with_sma():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = wilder(x, 3)
    assert np.isclose(out[2], 2.0)
    assert np.isclose(out[3], (2.0 * 2 + 4.0) / 3)


def test_supertrend_uptrend_then_downtrend():
    n = 60
    up = np.linspace(100, 200, n)
    down = np.linspace(200, 100, n)
    close = np.concatenate([up, down])
    high = close + 1.0
    low = close - 1.0
    trend, line = supertrend(high, low, close, length=10, mult=3.0)
    assert trend.shape == close.shape
    assert line.shape == close.shape
    assert trend[n - 1] == 1
    assert trend[-1] == -1


def test_adx_high_in_trend_low_in_chop():
    n = 120
    trend_close = np.linspace(100, 300, n)
    high_t = trend_close + 1.0
    low_t = trend_close - 1.0
    plus_di, minus_di, adx = dmi_adx(high_t, low_t, trend_close, period=14)
    assert adx.shape == trend_close.shape
    assert adx[-1] > 25
    assert plus_di[-1] > minus_di[-1]

    chop = 100 + np.tile([0.0, 1.0, 0.0, -1.0], n // 4)
    high_c = chop + 1.0
    low_c = chop - 1.0
    _, _, adx_c = dmi_adx(high_c, low_c, chop, period=14)
    assert adx_c[-1] < 25

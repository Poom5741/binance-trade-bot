import numpy as np
from bot.indicators import true_range, wilder


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

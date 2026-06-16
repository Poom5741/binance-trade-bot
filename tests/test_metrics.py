import numpy as np
from bot.metrics import total_return, sharpe, max_drawdown, win_rate


def test_total_return():
    equity = np.array([100.0, 110.0, 121.0])
    assert np.isclose(total_return(equity), 0.21)


def test_max_drawdown():
    equity = np.array([100.0, 120.0, 90.0, 130.0])
    assert np.isclose(max_drawdown(equity), -0.25)


def test_sharpe_zero_when_no_variance():
    equity = np.array([100.0, 100.0, 100.0])
    assert sharpe(equity) == 0.0


def test_win_rate():
    trades = [5.0, -2.0, 3.0, -1.0]
    assert np.isclose(win_rate(trades), 0.5)


def test_win_rate_empty():
    assert win_rate([]) == 0.0


from bot.metrics import stability_pick


def test_stability_pick_prefers_plateau_over_spike():
    grid = np.full((5, 5), 1.0)
    grid[0, 0] = 100.0
    grid[2, 2] = 5.0
    grid[1:4, 1:4] = 5.0
    i, j, score = stability_pick(grid, k=1.5)
    assert (i, j) == (2, 2)

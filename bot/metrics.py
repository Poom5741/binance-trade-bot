import numpy as np


def total_return(equity):
    equity = np.asarray(equity, dtype=float)
    if len(equity) < 2 or equity[0] == 0:
        return 0.0
    return equity[-1] / equity[0] - 1.0


def max_drawdown(equity):
    equity = np.asarray(equity, dtype=float)
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min())


def sharpe(equity, periods_per_year=365 * 24):
    """Annualized Sharpe from an equity curve sampled per bar. Assumes hourly bars by default."""
    equity = np.asarray(equity, dtype=float)
    if len(equity) < 3:
        return 0.0
    rets = np.diff(equity) / equity[:-1]
    if rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(periods_per_year))


def win_rate(trade_pnls):
    if len(trade_pnls) == 0:
        return 0.0
    wins = sum(1 for p in trade_pnls if p > 0)
    return wins / len(trade_pnls)


def stability_pick(grid, k=1.5):
    """Pick the 3x3-neighborhood center maximizing mean - k*std. Returns (i, j, score).
    Only interior cells (with a full 3x3 window) are candidates."""
    grid = np.asarray(grid, dtype=float)
    rows, cols = grid.shape
    best = (-np.inf, 0, 0)
    for i in range(1, rows - 1):
        for j in range(1, cols - 1):
            window = grid[i - 1:i + 2, j - 1:j + 2]
            score = window.mean() - k * window.std()
            if score > best[0]:
                best = (score, i, j)
    return best[1], best[2], best[0]

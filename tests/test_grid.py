import numpy as np
import pandas as pd
from tools.grid import compute_grid


def _trending_df(n=300):
    up = np.linspace(100, 300, n // 2)
    down = np.linspace(300, 120, n // 2)
    close = np.concatenate([up, down])
    return pd.DataFrame({
        "open_time": np.arange(len(close)),
        "open": close, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": np.ones(len(close)),
    })


def test_compute_grid_shape_and_pick():
    df = _trending_df()
    lengths = [5, 7, 9, 11, 13]
    mults = [1.0, 1.5, 2.0, 2.5, 3.0]
    grid, (si, sj) = compute_grid(
        df, lengths, mults, adx_period=14, adx_thresh=20,
        risk_pct=0.02, leverage_cap=3.0, taker_fee=0.0, funding_per_bar=0.0,
    )
    assert grid.shape == (5, 5)
    assert 0 <= si < 5 and 0 <= sj < 5

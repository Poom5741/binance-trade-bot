import numpy as np
import pandas as pd
from tools.backtest import run


def _trending_df(n=300):
    up = np.linspace(100, 300, n // 2)
    down = np.linspace(300, 120, n // 2)
    close = np.concatenate([up, down])
    return pd.DataFrame({
        "open_time": np.arange(len(close)),
        "open": close, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": np.ones(len(close)),
    })


def test_run_returns_metrics_and_oos():
    df = _trending_df()
    result = run(df, st_len=10, st_mult=3.0, adx_period=14, adx_thresh=20,
                 risk_pct=0.02, leverage_cap=3.0, starting_balance=1000.0,
                 taker_fee=0.00045, funding_per_bar=0.0)
    for key in ("total_return", "sharpe", "max_drawdown", "win_rate", "trades",
                "oos_total_return", "final_equity"):
        assert key in result
    assert result["trades"] >= 1
    assert result["final_equity"] > 0

import pandas as pd
from unittest.mock import patch
from bot.data import load


def _fake_klines(symbol, interval, start_ms, end_ms):
    return pd.DataFrame({
        "open_time": [start_ms, start_ms + 1],
        "open": [1.0, 2.0],
        "high": [1.5, 2.5],
        "low": [0.5, 1.5],
        "close": [1.2, 2.2],
        "volume": [10.0, 20.0],
    })


def test_load_fetches_then_caches(tmp_path):
    with patch("bot.data.fetch_binance_klines", side_effect=_fake_klines) as m:
        df1 = load("BTCUSDT", "1h", 0, 1, cache_dir=str(tmp_path))
        assert list(df1["close"]) == [1.2, 2.2]
        assert m.call_count == 1
        df2 = load("BTCUSDT", "1h", 0, 1, cache_dir=str(tmp_path))
        assert m.call_count == 1
        assert list(df2["close"]) == [1.2, 2.2]

import os
import time
import pandas as pd
import requests

_BINANCE_URL = "https://api.binance.com/api/v3/klines"
_COLS = ["open_time", "open", "high", "low", "close", "volume"]


def fetch_binance_klines(symbol, interval, start_ms, end_ms):
    """Fetch klines from Binance public REST, paginating 1000 bars per call."""
    rows = []
    cur = start_ms
    while cur < end_ms:
        resp = requests.get(_BINANCE_URL, params={
            "symbol": symbol, "interval": interval,
            "startTime": cur, "endTime": end_ms, "limit": 1000,
        }, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for k in batch:
            rows.append([k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
        cur = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.2)  # ponytail: crude rate-limit; swap for header-aware backoff if Binance 429s
    return pd.DataFrame(rows, columns=_COLS)


def load(symbol, interval, start_ms, end_ms, cache_dir="data/cache"):
    """Return klines as a DataFrame, reading a parquet cache if present else fetching + caching."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{symbol}_{interval}_{start_ms}_{end_ms}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    df = fetch_binance_klines(symbol, interval, start_ms, end_ms)
    df.to_parquet(path, index=False)
    return df

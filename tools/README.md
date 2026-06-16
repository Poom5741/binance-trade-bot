# Backtest Harness (Subsystem 1)

Single run:

    python -m tools.backtest --symbol BTCUSDT --interval 1h \
        --start-ms 1609459200000 --end-ms 1704067200000 \
        --threshold 0.10

Stability grid search:

    python -m tools.backtest --symbol BTCUSDT --interval 1h \
        --start-ms 1609459200000 --end-ms 1704067200000 --grid

- `--start-ms`/`--end-ms` are Unix epoch milliseconds.
- Data is fetched from Binance public API and cached to `data/cache/*.parquet`.
- Fees default to Hyperliquid taker (0.045%). Set `--funding-per-bar` to model funding.
- The OOS line reports 2nd-half return for sanity; only total return is gated.

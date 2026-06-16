import argparse
import numpy as np
import pandas as pd

from bot.data import load
from bot.strategy.supertrend_adx import signal
from bot.indicators import supertrend
from bot.exchange.backtest import BacktestExchange
from bot import metrics


def _simulate(df, st_len, st_mult, adx_period, adx_thresh,
              risk_pct, leverage_cap, starting_balance, taker_fee, funding_per_bar):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    sig = signal(high, low, close, st_len, st_mult, adx_period, adx_thresh)
    _, st_line = supertrend(high, low, close, st_len, st_mult)

    ex = BacktestExchange(starting_balance, taker_fee, funding_per_bar)
    equity_curve = []
    trade_pnls = []
    coin = "SYM"

    for i in range(len(close)):
        price = close[i]
        ex.mark(coin, price)
        pos = ex.position(coin)
        # Act on the PREVIOUS bar's completed signal/stop, fill at this bar's close.
        # Using sig[i]/st_line[i] here would be look-ahead bias (deciding and filling on the
        # same close you used to compute the signal). i==0 has no prior bar -> stay flat.
        desired = int(sig[i - 1]) if i > 0 else 0

        if pos is not None:
            ex.charge_funding(coin)

        cur_side = pos["side"] if pos else 0
        if desired != cur_side:
            if pos is not None:
                trade_pnls.append(ex.close(coin, price))
                pos = None
            if desired != 0:
                stop = st_line[i - 1]
                stop_dist = abs(price - stop) / price
                if stop_dist > 1e-6:
                    equity = ex.equity()
                    notional = (equity * risk_pct) / stop_dist
                    notional = min(notional, equity * leverage_cap)
                    if notional > 0:
                        ex.open(coin, desired, notional, price)
        equity_curve.append(ex.equity())

    if ex.position(coin) is not None:
        trade_pnls.append(ex.close(coin, close[-1]))
    equity_curve = np.array(equity_curve)
    return equity_curve, trade_pnls


def run(df, st_len=10, st_mult=3.0, adx_period=14, adx_thresh=25,
        risk_pct=0.02, leverage_cap=3.0, starting_balance=1000.0,
        taker_fee=0.00045, funding_per_bar=0.0):
    args = (st_len, st_mult, adx_period, adx_thresh, risk_pct, leverage_cap,
            starting_balance, taker_fee, funding_per_bar)
    eq, pnls = _simulate(df, *args)

    half = len(df) // 2
    oos_eq, _ = _simulate(df.iloc[half:].reset_index(drop=True), *args)

    return {
        "total_return": metrics.total_return(eq),
        "sharpe": metrics.sharpe(eq),
        "max_drawdown": metrics.max_drawdown(eq),
        "win_rate": metrics.win_rate(pnls),
        "trades": len(pnls),
        "final_equity": float(eq[-1]) if len(eq) else starting_balance,
        "oos_total_return": metrics.total_return(oos_eq),
    }


def _print_report(r, threshold):
    print("\n=== Backtest Report ===")
    print(f"Total return   : {r['total_return']*100:8.2f}%")
    print(f"OOS return     : {r['oos_total_return']*100:8.2f}%  (2nd-half, not gated)")
    print(f"Sharpe (ann.)  : {r['sharpe']:8.2f}")
    print(f"Max drawdown   : {r['max_drawdown']*100:8.2f}%")
    print(f"Win rate       : {r['win_rate']*100:8.2f}%")
    print(f"Trades         : {r['trades']}")
    print(f"Final equity   : {r['final_equity']:8.2f}")
    verdict = "PASS" if r["total_return"] >= threshold else "FAIL"
    print(f"Gate (>= {threshold*100:.1f}% total return): {verdict}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="1h")
    p.add_argument("--start-ms", type=int, required=True)
    p.add_argument("--end-ms", type=int, required=True)
    p.add_argument("--st-len", type=int, default=10)
    p.add_argument("--st-mult", type=float, default=3.0)
    p.add_argument("--adx-period", type=int, default=14)
    p.add_argument("--adx-thresh", type=float, default=25)
    p.add_argument("--risk-pct", type=float, default=0.02)
    p.add_argument("--leverage-cap", type=float, default=3.0)
    p.add_argument("--taker-fee", type=float, default=0.00045)
    p.add_argument("--funding-per-bar", type=float, default=0.0)
    p.add_argument("--threshold", type=float, default=0.10)
    p.add_argument("--grid", action="store_true", help="run stability grid search")
    args = p.parse_args()

    df = load(args.symbol, args.interval, args.start_ms, args.end_ms)

    if args.grid:
        from tools.grid import run_grid
        run_grid(df, args)
        return

    r = run(df, args.st_len, args.st_mult, args.adx_period, args.adx_thresh,
            args.risk_pct, args.leverage_cap, 1000.0, args.taker_fee, args.funding_per_bar)
    _print_report(r, args.threshold)


if __name__ == "__main__":
    main()

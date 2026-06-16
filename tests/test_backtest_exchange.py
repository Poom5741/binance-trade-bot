import numpy as np
from bot.exchange.backtest import BacktestExchange


def test_long_profit_minus_fees():
    ex = BacktestExchange(starting_balance=1000.0, taker_fee=0.0, funding_per_bar=0.0)
    ex.open("BTC", side=1, notional=1000.0, price=100.0)
    ex.mark("BTC", price=110.0)
    assert np.isclose(ex.equity(), 1100.0)
    pnl = ex.close("BTC", price=110.0)
    assert np.isclose(pnl, 100.0)
    assert np.isclose(ex.balance, 1100.0)


def test_fees_and_funding_charged():
    ex = BacktestExchange(starting_balance=1000.0, taker_fee=0.001, funding_per_bar=0.0001)
    ex.open("BTC", side=1, notional=1000.0, price=100.0)
    ex.charge_funding("BTC")
    pnl = ex.close("BTC", price=100.0)
    assert np.isclose(pnl, 0.0)
    assert np.isclose(ex.balance, 997.9)


def test_short_profit():
    ex = BacktestExchange(starting_balance=1000.0, taker_fee=0.0, funding_per_bar=0.0)
    ex.open("BTC", side=-1, notional=1000.0, price=100.0)
    pnl = ex.close("BTC", price=90.0)
    assert np.isclose(pnl, 100.0)

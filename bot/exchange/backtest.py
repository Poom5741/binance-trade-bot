from bot.exchange.base import Exchange


class BacktestExchange(Exchange):
    """Simulated perps exchange. Applies a taker fee on open/close and a per-bar funding charge.

    funding_per_bar is a fraction of position notional charged each time charge_funding is called
    (the runner calls it once per held bar). ponytail: flat funding rate; swap for a funding series
    if accuracy matters.
    """

    def __init__(self, starting_balance=1000.0, taker_fee=0.00045, funding_per_bar=0.0):
        self.balance = float(starting_balance)
        self.taker_fee = taker_fee
        self.funding_per_bar = funding_per_bar
        self._pos = {}
        self._mark = {}

    def position(self, coin):
        return self._pos.get(coin)

    def balance_value(self):
        return self.balance

    def open(self, coin, side, notional, price):
        self.balance -= notional * self.taker_fee
        self._pos[coin] = {"side": side, "notional": notional, "entry": price}
        self._mark[coin] = price

    def mark(self, coin, price):
        self._mark[coin] = price

    def charge_funding(self, coin):
        pos = self._pos.get(coin)
        if pos:
            self.balance -= pos["notional"] * self.funding_per_bar

    def close(self, coin, price):
        pos = self._pos.pop(coin, None)
        if pos is None:
            return 0.0
        pnl = pos["side"] * (price - pos["entry"]) / pos["entry"] * pos["notional"]
        self.balance += pnl
        self.balance -= pos["notional"] * self.taker_fee
        self._mark[coin] = price
        return pnl

    def equity(self):
        """Realized balance + unrealized pnl of open positions at last mark."""
        eq = self.balance
        for coin, pos in self._pos.items():
            price = self._mark.get(coin, pos["entry"])
            eq += pos["side"] * (price - pos["entry"]) / pos["entry"] * pos["notional"]
        return eq

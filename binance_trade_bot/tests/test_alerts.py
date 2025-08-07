from datetime import datetime, timedelta

from binance_trade_bot.alerts import AlertManager


def collect():
    msgs = []

    def notifier(msg, priority):
        msgs.append((msg, priority))

    return msgs, notifier


def test_market_volatility_alert():
    messages, notifier = collect()
    manager = AlertManager(notifier, volatility_threshold=0.1)
    manager.check_market_volatility([100, 120, 90], "BTC")
    assert messages, "volatility alert should be emitted"
    assert "volatility" in messages[0][0]


def test_exceptional_performance_alert():
    messages, notifier = collect()
    manager = AlertManager(notifier, exceptional_change=0.1)
    manager.notify_coin_performance("ETH", 0.15)
    assert messages and "moved" in messages[0][0]


def test_trade_frequency_alert():
    messages, notifier = collect()
    manager = AlertManager(notifier, trade_frequency_threshold=5)
    now = datetime.utcnow()
    trade_times = [now - timedelta(minutes=i * 5) for i in range(6)]
    manager.monitor_trade_frequency(trade_times)
    assert messages and "High trading frequency" in messages[0][0]


def test_api_error_tracking():
    messages, notifier = collect()
    manager = AlertManager(notifier, api_error_threshold=3)
    for _ in range(3):
        manager.track_api_error(Exception("boom"))
    assert messages and messages[0][1] == "critical"


def test_portfolio_change_and_rate_limit():
    messages, notifier = collect()
    manager = AlertManager(notifier, portfolio_change_threshold=0.1, rate_limit_seconds=1000)
    manager.check_portfolio_change(1000)
    manager.check_portfolio_change(1200)
    manager.check_portfolio_change(1080)  # rate limited
    # Only first change triggers alert
    assert len(messages) == 1 and "Portfolio value changed" in messages[0][0]


def test_rate_limiting_and_priority_bypass():
    messages, notifier = collect()
    manager = AlertManager(notifier, rate_limit_seconds=1000)
    manager._alert("repeat", key="r")
    manager._alert("repeat", key="r")
    manager._alert("critical", priority="critical", key="c")
    manager._alert("critical", priority="critical", key="c")
    assert len(messages) == 3
    assert messages[-1][1] == "critical"

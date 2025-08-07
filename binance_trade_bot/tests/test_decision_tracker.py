import math

from binance_trade_bot.decision_tracker import DecisionTracker


def test_log_and_performance_summary():
    tracker = DecisionTracker()
    record1 = tracker.log_decision("buy", "BTC", "trend up")
    tracker.record_result(record1, 0.1)
    record2 = tracker.log_decision("sell", "ETH", "stop loss")
    tracker.record_result(record2, -0.05)

    assert tracker.decisions[0].reason == "trend up"
    summary = tracker.performance_summary()
    assert summary["trades"] == 2
    assert math.isclose(summary["average_result"], (0.1 - 0.05) / 2)

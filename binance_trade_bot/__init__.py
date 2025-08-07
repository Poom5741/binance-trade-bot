try:
    from .backtest import backtest
except Exception:  # pragma: no cover
    backtest = None  # type: ignore

try:
    from .binance_api_manager import BinanceAPIManager
except Exception:  # pragma: no cover
    BinanceAPIManager = None  # type: ignore

try:
    from .crypto_trading import main as run_trader
except Exception:  # pragma: no cover
    run_trader = None  # type: ignore

try:
    from .alerts import AlertManager
except Exception:  # pragma: no cover
    AlertManager = None  # type: ignore

try:
    from .decision_tracker import DecisionTracker
except Exception:  # pragma: no cover
    DecisionTracker = None  # type: ignore

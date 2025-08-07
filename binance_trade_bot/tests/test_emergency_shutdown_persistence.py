import json
from pathlib import Path
from unittest.mock import Mock

import pytest

try:
    import sqlalchemy  # type: ignore
except Exception:  # pragma: no cover
    sqlalchemy = None
    pytest.skip("SQLAlchemy not installed", allow_module_level=True)

from binance_trade_bot.risk_management.emergency_shutdown_manager import EmergencyShutdownManager, ShutdownReason
from binance_trade_bot.state_persistence import StatePersistence


def test_preserve_trading_state_writes_file(tmp_path):
    persistence = StatePersistence(tmp_path / "state.json")
    database = Mock()
    database.db_session.return_value.__enter__.return_value = Mock()
    logger = Mock()
    notification = Mock()
    manager = EmergencyShutdownManager(database, logger, {}, notification, persistence=persistence)
    manager.shutdown_triggered_at = __import__('datetime').datetime.utcnow()
    manager.shutdown_reason = ShutdownReason.MANUAL_SHUTDOWN
    manager.shutdown_triggered_by = "tester"
    manager._preserve_trading_state()
    assert (tmp_path / "state.json").exists()
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["shutdown_reason"] == ShutdownReason.MANUAL_SHUTDOWN.value

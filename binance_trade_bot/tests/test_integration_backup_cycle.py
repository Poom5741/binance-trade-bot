from pathlib import Path

from binance_trade_bot.state_persistence import StatePersistence
from binance_trade_bot.backup_manager import BackupManager


def test_state_and_backup_cycle(tmp_path):
    state_file = tmp_path / "state.json"
    persistence = StatePersistence(state_file)
    persistence.save({"alpha": 1})
    assert state_file.exists()

    db_path = tmp_path / "db.sqlite"
    import sqlite3
    sqlite3.connect(db_path).close()
    bm = BackupManager(db_path, tmp_path / "backups")
    bm.backup_trading_history([{"alpha": 1}])
    bm.backup_database()

    assert any((tmp_path / "backups").glob("trades_*.json"))
    assert any((tmp_path / "backups").glob("db_*.db"))

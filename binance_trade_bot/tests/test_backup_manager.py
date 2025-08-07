import json
import sqlite3
import time
from pathlib import Path

from binance_trade_bot.backup_manager import BackupManager


def _create_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t(id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def test_backup_trading_history_creates_file_and_archives_old(tmp_path):
    bm = BackupManager(tmp_path / "db.sqlite", tmp_path / "backups", max_backups=2)
    history = [{"id": 1, "result": "win"}]
    bm.backup_trading_history(history)
    time.sleep(0.002)
    bm.backup_trading_history(history)
    time.sleep(0.002)
    bm.backup_trading_history(history)
    backups = list((tmp_path / "backups").glob("trades_*.json"))
    assert len(backups) == 2
    data = json.loads(backups[-1].read_text())
    assert data[0]["id"] == 1


def test_detect_and_recover_db_from_backup(tmp_path):
    db_path = tmp_path / "db.sqlite"
    _create_db(db_path)
    bm = BackupManager(db_path, tmp_path / "backups")
    bm.backup_database()
    db_path.write_text("corruption")
    assert bm.detect_and_recover_db() is True
    # Should be able to connect again
    sqlite3.connect(db_path).close()


def test_schedule_backup_non_blocking(tmp_path):
    db_path = tmp_path / "db.sqlite"
    _create_db(db_path)
    bm = BackupManager(db_path, tmp_path / "backups")

    history = [{"id": 1}]

    def provider():
        return history

    timer = bm.schedule_backup(0.1, provider)
    time.sleep(0.25)
    timer.cancel()
    assert any((tmp_path / "backups").glob("trades_*.json"))
    assert any((tmp_path / "backups").glob("db_*.db"))

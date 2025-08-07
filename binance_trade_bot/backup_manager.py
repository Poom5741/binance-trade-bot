import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Dict, Any


class BackupManager:
    """Simple backup and recovery utilities for the trading bot.

    The manager handles periodic backups of trading history and the main
    database file. Backups are rotated to keep only a limited number of
    snapshots to avoid unbounded storage growth. When corruption is detected
    in the primary database, the most recent backup is restored.
    """

    def __init__(self, db_path: Path, backup_dir: Path, max_backups: int = 5):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups

    # ------------------------------------------------------------------
    # Backup helpers
    # ------------------------------------------------------------------
    def backup_trading_history(self, history: Iterable[Dict[str, Any]]) -> Path:
        """Persist *history* as JSON in the backup directory."""
        timestamp = int(time.time() * 1000)
        backup_file = self.backup_dir / f"trades_{timestamp}.json"
        backup_file.write_text(json.dumps(list(history), indent=2))
        self._prune_old_backups(pattern="trades_*.json")
        return backup_file

    def backup_database(self) -> Path:
        """Create a copy of the SQLite database in the backup directory."""
        timestamp = int(time.time() * 1000)
        backup_file = self.backup_dir / f"db_{timestamp}.db"
        if self.db_path.exists():
            shutil.copy(self.db_path, backup_file)
        self._prune_old_backups(pattern="db_*.db")
        return backup_file

    # ------------------------------------------------------------------
    # Recovery helpers
    # ------------------------------------------------------------------
    def detect_and_recover_db(self) -> bool:
        """Detect SQLite corruption and recover from the latest backup.

        Returns ``True`` if the database is usable after the call.
        """
        try:
            sqlite3.connect(self.db_path).close()
            return True
        except Exception:
            backups = sorted(self.backup_dir.glob("db_*.db"), reverse=True)
            if backups:
                shutil.copy(backups[0], self.db_path)
                return True
            return False

    def safe_fallback(self) -> None:
        """Create a blank database file when recovery is impossible."""
        self.db_path.write_text("")

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def schedule_backup(self, interval: int, history_provider: Callable[[], Iterable[Dict[str, Any]]]):
        """Schedule periodic backups in a background thread.

        The operation is non-blocking and returns the ``threading.Timer``
        instance so callers can cancel it if needed.
        """

        def _run():
            self.backup_trading_history(history_provider())
            self.backup_database()
            self.schedule_backup(interval, history_provider)

        timer = threading.Timer(interval, _run)
        timer.daemon = True
        timer.start()
        return timer

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _prune_old_backups(self, pattern: str) -> None:
        backups = sorted(self.backup_dir.glob(pattern))
        while len(backups) > self.max_backups:
            old = backups.pop(0)
            old.unlink(missing_ok=True)

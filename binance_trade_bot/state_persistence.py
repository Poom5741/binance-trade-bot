import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


class StatePersistence:
    """Simple JSON-based persistence for configuration and runtime state."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or "bot_state.json")
        self.log = logging.getLogger(__name__)

    def save(self, data: Dict[str, Any]) -> None:
        """Persist *data* to disk as JSON.

        Errors are logged but not raised to avoid interrupting shutdown flows.
        """
        try:
            self.path.write_text(json.dumps(data, indent=2))
        except Exception as exc:  # pragma: no cover - logging only
            self.log.error("Failed to persist state: %s", exc)

    def load(self) -> Dict[str, Any]:
        """Load previously persisted state if it exists."""
        try:
            if self.path.exists():
                return json.loads(self.path.read_text())
        except Exception as exc:  # pragma: no cover - logging only
            self.log.error("Failed to load state: %s", exc)
        return {}

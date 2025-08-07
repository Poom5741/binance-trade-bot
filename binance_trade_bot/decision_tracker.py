from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - optional runtime dependency
    from .logger import Logger


@dataclass
class DecisionRecord:
    """Represents a single trading decision and its outcome."""

    timestamp: datetime
    action: str
    symbol: str
    reason: str
    result: Optional[float] = None  # profit/loss percentage or other metric


class DecisionTracker:
    """Tracks trading decisions and their outcomes for analysis."""

    def __init__(self, logger: Optional["Logger"] = None):
        self.logger = logger
        self.decisions: List[DecisionRecord] = []

    def log_decision(self, action: str, symbol: str, reason: str) -> DecisionRecord:
        """Record a trading decision with reasoning."""

        record = DecisionRecord(datetime.utcnow(), action, symbol, reason)
        self.decisions.append(record)

        if self.logger:
            self.logger.info(
                f"Decision logged: action={action}, symbol={symbol}, reason={reason}",
                notification=False,
            )
        return record

    def record_result(self, record: DecisionRecord, result: float) -> None:
        """Attach an outcome metric (e.g., profit percentage) to a decision."""

        record.result = result
        if self.logger:
            self.logger.info(
                f"Decision result: action={record.action}, symbol={record.symbol}, result={result}",
                notification=False,
            )

    def performance_summary(self) -> dict:
        """Summarize outcomes across all completed decisions."""

        completed = [d.result for d in self.decisions if d.result is not None]
        if not completed:
            return {"trades": 0, "average_result": 0.0}
        avg = sum(completed) / len(completed)
        return {"trades": len(completed), "average_result": avg}

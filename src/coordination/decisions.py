from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DecisionRecord:
    decision_id: str
    timestamp: int
    category: str
    problem: str
    decision: str
    reason: str
    participants: list[str] = field(default_factory=list)
    action: str = ""
    result: str = "Resolved safely with zero collisions"
    resolution_time_ticks: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "problem": self.problem,
            "decision": self.decision,
            "reason": self.reason,
            "participants": list(self.participants),
            "action": self.action,
            "result": self.result,
            "resolution_time_ticks": self.resolution_time_ticks,
        }


class DecisionLogger:
    """Maintains an auditable, structured record of every autonomous operational decision."""

    def __init__(self) -> None:
        self.records: list[DecisionRecord] = []
        self._counter: int = 1000

    def log_decision(
        self,
        timestamp: int,
        category: str,
        problem: str,
        decision: str,
        reason: str,
        participants: list[str] | None = None,
        action: str = "",
        result: str = "Resolved safely with zero collisions",
        resolution_time_ticks: int = 1,
    ) -> DecisionRecord:
        self._counter += 1
        record = DecisionRecord(
            decision_id=f"DEC-{self._counter}",
            timestamp=timestamp,
            category=category,
            problem=problem,
            decision=decision,
            reason=reason,
            participants=list(participants or []),
            action=action or decision,
            result=result,
            resolution_time_ticks=resolution_time_ticks,
        )
        self.records.append(record)
        return record

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records[-limit:]]

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]

    def clear(self) -> None:
        self.records.clear()

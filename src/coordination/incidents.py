from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IncidentSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IncidentStatus(Enum):
    OPEN = "OPEN"
    ANALYZING = "ANALYZING"
    RESOLVING = "RESOLVING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


@dataclass
class Incident:
    id: str
    timestamp: int
    incident_type: str
    severity: IncidentSeverity
    affected_entities: dict[str, list[str]] = field(default_factory=dict)
    detected_by: str = "SystemMonitor"
    decision: str = "Pending triage"
    action: str = "None"
    status: IncidentStatus = IncidentStatus.OPEN
    resolution_time: int | None = None
    impact: str = "Nominal operations"
    escalation_details: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.incident_type,
            "severity": self.severity.value,
            "affected_entities": self.affected_entities,
            "detected_by": self.detected_by,
            "decision": self.decision,
            "action": self.action,
            "status": self.status.value,
            "resolution_time": self.resolution_time,
            "impact": self.impact,
            "escalation_details": self.escalation_details,
        }


class IncidentManager:
    """
    Organizational incident lifecycle management and escalation engine.
    Tracks active operational disruptions, triages actions, and triggers
    transparent human escalations when safety boundaries are exceeded.
    """

    def __init__(self) -> None:
        self.incidents: dict[str, Incident] = {}
        self._next_id = 101

    def raise_incident(
        self,
        incident_type: str,
        severity: IncidentSeverity,
        timestamp: int,
        affected_entities: dict[str, list[str]],
        detected_by: str = "AutomatedWatchdog",
        decision: str = "Initiating automated resolution",
        action: str = "Triage in progress",
        impact: str = "Local operational diversion",
    ) -> Incident:
        inc_id = f"INC-{self._next_id}"
        self._next_id += 1
        incident = Incident(
            id=inc_id,
            timestamp=timestamp,
            incident_type=incident_type,
            severity=severity,
            affected_entities=affected_entities,
            detected_by=detected_by,
            decision=decision,
            action=action,
            status=IncidentStatus.OPEN,
            impact=impact,
        )
        self.incidents[inc_id] = incident
        return incident

    def update_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        decision: str | None = None,
        action: str | None = None,
    ) -> Incident | None:
        inc = self.incidents.get(incident_id)
        if not inc:
            return None
        inc.status = status
        if decision:
            inc.decision = decision
        if action:
            inc.action = action
        return inc

    def resolve(self, incident_id: str, timestamp: int, outcome_action: str) -> Incident | None:
        inc = self.incidents.get(incident_id)
        if not inc:
            return None
        inc.status = IncidentStatus.RESOLVED
        inc.resolution_time = timestamp
        inc.action = outcome_action
        return inc

    def escalate(
        self,
        incident_id: str,
        why: str,
        blocked: str,
        attempted_options: str,
        human_action_required: str,
    ) -> Incident | None:
        """Escalates an incident when autonomous solutions cannot guarantee safety or SLA."""
        inc = self.incidents.get(incident_id)
        if not inc:
            return None
        inc.status = IncidentStatus.ESCALATED
        inc.severity = IncidentSeverity.CRITICAL
        inc.escalation_details = {
            "why": why,
            "blocked": blocked,
            "attempted_options": attempted_options,
            "human_action_required": human_action_required,
        }
        inc.decision = f"ESCALATION REQUIRED: {why}"
        inc.action = f"Alerted human operator: {human_action_required}"
        return inc

    def get_active(self) -> list[Incident]:
        return [i for i in self.incidents.values() if i.status != IncidentStatus.RESOLVED]

    def get_all(self) -> list[Incident]:
        return list(self.incidents.values())

    def to_list(self) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self.incidents.values()]

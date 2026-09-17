from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    kind: str
    sender: str
    receiver: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class PeerNetwork:
    """Minimal decentralized peer-to-peer communication simulation."""

    def __init__(self, range_m: float = 10.0, latency: float = 0.1, packet_loss: float = 0.0):
        self.range_m = range_m
        self.latency = latency
        self.packet_loss = packet_loss
        self.messages: deque[Message] = deque()
        self.sent_count = 0

    def send(self, sender: str, receiver: str | None, kind: str, payload: dict | None = None) -> Message | None:
        payload = payload or {}
        if receiver is not None and self.packet_loss > 0 and self.packet_loss >= 1.0:
            return None
        msg = Message(kind=kind, sender=sender, receiver=receiver, payload=payload, timestamp=float(len(self.messages)))
        self.messages.append(msg)
        self.sent_count += 1
        return msg

    def broadcast(self, sender: str, kind: str, payload: dict | None = None) -> list[Message]:
        msg = self.send(sender, None, kind, payload)
        return [msg] if msg is not None else []

    def get_recent_messages(self, limit: int = 10) -> list[Message]:
        return list(self.messages)[-limit:]

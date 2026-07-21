#!/usr/bin/env python3
"""Thread-sicheres internes Ereignissystem für PowerGateway."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    name: str
    payload: dict[str, Any]
    source: str
    timestamp: str


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self, history_size: int = 200) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._history: deque[Event] = deque(maxlen=history_size)
        self._lock = RLock()

    def subscribe(self, name: str, handler: Handler) -> None:
        with self._lock:
            if handler not in self._handlers[name]:
                self._handlers[name].append(handler)

    def unsubscribe(self, name: str, handler: Handler) -> None:
        with self._lock:
            if handler in self._handlers.get(name, []):
                self._handlers[name].remove(handler)

    def publish(self, name: str, payload: dict[str, Any] | None = None, source: str = "core") -> Event:
        event = Event(
            name=name,
            payload=dict(payload or {}),
            source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._history.append(event)
            handlers = list(self._handlers.get(name, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            handler(event)
        return event

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._history)[-max(1, min(limit, 200)):]
        return [asdict(event) for event in events]


bus = EventBus()

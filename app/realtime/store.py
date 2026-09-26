from __future__ import annotations

from datetime import datetime
from threading import RLock

from app.realtime.contracts import (
    RealtimeEvent,
    RealtimeEventType,
    RealtimeFact,
)


class RealtimeFactStore:
    """
    Thread-safe in-memory latest-state store.

    REALTIME-1A intentionally persists no history by default.
    The store keeps only the latest fact for each (kind, location) key.
    """

    def __init__(
        self,
        *,
        event_bus=None,
    ) -> None:
        self._lock = RLock()
        self._latest: dict[
            tuple[str, str | None],
            RealtimeFact,
        ] = {}
        self._event_bus = event_bus

    def put(
        self,
        fact: RealtimeFact,
    ) -> bool:
        key = fact.storage_key

        with self._lock:
            previous = self._latest.get(
                key
            )

            if (
                previous is not None
                and fact.observed_at < previous.observed_at
            ):
                return False

            if previous == fact:
                return False

            self._latest[key] = fact

        self._publish(
            RealtimeEvent(
                event_type=(
                    RealtimeEventType.ADDED
                    if previous is None
                    else RealtimeEventType.UPDATED
                ),
                fact=fact,
                previous_fact=previous,
            )
        )

        return True

    def get_latest(
        self,
        kind: str,
        *,
        location: str | None = None,
        at: datetime | None = None,
        allow_expired: bool = False,
    ) -> RealtimeFact | None:
        key = (
            kind.strip(),
            location.strip()
            if location
            else None,
        )

        with self._lock:
            fact = self._latest.get(
                key
            )

        if fact is None:
            return None

        if (
            at is not None
            and not allow_expired
            and fact.is_expired(
                at=at
            )
        ):
            return None

        return fact

    def snapshot(
        self,
        *,
        at: datetime | None = None,
        include_expired: bool = False,
    ) -> tuple[RealtimeFact, ...]:
        with self._lock:
            facts = tuple(
                self._latest.values()
            )

        if at is None or include_expired:
            return facts

        return tuple(
            fact
            for fact in facts
            if not fact.is_expired(
                at=at
            )
        )

    def purge_expired(
        self,
        *,
        at: datetime,
    ) -> int:
        removed: list[
            RealtimeFact
        ] = []

        with self._lock:
            for key, fact in tuple(
                self._latest.items()
            ):
                if not fact.is_expired(
                    at=at
                ):
                    continue

                removed.append(
                    fact
                )
                del self._latest[
                    key
                ]

        for fact in removed:
            self._publish(
                RealtimeEvent(
                    event_type=RealtimeEventType.EXPIRED,
                    fact=fact,
                )
            )

        return len(
            removed
        )

    def remove(
        self,
        kind: str,
        *,
        location: str | None = None,
    ) -> bool:
        key = (
            kind.strip(),
            location.strip()
            if location
            else None,
        )

        with self._lock:
            fact = self._latest.pop(
                key,
                None,
            )

        if fact is None:
            return False

        self._publish(
            RealtimeEvent(
                event_type=RealtimeEventType.REMOVED,
                fact=fact,
            )
        )

        return True

    def clear(self) -> None:
        with self._lock:
            self._latest.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(
                self._latest
            )

    def _publish(
        self,
        event: RealtimeEvent,
    ) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            event
        )

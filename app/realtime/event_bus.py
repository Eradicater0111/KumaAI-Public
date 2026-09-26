from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable
from uuid import uuid4

from app.realtime.contracts import RealtimeEvent


RealtimeCallback = Callable[
    [RealtimeEvent],
    None,
]


@dataclass(frozen=True, slots=True)
class _Subscription:
    token: str
    callback: RealtimeCallback
    kind: str | None


class RealtimeEventBus:
    """
    Synchronous event bus for realtime state changes.

    Subscriber failures are isolated from the publisher. Publishing an
    event does not execute KUMA tools or grant action authority.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._subscriptions: dict[
            str,
            _Subscription,
        ] = {}

    def subscribe(
        self,
        callback: RealtimeCallback,
        *,
        kind: str | None = None,
    ) -> str:
        if not callable(
            callback
        ):
            raise TypeError(
                "callback must be callable."
            )

        token = uuid4().hex

        subscription = _Subscription(
            token=token,
            callback=callback,
            kind=(
                kind.strip()
                if kind
                else None
            ),
        )

        with self._lock:
            self._subscriptions[
                token
            ] = subscription

        return token

    def unsubscribe(
        self,
        token: str,
    ) -> bool:
        with self._lock:
            return (
                self._subscriptions.pop(
                    token,
                    None,
                )
                is not None
            )

    def publish(
        self,
        event: RealtimeEvent,
    ) -> int:
        with self._lock:
            subscriptions = tuple(
                self._subscriptions.values()
            )

        delivered = 0

        for subscription in subscriptions:
            if (
                subscription.kind is not None
                and subscription.kind != event.fact.kind
            ):
                continue

            try:
                subscription.callback(
                    event
                )
            except Exception:
                continue

            delivered += 1

        return delivered

    def subscriber_count(self) -> int:
        with self._lock:
            return len(
                self._subscriptions
            )

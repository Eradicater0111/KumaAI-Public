from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import RLock

from app.realtime.change_detection import (
    RealtimeChangeDetector,
    RealtimeRelevanceLevel,
)
from app.realtime.event_bus import RealtimeEventBus
from app.realtime.location_adapter import ingest_location_evidence
from app.realtime.scheduler import RealtimeScheduler
from app.realtime.store import RealtimeFactStore
from app.realtime.weather_provider import OpenMeteoWeatherProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RealtimeRuntime:
    """Safe zero-authority live-process owner for KUMA realtime state."""

    def __init__(
        self,
        *,
        clock=None,
        weather_provider=None,
        max_pending_signals: int = 32,
    ) -> None:
        if (
            not isinstance(max_pending_signals, int)
            or max_pending_signals <= 0
        ):
            raise ValueError(
                "max_pending_signals must be a positive integer."
            )

        self._clock = clock or _utc_now
        self.event_bus = RealtimeEventBus()
        self.store = RealtimeFactStore(
            event_bus=self.event_bus
        )
        self.scheduler = RealtimeScheduler(
            store=self.store
        )
        self.detector = RealtimeChangeDetector()

        self.weather_provider = (
            weather_provider
            or OpenMeteoWeatherProvider(
                store=self.store,
                clock=self._clock,
            )
        )

        self._pending_signals = deque(
            maxlen=max_pending_signals
        )
        self._signal_lock = RLock()

        self._subscription_token = (
            self.event_bus.subscribe(
                self._on_event
            )
        )

    def tick(self):
        """
        Advance expiry/lifecycle at a user-turn boundary only.

        REALTIME-1F registers no autonomous provider jobs, so this does
        not read device location or perform network access.
        """

        return self.scheduler.tick(
            at=self._clock()
        )

    def observe_location_tool_result(
        self,
        result,
    ) -> bool:
        """
        Passively ingest already-authorized approximate location evidence.

        Address-mode evidence is intentionally rejected by the
        approximate-only realtime adapter.
        """

        if getattr(
            result,
            "success",
            None,
        ) is False:
            return False

        payload = getattr(
            result,
            "result",
            result,
        )

        if not isinstance(
            payload,
            str,
        ):
            return False

        if (
            "KUMA_LOCAL_LOCATION_EVIDENCE"
            not in payload
        ):
            return False

        try:
            ingest_location_evidence(
                self.store,
                payload,
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        return True

    def refresh_weather(self):
        """
        Explicit read-only weather refresh.

        REALTIME-1F never invokes this automatically. A future explicit
        weather-routing phase may call it when user intent warrants it.
        """

        fact = self.weather_provider.refresh()

        if fact is None:
            return None

        self.store.put(
            fact
        )

        return fact

    def refresh_weather_daily(
        self,
        *,
        period: str,
    ):
        """
        Explicit read-only daily weather refresh for today/tomorrow.

        Like refresh_weather(), this is never invoked autonomously.
        """

        fact = self.weather_provider.refresh_daily(
            period=period,
        )

        if fact is None:
            return None

        self.store.put(
            fact
        )

        return fact

    def pending_signals(self):
        with self._signal_lock:
            return tuple(
                self._pending_signals
            )

    def drain_signals(self):
        with self._signal_lock:
            signals = tuple(
                self._pending_signals
            )
            self._pending_signals.clear()

        return signals

    def _on_event(self, event) -> None:
        signal = self.detector.evaluate(
            event
        )

        if (
            signal.level
            == RealtimeRelevanceLevel.IGNORE
        ):
            return

        with self._signal_lock:
            self._pending_signals.append(
                signal
            )


_RUNTIME = None
_RUNTIME_LOCK = RLock()


def get_realtime_runtime() -> RealtimeRuntime:
    global _RUNTIME

    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = RealtimeRuntime()

        return _RUNTIME


def reset_realtime_runtime_for_tests() -> None:
    global _RUNTIME

    with _RUNTIME_LOCK:
        _RUNTIME = None

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock

from app.realtime.contracts import (
    RealtimeEvent,
    RealtimeEventType,
    RealtimeFact,
)


REALTIME_SIGNAL_AUTHORITY_NONE = "NONE"


class RealtimeRelevanceLevel(str, Enum):
    IGNORE = "ignore"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class RealtimeSignal:
    """
    Ephemeral result of realtime change evaluation.

    A signal can describe relevance, but it cannot authorize any KUMA
    action. Runtime notification/proactive behavior remains a separate
    future policy boundary.
    """

    kind: str
    level: RealtimeRelevanceLevel
    score: float
    reason: str
    fact: RealtimeFact
    previous_fact: RealtimeFact | None
    authority: str = REALTIME_SIGNAL_AUTHORITY_NONE

    def __post_init__(self) -> None:
        if self.authority != REALTIME_SIGNAL_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeSignal authority is permanently NONE."
            )

        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError(
                "RealtimeSignal.score must be between 0.0 and 1.0."
            )


class RealtimeChangeDetector:
    """
    Stateful in-memory change/relevance evaluator.

    REALTIME-1E does not notify the user, call tools, or run background
    work. It only converts RealtimeEvent objects into zero-authority
    relevance signals.

    The detector keeps only the most recent fact per kind in memory so
    that location changes can be detected even though the realtime store
    intentionally keys location facts by (kind, location).
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._last_by_kind: dict[
            str,
            RealtimeFact,
        ] = {}

    def evaluate(
        self,
        event: RealtimeEvent,
    ) -> RealtimeSignal:
        if not isinstance(
            event,
            RealtimeEvent,
        ):
            raise TypeError(
                "event must be a RealtimeEvent."
            )

        with self._lock:
            remembered = self._last_by_kind.get(
                event.fact.kind
            )

            previous = (
                event.previous_fact
                or remembered
            )

            signal = self._evaluate_event(
                event,
                previous=previous,
            )

            if event.event_type in (
                RealtimeEventType.ADDED,
                RealtimeEventType.UPDATED,
            ):
                self._last_by_kind[
                    event.fact.kind
                ] = event.fact

            elif event.event_type in (
                RealtimeEventType.EXPIRED,
                RealtimeEventType.REMOVED,
            ):
                current = self._last_by_kind.get(
                    event.fact.kind
                )

                if current == event.fact:
                    self._last_by_kind.pop(
                        event.fact.kind,
                        None,
                    )

            return signal

    def reset(self) -> None:
        with self._lock:
            self._last_by_kind.clear()

    def _evaluate_event(
        self,
        event: RealtimeEvent,
        *,
        previous: RealtimeFact | None,
    ) -> RealtimeSignal:
        if event.event_type in (
            RealtimeEventType.EXPIRED,
            RealtimeEventType.REMOVED,
        ):
            return self._signal(
                event,
                previous=previous,
                level=RealtimeRelevanceLevel.LOW,
                score=0.20,
                reason=(
                    "realtime fact expired"
                    if event.event_type
                    == RealtimeEventType.EXPIRED
                    else "realtime fact removed"
                ),
            )

        if previous is None:
            return self._signal(
                event,
                previous=None,
                level=RealtimeRelevanceLevel.IGNORE,
                score=0.0,
                reason="initial baseline fact",
            )

        if event.fact == previous:
            return self._signal(
                event,
                previous=previous,
                level=RealtimeRelevanceLevel.IGNORE,
                score=0.0,
                reason="no material change",
            )

        if event.fact.kind == "location.current":
            return self._evaluate_location(
                event,
                previous=previous,
            )

        if event.fact.kind == "weather.current":
            return self._evaluate_weather(
                event,
                previous=previous,
            )

        return self._signal(
            event,
            previous=previous,
            level=RealtimeRelevanceLevel.LOW,
            score=0.25,
            reason="realtime fact changed",
        )

    def _evaluate_location(
        self,
        event: RealtimeEvent,
        *,
        previous: RealtimeFact,
    ) -> RealtimeSignal:
        before = str(
            previous.location
            or ""
        ).strip()

        after = str(
            event.fact.location
            or ""
        ).strip()

        if before and after and before != after:
            return self._signal(
                event,
                previous=previous,
                level=RealtimeRelevanceLevel.HIGH,
                score=0.85,
                reason="approximate location changed",
            )

        before_value = previous.value
        after_value = event.fact.value

        if (
            isinstance(
                before_value,
                dict,
            )
            and isinstance(
                after_value,
                dict,
            )
        ):
            before_locality = str(
                before_value.get(
                    "locality"
                )
                or ""
            ).strip()

            after_locality = str(
                after_value.get(
                    "locality"
                )
                or ""
            ).strip()

            if (
                before_locality
                and after_locality
                and before_locality
                != after_locality
            ):
                return self._signal(
                    event,
                    previous=previous,
                    level=RealtimeRelevanceLevel.HIGH,
                    score=0.85,
                    reason="approximate locality changed",
                )

        return self._signal(
            event,
            previous=previous,
            level=RealtimeRelevanceLevel.IGNORE,
            score=0.05,
            reason="location refresh without material movement",
        )

    def _evaluate_weather(
        self,
        event: RealtimeEvent,
        *,
        previous: RealtimeFact,
    ) -> RealtimeSignal:
        before = (
            previous.value
            if isinstance(
                previous.value,
                dict,
            )
            else {}
        )

        after = (
            event.fact.value
            if isinstance(
                event.fact.value,
                dict,
            )
            else {}
        )

        before_precip = self._number(
            before.get(
                "precipitation_mm"
            )
        )
        after_precip = self._number(
            after.get(
                "precipitation_mm"
            )
        )

        if (
            before_precip is not None
            and after_precip is not None
        ):
            started = (
                before_precip <= 0.0
                and after_precip > 0.0
            )

            stopped = (
                before_precip > 0.0
                and after_precip <= 0.0
            )

            if started:
                return self._signal(
                    event,
                    previous=previous,
                    level=RealtimeRelevanceLevel.HIGH,
                    score=0.90,
                    reason="precipitation started",
                )

            if stopped:
                return self._signal(
                    event,
                    previous=previous,
                    level=RealtimeRelevanceLevel.MEDIUM,
                    score=0.65,
                    reason="precipitation stopped",
                )

        before_temp = self._number(
            before.get(
                "temperature_c"
            )
        )
        after_temp = self._number(
            after.get(
                "temperature_c"
            )
        )

        if (
            before_temp is not None
            and after_temp is not None
        ):
            delta = abs(
                after_temp
                - before_temp
            )

            if delta >= 5.0:
                return self._signal(
                    event,
                    previous=previous,
                    level=RealtimeRelevanceLevel.HIGH,
                    score=0.80,
                    reason="temperature changed by at least 5°C",
                )

            if delta >= 3.0:
                return self._signal(
                    event,
                    previous=previous,
                    level=RealtimeRelevanceLevel.MEDIUM,
                    score=0.60,
                    reason="temperature changed by at least 3°C",
                )

        before_code = self._number(
            before.get(
                "weather_code"
            )
        )
        after_code = self._number(
            after.get(
                "weather_code"
            )
        )

        if (
            before_code is not None
            and after_code is not None
            and before_code != after_code
        ):
            return self._signal(
                event,
                previous=previous,
                level=RealtimeRelevanceLevel.MEDIUM,
                score=0.55,
                reason="weather condition code changed",
            )

        before_wind = self._number(
            before.get(
                "wind_speed_kmh"
            )
        )
        after_wind = self._number(
            after.get(
                "wind_speed_kmh"
            )
        )

        if (
            before_wind is not None
            and after_wind is not None
            and abs(
                after_wind
                - before_wind
            ) >= 15.0
        ):
            return self._signal(
                event,
                previous=previous,
                level=RealtimeRelevanceLevel.MEDIUM,
                score=0.55,
                reason="wind speed changed by at least 15 km/h",
            )

        return self._signal(
            event,
            previous=previous,
            level=RealtimeRelevanceLevel.IGNORE,
            score=0.10,
            reason="weather refresh without material change",
        )

    @staticmethod
    def _number(
        value,
    ) -> float | None:
        if isinstance(
            value,
            bool,
        ):
            return float(
                int(
                    value
                )
            )

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            return float(
                value
            )

        return None

    @staticmethod
    def _signal(
        event: RealtimeEvent,
        *,
        previous: RealtimeFact | None,
        level: RealtimeRelevanceLevel,
        score: float,
        reason: str,
    ) -> RealtimeSignal:
        return RealtimeSignal(
            kind=event.fact.kind,
            level=level,
            score=score,
            reason=reason,
            fact=event.fact,
            previous_fact=previous,
        )

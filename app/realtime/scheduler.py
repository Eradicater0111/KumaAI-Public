from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
)
from threading import RLock
from typing import Callable, Iterable

from app.realtime.contracts import RealtimeFact
from app.realtime.store import RealtimeFactStore


RefreshCallback = Callable[
    [],
    RealtimeFact
    | Iterable[RealtimeFact]
    | None,
]


def _require_aware(
    name: str,
    value: datetime,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{name} must be timezone-aware."
        )


@dataclass(
    frozen=True,
    slots=True,
)
class RefreshExecution:
    """
    One scheduler execution result.

    This is ephemeral operational state only; the scheduler does not
    persist execution history.
    """

    name: str
    started_at: datetime
    finished_at: datetime
    success: bool
    fact_count: int
    error_type: str | None = None


@dataclass(
    slots=True,
)
class _RefreshJob:
    name: str
    interval_seconds: int
    callback: RefreshCallback
    next_run_at: datetime
    enabled: bool = True


class RealtimeScheduler:
    """
    Deterministic refresh scheduler for KUMA realtime providers.

    REALTIME-1C intentionally does NOT start its own background thread.

    REALTIME-1F binds tick() to an existing caller-owned KUMA user-turn
    boundary. The scheduler itself still does not start, own, or schedule
    a background worker.

    USER-TURN TICK != AUTONOMOUS INVOCATION
    SCHEDULE DUE != PERMISSION

    Safety:
    - callbacks only return RealtimeFact objects
    - scheduler cannot invoke KUMA tools
    - facts retain permanent AUTHORITY: NONE
    - no execution history is persisted
    - callback failures are isolated per job
    """

    def __init__(
        self,
        *,
        store: RealtimeFactStore,
    ) -> None:
        if not isinstance(
            store,
            RealtimeFactStore,
        ):
            raise TypeError(
                "store must be a RealtimeFactStore."
            )

        self._store = store
        self._lock = RLock()
        self._jobs: dict[
            str,
            _RefreshJob,
        ] = {}

    def register(
        self,
        *,
        name: str,
        interval_seconds: int,
        callback: RefreshCallback,
        now: datetime,
        run_immediately: bool = True,
    ) -> None:
        clean_name = str(
            name
        ).strip()

        if not clean_name:
            raise ValueError(
                "job name cannot be blank."
            )

        if (
            not isinstance(
                interval_seconds,
                int,
            )
            or interval_seconds <= 0
        ):
            raise ValueError(
                "interval_seconds must be a positive integer."
            )

        if not callable(
            callback
        ):
            raise TypeError(
                "callback must be callable."
            )

        _require_aware(
            "now",
            now,
        )

        with self._lock:
            if clean_name in self._jobs:
                raise ValueError(
                    f"job already registered: {clean_name}"
                )

            self._jobs[
                clean_name
            ] = _RefreshJob(
                name=clean_name,
                interval_seconds=interval_seconds,
                callback=callback,
                next_run_at=(
                    now
                    if run_immediately
                    else (
                        now
                        + timedelta(
                            seconds=interval_seconds
                        )
                    )
                ),
            )

    def unregister(
        self,
        name: str,
    ) -> bool:
        clean_name = str(
            name
        ).strip()

        with self._lock:
            return (
                self._jobs.pop(
                    clean_name,
                    None,
                )
                is not None
            )

    def set_enabled(
        self,
        name: str,
        *,
        enabled: bool,
        now: datetime | None = None,
        run_immediately: bool = False,
    ) -> None:
        clean_name = str(
            name
        ).strip()

        with self._lock:
            job = self._jobs.get(
                clean_name
            )

            if job is None:
                raise KeyError(
                    clean_name
                )

            if (
                enabled
                and not job.enabled
            ):
                if now is None:
                    raise ValueError(
                        "now is required when enabling a disabled job."
                    )

                _require_aware(
                    "now",
                    now,
                )

                job.next_run_at = (
                    now
                    if run_immediately
                    else (
                        now
                        + timedelta(
                            seconds=job.interval_seconds
                        )
                    )
                )

            job.enabled = bool(
                enabled
            )

    def due_names(
        self,
        *,
        at: datetime,
    ) -> tuple[str, ...]:
        _require_aware(
            "at",
            at,
        )

        with self._lock:
            return tuple(
                sorted(
                    job.name
                    for job in self._jobs.values()
                    if (
                        job.enabled
                        and at >= job.next_run_at
                    )
                )
            )

    def next_run_at(
        self,
        name: str,
    ) -> datetime:
        clean_name = str(
            name
        ).strip()

        with self._lock:
            job = self._jobs.get(
                clean_name
            )

            if job is None:
                raise KeyError(
                    clean_name
                )

            return job.next_run_at

    def tick(
        self,
        *,
        at: datetime,
    ) -> tuple[RefreshExecution, ...]:
        """
        Execute each due job at most once.

        Missed intervals are intentionally coalesced into one refresh.
        This avoids catch-up storms after sleep, suspend, or UI pauses.
        """

        _require_aware(
            "at",
            at,
        )

        self._store.purge_expired(
            at=at
        )

        with self._lock:
            due = tuple(
                job
                for job in self._jobs.values()
                if (
                    job.enabled
                    and at >= job.next_run_at
                )
            )

            for job in due:
                job.next_run_at = (
                    at
                    + timedelta(
                        seconds=job.interval_seconds
                    )
                )

        executions = []

        for job in sorted(
            due,
            key=lambda item: item.name,
        ):
            executions.append(
                self._run_job(
                    job,
                    at=at,
                )
            )

        return tuple(
            executions
        )

    def job_count(
        self,
    ) -> int:
        with self._lock:
            return len(
                self._jobs
            )

    def _run_job(
        self,
        job: _RefreshJob,
        *,
        at: datetime,
    ) -> RefreshExecution:
        try:
            result = job.callback()

            facts = self._normalize_facts(
                result
            )

            for fact in facts:
                self._store.put(
                    fact
                )

            return RefreshExecution(
                name=job.name,
                started_at=at,
                finished_at=at,
                success=True,
                fact_count=len(
                    facts
                ),
            )

        except Exception as error:
            return RefreshExecution(
                name=job.name,
                started_at=at,
                finished_at=at,
                success=False,
                fact_count=0,
                error_type=type(
                    error
                ).__name__,
            )

    @staticmethod
    def _normalize_facts(
        result,
    ) -> tuple[RealtimeFact, ...]:
        if result is None:
            return ()

        if isinstance(
            result,
            RealtimeFact,
        ):
            return (
                result,
            )

        try:
            facts = tuple(
                result
            )
        except TypeError as error:
            raise TypeError(
                "refresh callback must return RealtimeFact, "
                "an iterable of RealtimeFact, or None."
            ) from error

        for fact in facts:
            if not isinstance(
                fact,
                RealtimeFact,
            ):
                raise TypeError(
                    "refresh callback iterable contained a non-RealtimeFact value."
                )

        return facts

"""
KUMA-RUNTIME-2B — zero-authority session / turn / trace correlation.

Runtime-2B adds correlation identity and lifecycle boundaries on top of the
frozen Runtime-2A trace recorder without instrumenting KUMA's frozen agent,
window, voice, avatar, or execution paths yet.

Core boundaries:

- SESSION ID != USER ID
- TURN ID != PROMPT
- TRACE ID != COMMAND
- CORRELATION != AUTHORITY
- NEW TURN -> NEW TRACE
- ONE TURN -> ONE TRACE ID
- SESSION MAY SPAN TURNS
- TRACE MUST NOT SPAN UNRELATED TURNS
- RESPONSE TERMINAL != VERIFIED GOAL COMPLETION
- ERROR STILL TERMINATES A TURN
- BLOCKED STILL TERMINATES A TURN
- CORRELATION DATA != MODEL CONTEXT
- CORRELATION DATA != MEMORY
- CORRELATION AUTHORITY = NONE

The identifiers are locally-generated opaque tokens. They never contain user
text, prompts, transcripts, mission goals, account identity, device identity,
or persisted conversation content.

Runtime-2B remains additive:
- no agent imports
- no UI imports
- no voice/avatar imports
- no tool/executor imports
- no disk persistence
- no network
- no model/provider imports
- no ContextVar, thread-local, or process-global "current turn"
- no autonomous/background loop

A future integration phase can bind these lifecycle objects to real KUMA turn
boundaries. Runtime-2B itself only defines and proves the correlation contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
import secrets
from threading import RLock
from types import MappingProxyType
from typing import Callable, Mapping

from app.runtime_trace import (
    KumaRuntimeTrace,
    RuntimeTraceEvent,
    TRACE_AUTHORITY_NONE,
)


CORRELATION_AUTHORITY_NONE = (
    TRACE_AUTHORITY_NONE
)

CORRELATION_ID_MAX_CHARS = 64

_SAFE_CORRELATION_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
)


class RuntimeTurnEndKind(
    str,
    Enum,
):
    """
    Diagnostic terminal boundary for one runtime turn.

    RESPONSE means the runtime produced a response boundary. It does not mean
    the user's objective was verified complete.
    """

    RESPONSE = "response"
    ERROR = "error"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


def _normalize_correlation_id(
    value,
    *,
    field_name: str,
) -> str:
    if type(value) is not str:
        raise TypeError(
            f"{field_name} must be a string."
        )

    normalized = (
        value.strip()
    )

    if not normalized:
        raise ValueError(
            f"{field_name} must be nonempty."
        )

    if (
        len(normalized)
        > CORRELATION_ID_MAX_CHARS
    ):
        raise ValueError(
            f"{field_name} exceeds its bounded length."
        )

    if (
        _SAFE_CORRELATION_ID.fullmatch(
            normalized
        )
        is None
    ):
        raise ValueError(
            f"{field_name} must be an opaque identifier-like token."
        )

    return normalized


def _require_positive_int(
    value,
    *,
    field_name: str,
) -> int:
    if (
        type(value) is not int
        or value < 1
    ):
        raise TypeError(
            f"{field_name} must be an int >= 1."
        )

    return value


def _require_nonnegative_int(
    value,
    *,
    field_name: str,
) -> int:
    if (
        type(value) is not int
        or value < 0
    ):
        raise TypeError(
            f"{field_name} must be an int >= 0."
        )

    return value


def new_runtime_session_id() -> str:
    """
    Return a local opaque session identifier containing no user identity.
    """

    return (
        "session-"
        + secrets.token_hex(
            16
        )
    )


def new_runtime_turn_id() -> str:
    """
    Return a local opaque turn identifier containing no prompt content.
    """

    return (
        "turn-"
        + secrets.token_hex(
            16
        )
    )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeTurnCorrelation:
    """
    Immutable identity binding for exactly one runtime turn.

    One instance binds one application session, one turn identifier, and one
    Runtime-2A trace identifier. It has zero authority.
    """

    session_id: str
    turn_id: str
    trace_id: str
    turn_index: int
    started_monotonic_ns: int
    authority: str = field(
        default=(
            CORRELATION_AUTHORITY_NONE
        ),
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "session_id",
            _normalize_correlation_id(
                self.session_id,
                field_name="session_id",
            ),
        )

        object.__setattr__(
            self,
            "turn_id",
            _normalize_correlation_id(
                self.turn_id,
                field_name="turn_id",
            ),
        )

        object.__setattr__(
            self,
            "trace_id",
            _normalize_correlation_id(
                self.trace_id,
                field_name="trace_id",
            ),
        )

        _require_positive_int(
            self.turn_index,
            field_name="turn_index",
        )

        _require_nonnegative_int(
            self.started_monotonic_ns,
            field_name=(
                "started_monotonic_ns"
            ),
        )

        if (
            self.authority
            != CORRELATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime correlation authority must remain NONE."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeTurnClosure:
    """
    Immutable terminal record for one already-correlated runtime turn.

    A closure proves only that the correlation lifecycle ended. It does not
    prove successful execution, objective verification, or goal completion.
    """

    context: RuntimeTurnCorrelation
    end_kind: RuntimeTurnEndKind
    ended_monotonic_ns: int
    duration_ms: float
    authority: str = field(
        default=(
            CORRELATION_AUTHORITY_NONE
        ),
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.context,
            RuntimeTurnCorrelation,
        ):
            raise TypeError(
                "context must be RuntimeTurnCorrelation."
            )

        if not isinstance(
            self.end_kind,
            RuntimeTurnEndKind,
        ):
            raise TypeError(
                "end_kind must be RuntimeTurnEndKind."
            )

        _require_nonnegative_int(
            self.ended_monotonic_ns,
            field_name=(
                "ended_monotonic_ns"
            ),
        )

        if (
            type(self.duration_ms)
            not in (
                int,
                float,
            )
            or isinstance(
                self.duration_ms,
                bool,
            )
        ):
            raise TypeError(
                "duration_ms must be numeric."
            )

        duration = float(
            self.duration_ms
        )

        if (
            not math.isfinite(
                duration
            )
            or duration < 0.0
        ):
            raise ValueError(
                "duration_ms must be finite and nonnegative."
            )

        object.__setattr__(
            self,
            "duration_ms",
            duration,
        )

        if (
            self.ended_monotonic_ns
            < self.context.started_monotonic_ns
        ):
            raise ValueError(
                "turn closure cannot end before the turn starts."
            )

        if (
            self.authority
            != CORRELATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime correlation authority must remain NONE."
            )


def correlation_metadata(
    context: RuntimeTurnCorrelation,
) -> Mapping[
    str,
    str | int,
]:
    """
    Return immutable structural metadata suitable for Runtime-2A events.

    The mapping contains opaque correlation identifiers only. No user content
    or model content is introduced.
    """

    if not isinstance(
        context,
        RuntimeTurnCorrelation,
    ):
        raise TypeError(
            "context must be RuntimeTurnCorrelation."
        )

    return MappingProxyType(
        {
            "session.id": (
                context.session_id
            ),
            "turn.id": (
                context.turn_id
            ),
            "turn.index": (
                context.turn_index
            ),
        }
    )


def _metadata_dict(
    event: RuntimeTraceEvent,
) -> dict:
    return dict(
        event.metadata
    )


class KumaRuntimeCorrelation:
    """
    Single-session, single-active-turn correlation manager.

    The manager creates one opaque session id at construction. Each begin_turn()
    creates exactly one opaque turn id and exactly one fresh Runtime-2A trace id.
    At most one turn may be active inside a session.

    This object is diagnostic-only. It cannot authorize, execute, verify, or
    complete a KUMA task.
    """

    def __init__(
        self,
        *,
        trace: KumaRuntimeTrace
        | None = None,
        session_id_factory: Callable[
            [],
            str,
        ] = new_runtime_session_id,
        turn_id_factory: Callable[
            [],
            str,
        ] = new_runtime_turn_id,
    ):
        if (
            trace is not None
            and not isinstance(
                trace,
                KumaRuntimeTrace,
            )
        ):
            raise TypeError(
                "trace must be KumaRuntimeTrace or None."
            )

        if not callable(
            session_id_factory
        ):
            raise TypeError(
                "session_id_factory must be callable."
            )

        if not callable(
            turn_id_factory
        ):
            raise TypeError(
                "turn_id_factory must be callable."
            )

        self._trace = (
            trace
            if trace is not None
            else KumaRuntimeTrace()
        )

        self._session_id = (
            _normalize_correlation_id(
                session_id_factory(),
                field_name="session_id",
            )
        )

        self._turn_id_factory = (
            turn_id_factory
        )

        self._active_turn = None
        self._last_closure = None
        self._turn_count = 0
        self._closed = False

        self._seen_turn_ids = set()
        self._seen_trace_ids = set()

        self._lock = RLock()

    @property
    def authority(
        self,
    ) -> str:
        return (
            CORRELATION_AUTHORITY_NONE
        )

    @property
    def session_id(
        self,
    ) -> str:
        return self._session_id

    @property
    def trace(
        self,
    ) -> KumaRuntimeTrace:
        return self._trace

    @property
    def active_turn(
        self,
    ) -> RuntimeTurnCorrelation | None:
        with self._lock:
            return self._active_turn

    @property
    def last_closure(
        self,
    ) -> RuntimeTurnClosure | None:
        with self._lock:
            return self._last_closure

    @property
    def turn_count(
        self,
    ) -> int:
        with self._lock:
            return self._turn_count

    @property
    def closed(
        self,
    ) -> bool:
        with self._lock:
            return self._closed

    def begin_turn(
        self,
    ) -> RuntimeTurnCorrelation:
        """
        Begin exactly one fresh turn.

        No prompt, request text, command, goal, or user identifier is accepted.
        """

        with self._lock:
            if self._closed:
                raise RuntimeError(
                    "runtime correlation session is closed."
                )

            if (
                self._active_turn
                is not None
            ):
                raise RuntimeError(
                    "a runtime turn is already active."
                )

            turn_id = (
                _normalize_correlation_id(
                    self._turn_id_factory(),
                    field_name="turn_id",
                )
            )

            if (
                turn_id
                in self._seen_turn_ids
            ):
                raise ValueError(
                    "turn_id factory produced a duplicate identifier."
                )

            trace_id = (
                _normalize_correlation_id(
                    self._trace.start_trace(),
                    field_name="trace_id",
                )
            )

            if (
                trace_id
                in self._seen_trace_ids
            ):
                raise ValueError(
                    "trace factory produced a duplicate identifier."
                )

            next_index = (
                self._turn_count
                + 1
            )

            provisional = (
                RuntimeTurnCorrelation(
                    session_id=(
                        self._session_id
                    ),
                    turn_id=turn_id,
                    trace_id=trace_id,
                    turn_index=(
                        next_index
                    ),
                    started_monotonic_ns=0,
                )
            )

            start_event = (
                self._trace.record(
                    trace_id=trace_id,
                    stage="correlation",
                    event_kind=(
                        "turn.started"
                    ),
                    outcome="observed",
                    metadata=(
                        correlation_metadata(
                            provisional
                        )
                    ),
                )
            )

            context = (
                RuntimeTurnCorrelation(
                    session_id=(
                        self._session_id
                    ),
                    turn_id=turn_id,
                    trace_id=trace_id,
                    turn_index=(
                        next_index
                    ),
                    started_monotonic_ns=(
                        start_event.monotonic_ns
                    ),
                )
            )

            self._seen_turn_ids.add(
                turn_id
            )

            self._seen_trace_ids.add(
                trace_id
            )

            self._turn_count = (
                next_index
            )

            self._active_turn = (
                context
            )

            return context

    def _end_active_turn_locked(
        self,
        *,
        turn_id: str,
        end_kind: RuntimeTurnEndKind,
    ) -> RuntimeTurnClosure:
        active = (
            self._active_turn
        )

        if active is None:
            raise RuntimeError(
                "no runtime turn is active."
            )

        normalized_turn_id = (
            _normalize_correlation_id(
                turn_id,
                field_name="turn_id",
            )
        )

        if (
            normalized_turn_id
            != active.turn_id
        ):
            raise ValueError(
                "turn_id does not match the active runtime turn."
            )

        if not isinstance(
            end_kind,
            RuntimeTurnEndKind,
        ):
            raise TypeError(
                "end_kind must be RuntimeTurnEndKind."
            )

        metadata = dict(
            correlation_metadata(
                active
            )
        )

        metadata[
            "turn.end_kind"
        ] = (
            end_kind.value
        )

        end_event = (
            self._trace.record(
                trace_id=(
                    active.trace_id
                ),
                stage="correlation",
                event_kind=(
                    "turn.ended"
                ),
                outcome=(
                    end_kind.value
                ),
                metadata=metadata,
            )
        )

        duration_ms = (
            (
                end_event.monotonic_ns
                - active.started_monotonic_ns
            )
            / 1_000_000.0
        )

        closure = (
            RuntimeTurnClosure(
                context=active,
                end_kind=end_kind,
                ended_monotonic_ns=(
                    end_event.monotonic_ns
                ),
                duration_ms=(
                    duration_ms
                ),
            )
        )

        self._active_turn = None
        self._last_closure = (
            closure
        )

        return closure

    def end_turn(
        self,
        *,
        turn_id: str,
        end_kind: RuntimeTurnEndKind,
    ) -> RuntimeTurnClosure:
        """
        End the exact active turn.

        RESPONSE is a response boundary only and is never interpreted as
        verified goal completion.
        """

        with self._lock:
            return (
                self._end_active_turn_locked(
                    turn_id=turn_id,
                    end_kind=end_kind,
                )
            )

    def close_session(
        self,
    ) -> RuntimeTurnClosure | None:
        """
        Close the local runtime session.

        If a turn is active, it is explicitly terminated as CANCELLED so a
        trace never remains logically open across application shutdown.
        """

        with self._lock:
            if self._closed:
                return None

            closure = None

            if (
                self._active_turn
                is not None
            ):
                closure = (
                    self._end_active_turn_locked(
                        turn_id=(
                            self._active_turn
                            .turn_id
                        ),
                        end_kind=(
                            RuntimeTurnEndKind
                            .CANCELLED
                        ),
                    )
                )

            self._closed = True

            return closure

    def events_for_session(
        self,
    ) -> tuple[
        RuntimeTraceEvent,
        ...,
    ]:
        """
        Return the current bounded trace-buffer events for this session.
        """

        with self._lock:
            return tuple(
                event
                for event
                in self._trace.snapshot()
                if (
                    _metadata_dict(
                        event
                    ).get(
                        "session.id"
                    )
                    == self._session_id
                )
            )

    def events_for_turn(
        self,
        turn_id: str,
    ) -> tuple[
        RuntimeTraceEvent,
        ...,
    ]:
        normalized = (
            _normalize_correlation_id(
                turn_id,
                field_name="turn_id",
            )
        )

        with self._lock:
            return tuple(
                event
                for event
                in self._trace.snapshot()
                if (
                    _metadata_dict(
                        event
                    ).get(
                        "session.id"
                    )
                    == self._session_id
                    and _metadata_dict(
                        event
                    ).get(
                        "turn.id"
                    )
                    == normalized
                )
            )

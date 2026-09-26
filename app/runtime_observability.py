"""
KUMA-RUNTIME-2F — live zero-authority observability projection.

Runtime-2F projects the already-recorded Runtime-2A→2E structural trace
into a small immutable read model suitable for diagnostics.

It does not create events.
It does not execute capabilities.
It does not authorize actions.
It does not grant permissions.
It does not verify goals.
It does not perform recovery.
It does not write memory.
It does not persist trace data.
It does not call a model.
It does not perform network I/O.
It does not start a background worker.

TRACE != CONTROL
OBSERVATION != COMMAND
OBSERVATION != PERMISSION
OBSERVATION != EXECUTION
OBSERVATION != VERIFICATION AUTHORITY
OBSERVATION != RECOVERY AUTHORITY
RESPONSE != VERIFIED GOAL COMPLETION

AUTHORITY = NONE

Only structural fields already present in RuntimeTraceEvent are projected.
Raw metadata is never exposed by the Runtime-2F snapshot. The only metadata
values admitted into the projection are the frozen Runtime-2B correlation
identifiers:

    session.id
    turn.id
    turn.index

Reason text and arbitrary metadata are intentionally omitted.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)

from app.runtime_trace import (
    RuntimeTraceEvent,
)


RUNTIME_OBSERVABILITY_AUTHORITY_NONE = (
    "NONE"
)

RUNTIME_OBSERVABILITY_MAX_EVENTS = 256


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeObservationEvent:
    """
    Immutable payload-free projection of one structural runtime event.

    This object is diagnostic only. It carries no execution, permission,
    verification, recovery, or task-completion authority.
    """

    trace_id: str
    sequence: int
    stage: str
    event_kind: str
    monotonic_ns: int
    duration_ms: float | None
    outcome: str

    session_id: str
    turn_id: str
    turn_index: int

    authority: str = field(
        default=(
            RUNTIME_OBSERVABILITY_AUTHORITY_NONE
        ),
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        for name in (
            "trace_id",
            "stage",
            "event_kind",
            "outcome",
            "session_id",
            "turn_id",
        ):
            value = getattr(
                self,
                name,
            )

            if not isinstance(
                value,
                str,
            ):
                raise TypeError(
                    f"{name} must be a string."
                )

            if not value.strip():
                raise ValueError(
                    f"{name} cannot be blank."
                )

        if (
            type(self.sequence)
            is not int
            or self.sequence <= 0
        ):
            raise ValueError(
                "sequence must be a positive integer."
            )

        if (
            type(self.monotonic_ns)
            is not int
            or self.monotonic_ns < 0
        ):
            raise ValueError(
                "monotonic_ns must be a nonnegative integer."
            )

        if (
            type(self.turn_index)
            is not int
            or self.turn_index <= 0
        ):
            raise ValueError(
                "turn_index must be a positive integer."
            )

        if (
            self.duration_ms is not None
            and (
                isinstance(
                    self.duration_ms,
                    bool,
                )
                or not isinstance(
                    self.duration_ms,
                    (int, float),
                )
                or self.duration_ms < 0
            )
        ):
            raise ValueError(
                "duration_ms must be nonnegative numeric or None."
            )

        if (
            self.authority
            != RUNTIME_OBSERVABILITY_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime observation authority must remain NONE."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeObservationSnapshot:
    """
    Immutable bounded diagnostic projection of the current runtime trace.

    An empty snapshot means observability was unavailable or no structural
    events have been recorded. It does not imply task success or failure.
    """

    events: tuple[
        RuntimeObservationEvent,
        ...,
    ] = ()

    authority: str = field(
        default=(
            RUNTIME_OBSERVABILITY_AUTHORITY_NONE
        ),
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.events,
            tuple,
        ):
            raise TypeError(
                "events must be a tuple."
            )

        if (
            len(self.events)
            > RUNTIME_OBSERVABILITY_MAX_EVENTS
        ):
            raise ValueError(
                "runtime observation snapshot exceeds bounded capacity."
            )

        if not all(
            isinstance(
                event,
                RuntimeObservationEvent,
            )
            for event in self.events
        ):
            raise TypeError(
                "events must contain RuntimeObservationEvent values."
            )

        if (
            self.authority
            != RUNTIME_OBSERVABILITY_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime observation authority must remain NONE."
            )

    @property
    def event_count(
        self,
    ) -> int:
        return len(
            self.events
        )


def project_runtime_observation(
    events: tuple[
        RuntimeTraceEvent,
        ...,
    ],
) -> RuntimeObservationSnapshot:
    """
    Project bounded Runtime-2A events into the Runtime-2F read model.

    The input must be an immutable tuple. Projection never mutates the
    underlying trace and accepts no prompt, command, tool argument, result,
    response, evidence, objective, state text, exception, memory, screen,
    permission, or execution callback.
    """

    if not isinstance(
        events,
        tuple,
    ):
        raise TypeError(
            "events must be a tuple."
        )

    bounded = events[
        -RUNTIME_OBSERVABILITY_MAX_EVENTS:
    ]

    projected = []

    for event in bounded:
        if not isinstance(
            event,
            RuntimeTraceEvent,
        ):
            raise TypeError(
                "events must contain RuntimeTraceEvent values."
            )

        metadata = dict(
            event.metadata
        )

        session_id = metadata.get(
            "session.id"
        )
        turn_id = metadata.get(
            "turn.id"
        )
        turn_index = metadata.get(
            "turn.index"
        )

        if not isinstance(
            session_id,
            str,
        ) or not session_id.strip():
            raise ValueError(
                "runtime event is missing structural session correlation."
            )

        if not isinstance(
            turn_id,
            str,
        ) or not turn_id.strip():
            raise ValueError(
                "runtime event is missing structural turn correlation."
            )

        if (
            type(turn_index)
            is not int
            or turn_index <= 0
        ):
            raise ValueError(
                "runtime event has invalid structural turn index."
            )

        projected.append(
            RuntimeObservationEvent(
                trace_id=(
                    event.trace_id
                ),
                sequence=(
                    event.sequence
                ),
                stage=(
                    event.stage
                ),
                event_kind=(
                    event.event_kind
                ),
                monotonic_ns=(
                    event.monotonic_ns
                ),
                duration_ms=(
                    event.duration_ms
                ),
                outcome=(
                    event.outcome
                ),
                session_id=(
                    session_id
                ),
                turn_id=(
                    turn_id
                ),
                turn_index=(
                    turn_index
                ),
            )
        )

    return RuntimeObservationSnapshot(
        events=tuple(
            projected
        )
    )

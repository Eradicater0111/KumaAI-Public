
"""
KUMA-INTEGRATION-1E — proactive attention surfacing adapter.

This module connects caller-supplied, already-existing RealtimeSignal values to
the frozen RAPHAEL-1J ProactiveAttentionEngine and projects only a bounded
presentation decision.

It never polls providers, ticks or drains the realtime runtime, calls tools,
executes actions, asks a model, writes memory, mutates TaskState, or grants
authority.

Critical boundaries:

- REALTIME SIGNAL != COMMAND
- ATTENTION != AUTHORITY
- SURFACE != EXECUTE
- ESCALATE != EMERGENCY ACTION
- NOTIFICATION != TOOL CALL
- SEEN != ACKNOWLEDGED
- STATUS TEXT != MODEL CONTEXT

The caller owns signal acquisition and seen/acknowledged lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)
from app.agent.proactive_attention import (
    AttentionContext,
    AttentionCue,
    ProactiveAttentionEngine,
)
from app.realtime.change_detection import (
    RealtimeSignal,
)


ATTENTION_SURFACING_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_STATUS_TEXT_CHARS = 280
_MAX_CONTEXT_TEXT_CHARS = 600
_MAX_EVENT_IDS = 32
_MAX_SIGNALS = 32


def _bounded_text(
    value,
    *,
    limit: int,
    allow_empty: bool = True,
) -> str:
    if value is None:
        text = ""
    else:
        text = " ".join(
            str(value).split()
        )

    if len(text) > limit:
        text = text[:limit].rstrip()

    if not text and not allow_empty:
        raise ValueError(
            "text cannot be blank."
        )

    return text


def _event_ids(
    values: Iterable[str],
    *,
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            f"{field_name} must be an iterable of event IDs."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            f"{field_name} must be iterable."
        ) from error

    if len(items) > _MAX_EVENT_IDS:
        raise ValueError(
            f"{field_name} exceed the bounded item limit."
        )

    normalized = []

    for value in items:
        if type(value) is not str:
            raise TypeError(
                f"{field_name} values must be strings."
            )

        event_id = value.strip()

        if (
            len(event_id) != 64
            or any(
                character
                not in "0123456789abcdef"
                for character
                in event_id
            )
        ):
            raise ValueError(
                f"{field_name} values must be lowercase SHA-256 digests."
            )

        normalized.append(
            event_id
        )

    return tuple(
        dict.fromkeys(
            normalized
        )
    )


def _signals(
    values: Iterable[RealtimeSignal],
) -> tuple[RealtimeSignal, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "signals must be an iterable of RealtimeSignal values."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "signals must be iterable."
        ) from error

    if len(items) > _MAX_SIGNALS:
        raise ValueError(
            "signals exceed the bounded surfacing limit."
        )

    for signal in items:
        if not isinstance(
            signal,
            RealtimeSignal,
        ):
            raise TypeError(
                "signals must contain RealtimeSignal values."
            )

        if signal.authority != ATTENTION_SURFACING_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeSignal authority must remain NONE."
            )

    return items


def _cues(
    values: Iterable[AttentionCue],
) -> tuple[AttentionCue, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "cues must be an iterable of AttentionCue values."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "cues must be iterable."
        ) from error

    for cue in items:
        if not isinstance(
            cue,
            AttentionCue,
        ):
            raise TypeError(
                "cues must contain AttentionCue values."
            )

        if cue.authority != ATTENTION_SURFACING_AUTHORITY_NONE:
            raise ValueError(
                "AttentionCue authority must remain NONE."
            )

    return items


@dataclass(
    frozen=True,
    slots=True,
)
class AttentionSurfacingObservation:
    """
    Zero-authority presentation projection of one frozen 1J decision.

    should_surface controls only whether the caller may show informational
    status text. It is never permission for a tool or real-world action.
    """

    disposition: str
    reason: str
    should_surface: bool
    selected_event_id: str = ""
    selected_event_kind: str = ""
    status_text: str = ""
    authority: str = field(
        default=ATTENTION_SURFACING_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        disposition = _bounded_text(
            self.disposition,
            limit=80,
            allow_empty=False,
        )

        reason = _bounded_text(
            self.reason,
            limit=_MAX_STATUS_TEXT_CHARS,
            allow_empty=False,
        )

        if type(
            self.should_surface
        ) is not bool:
            raise TypeError(
                "should_surface must be bool."
            )

        if type(
            self.selected_event_id
        ) is not str:
            raise TypeError(
                "selected_event_id must be a string."
            )

        selected_event_id = (
            self.selected_event_id.strip()
        )

        if selected_event_id:
            _event_ids(
                (
                    selected_event_id,
                ),
                field_name="selected_event_id",
            )

        selected_event_kind = _bounded_text(
            self.selected_event_kind,
            limit=160,
            allow_empty=True,
        )

        status_text = _bounded_text(
            self.status_text,
            limit=_MAX_STATUS_TEXT_CHARS,
            allow_empty=True,
        )

        if self.should_surface:
            if not selected_event_id:
                raise ValueError(
                    "surfacing requires a selected event ID."
                )

            if not selected_event_kind:
                raise ValueError(
                    "surfacing requires a selected event kind."
                )

            if not status_text:
                raise ValueError(
                    "surfacing requires nonblank status text."
                )

        elif (
            selected_event_id
            or selected_event_kind
            or status_text
        ):
            raise ValueError(
                "non-surfacing observation cannot carry selected event data."
            )

        object.__setattr__(
            self,
            "disposition",
            disposition,
        )
        object.__setattr__(
            self,
            "reason",
            reason,
        )
        object.__setattr__(
            self,
            "selected_event_id",
            selected_event_id,
        )
        object.__setattr__(
            self,
            "selected_event_kind",
            selected_event_kind,
        )
        object.__setattr__(
            self,
            "status_text",
            status_text,
        )


def evaluate_attention_surfacing(
    *,
    signals: Iterable[RealtimeSignal],
    active_goal: str = "",
    remaining_objective: str = "",
    mission_status: str = "",
    seen_event_ids: Iterable[str] = (),
    acknowledged_event_ids: Iterable[str] = (),
    cues: Iterable[AttentionCue] = (),
    current_time: datetime | None = None,
) -> AttentionSurfacingObservation:
    """
    Evaluate explicit caller-supplied realtime signals using frozen RAPHAEL-1J.

    The function performs no signal acquisition and no user notification.
    """

    supplied_signals = _signals(
        signals
    )

    seen = _event_ids(
        seen_event_ids,
        field_name="seen_event_ids",
    )

    acknowledged = _event_ids(
        acknowledged_event_ids,
        field_name="acknowledged_event_ids",
    )

    supplied_cues = _cues(
        cues
    )

    if current_time is None:
        now = datetime.now(
            timezone.utc
        )
    else:
        if not isinstance(
            current_time,
            datetime,
        ):
            raise TypeError(
                "current_time must be datetime or None."
            )

        if (
            current_time.tzinfo is None
            or current_time.utcoffset()
            is None
        ):
            raise ValueError(
                "current_time must be timezone-aware."
            )

        now = current_time.astimezone(
            timezone.utc
        )

    context = AttentionContext(
        current_time=now,
        active_goal=_bounded_text(
            active_goal,
            limit=_MAX_CONTEXT_TEXT_CHARS,
        ),
        remaining_objective=_bounded_text(
            remaining_objective,
            limit=_MAX_CONTEXT_TEXT_CHARS,
        ),
        mission_status=_bounded_text(
            mission_status,
            limit=_MAX_CONTEXT_TEXT_CHARS,
        ),
        seen_event_ids=seen,
        acknowledged_event_ids=acknowledged,
        cues=supplied_cues,
    )

    decision = ProactiveAttentionEngine().decide(
        supplied_signals,
        context,
    )

    if (
        decision.authority
        != ATTENTION_SURFACING_AUTHORITY_NONE
    ):
        raise ValueError(
            "AttentionDecision authority must remain NONE."
        )

    selected_event = (
        decision.selected_event
    )

    if selected_event is None:
        return AttentionSurfacingObservation(
            disposition=(
                decision.disposition.value
            ),
            reason=decision.reason,
            should_surface=False,
        )

    if (
        selected_event.authority
        != ATTENTION_SURFACING_AUTHORITY_NONE
    ):
        raise ValueError(
            "selected ProactiveEvent authority must remain NONE."
        )

    event_kind = _bounded_text(
        selected_event.kind,
        limit=160,
        allow_empty=False,
    )

    event_reason = _bounded_text(
        selected_event.reason,
        limit=180,
        allow_empty=False,
    )

    status_text = _bounded_text(
        (
            "KUMA attention — "
            + event_kind
            + ": "
            + event_reason
        ),
        limit=_MAX_STATUS_TEXT_CHARS,
        allow_empty=False,
    )

    return AttentionSurfacingObservation(
        disposition=(
            decision.disposition.value
        ),
        reason=decision.reason,
        should_surface=True,
        selected_event_id=(
            selected_event.event_id
        ),
        selected_event_kind=event_kind,
        status_text=status_text,
    )


def remember_seen_event(
    seen_event_ids: Iterable[str],
    event_id: str,
) -> tuple[str, ...]:
    """
    Return a bounded caller-owned seen-event history.

    Seen means presented/observed by the runtime, not acknowledged by the user.
    """

    seen = list(
        _event_ids(
            seen_event_ids,
            field_name="seen_event_ids",
        )
    )

    current = _event_ids(
        (
            event_id,
        ),
        field_name="event_id",
    )[0]

    seen = [
        item
        for item
        in seen
        if item != current
    ]

    seen.append(
        current
    )

    return tuple(
        seen[
            -_MAX_EVENT_IDS:
        ]
    )

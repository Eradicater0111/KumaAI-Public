"""
KUMA-RUNTIME-2A — bounded zero-authority runtime trace contract.

This module is intentionally infrastructure-only. It records sanitized,
structural diagnostics in memory so later Runtime phases can observe KUMA's
lifecycle without giving diagnostics any control over cognition or execution.

Core boundaries:

- TRACE != AUTHORITY
- TRACE != COMMAND
- TRACE != VERIFIED FACT
- OBSERVED != AUTHORIZED
- LOGGED RESULT != GOAL COMPLETION
- DIAGNOSTIC DATA != MODEL CONTEXT
- TRACE STORAGE != LONG-TERM MEMORY
- TRACE METADATA != RAW USER CONTENT
- TRACE AUTHORITY = NONE

Runtime-2A deliberately has:
- no disk persistence
- no network
- no model/provider imports
- no agent/tool/UI/voice/realtime imports
- no permission or execution calls
- no background loop
- no raw prompt, transcript, command, screen, clipboard, response, or memory
  context fields

Metadata is fail-closed rather than best-effort-redacted: keys associated with
raw/sensitive payloads are rejected, and string values must be compact
identifier-like labels rather than arbitrary prose.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
import re
import secrets
from threading import RLock
import time
from typing import Callable, Mapping


TRACE_AUTHORITY_NONE = "NONE"

TRACE_ID_MAX_CHARS = 64
TRACE_LABEL_MAX_CHARS = 64
TRACE_REASON_MAX_CHARS = 96
TRACE_METADATA_KEY_MAX_CHARS = 48
TRACE_METADATA_STRING_MAX_CHARS = 96
TRACE_METADATA_MAX_ITEMS = 16

TRACE_DEFAULT_MAX_EVENTS = 256
TRACE_MAX_EVENTS = 4096
TRACE_MAX_DURATION_MS = 86_400_000.0

_SAFE_TRACE_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
)

_SAFE_LABEL = re.compile(
    r"^[a-z0-9][a-z0-9_.:-]*$"
)

_SAFE_METADATA_STRING = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]*$"
)

_SENSITIVE_METADATA_TOKENS = frozenset(
    {
        "api",
        "apikey",
        "api_key",
        "argument",
        "arguments",
        "args",
        "authorization",
        "clipboard",
        "command",
        "content",
        "cookie",
        "credential",
        "credentials",
        "filecontent",
        "filecontents",
        "file_content",
        "file_contents",
        "memorycontext",
        "memory_context",
        "message",
        "password",
        "payload",
        "prompt",
        "raw",
        "response",
        "screen",
        "screenshot",
        "secret",
        "text",
        "token",
        "transcript",
    }
)

_SECRET_LIKE_PREFIXES = (
    "sk-",
    "ghp_",
    "github_pat_",
    "tvly-",
    "xoxb-",
    "xoxp-",
    "xoxa-",
    "xoxr-",
    "akia",
    "aiza",
)


TraceMetadataValue = (
    str
    | int
    | float
    | bool
    | None
)


def _require_exact_int(
    value,
    *,
    field_name: str,
    minimum: int = 0,
) -> int:
    if (
        type(value) is not int
        or value < minimum
    ):
        raise TypeError(
            f"{field_name} must be an int >= {minimum}."
        )

    return value


def _normalize_identifier(
    value,
    *,
    field_name: str,
    max_chars: int,
    allow_empty: bool = False,
    pattern=_SAFE_LABEL,
) -> str:
    if type(value) is not str:
        raise TypeError(
            f"{field_name} must be a string."
        )

    normalized = (
        value.strip()
        .lower()
    )

    if not normalized:
        if allow_empty:
            return ""

        raise ValueError(
            f"{field_name} must be nonempty."
        )

    if len(normalized) > max_chars:
        raise ValueError(
            f"{field_name} exceeds its bounded length."
        )

    if (
        pattern.fullmatch(
            normalized
        )
        is None
    ):
        raise ValueError(
            f"{field_name} must be an identifier-like label."
        )

    return normalized


def _normalize_trace_id(
    value,
) -> str:
    if type(value) is not str:
        raise TypeError(
            "trace_id must be a string."
        )

    normalized = (
        value.strip()
    )

    if not normalized:
        raise ValueError(
            "trace_id must be nonempty."
        )

    if len(normalized) > TRACE_ID_MAX_CHARS:
        raise ValueError(
            "trace_id exceeds its bounded length."
        )

    if (
        _SAFE_TRACE_ID.fullmatch(
            normalized
        )
        is None
    ):
        raise ValueError(
            "trace_id must be an identifier-like token."
        )

    return normalized


def _metadata_key_tokens(
    key: str,
) -> set[str]:
    lowered = (
        key.lower()
    )

    parts = {
        part
        for part in re.split(
            r"[._:-]+",
            lowered,
        )
        if part
    }

    collapsed = (
        re.sub(
            r"[^a-z0-9]",
            "",
            lowered,
        )
    )

    parts.add(
        collapsed
    )

    return parts


def _reject_sensitive_metadata_key(
    key: str,
) -> None:
    tokens = (
        _metadata_key_tokens(
            key
        )
    )

    if (
        tokens
        & _SENSITIVE_METADATA_TOKENS
    ):
        raise ValueError(
            "sensitive/raw metadata keys are not allowed in runtime traces."
        )


def _normalize_metadata_value(
    value,
):
    if value is None:
        return None

    if type(value) is bool:
        return value

    if type(value) is int:
        return value

    if type(value) is float:
        if not math.isfinite(
            value
        ):
            raise ValueError(
                "trace metadata floats must be finite."
            )

        return value

    if type(value) is str:
        normalized = (
            value.strip()
        )

        if not normalized:
            raise ValueError(
                "trace metadata strings must be nonempty."
            )

        if (
            len(normalized)
            > TRACE_METADATA_STRING_MAX_CHARS
        ):
            raise ValueError(
                "trace metadata string exceeds its bounded length."
            )

        if (
            _SAFE_METADATA_STRING.fullmatch(
                normalized
            )
            is None
        ):
            raise ValueError(
                "trace metadata strings must be identifier-like labels."
            )

        lowered = (
            normalized.lower()
        )

        if any(
            lowered.startswith(
                prefix
            )
            for prefix
            in _SECRET_LIKE_PREFIXES
        ):
            raise ValueError(
                "secret-like trace metadata values are not allowed."
            )

        return normalized

    raise TypeError(
        "trace metadata values must be scalar labels or numbers."
    )


def sanitize_trace_metadata(
    metadata: Mapping[str, TraceMetadataValue]
    | None,
) -> tuple[
    tuple[
        str,
        TraceMetadataValue,
    ],
    ...,
]:
    """
    Validate and freeze bounded trace metadata.

    Unsafe content is rejected rather than silently copied, truncated, or
    persisted. Returned metadata is a sorted immutable tuple for deterministic
    equality and serialization by future presentation-only consumers.
    """

    if metadata is None:
        return ()

    if not isinstance(
        metadata,
        Mapping,
    ):
        raise TypeError(
            "metadata must be a mapping."
        )

    if (
        len(metadata)
        > TRACE_METADATA_MAX_ITEMS
    ):
        raise ValueError(
            "trace metadata exceeds its bounded item count."
        )

    items = []

    for (
        raw_key,
        raw_value,
    ) in metadata.items():
        key = (
            _normalize_identifier(
                raw_key,
                field_name="metadata key",
                max_chars=(
                    TRACE_METADATA_KEY_MAX_CHARS
                ),
            )
        )

        _reject_sensitive_metadata_key(
            key
        )

        value = (
            _normalize_metadata_value(
                raw_value
            )
        )

        items.append(
            (
                key,
                value,
            )
        )

    items.sort(
        key=lambda item: item[0]
    )

    return tuple(
        items
    )


def new_runtime_trace_id() -> str:
    """
    Create a local opaque correlation identifier.

    This identifier contains no user content, device data, or authority.
    """

    return (
        "trace-"
        + secrets.token_hex(
            16
        )
    )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeTraceEvent:
    """
    One immutable, bounded, zero-authority runtime diagnostic event.

    `outcome` describes only the local observed stage event. It never means
    the user's goal is verified complete.
    """

    trace_id: str
    sequence: int
    stage: str
    event_kind: str
    monotonic_ns: int
    duration_ms: float | None = None
    outcome: str = "observed"
    reason: str = ""
    metadata: tuple[
        tuple[
            str,
            TraceMetadataValue,
        ],
        ...,
    ] = ()
    authority: str = field(
        default=TRACE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "trace_id",
            _normalize_trace_id(
                self.trace_id
            ),
        )

        _require_exact_int(
            self.sequence,
            field_name="sequence",
            minimum=1,
        )

        object.__setattr__(
            self,
            "stage",
            _normalize_identifier(
                self.stage,
                field_name="stage",
                max_chars=(
                    TRACE_LABEL_MAX_CHARS
                ),
            ),
        )

        object.__setattr__(
            self,
            "event_kind",
            _normalize_identifier(
                self.event_kind,
                field_name="event_kind",
                max_chars=(
                    TRACE_LABEL_MAX_CHARS
                ),
            ),
        )

        _require_exact_int(
            self.monotonic_ns,
            field_name="monotonic_ns",
            minimum=0,
        )

        if self.duration_ms is not None:
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
                    "duration_ms must be numeric or None."
                )

            duration = float(
                self.duration_ms
            )

            if (
                not math.isfinite(
                    duration
                )
                or duration < 0.0
                or duration
                > TRACE_MAX_DURATION_MS
            ):
                raise ValueError(
                    "duration_ms must be finite, nonnegative, and bounded."
                )

            object.__setattr__(
                self,
                "duration_ms",
                duration,
            )

        object.__setattr__(
            self,
            "outcome",
            _normalize_identifier(
                self.outcome,
                field_name="outcome",
                max_chars=(
                    TRACE_LABEL_MAX_CHARS
                ),
            ),
        )

        object.__setattr__(
            self,
            "reason",
            _normalize_identifier(
                self.reason,
                field_name="reason",
                max_chars=(
                    TRACE_REASON_MAX_CHARS
                ),
                allow_empty=True,
            ),
        )

        metadata = dict(
            self.metadata
        )

        if (
            len(metadata)
            != len(
                self.metadata
            )
        ):
            raise ValueError(
                "duplicate trace metadata keys are not allowed."
            )

        object.__setattr__(
            self,
            "metadata",
            sanitize_trace_metadata(
                metadata
            ),
        )

        if (
            self.authority
            != TRACE_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime trace authority must remain NONE."
            )


class KumaRuntimeTrace:
    """
    Thread-safe bounded in-memory recorder for RuntimeTraceEvent values.

    The recorder is diagnostic-only. It does not publish into model context,
    authorize actions, persist to disk, or perform network I/O.
    """

    def __init__(
        self,
        *,
        max_events: int = (
            TRACE_DEFAULT_MAX_EVENTS
        ),
        clock_ns: Callable[[], int] = (
            time.monotonic_ns
        ),
        trace_id_factory: Callable[
            [],
            str,
        ] = new_runtime_trace_id,
    ):
        if (
            type(max_events) is not int
            or not (
                1
                <= max_events
                <= TRACE_MAX_EVENTS
            )
        ):
            raise ValueError(
                "max_events must be an int within the bounded trace capacity."
            )

        if not callable(
            clock_ns
        ):
            raise TypeError(
                "clock_ns must be callable."
            )

        if not callable(
            trace_id_factory
        ):
            raise TypeError(
                "trace_id_factory must be callable."
            )

        self._max_events = (
            max_events
        )

        self._clock_ns = (
            clock_ns
        )

        self._trace_id_factory = (
            trace_id_factory
        )

        self._events = deque(
            maxlen=max_events
        )

        self._next_sequence = {}

        self._last_timestamp = {}

        self._lock = RLock()

    @property
    def authority(
        self,
    ) -> str:
        return TRACE_AUTHORITY_NONE

    @property
    def max_events(
        self,
    ) -> int:
        return self._max_events

    def __len__(
        self,
    ) -> int:
        with self._lock:
            return len(
                self._events
            )

    def start_trace(
        self,
    ) -> str:
        trace_id = (
            self._trace_id_factory()
        )

        return (
            _normalize_trace_id(
                trace_id
            )
        )

    def _read_clock(
        self,
    ) -> int:
        value = (
            self._clock_ns()
        )

        return (
            _require_exact_int(
                value,
                field_name="monotonic clock",
                minimum=0,
            )
        )

    def append(
        self,
        event: RuntimeTraceEvent,
    ) -> RuntimeTraceEvent:
        if not isinstance(
            event,
            RuntimeTraceEvent,
        ):
            raise TypeError(
                "event must be RuntimeTraceEvent."
            )

        with self._lock:
            expected = (
                self._next_sequence
                .get(
                    event.trace_id,
                    1,
                )
            )

            if (
                event.sequence
                != expected
            ):
                raise ValueError(
                    "trace event sequence is not the next expected value."
                )

            previous_timestamp = (
                self._last_timestamp
                .get(
                    event.trace_id
                )
            )

            if (
                previous_timestamp
                is not None
                and event.monotonic_ns
                < previous_timestamp
            ):
                raise ValueError(
                    "trace event monotonic timestamp moved backwards."
                )

            self._events.append(
                event
            )

            self._next_sequence[
                event.trace_id
            ] = (
                event.sequence
                + 1
            )

            self._last_timestamp[
                event.trace_id
            ] = (
                event.monotonic_ns
            )

            return event

    def record(
        self,
        *,
        trace_id: str,
        stage: str,
        event_kind: str,
        outcome: str = "observed",
        reason: str = "",
        metadata: Mapping[
            str,
            TraceMetadataValue,
        ]
        | None = None,
        duration_ms: float
        | None = None,
    ) -> RuntimeTraceEvent:
        normalized_trace_id = (
            _normalize_trace_id(
                trace_id
            )
        )

        with self._lock:
            sequence = (
                self._next_sequence
                .get(
                    normalized_trace_id,
                    1,
                )
            )

            timestamp = (
                self._read_clock()
            )

            event = (
                RuntimeTraceEvent(
                    trace_id=(
                        normalized_trace_id
                    ),
                    sequence=sequence,
                    stage=stage,
                    event_kind=event_kind,
                    monotonic_ns=(
                        timestamp
                    ),
                    duration_ms=(
                        duration_ms
                    ),
                    outcome=outcome,
                    reason=reason,
                    metadata=(
                        sanitize_trace_metadata(
                            metadata
                        )
                    ),
                )
            )

            return self.append(
                event
            )

    def snapshot(
        self,
    ) -> tuple[
        RuntimeTraceEvent,
        ...,
    ]:
        with self._lock:
            return tuple(
                self._events
            )

    def events_for_trace(
        self,
        trace_id: str,
    ) -> tuple[
        RuntimeTraceEvent,
        ...,
    ]:
        normalized = (
            _normalize_trace_id(
                trace_id
            )
        )

        with self._lock:
            return tuple(
                event
                for event
                in self._events
                if (
                    event.trace_id
                    == normalized
                )
            )

    def clear(
        self,
    ) -> None:
        with self._lock:
            self._events.clear()
            self._next_sequence.clear()
            self._last_timestamp.clear()

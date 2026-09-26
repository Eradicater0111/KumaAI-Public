from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


REALTIME_AUTHORITY_NONE = "NONE"


def _require_aware_datetime(
    name: str,
    value: datetime | None,
) -> None:
    if value is None:
        return

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{name} must be timezone-aware."
        )


@dataclass(frozen=True, slots=True)
class RealtimeFact:
    """
    Canonical KUMA realtime world-state fact.

    Realtime facts are evidence/state only. They carry AUTHORITY: NONE
    and can never grant clicks, typing, commands, file mutations,
    purchases, credential use, or policy changes.
    """

    kind: str
    value: Any
    source: str
    observed_at: datetime
    expires_at: datetime | None
    source_timestamp: datetime | None = None
    confidence: float = 1.0
    location: str | None = None
    raw_evidence_digest: str | None = None
    authority: str = REALTIME_AUTHORITY_NONE

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError(
                "RealtimeFact.kind cannot be blank."
            )

        if not self.source.strip():
            raise ValueError(
                "RealtimeFact.source cannot be blank."
            )

        if self.authority != REALTIME_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeFact authority is permanently NONE."
            )

        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(
                "RealtimeFact.confidence must be between 0.0 and 1.0."
            )

        _require_aware_datetime(
            "observed_at",
            self.observed_at,
        )
        _require_aware_datetime(
            "expires_at",
            self.expires_at,
        )
        _require_aware_datetime(
            "source_timestamp",
            self.source_timestamp,
        )

        if (
            self.expires_at is not None
            and self.expires_at < self.observed_at
        ):
            raise ValueError(
                "expires_at cannot be earlier than observed_at."
            )

        if (
            self.raw_evidence_digest is not None
            and not self.raw_evidence_digest.strip()
        ):
            raise ValueError(
                "raw_evidence_digest cannot be blank when supplied."
            )

    @property
    def storage_key(self) -> tuple[str, str | None]:
        return (
            self.kind.strip(),
            self.location.strip()
            if self.location
            else None,
        )

    def is_expired(
        self,
        *,
        at: datetime,
    ) -> bool:
        _require_aware_datetime(
            "at",
            at,
        )

        if self.expires_at is None:
            return False

        return at >= self.expires_at


class RealtimeEventType(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    EXPIRED = "expired"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    """
    Internal realtime event notification.

    Events do not execute actions. Consumers may observe them and make
    separate policy decisions through KUMA's existing safety system.
    """

    event_type: RealtimeEventType
    fact: RealtimeFact
    previous_fact: RealtimeFact | None = None

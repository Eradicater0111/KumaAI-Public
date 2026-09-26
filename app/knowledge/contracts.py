from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


KNOWLEDGE_AUTHORITY_NONE = "NONE"


class KnowledgeDomain(str, Enum):
    WEATHER = "weather"
    MEMORY = "memory"
    PUBLIC_WEB = "public_web"
    SYSTEM = "system"
    SATELLITE = "satellite"
    UNKNOWN = "unknown"


class TemporalScope(str, Enum):
    NOW = "now"
    TODAY = "today"
    TOMORROW = "tomorrow"
    HISTORICAL = "historical"
    FUTURE = "future"
    UNSPECIFIED = "unspecified"


class LocationScope(str, Enum):
    CURRENT_DEVICE = "current_device"
    EXPLICIT_PLACE = "explicit_place"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class KnowledgeIntent:
    domain: KnowledgeDomain
    temporal_scope: TemporalScope
    location_scope: LocationScope
    query: str
    explicit_place: str | None = None
    confidence: float = 1.0
    authority: str = KNOWLEDGE_AUTHORITY_NONE

    def __post_init__(self) -> None:
        if self.authority != KNOWLEDGE_AUTHORITY_NONE:
            raise ValueError(
                "KnowledgeIntent authority is permanently NONE."
            )

        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(
                "KnowledgeIntent.confidence must be between 0.0 and 1.0."
            )

        if (
            self.location_scope == LocationScope.EXPLICIT_PLACE
            and not str(self.explicit_place or "").strip()
        ):
            raise ValueError(
                "explicit_place is required for EXPLICIT_PLACE scope."
            )


@dataclass(frozen=True, slots=True)
class KnowledgePlan:
    intent: KnowledgeIntent
    provider_order: tuple[str, ...]
    requires_device_location: bool = False
    authority: str = KNOWLEDGE_AUTHORITY_NONE

    def __post_init__(self) -> None:
        if self.authority != KNOWLEDGE_AUTHORITY_NONE:
            raise ValueError(
                "KnowledgePlan authority is permanently NONE."
            )

        if (
            self.requires_device_location
            and self.intent.location_scope != LocationScope.CURRENT_DEVICE
        ):
            raise ValueError(
                "device location may only be required for CURRENT_DEVICE scope."
            )

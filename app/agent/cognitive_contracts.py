"""
KUMA RAPHAEL-1A cognitive contracts.

These objects describe tactical cognition only. They do not grant permission,
confirm actions, execute tools, mutate KUMA state, or bypass any existing
authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.agent.permissions import PermissionLevel


COGNITIVE_AUTHORITY_NONE = "NONE"


class TacticalRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class TacticalDisposition(str, Enum):
    ADVISE = "advise"
    ACTION_CANDIDATE = "action_candidate"
    DEFER = "defer"
    BLOCKED = "blocked"


def _required_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _text_tuple(values: Iterable[str] | tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings.")
    try:
        raw_values = tuple(values)
    except TypeError as error:
        raise TypeError(f"{field_name} must be an iterable of strings.") from error
    return tuple(
        _required_text(value, field_name=field_name)
        for value in raw_values
    )


def _unit_interval(value: float, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
    return normalized


def _timestamp_text(value: str) -> str:
    normalized = _required_text(value, field_name="timestamp")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be a valid ISO-8601 datetime.") from error
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone information.")
    return normalized


@dataclass(frozen=True, slots=True)
class WorldStateSnapshot:
    """Read-only evidence snapshot for tactical reasoning."""

    timestamp: str
    task_goal: str | None = None
    system_state: tuple[str, ...] = ()
    desktop_state: tuple[str, ...] = ()
    realtime_state: tuple[str, ...] = ()
    task_state: tuple[str, ...] = ()
    mission_state: tuple[str, ...] = ()
    relevant_memory: tuple[str, ...] = ()
    authority: str = field(default=COGNITIVE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _timestamp_text(self.timestamp))
        object.__setattr__(
            self,
            "task_goal",
            _optional_text(self.task_goal, field_name="task_goal"),
        )
        for field_name in (
            "system_state",
            "desktop_state",
            "realtime_state",
            "task_state",
            "mission_state",
            "relevant_memory",
        ):
            object.__setattr__(
                self,
                field_name,
                _text_tuple(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class TacticalSituation:
    """Normalized input to tactical reasoning; evidence only."""

    goal: str
    observed_state: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    available_capabilities: tuple[str, ...] = ()
    world_state: WorldStateSnapshot | None = None
    authority: str = field(default=COGNITIVE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal", _required_text(self.goal, field_name="goal"))
        for field_name in (
            "observed_state",
            "known_facts",
            "uncertainties",
            "constraints",
            "available_capabilities",
        ):
            object.__setattr__(
                self,
                field_name,
                _text_tuple(getattr(self, field_name), field_name=field_name),
            )
        if self.world_state is not None and not isinstance(self.world_state, WorldStateSnapshot):
            raise TypeError("world_state must be WorldStateSnapshot or None.")


@dataclass(frozen=True, slots=True)
class TacticalOption:
    """Possible course of action/recommendation; never an authorization."""

    option_id: str
    objective: str
    rationale: str
    expected_outcome: str
    confidence: float
    risk: TacticalRisk
    required_permission: PermissionLevel
    reversible: bool
    capability: str | None = None
    cost: float = 0.0
    authority: str = field(default=COGNITIVE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        for field_name in ("option_id", "objective", "rationale", "expected_outcome"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "capability",
            _optional_text(self.capability, field_name="capability"),
        )
        object.__setattr__(self, "confidence", _unit_interval(self.confidence, field_name="confidence"))
        object.__setattr__(self, "cost", _unit_interval(self.cost, field_name="cost"))
        if not isinstance(self.risk, TacticalRisk):
            raise TypeError("risk must be TacticalRisk.")
        if not isinstance(self.required_permission, PermissionLevel):
            raise TypeError("required_permission must be PermissionLevel.")
        if type(self.reversible) is not bool:
            raise TypeError("reversible must be bool.")


@dataclass(frozen=True, slots=True)
class TacticalDecision:
    """Tactical recommendation; ACTION_CANDIDATE still has AUTHORITY:NONE."""

    disposition: TacticalDisposition
    reason: str
    confidence: float
    chosen_option: TacticalOption | None = None
    rejected_options: tuple[TacticalOption, ...] = ()
    remaining_uncertainties: tuple[str, ...] = ()
    authority: str = field(default=COGNITIVE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, TacticalDisposition):
            raise TypeError("disposition must be TacticalDisposition.")
        object.__setattr__(self, "reason", _required_text(self.reason, field_name="reason"))
        object.__setattr__(self, "confidence", _unit_interval(self.confidence, field_name="confidence"))
        if self.chosen_option is not None and not isinstance(self.chosen_option, TacticalOption):
            raise TypeError("chosen_option must be TacticalOption or None.")
        rejected = tuple(self.rejected_options)
        for option in rejected:
            if not isinstance(option, TacticalOption):
                raise TypeError("rejected_options must contain TacticalOption values.")
        object.__setattr__(self, "rejected_options", rejected)
        object.__setattr__(
            self,
            "remaining_uncertainties",
            _text_tuple(self.remaining_uncertainties, field_name="remaining_uncertainties"),
        )
        ids = [option.option_id for option in rejected]
        if self.chosen_option is not None and self.chosen_option.option_id in ids:
            raise ValueError("chosen_option cannot also appear in rejected_options.")
        if len(ids) != len(set(ids)):
            raise ValueError("rejected_options cannot contain duplicate option ids.")

    @property
    def required_permission(self) -> PermissionLevel | None:
        if self.chosen_option is None:
            return None
        return self.chosen_option.required_permission

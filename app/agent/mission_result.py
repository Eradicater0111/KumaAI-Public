from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MissionExecutionResult:
    """
    Authoritative result of one mission-step execution.
    """

    success: bool

    step_id: str

    capability: str = ""

    tool_name: str = ""

    arguments: dict[str, Any] | None = None

    result: Any = None

    error: str = ""

    verified: bool = False

    verification: str = ""

    # Advisory recovery information produced after a failed or
    # incomplete execution attempt.
    #
    # These fields do not authorize execution. They allow the
    # mission layer to understand what the recovery system
    # recommends without creating a second planning loop inside
    # KumaMissionExecutor.
    recovery_action: str = ""
    recovery_reason: str = ""
    recovery_evidence: str = ""

    # Runtime-only indication that this attempt crossed an
    # irreversible external-effect boundary.
    #
    # This is recovery evidence, not permission or authority.
    effect_started: bool = False

    def __post_init__(
        self,
    ):
        if (
            type(self.effect_started)
            is not bool
        ):
            raise TypeError(
                "effect_started must be a boolean."
            )

    @property
    def completed(self) -> bool:
        return (
            self.success
            and self.verified
        )
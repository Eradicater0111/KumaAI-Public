from __future__ import annotations

"""
KUMA RUNTIME-V2B — immutable explicit invocation carrier.

This module carries already-existing explicit caller intent together with an
optional already-admitted RealtimeTriggerObservation.

It does not execute, dispatch, invoke, schedule, admit, select, rank, trace,
or open a runtime turn.

CALLER INTENT -> INVOCATION
OPTIONAL OBSERVATION -> EVIDENCE ONLY
CARRIER != EXECUTION
OBSERVATION != INVOCATION
OBSERVATION != PERMISSION
TRACE != CONTROL
AUTHORITY: NONE
"""

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
)


_ResultT = TypeVar("_ResultT")

RUNTIME_V2B_AUTHORITY_NONE = "NONE"


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeInvocation(
    Generic[_ResultT],
):
    """
    Zero-authority transport value for one already-explicit caller operation.

    The optional observation may accompany caller intent as evidence only.
    Merely constructing this value never invokes the operation.
    """

    operation: Callable[[], _ResultT]
    observation: RealtimeTriggerObservation | None = None
    authority: str = field(
        default=RUNTIME_V2B_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not callable(
            self.operation
        ):
            raise TypeError(
                "operation must be callable."
            )

        observation = self.observation

        if (
            observation is not None
            and not isinstance(
                observation,
                RealtimeTriggerObservation,
            )
        ):
            raise TypeError(
                "observation must be a RealtimeTriggerObservation or None."
            )

        if (
            observation is not None
            and observation.authority
            != RUNTIME_V2B_AUTHORITY_NONE
        ):
            raise ValueError(
                "RealtimeTriggerObservation authority must remain NONE."
            )

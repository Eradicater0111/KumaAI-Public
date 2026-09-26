from __future__ import annotations

"""
KUMA INTEGRATION-V2B — explicit-signal runtime observation composition.

This additive bridge composes one already-explicit caller operation with at
most one caller-supplied RealtimeSignal:

    explicit caller operation
              +
    optional explicit RealtimeSignal
              +
    explicit admission thresholds
              ↓
    Integration-V2A admission
              ↓
    optional RealtimeTriggerObservation
              ↓
    Runtime-V2D live owner
              ↓
    Runtime-V2C / one Runtime V1 turn

The bridge never acquires realtime state, selects among multiple signals,
drains queues, schedules work, wakes KUMA, surfaces UI, grants permission,
calls tools/models, or creates caller intent.

If observation admission fails, the already-explicit caller operation still
runs once without observation. Optional trace evidence must never become a
control dependency.

EXPLICIT OPERATION != REALTIME INVOCATION
SIGNAL INPUT != INVOCATION
ADMISSION != INVOCATION
OBSERVATION != INVOCATION
ADMISSION FAILURE != CALLER OPERATION FAILURE
BRIDGE != SIGNAL ACQUISITION
BRIDGE != SIGNAL SELECTION
BRIDGE != WAKE
AUTHORITY: NONE
"""

from typing import Callable, TypeVar

from app.integration_realtime_observation_admission import (
    admit_realtime_observation,
)
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)


_ResultT = TypeVar("_ResultT")

INTEGRATION_V2B_AUTHORITY_NONE = "NONE"


def run_explicit_operation_with_realtime_signal(
    runtime_owner: KumaRuntimeV2LiveOwner,
    operation: Callable[[], _ResultT],
    *,
    signal: RealtimeSignal | None,
    minimum_level: RealtimeRelevanceLevel,
    minimum_score: float,
) -> _ResultT:
    """
    Run one already-explicit operation with optional realtime trace evidence.

    Realtime admission is auxiliary. Failure to admit observation evidence
    cannot create, cancel, duplicate, or otherwise control the caller's
    already-explicit operation.
    """

    if not isinstance(
        runtime_owner,
        KumaRuntimeV2LiveOwner,
    ):
        raise TypeError(
            "runtime_owner must be KumaRuntimeV2LiveOwner."
        )

    if (
        runtime_owner.authority
        != INTEGRATION_V2B_AUTHORITY_NONE
    ):
        raise ValueError(
            "Runtime-V2D owner authority must remain NONE."
        )

    if not callable(
        operation
    ):
        raise TypeError(
            "operation must be callable."
        )

    observation = None

    if signal is not None:
        try:
            observation = admit_realtime_observation(
                signal,
                minimum_level=minimum_level,
                minimum_score=minimum_score,
            )
        except Exception:
            observation = None

    return runtime_owner.run(
        operation,
        observation=observation,
    )
